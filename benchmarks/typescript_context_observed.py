"""Protocol v3: observed retrieval work, exact delivery, and source coverage.

No agent-authored intent or per-read counterfactual is collected. Existing
source validation is reused; causal classification is deliberately not called.
"""
from __future__ import annotations

import json
from pathlib import Path

from benchmarks.typescript_context_corpus import check_answer, load_controls
from benchmarks.typescript_context_delivery import payload_texts
from benchmarks.typescript_context_trace import ReadTrace, _covered


HELPERS = {'list_mcp_resources', 'list_mcp_resource_templates', 'read_mcp_resource'}


class ObservedTrace(ReadTrace):
    """An exact source/cost recorder without inferred or declared read intent."""

    def record(self, *, operation, response_json, spans, elapsed_ms, arguments=None,
               reason=None, detail=None, because=None):
        if because is not None:
            raise ValueError('v3 does not collect causal attribution')
        # The legacy validator also verifies actual search selection. Its
        # required intent arguments are an internal bridge, never observations.
        event_id = super().record(
            operation=operation, reason='task_context', detail='Observed tool request.',
            response_json=response_json, spans=spans, elapsed_ms=elapsed_ms,
            arguments=arguments, because=None,
        )
        for field in ('reason', 'detail', 'because'):
            self.events[-1].pop(field)
        return event_id

    def report(self, answer, *, usage=None, usage_semantics=None, outcome='completed'):
        if outcome not in {'completed', 'timeout', 'budget_exhausted', 'tool_failure', 'malformed_answer'}:
            raise ValueError('unknown run outcome')
        if usage is not None:
            if (not usage_semantics or any(type(usage.get(k)) is not int or usage[k] < 0
                    for k in ('input_tokens', 'cached_input_tokens', 'output_tokens'))
                    or usage['cached_input_tokens'] > usage['input_tokens']):
                raise ValueError('valid provider token totals and inclusion semantics required')
        spans = [span for event in self.events for span in event['spans']]
        covered = sorted(gold['id'] for gold in self.case['context'] if _covered(spans, gold))
        source_bytes = sum(event['source_bytes'] for event in self.events)
        answer_correct = check_answer(self.corpus, self.case['id'], answer)
        return {
            **self.identity, 'schema_version': 3, 'measurement_method': 'observed_tool_calls',
            'intent_collection': 'not_collected', 'outcome': outcome, 'answer': answer,
            'answer_correct': answer_correct, 'task_correct': outcome == 'completed' and answer_correct,
            'read_count': len(self.events), 'validated_read_count': len(self.events),
            'required_context_delivered': covered, 'required_context_total': len(self.case['context']),
            'context_recall': len(covered) / len(self.case['context']),
            'serialized_tool_output_bytes': sum(event['serialized_bytes'] for event in self.events),
            'source_bytes': source_bytes, 'estimated_source_tokens': (source_bytes + 3) // 4,
            'tool_elapsed_ms': sum(event['elapsed_ms'] for event in self.events),
            'provider_usage': usage, 'usage_semantics': usage_semantics,
            'token_status': 'measured' if usage is not None else 'unavailable',
        }


def replay_trace(corpus, raw):
    if raw.get('schema_version') != 3:
        raise ValueError('v3 observation trace required')
    identity = raw['identity']
    trace = ObservedTrace(corpus, identity['task_id'], identity['session_id'], identity['arm'], identity['repetition'])
    if trace.identity != identity:
        raise ValueError('trace corpus/control identity mismatch')
    for event in raw['events']:
        trace.record(**{key: event[key] for key in ('operation', 'response_json', 'elapsed_ms', 'arguments')},
                     spans=[{key: span[key] for key in ('file', 'start_byte', 'text')} for span in event['spans']])
        if trace.events[-1] != event:
            raise ValueError('recorded source event does not replay exactly')
    return trace


