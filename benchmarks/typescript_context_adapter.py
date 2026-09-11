"""Read-only, snapshot-bound tool adapter for the TypeScript comparison."""
from __future__ import annotations

import argparse
import asyncio
import copy
import json
import signal
import time
from pathlib import Path
from typing import Literal

from mcp.server.mcpserver import MCPServer
from mcp.types import CallToolResult, ToolAnnotations

from benchmarks.typescript_context_corpus import load_controls, load_corpus
from benchmarks.typescript_context_trace import ReadTrace
from loci import service


def wire(value: dict) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False)


class Adapter:
    """One immutable snapshot and prebuilt index; no caller-supplied repository."""

    def __init__(self, run: dict):
        self.run = run
        self.repo = Path(run['repo']).resolve()
        self.corpus = load_corpus(Path(run['corpus_root']))
        self.is_v2 = self.corpus.get('version') == 'typescript-context-v2'
        self.limits = load_controls(self.corpus)['limits']
        self.trace = ReadTrace(self.corpus, run['case_id'], run['session_id'], run['arm'], run['repetition'])
        entries = list(self.repo.rglob('*'))
        if any(path.is_symlink() for path in entries):
            raise ValueError('snapshot must not contain symlinks')
        files = {path.relative_to(self.repo).as_posix(): path for path in entries if path.is_file()}
        if files.keys() != self.trace.files.keys():
            raise ValueError('repository inventory must match the frozen snapshot exactly')
        if any(path.read_bytes() != self.trace.files[name] for name, path in files.items()):
            raise ValueError('repository contents must match the frozen snapshot exactly')
        index = service.get_store().load(self.repo)
        if index is None:
            raise ValueError('fresh index must be built before agent timing')
        self.symbols = {s['id']: s for s in index['symbols']}
        self.lines = {f: data.decode('utf-8').splitlines(keepends=True) for f, data in self.trace.files.items()}
        self.failures: list[dict] = []
        self.deliveries: list[dict] = []
        self.lock = asyncio.Lock()
        self.attempts = 0
        self.persist()

    def persist(self):
        target = Path(self.run['trace_path'])
        payload = {'identity': self.trace.identity, 'events': self.trace.events,
                   'failures': self.failures, 'attempts': self.attempts}
        if self.is_v2:
            payload['deliveries'] = self.deliveries
        target.write_text(wire(payload) + '\n')

    def _file(self, value: str) -> str:
        if not isinstance(value, str) or value not in self.trace.files:
            raise ValueError('file must be an exact relative path in the supplied snapshot')
        return value

    def _line_span(self, file: str, line: int, text: str) -> dict | None:
        if not text:
            return None
        file = self._file(file)
        if type(line) is not int or not 1 <= line <= len(self.lines[file]):
            raise ValueError('invalid source line provenance')
        return {'file': file, 'start_byte': sum(len(s.encode('utf-8')) for s in self.lines[file][:line - 1]),
                'text': text}

    def _v2_signature_span(self, record: object) -> dict | None:
        """Credit only a signature proven inside its indexed declaration range."""
        if not self.is_v2 or not isinstance(record, dict):
            return None
        symbol_id = record.get('id')
        signature = record.get('signature')
        indexed = self.symbols.get(symbol_id) if isinstance(symbol_id, str) else None
        if (not isinstance(signature, str) or not signature or not isinstance(indexed, dict)):
            return None
        file = indexed.get('file_path')
        start = indexed.get('byte_offset')
        length = indexed.get('byte_length')
        if (not isinstance(file, str) or type(start) is not int or type(length) is not int
                or start < 0 or length <= 0 or file not in self.trace.files):
            return None
        try:
            raw_signature = signature.encode('utf-8')
        except UnicodeEncodeError:
            return None
        if not raw_signature or start + length > len(self.trace.files[file]):
            return None
        declaration = self.trace.files[file][start:start + length]
        offset = declaration.find(raw_signature)
        if offset < 0:
            return None
        return {'file': file, 'start_byte': start + offset, 'text': signature}

    def _v2_signature_spans(self, operation: str, result: dict) -> list[dict]:
        if not self.is_v2 or not isinstance(result, dict):
            return []
        records: list[object] = []
        if operation in {'search', 'get'}:
            symbols = result.get('symbols')
            if isinstance(symbols, list):
                records.extend(symbols)
        elif operation == 'outline':
            files = result.get('files')
            if isinstance(files, list):
                for entry in files:
                    if isinstance(entry, dict) and isinstance(entry.get('symbols'), list):
                        records.extend(entry['symbols'])
        elif operation.startswith('graph_'):
            def walk(value: object) -> None:
                if isinstance(value, dict):
                    records.append(value)
                    for child in value.values():
                        walk(child)
                elif isinstance(value, list):
                    for child in value:
                        walk(child)
            walk(result)
        spans = []
        for record in records:
            span = self._v2_signature_span(record)
            if span is not None:
                spans.append(span)
        return spans

    def spans(self, operation: str, result: dict) -> list[dict]:
        spans = []
        if operation == 'get':
            for item in result['symbols']:
                file = self.symbols[item['id']]['file_path']
                if item['source']:
                    spans.append({'file': file, 'start_byte': item['byte_offset'], 'text': item['source']})
                for key, start in [('context_before', item['line'] - len(item.get('context_before', []))),
                                   ('context_after', item['end_line'] + 1)]:
                    spans.extend(self._line_span(file, start + i, text)
                                 for i, text in enumerate(item.get(key, [])))
        elif operation == 'file':
            spans.append(self._line_span(result['file'], result['start_line'], result['content']))
        elif operation == 'grep':
            for item in result['matches']:
                spans.append(self._line_span(item['file'], item['line'], item['match']))
                for key, start in [('context_before', item['line'] - len(item['context_before'])),
                                   ('context_after', item['line'] + 1)]:
                    spans.extend(self._line_span(item['file'], start + i, text)
                                 for i, text in enumerate(item[key]))
        elif operation.startswith('graph_'):
            def walk(value):
                if isinstance(value, dict):
                    for key, child in value.items():
                        if key == 'evidence_span' and isinstance(child, dict):
                            spans.append(self._line_span(child['file'], child['start_line'], child['content']))
                        else:
                            walk(child)
                elif isinstance(value, list):
                    for child in value:
                        walk(child)
            walk(result)
        spans.extend(self._v2_signature_spans(operation, result))
        return [s for s in spans if s is not None]

    def dispatch(self, operation: str, parameters: dict) -> dict:
        p = dict(parameters)
        allowed = {
            'search': {'query', 'kind', 'lang', 'file_paths'},
            'get': {'symbol_ids', 'context', 'selected_from_search_id'},
            'outline': {'file'}, 'file': {'file_path', 'start_line', 'end_line'}, 'grep': {'pattern'},
            'graph_anchors': {'question', 'seed_ids'}, 'graph_neighbors': {'seed_ids'},
            'graph_traverse_neighbors': {'seed_ids', 'edge_types'},
            'graph_paths': {'source_ids', 'target_ids', 'edge_types'},
            'graph_retrieve': {'question', 'seed_ids', 'edge_types'},
            'graph_imports': {'file', 'status', 'offset', 'limit'},
            'graph_references': {'file', 'status', 'offset', 'limit'},
            'graph_calls': {'file', 'status', 'offset', 'limit'},
        }
        if operation not in allowed or p.keys() - allowed[operation]:
            raise ValueError('unknown operation or parameters outside the fixed tool contract')
        for key in ('file', 'file_path'):
            if p.get(key) is not None:
                self._file(p[key])
        if p.get('file_paths') is not None:
            for file in p['file_paths']:
                self._file(file)
        for key in ('symbol_ids', 'seed_ids', 'source_ids', 'target_ids'):
            if p.get(key) is not None:
                maximum = self.limits['max_nodes'] if key == 'symbol_ids' else self.limits['max_anchors']
                if not isinstance(p[key], list) or len(p[key]) > maximum:
                    raise ValueError('explicit IDs exceed the frozen node/anchor limit')
                if any(s not in self.symbols for s in p[key]):
                    raise ValueError('IDs must belong to this snapshot index')
        if operation == 'search':
            return service.search_symbols_result(self.repo, **p, limit=self.limits['search_k'])
        if operation == 'get':
            if type(p.get('context', 0)) is not int or p.get('context', 0) < 0:
                raise ValueError('context must be a nonnegative line count')
            return {'symbols': service.get_symbols(self.repo, **p)}
        if operation == 'outline':
            return {'files': service.outline_repo(self.repo, **p)}
        if operation == 'file':
            return service.get_cached_file(self.repo, **p)
        if operation == 'grep':
            return service.grep_repo_result(self.repo, **p)
        if operation == 'graph_anchors':
            return service.graph_anchors(self.repo, **p, max_anchors=self.limits['max_anchors'])
        if operation == 'graph_neighbors':
            return service.graph_neighbors(self.repo, **p)
        filters = {'direction': 'outgoing', 'resolutions': ['exact', 'declared', 'import-resolved']}
        if operation == 'graph_traverse_neighbors':
            return service.graph_traverse_neighbors(self.repo, **p, **filters,
                                                    max_neighbors=self.limits['max_neighbors_per_seed'])
        if operation in {'graph_paths', 'graph_retrieve'}:
            limits = {k: self.limits[k] for k in ('max_hops', 'max_nodes', 'max_paths', 'max_evidence_bytes')}
            limits['max_estimated_tokens'] = self.limits['max_estimated_evidence_tokens']
            if operation == 'graph_retrieve':
                limits['max_anchors'] = self.limits['max_anchors']
            return getattr(service, operation)(self.repo, **p, **filters, **limits, path_offset=0)
        for key, default, maximum in [('offset', 0, 10000), ('limit', 20, 32)]:
            value = p.get(key, default)
            if type(value) is not int or not 0 <= value <= maximum:
                raise ValueError('invalid record pagination')
            p[key] = value
        return getattr(service, operation)(self.repo, **p)

    def _read_v1(self, operation: str, parameters: dict, reason: str, detail: str,
                 because: str | None = None) -> CallToolResult:
        self.attempts += 1
        started = time.monotonic()
        event_id = f"{self.trace.identity['session_id']}:{len(self.trace.events) + 1}"
        exhausted = self.attempts > self.limits['max_top_level_tool_calls_per_run']
        if exhausted:
            self.failures.append({'event_id': event_id, 'category': 'budget_exhausted', 'limit': 'tool_calls'})
            self.persist()
            raise ValueError('run tool-call budget exhausted; no further source delivery')
        try:
            def timeout(_signum, _frame):
                raise TimeoutError('retrieval operation exceeded ten seconds')
            previous = signal.signal(signal.SIGALRM, timeout)
            signal.setitimer(signal.ITIMER_REAL, self.limits['max_retrieval_seconds_per_operation'])
            try:
                result = self.dispatch(operation, parameters)
                spans = self.spans(operation, result)
            finally:
                signal.setitimer(signal.ITIMER_REAL, 0)
                signal.signal(signal.SIGALRM, previous)
        except Exception as exc:
            result, spans = {'error': {'code': type(exc).__name__, 'message': str(exc)}}, []
            if isinstance(exc, TimeoutError):
                self.failures.append({'event_id': event_id, 'category': 'budget_exhausted', 'limit': 'operation_time'})
        result['_evaluation'] = {'event_id': event_id, 'calls_remaining': max(0, 24 - self.attempts)}
        source_bytes = sum(len(s['text'].encode('utf-8')) for s in spans)
        raw = wire(result)
        totals = self.trace.events
        exceeded = []
        if operation.startswith('graph_'):
            nodes = set()
            def inspect_graph(value):
                if isinstance(value, dict):
                    if {'id', 'namespace', 'kind'} <= value.keys():
                        nodes.add(value['id'])
                    if isinstance(value.get('neighbors'), list) and len(value['neighbors']) > self.limits['max_neighbors_per_seed']:
                        exceeded.append('max_neighbors_per_seed')
                    for child in value.values():
                        inspect_graph(child)
                elif isinstance(value, list):
                    for child in value:
                        inspect_graph(child)
            inspect_graph(result)
            if len(nodes) > self.limits['max_nodes']:
                exceeded.append('max_nodes')
        for name, value in [
            ('max_evidence_spans', len(spans)), ('max_evidence_bytes', source_bytes),
            ('max_estimated_evidence_tokens', (source_bytes + 3) // 4),
            ('max_serialized_output_bytes_per_operation', len(raw.encode('utf-8'))),
            ('max_serialized_output_bytes_per_run', sum(e['serialized_bytes'] for e in totals) + len(raw.encode('utf-8')) + (24 - self.attempts) * 1024),
            ('max_source_bytes_per_run', sum(e['source_bytes'] for e in totals) + source_bytes),
        ]:
            if value > self.limits[name]:
                exceeded.append(name)
        if exceeded:
            self.failures.append({'event_id': event_id, 'category': 'budget_exhausted', 'limits': exceeded})
            result = {'error': {'code': 'BUDGET_EXHAUSTED', 'limits': exceeded,
                                'message': 'Result withheld before source delivery; run budget failure retained.'},
                      '_evaluation': result['_evaluation']}
            raw, spans = wire(result), []
        try:
            self.trace.record(operation='graph' if operation.startswith('graph_') else operation,
                              reason=reason, detail=detail, response_json=raw, spans=spans,
                              elapsed_ms=(time.monotonic() - started) * 1000,
                              arguments=parameters, because=because)
        except Exception as exc:
            # Invalid lineage is never silently repaired or charged as a success.
            self.failures.append({'event_id': event_id, 'category': 'invalid_trace', 'message': str(exc)})
            self.persist()
            raise
        self.persist()
        return CallToolResult(content=[], structured_content=result)

    def _v2_evaluation(self, attempt_id: str, event_id: str | None = None) -> dict:
        remaining = max(0, int(self.limits['max_top_level_tool_calls_per_run']) - self.attempts)
        evaluation = {'attempt_id': attempt_id, 'calls_remaining': remaining}
        if event_id is not None:
            evaluation['event_id'] = event_id
        return evaluation

    @staticmethod
    def _json_copy(value):
        return json.loads(json.dumps(value, allow_nan=False))

    def _v2_delivery(self, *, operation: str, parameters: dict, reason: str, detail: str,
                     because, result: dict, response_json: str, started: float,
                     status: str, trace_event_id: str | None, spans: list[dict]) -> None:
        if status not in {'recorded', 'rejected'}:
            raise ValueError('invalid v2 delivery status')
        if status == 'recorded':
            delivered_spans = self._json_copy(spans)
            source_bytes = sum(s['end_byte'] - s['start_byte'] for s in delivered_spans)
        else:
            delivered_spans = []
            source_bytes = 0
        self.deliveries.append({
            'attempt_id': f"{self.trace.identity['session_id']}/attempt/{self.attempts}",
            'operation': operation,
            'arguments': self._json_copy(parameters),
            'reason': reason,
            'detail': detail,
            'because': because,
            'response_json': response_json,
            'serialized_bytes': len(response_json.encode('utf-8')),
            'source_bytes': source_bytes,
            'elapsed_ms': (time.monotonic() - started) * 1000,
            'trace_event_id': trace_event_id,
            'status': status,
            'spans': delivered_spans,
        })

    @staticmethod
    def _v2_invalid_result(attempt_id: str, message: str, calls_remaining: int) -> dict:
        return {
            'error': {'code': 'INVALID_TRACE', 'message': str(message)[:240]},
            '_evaluation': {'attempt_id': attempt_id, 'calls_remaining': calls_remaining},
        }

    def _read_v2(self, operation: str, parameters: dict, reason: str, detail: str,
                 because: str | None = None) -> CallToolResult:
        """Record every v2 attempt, including failures that never reach ReadTrace."""
        self.attempts += 1
        started = time.monotonic()
        session = self.trace.identity['session_id']
        attempt_id = f'{session}/attempt/{self.attempts}'
        event_id = f'{session}:{len(self.trace.events) + 1}'
        max_calls = int(self.limits['max_top_level_tool_calls_per_run'])

        # A call-cap rejection has no candidate ReadTrace event.  It still gets
        # a stable attempt ID, bounded response, failure record, and ledger row.
        if self.attempts > max_calls:
            result = {
                'error': {'code': 'BUDGET_EXHAUSTED',
                          'message': 'Run tool-call budget exhausted; no further source delivery.'},
                '_evaluation': self._v2_evaluation(attempt_id),
            }
            raw = wire(result)
            self.failures.append({'attempt_id': attempt_id, 'category': 'budget_exhausted',
                                  'limit': 'tool_calls'})
            self._v2_delivery(operation=operation, parameters=parameters, reason=reason,
                              detail=detail, because=because, result=result, response_json=raw,
                              started=started, status='rejected', trace_event_id=None, spans=[])
            self.persist()
            return CallToolResult(content=[], structured_content=result)

        try:
            def timeout(_signum, _frame):
                raise TimeoutError('retrieval operation exceeded ten seconds')
            previous = signal.signal(signal.SIGALRM, timeout)
            signal.setitimer(signal.ITIMER_REAL, self.limits['max_retrieval_seconds_per_operation'])
            try:
                result = self.dispatch(operation, parameters)
                spans = self.spans(operation, result)
            finally:
                signal.setitimer(signal.ITIMER_REAL, 0)
                signal.signal(signal.SIGALRM, previous)
        except Exception as exc:
            result, spans = {'error': {'code': type(exc).__name__, 'message': str(exc)}}, []
            if isinstance(exc, TimeoutError):
                self.failures.append({'attempt_id': attempt_id, 'category': 'budget_exhausted',
                                      'limit': 'operation_time'})
            else:
                self.failures.append({'attempt_id': attempt_id, 'category': 'tool_error',
                                      'message': str(exc)[:240]})

        result['_evaluation'] = self._v2_evaluation(attempt_id, event_id)
        source_bytes = sum(len(s['text'].encode('utf-8')) for s in spans)
        raw = wire(result)
        totals = self.deliveries
        exceeded = []
        if operation.startswith('graph_'):
            nodes = set()

            def inspect_graph(value):
                if isinstance(value, dict):
                    if {'id', 'namespace', 'kind'} <= value.keys():
                        nodes.add(value['id'])
                    if (isinstance(value.get('neighbors'), list)
                            and len(value['neighbors']) > self.limits['max_neighbors_per_seed']):
                        exceeded.append('max_neighbors_per_seed')
                    for child in value.values():
                        inspect_graph(child)
                elif isinstance(value, list):
                    for child in value:
                        inspect_graph(child)

            inspect_graph(result)
            if len(nodes) > self.limits['max_nodes']:
                exceeded.append('max_nodes')
        for name, value in [
            ('max_evidence_spans', len(spans)), ('max_evidence_bytes', source_bytes),
            ('max_estimated_evidence_tokens', (source_bytes + 3) // 4),
            ('max_serialized_output_bytes_per_operation', len(raw.encode('utf-8'))),
            ('max_serialized_output_bytes_per_run',
             sum(e['serialized_bytes'] for e in totals) + len(raw.encode('utf-8'))
             + (max_calls - self.attempts) * 1024),
            ('max_source_bytes_per_run', sum(e['source_bytes'] for e in totals) + source_bytes),
        ]:
            if value > self.limits[name]:
                exceeded.append(name)
        if exceeded:
            self.failures.append({'attempt_id': attempt_id, 'event_id': event_id,
                                  'category': 'budget_exhausted', 'limits': exceeded})
            result = {
                'error': {'code': 'BUDGET_EXHAUSTED', 'limits': exceeded,
                          'message': 'Result withheld before source delivery; run budget failure retained.'},
                '_evaluation': result['_evaluation'],
            }
            raw, spans = wire(result), []

        trace_operation = 'graph' if operation.startswith('graph_') else operation
        elapsed = (time.monotonic() - started) * 1000
        try:
            # Validate against a shallow trace copy first.  ReadTrace.record is
            # intentionally unchanged; its event list is isolated here so a
            # rejected source response cannot mutate the real causal history.
            candidate = copy.copy(self.trace)
            candidate.events = list(self.trace.events)
            candidate.record(operation=trace_operation, reason=reason, detail=detail,
                             response_json=raw, spans=spans, elapsed_ms=elapsed,
                             arguments=parameters, because=because)
        except Exception as exc:
            message = str(exc)
            self.failures.append({'attempt_id': attempt_id, 'category': 'invalid_trace',
                                  'message': message[:240]})
            rejected = self._v2_invalid_result(
                attempt_id, message,
                max(0, max_calls - self.attempts),
            )
            rejected_raw = wire(rejected)
            self._v2_delivery(operation=operation, parameters=parameters, reason=reason,
                              detail=detail, because=because, result=rejected,
                              response_json=rejected_raw, started=started, status='rejected',
                              trace_event_id=None, spans=[])
            self.persist()
            return CallToolResult(content=[], structured_content=rejected)

        try:
            recorded_id = self.trace.record(operation=trace_operation, reason=reason,
                                            detail=detail, response_json=raw, spans=spans,
                                            elapsed_ms=elapsed, arguments=parameters,
                                            because=because)
        except Exception as exc:
            # This should be unreachable after candidate validation, but it is
            # still a bounded v2 rejection if a trace invariant changes.
            message = str(exc)
            self.failures.append({'attempt_id': attempt_id, 'category': 'invalid_trace',
                                  'message': message[:240]})
            rejected = self._v2_invalid_result(
                attempt_id, message,
                max(0, max_calls - self.attempts),
            )
            rejected_raw = wire(rejected)
            self._v2_delivery(operation=operation, parameters=parameters, reason=reason,
                              detail=detail, because=because, result=rejected,
                              response_json=rejected_raw, started=started, status='rejected',
                              trace_event_id=None, spans=[])
            self.persist()
            return CallToolResult(content=[], structured_content=rejected)

        recorded_spans = self.trace.events[-1]['spans']
        self._v2_delivery(operation=operation, parameters=parameters, reason=reason,
                          detail=detail, because=because, result=result, response_json=raw,
                          started=started, status='recorded', trace_event_id=recorded_id,
                          spans=recorded_spans)
        self.persist()
        return CallToolResult(content=[], structured_content=result)

    def read(self, operation: str, parameters: dict, reason: str, detail: str,
             because: str | None = None) -> CallToolResult:
        if self.is_v2:
            return self._read_v2(operation, parameters, reason, detail, because)
        return self._read_v1(operation, parameters, reason, detail, because)


TOOL_HELP = """Read only the supplied repository snapshot. No external files or execution.
Use operation and its parameters:
search: query, optional kind/lang/file_paths (K=5).
get: symbol_ids (max 32), optional context (nonnegative lines), selected_from_search_id.
outline: optional file. file: file_path, optional start_line/end_line.
grep: pattern (regex). graph_anchors: question, optional seed_ids.
graph_neighbors: seed_ids (exact contains). graph_traverse_neighbors: seed_ids, optional edge_types.
graph_paths: source_ids, target_ids, optional edge_types.
graph_retrieve: question, optional seed_ids/edge_types.
graph_imports/graph_references/graph_calls: optional file/status/offset/limit (max32).
Graph direction is outgoing; hops3, nodes32, paths16, anchors5, neighbors16,
evidence64 spans/16KiB/4096 estimated tokens; output32KiB per call.
Run ceilings: 24 reads, 256KiB JSON, 128KiB source, 180 seconds.
Every call needs a reason and short detail explaining intent BEFORE the read.
task_context=initial task retrieval; missing_context=follow-up caused by absent
context in an earlier result; hydration=deliberate source hydration;
verification=necessary verification; setup=setup; unrelated=unrelated work.
For missing_context, because must explicitly name the earlier result's
_evaluation.event_id that caused the need; never infer a cause from timing.
Preserve the causal chain through search then get when both recover that gap.
selected_from_search_id is separate: supply it only for a get deliberately
selected because of that exact search, including selections not surfaced there.
Omit it for direct/outline/hydration/mixed-purpose reads; split mixed purposes.
No caller-supplied repo, budget overrides, or other parameter names are accepted.
"""


def create_server(adapter: Adapter) -> MCPServer:
    server = MCPServer('evaluation', instructions='Snapshot-only TypeScript baseline reads with explicit task lineage.')

    @server.tool(description=TOOL_HELP, annotations=ToolAnnotations(
        read_only_hint=True, destructive_hint=False, open_world_hint=False), structured_output=False)
    async def read(operation: Literal['search', 'get', 'outline', 'file', 'grep', 'graph_anchors',
                                     'graph_neighbors', 'graph_traverse_neighbors', 'graph_paths',
                                     'graph_retrieve', 'graph_imports', 'graph_references', 'graph_calls'],
                   parameters: dict, reason: Literal['task_context', 'missing_context', 'hydration',
                                                     'verification', 'setup', 'unrelated'],
                   detail: str, because: str | None = None) -> CallToolResult:
        async with adapter.lock:
            return adapter.read(operation, parameters, reason, detail, because)
    return server


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run', type=Path)
    args = parser.parse_args()
    create_server(Adapter(json.loads(args.run.read_text()))).run()


if __name__ == '__main__':
    main()
