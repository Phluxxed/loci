"""Evaluator-owned read lineage for the frozen TypeScript comparison.

This module never supplies gold or classifications to the task agent. An adapter
passes the exact JSON delivered to the agent and source slices from that result.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from benchmarks.typescript_context_corpus import (
    DEFAULT_ROOT, _snapshot_files, check_answer, load_controls, load_corpus,
)

REASONS = {'task_context', 'missing_context', 'hydration', 'verification', 'setup', 'unrelated'}
OPERATIONS = {'search', 'get', 'graph', 'file', 'grep', 'outline'}


def _strings(value: Any):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for child in value.values():
            yield from _strings(child)
    elif isinstance(value, list):
        for child in value:
            yield from _strings(child)


def _covered(spans: list[dict], gold: dict) -> bool:
    """Require the whole gold interval, allowing adjacent delivered fragments."""
    cursor = gold['start_byte']
    for span in sorted((s for s in spans if s['file'] == gold['file']),
                       key=lambda s: s['start_byte']):
        if span['start_byte'] > cursor:
            break
        cursor = max(cursor, span['end_byte'])
        if cursor >= gold['end_byte']:
            return True
    return False


class ReadTrace:
    """One task/session/arm/repetition; append only after successful validation."""

    def __init__(self, corpus: dict, case_id: str, session_id: str,
                 arm: str = 'A', repetition: int = 1):
        if not session_id or arm not in {'A', 'B', 'C'} or type(repetition) is not int or repetition not in {1, 2, 3}:
            raise ValueError('invalid run identity')
        self.corpus = corpus
        self.case = next(c for c in corpus['cases'] if c['id'] == case_id)
        self.files = _snapshot_files(corpus, self.case['snapshot'])
        controls = load_controls(corpus)
        root = Path(corpus['_root'])
        self.identity = {'task_id': case_id, 'session_id': session_id, 'arm': arm,
                         'repetition': repetition, 'snapshot': self.case['snapshot'],
                         'corpus_sha256': (root / 'corpus.sha256').read_text().strip(),
                         'controls_sha256': (root / 'comparison-controls.sha256').read_text().strip(),
                         'controls_version': controls['version']}
        self.events: list[dict] = []

    def record(self, *, operation: str, reason: str, detail: str,
               response_json: str, spans: list[dict], elapsed_ms: float,
               arguments: dict | None = None, because: str | None = None) -> str:
        """Record one logical operation, including failed/empty tool responses.

        Each source span is {file, start_byte, text}; it must occur in a JSON
        string actually delivered and exactly match the frozen source bytes.
        `because` is the agent's explicit causal attribution, never a timestamp.
        `arguments` retains existing selected_from_search_id without redefining it.
        """
        if operation not in OPERATIONS or reason not in REASONS or not detail.strip():
            raise ValueError('operation, reason and explanation are required')
        if isinstance(elapsed_ms, bool) or not isinstance(elapsed_ms, (int, float)) or not 0 <= elapsed_ms < float('inf'):
            raise ValueError('invalid latency')
        previous = {e['id']: e for e in self.events}
        if because is not None and because not in previous:
            raise ValueError('causal parent must be an earlier event in this run')
        payload = json.loads(response_json, parse_constant=lambda x: (_ for _ in ()).throw(ValueError(x)))
        delivered_strings = list(_strings(payload))
        verified = []
        for span in spans:
            file, start, source = span['file'], span['start_byte'], span['text']
            raw = source.encode('utf-8')
            if (file not in self.files or type(start) is not int or start < 0 or not raw
                    or self.files[file][start:start + len(raw)] != raw
                    or not any(source in value for value in delivered_strings)):
                raise ValueError('source span is not exact delivered snapshot content')
            verified.append({'file': file, 'start_byte': start, 'end_byte': start + len(raw),
                             'sha256': hashlib.sha256(raw).hexdigest(), 'text': source})
        arguments = json.loads(json.dumps(arguments or {}, allow_nan=False))
        selection = arguments.get('selected_from_search_id')
        if selection is not None:
            searches = [e for e in self.events if e['operation'] == 'search'
                        and e['search_id'] == selection]
            if operation != 'get' or not searches or not arguments.get('symbol_ids'):
                raise ValueError('selection must reference an earlier search in this run')
            # Loci permits explicitly selected symbols outside the result envelope.
            # It validates repository identity itself; the evaluator adds run scope.
            if reason in {'hydration', 'setup', 'unrelated'}:
                raise ValueError('non-selection reads must omit search selection lineage')
        search_id = payload.get('search_id') if operation == 'search' and isinstance(payload, dict) else None
        if search_id is not None and (not isinstance(search_id, str) or not search_id
                or any(e['search_id'] == search_id for e in self.events)):
            raise ValueError('invalid or repeated search id')
        event_id = f"{self.identity['session_id']}:{len(self.events) + 1}"
        event = {'id': event_id, **self.identity, 'operation': operation, 'reason': reason,
                 'detail': detail, 'because': because, 'arguments': arguments,
                 'search_id': search_id, 'response_json': response_json,
                 'serialized_bytes': len(response_json.encode('utf-8')),
                 'source_bytes': sum(s['end_byte'] - s['start_byte'] for s in verified),
                 'elapsed_ms': elapsed_ms, 'spans': verified}
        self.events.append(event)
        return event_id

    def report(self, answer: dict, *, usage: dict | None = None,
               usage_semantics: str | None = None, outcome: str = 'completed') -> dict:
        """Classify declared gap chains only after their source recovery is known."""
        if outcome not in {'completed', 'timeout', 'budget_exhausted', 'tool_failure', 'malformed_answer'}:
            raise ValueError('unknown run outcome')
        if usage is not None:
            if not usage_semantics or any(type(usage.get(k)) is not int or usage[k] < 0
                                         for k in ('input_tokens', 'cached_input_tokens', 'output_tokens')):
                raise ValueError('provider token totals and inclusion semantics required')
            if usage['cached_input_tokens'] > usage['input_tokens']:
                raise ValueError('cached input exceeds gross input')
        gold = self.case['context']
        by_id = {e['id']: e for e in self.events}
        before, after, seen = {}, {}, []
        for event in self.events:
            before[event['id']] = {g['id'] for g in gold if _covered(seen, g)}
            seen.extend(event['spans'])
            after[event['id']] = {g['id'] for g in gold if _covered(seen, g)}
        recovered: dict[str, set[str]] = {e['id']: set() for e in self.events}
        for event in self.events:
            if event['reason'] != 'missing_context':
                continue
            new_gold = after[event['id']] - before[event['id']]
            chain, node = [], event
            while node['reason'] == 'missing_context':
                chain.append(node)
                node = by_id.get(node['because'])
                if node is None:
                    break
            # A declared gap must originate in a task retrieval that actually
            # supplied required source, rather than setup or a merely nearby call.
            if node is None or node['reason'] != 'task_context' or not any(
                    s['file'] == g['file'] and s['start_byte'] < g['end_byte']
                    and g['start_byte'] < s['end_byte']
                    for s in node['spans'] for g in gold):
                continue
            for member in chain:
                recovered[member['id']].update(new_gold - before[member['id']])
        classifications = []
        for event in self.events:
            if event['reason'] != 'missing_context':
                classification = 'excluded' if event['reason'] != 'task_context' else 'initial_context'
            else:
                classification = 'avoidable' if recovered[event['id']] else 'unproven'
            classifications.append({'event_id': event['id'], 'classification': classification,
                                    'reason': event['reason'], 'because': event['because'],
                                    'recovered_gold': sorted(recovered[event['id']])})
        missing_lineage = any(c['classification'] == 'unproven' for c in classifications)
        source_bytes = sum(e['source_bytes'] for e in self.events)
        covered = {g['id'] for g in gold if _covered(seen, g)}
        return {**self.identity, 'schema_version': 1, 'outcome': outcome,
                'task_correct': outcome == 'completed' and check_answer(self.corpus, self.case['id'], answer),
                'answer': answer, 'read_count': len(self.events),
                'avoidable_reads': None if missing_lineage else sum(c['classification'] == 'avoidable' for c in classifications),
                'proven_avoidable_reads': sum(c['classification'] == 'avoidable' for c in classifications),
                'lineage_status': 'inconclusive' if missing_lineage else 'complete',
                'classifications': classifications, 'required_context_delivered': sorted(covered),
                'required_context_total': len(gold), 'context_recall': len(covered) / len(gold),
                'serialized_tool_output_bytes': sum(e['serialized_bytes'] for e in self.events),
                'source_bytes': source_bytes, 'estimated_source_tokens': (source_bytes + 3) // 4,
                'tool_elapsed_ms': sum(e['elapsed_ms'] for e in self.events),
                'provider_usage': usage, 'usage_semantics': usage_semantics,
                'token_status': 'measured' if usage is not None else 'unavailable'}

    def artifact(self, answer: dict, **kwargs) -> dict:
        return {'schema_version': 1, 'identity': self.identity, 'events': self.events,
                'measurement': self.report(answer, **kwargs)}


def replay(corpus: dict, artifact: dict) -> dict:
    """Validate saved events and reproduce metrics rather than trusting totals."""
    if artifact['schema_version'] != 1:
        raise ValueError('unsupported trace schema')
    identity = artifact['identity']
    trace = ReadTrace(corpus, identity['task_id'], identity['session_id'], identity['arm'], identity['repetition'])
    if trace.identity != identity:
        raise ValueError('trace corpus/controls identity mismatch')
    for event in artifact['events']:
        trace.record(**{k: event[k] for k in ('operation', 'reason', 'detail', 'response_json',
                                             'elapsed_ms', 'arguments', 'because')},
                     spans=[{'file': s['file'], 'start_byte': s['start_byte'], 'text': s['text']}
                            for s in event['spans']])
        if trace.events[-1] != event:
            raise ValueError('event identity or recorded accounting mismatch')
    measurement = artifact['measurement']
    result = trace.report(measurement['answer'], usage=measurement['provider_usage'],
                          usage_semantics=measurement['usage_semantics'], outcome=measurement['outcome'])
    if result != measurement:
        raise ValueError('saved measurement does not match replay')
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('trace', type=Path)
    parser.add_argument('--root', type=Path, default=DEFAULT_ROOT)
    args = parser.parse_args()
    print(json.dumps(replay(load_corpus(args.root), json.loads(args.trace.read_text())), indent=2))


if __name__ == '__main__':
    main()