def _terminal_calls(events):
    started, terminal, order, failures = {}, {}, [], []
    for event in events:
        item = event.get('item', {})
        kind = item.get('type')
        if kind and kind not in {'mcp_tool_call', 'agent_message', 'reasoning', 'error'}:
            failures.append({'category': 'unexpected_tool_event', 'type': kind, 'item': item.get('id')})
        if kind != 'mcp_tool_call':
            continue
        item_id = item.get('id')
        if not isinstance(item_id, str) or not item_id:
            failures.append({'category': 'invalid_tool_identity'})
            continue
        event_type = event.get('type')
        target = started if event_type == 'item.started' else terminal if event_type in {'item.completed', 'item.failed'} else None
        if target is None:
            continue
        if item_id in target:
            failures.append({'category': 'duplicate_tool_event', 'item': item_id, 'event_type': event_type})
        if item_id not in started and item_id not in terminal:
            order.append(item_id)
        target[item_id] = item
    for item_id in order:
        if item_id not in terminal or item_id not in started:
            failures.append({'category': 'incomplete_tool_lifecycle', 'item': item_id})
        elif any(started[item_id].get(key) != terminal[item_id].get(key) for key in ('server', 'tool', 'arguments')):
            failures.append({'category': 'changed_tool_request', 'item': item_id})
    return [(item_id, terminal.get(item_id), started.get(item_id)) for item_id in order], failures


def _source_free_helper(call, payload_kind, texts):
    tool, arguments = call['tool'], call.get('arguments', {})
    if tool not in HELPERS or not isinstance(arguments, dict):
        return False
    # Codex's event server field follows the helper's argument. It is not the
    # namespace of a newly configured server. The audited profile configures
    # only evaluation, with no resources. Verify the actual empty/error result.
    if call.get('status') == 'failed' and payload_kind == 'host_error':
        prefixes = {'read_mcp_resource': 'resources/read failed:',
                    'list_mcp_resources': 'resources/list failed:',
                    'list_mcp_resource_templates': 'resources/templates/list failed:'}
        return len(texts) == 1 and texts[0].startswith(prefixes[tool])
    if tool == 'read_mcp_resource' or payload_kind != 'text_blocks' or len(texts) != 1:
        return False
    try:
        payload = json.loads(texts[0])
    except ValueError:
        return False
    key = 'resources' if tool == 'list_mcp_resources' else 'resourceTemplates'
    return (isinstance(payload, dict) and payload.get(key) == []
            and set(payload) <= {key, 'server'} and payload.get('server') == arguments.get('server'))


def reconcile_observed(raw_trace, events):
    """Bind all host-observed calls to delivered payloads; retain failed calls."""
    from benchmarks.typescript_context_tools_v3 import TOOL_NAMES, normalize_arguments

    calls, failures = _terminal_calls(events)
    deliveries = raw_trace.get('deliveries', [])
    session = raw_trace['identity']['session_id']
    expected_ids = [f'{session}/attempt/{n}' for n in range(1, len(deliveries) + 1)]
    if ([entry.get('attempt_id') for entry in deliveries] != expected_ids
            or raw_trace.get('attempts') != len(deliveries)):
        failures.append({'category': 'invalid_attempt_sequence'})
    ledger = {entry.get('attempt_id'): entry for entry in deliveries}
    trace_events = {entry['id']: entry for entry in raw_trace['events']}
    matched, matched_events, rows, validated_results = set(), set(), [], []
    for item_id, call, started in calls:
        item = call or started
        row = {'item_id': item_id, 'server': item.get('server'), 'tool': item.get('tool'),
               'arguments': item.get('arguments'), 'status': item.get('status'),
               'attempt_id': None, 'trace_event_id': None, 'source_bytes': None,
               'serialized_bytes': None, 'payload_texts': None, 'payload_format': None}
        rows.append(row)
        if call is None:
            continue
        try:
            payload_kind, texts = payload_texts(call)
        except ValueError as exc:
            failures.append({'category': 'unaccounted_tool_output', 'item': item_id, 'message': str(exc)})
            continue
        row.update(payload_format=payload_kind, payload_texts=texts,
                   serialized_bytes=sum(len(text.encode('utf-8')) for text in texts))
        tool, server = call.get('tool'), call.get('server')
        result = (call.get('result') or {}).get('structured_content')
        if server == 'evaluation' and tool in TOOL_NAMES:
            attempt_id = result.get('_evaluation', {}).get('attempt_id') if isinstance(result, dict) else None
            row['attempt_id'] = attempt_id
            entry = ledger.get(attempt_id)
            if entry is None:
                # Argument validation runs before the adapter body and therefore
                # has no delivery row. Its exact text and call still cost work.
                if (call.get('status') == 'failed' and payload_kind in {'text_blocks', 'host_error'}
                        and all(text.startswith(f'Error executing tool {tool}:')
                                or text.startswith('Error calling tool') for text in texts)):
                    row['source_bytes'] = 0
                    continue
                failures.append({'category': 'unmatched_delivery', 'item': item_id})
                continue
            if attempt_id in matched:
                failures.append({'category': 'duplicate_delivery', 'item': item_id})
                continue
            matched.add(attempt_id)
            try:
                parameters = normalize_arguments(tool, call['arguments'])
                if entry['operation'] != tool or entry['arguments'] != parameters:
                    raise ValueError('actual request differs from recorded request')
                if payload_kind != 'compact_json' or texts != [entry['response_json']]:
                    raise ValueError('actual output differs from recorded output')
                if row['serialized_bytes'] != entry['serialized_bytes']:
                    raise ValueError('serialized byte count differs')
                if (type(entry['elapsed_ms']) not in (int, float)
                        or not 0 <= entry['elapsed_ms'] < float('inf')):
                    raise ValueError('invalid delivery latency')
                source_bytes = sum(span['end_byte'] - span['start_byte'] for span in entry['spans'])
                if source_bytes != entry['source_bytes']:
                    raise ValueError('delivery source byte count differs')
                trace_id = entry['trace_event_id']
                row['trace_event_id'] = trace_id
                if trace_id is None:
                    if entry['status'] != 'rejected' or entry['spans'] or source_bytes:
                        raise ValueError('rejected attempt delivered source')
                else:
                    trace_event = trace_events.get(trace_id)
                    if trace_event is None or trace_id in matched_events or entry['status'] != 'recorded':
                        raise ValueError('delivery has no unique recorded source event')
                    expected_operation = 'graph' if tool.startswith('graph_') else tool
                    if (trace_event['operation'] != expected_operation or trace_event['arguments'] != parameters
                            or any(trace_event[key] != entry[key] for key in
                                   ('response_json', 'serialized_bytes', 'source_bytes', 'spans'))
                            or entry['elapsed_ms'] < trace_event['elapsed_ms']):
                        raise ValueError('delivery differs from validated source event')
                    matched_events.add(trace_id)
                    validated_results.append(result)
                row['source_bytes'] = source_bytes
            except (KeyError, TypeError, ValueError) as exc:
                failures.append({'category': 'delivery_trace_mismatch', 'item': item_id, 'message': str(exc)})
        elif tool in HELPERS and _source_free_helper(call, payload_kind, texts):
            row['source_bytes'] = 0
        else:
            failures.append({'category': 'unaccounted_tool_output', 'item': item_id,
                             'message': 'tool or source-bearing payload outside verified surface'})
    if matched != set(ledger) or matched_events != set(trace_events):
        failures.append({'category': 'unmatched_recorded_delivery'})
    complete = not failures and all(row['serialized_bytes'] is not None and row['source_bytes'] is not None for row in rows)
    subtotal = sum(row['serialized_bytes'] or 0 for row in rows)
    return {'schema_version': 3, 'complete': complete, 'tool_call_count': len(calls),
            'recorded_payload_bytes': subtotal, 'complete_payload_bytes': subtotal if complete else None,
            'source_bytes': sum(row['source_bytes'] or 0 for row in rows) if complete else None,
            'calls': rows, 'failures': failures, 'validated_results': validated_results}


def measure(corpus, case, run, events, elapsed, exit_code, timed_out, index=None):
    raw = json.loads(Path(run['trace_path']).read_text())
    trace = replay_trace(corpus, raw)
    accounting = reconcile_observed(raw, events)
    delivered = accounting.pop('validated_results')
    messages = [event['item']['text'] for event in events if event.get('type') == 'item.completed'
                and event.get('item', {}).get('type') == 'agent_message']
    outcome = 'timeout' if timed_out else 'tool_failure' if exit_code else 'completed'
    try:
        answer = json.loads(messages[-1])
        if not isinstance(answer, dict):
            raise ValueError('answer must be an object')
    except (ValueError, IndexError):
        answer = {}
        if outcome == 'completed':
            outcome = 'malformed_answer'
    turns = [event for event in events if event.get('type') == 'turn.completed']
    usage = turns[-1].get('usage') if turns else None
    limits = load_controls(corpus)['limits']
    failures = list(raw['failures']) + accounting['failures']
    checks = [('all_tool_calls', accounting['tool_call_count'], limits['max_top_level_tool_calls_per_run']),
              ('all_tool_output', accounting['recorded_payload_bytes'], limits['max_serialized_output_bytes_per_run'])]
    if usage:
        checks.extend([('input_tokens', usage['input_tokens'], limits['max_reported_input_tokens_per_run']),
                       ('output_tokens', usage['output_tokens'], limits['max_reported_output_tokens_per_run'])])
    if accounting['source_bytes'] is not None:
        checks.append(('all_source', accounting['source_bytes'], limits['max_source_bytes_per_run']))
    for name, actual, maximum in checks:
        if actual > maximum:
            failures.append({'category': 'budget_exhausted', 'limit': name})
    for row in accounting['calls']:
        if (row['serialized_bytes'] or 0) > limits['max_serialized_output_bytes_per_operation']:
            failures.append({'category': 'budget_exhausted', 'limit': 'host_tool_output', 'item': row['item_id']})
    if outcome == 'completed' and any(failure['category'] == 'budget_exhausted' for failure in failures):
        outcome = 'budget_exhausted'
    if outcome == 'completed' and not accounting['complete']:
        outcome = 'tool_failure'
    semantics = 'Codex turn.completed gross input; cached input is a subset; output includes reasoning tokens.' if usage else None
    measurement = trace.report(answer, usage=usage, usage_semantics=semantics, outcome=outcome)
    measurement.update(read_count=accounting['tool_call_count'],
                       serialized_tool_output_bytes=accounting['complete_payload_bytes'],
                       source_bytes=accounting['source_bytes'])
    measurement['estimated_source_tokens'] = ((accounting['source_bytes'] + 3) // 4
                                               if accounting['source_bytes'] is not None else None)
    measurement['measurement_complete'] = accounting['complete'] and usage is not None
    measurement['task_correct'] = measurement['task_correct'] and measurement['measurement_complete']
    baseline = {
        'end_to_end_seconds': min(elapsed, limits['max_end_to_end_seconds_per_run']) if timed_out else elapsed,
        'actual_process_seconds': elapsed, 'exit_code': exit_code,
        'provider_thread_id': next((event['thread_id'] for event in events if event.get('type') == 'thread.started'), None),
        'failures': failures, 'tool_delivery_verified': accounting['complete'],
        'output_accounting': accounting, 'adapter_elapsed_ms': sum(entry['elapsed_ms'] for entry in raw['deliveries']),
        'recoverable_error_events': sum(failure['category'] in {'tool_error', 'invalid_trace'} for failure in raw['failures'])
                                   + sum(row['status'] == 'failed' for row in accounting['calls']),
    }
    if index is not None:
        from benchmarks.typescript_context_relationships import score_relationships
        baseline['relationships'] = score_relationships(case, index, delivered)
    return {'schema_version': 3, 'identity': trace.identity, 'events': trace.events,
            'measurement': measurement, 'baseline': baseline}
