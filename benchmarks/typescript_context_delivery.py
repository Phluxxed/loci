"""V2 delivered-cost accounting, independent of validated causal read events."""
import math
from typing import Any

from benchmarks.typescript_context_adapter import wire

RESOURCE_HELPERS = {'list_mcp_resources', 'list_mcp_resource_templates', 'read_mcp_resource'}


def payload_texts(call: dict) -> tuple[str, list[str]]:
    """Return the exact result payload strings in the verified Codex profile.

    Codex displays structured JSON once, or each MCP text block. Its timing
    prefix and host framing are accounted through provider tokens separately.
    Unknown/non-text payloads are not silently treated as empty responses.
    """
    result = call.get('result')
    if not isinstance(result, dict):
        error = call.get('error')
        if call.get('status') == 'failed' and isinstance(error, dict) and isinstance(error.get('message'), str):
            return 'host_error', [error['message']]
        raise ValueError('tool call has no delivered result')
    structured = result.get('structured_content')
    if structured is not None:
        if not isinstance(structured, dict):
            raise ValueError('unverified structured result representation')
        return 'compact_json', [wire(structured)]
    content = result.get('content')
    if not isinstance(content, list) or not content or any(
            not isinstance(part, dict) or part.get('type') != 'text'
            or not isinstance(part.get('text'), str) for part in content):
        raise ValueError('unverified tool content representation')
    return 'text_blocks', [part['text'] for part in content]


def reconcile_deliveries(raw_trace: dict, calls: list[dict], events: list[dict]) -> dict[str, Any]:
    """Bind every model-visible response to its source ledger or host result.

    Valid read events keep their original schema and replay. An invalid attempt
    may be completely costed without acquiring a valid causal event identity.
    """
    failures, rows, delivered, seen = [], [], [], set()
    ledger = raw_trace.get('deliveries', [])
    by_attempt = {entry['attempt_id']: entry for entry in ledger}
    by_event = {entry['id']: entry for entry in events}
    expected_attempts = [f"{raw_trace['identity']['session_id']}/attempt/{i + 1}" for i in range(len(ledger))]
    if ([entry['attempt_id'] for entry in ledger] != expected_attempts
            or raw_trace.get('attempts') != len(ledger)):
        failures.append({'category': 'delivery_trace_mismatch', 'message': 'noncontiguous adapter attempt identities'})
    if any(type(entry.get('elapsed_ms')) not in (int, float)
           or not math.isfinite(entry['elapsed_ms']) or entry['elapsed_ms'] < 0 for entry in ledger):
        failures.append({'category': 'delivery_trace_mismatch', 'message': 'invalid adapter duration'})
    if len(by_attempt) != len(ledger):
        failures.append({'category': 'delivery_trace_mismatch', 'message': 'duplicate attempt identity'})
    for call in calls:
        row = {'item_id': call['id'], 'server': call.get('server'), 'tool': call.get('tool'),
               'status': call.get('status'), 'arguments': call.get('arguments'),
               'attempt_id': None, 'trace_event_id': None, 'source_bytes': 0}
        try:
            kind, texts = payload_texts(call)
            row.update(payload_format=kind, payload_texts=texts,
                       serialized_bytes=sum(len(text.encode('utf-8')) for text in texts))
        except ValueError as exc:
            row.update(payload_format='unknown', payload_texts=None, serialized_bytes=None)
            failures.append({'category': 'unaccounted_tool_output', 'item': call['id'], 'message': str(exc)})
            rows.append(row)
            continue
        server, tool = call.get('server'), call.get('tool')
        structured = (call.get('result') or {}).get('structured_content')
        if server == 'evaluation' and tool == 'read' and isinstance(structured, dict):
            attempt = structured.get('_evaluation', {}).get('attempt_id')
            entry = by_attempt.get(attempt)
            if entry is None or attempt in seen:
                failures.append({'category': 'delivery_trace_mismatch', 'item': call['id'],
                                 'message': 'missing or duplicate delivery attempt'})
            else:
                seen.add(attempt)
                row.update(attempt_id=attempt, trace_event_id=entry.get('trace_event_id'))
                arguments = call.get('arguments') or {}
                valid = (entry['response_json'] == texts[0]
                         and entry['serialized_bytes'] == row['serialized_bytes']
                         and entry['operation'] == arguments.get('operation')
                         and entry['arguments'] == arguments.get('parameters')
                         and all(entry[key] == arguments.get(key) for key in ('reason', 'detail', 'because')))
                if entry['status'] == 'recorded':
                    event = by_event.get(entry.get('trace_event_id'))
                    valid = valid and event is not None
                    if event:
                        valid = valid and all(entry[key] == event[key] for key in
                                              ('response_json', 'serialized_bytes', 'source_bytes', 'spans'))
                        valid = valid and (isinstance(entry['elapsed_ms'], (int, float))
                                           and math.isfinite(entry['elapsed_ms'])
                                           and entry['elapsed_ms'] >= event['elapsed_ms'])
                        valid = valid and structured['_evaluation'].get('event_id') == event['id']
                        row['source_bytes'] = event['source_bytes']
                        delivered.append(structured)
                elif entry['status'] == 'rejected':
                    valid = valid and (entry.get('trace_event_id') is None
                                       and structured['_evaluation'].get('event_id') is None
                                       and entry['source_bytes'] == 0 and entry['spans'] == []
                                       and isinstance(structured.get('error'), dict))
                else:
                    valid = False
                if not valid:
                    failures.append({'category': 'delivery_trace_mismatch', 'item': call['id'],
                                     'message': 'ledger, arguments or validated event differs from delivery'})
        elif tool in RESOURCE_HELPERS and server in {'codex', 'evaluation'}:
            # This launch profile configures only evaluation, with no resources.
            if call.get('status') == 'failed' or call.get('error'):
                failures.append({'category': 'tool_error', 'item': call['id']})
        elif server == 'evaluation' and tool == 'read' and call.get('status') == 'failed':
            # MCP schema validation can reject before Adapter.read is invoked.
            failures.append({'category': 'tool_error', 'item': call['id'],
                             'message': 'host rejected read before adapter delivery'})
        else:
            failures.append({'category': 'unaccounted_tool_output', 'item': call['id'],
                             'message': 'tool outside the verified evaluation surface'})
        rows.append(row)
    if seen != set(by_attempt):
        failures.append({'category': 'delivery_trace_mismatch', 'message': 'undelivered adapter ledger entries'})
    matched_events = {row['trace_event_id'] for row in rows if row['trace_event_id'] is not None}
    if matched_events != set(by_event):
        failures.append({'category': 'delivery_trace_mismatch', 'message': 'unreconciled validated read events'})
    complete = not any(f['category'] in {'unaccounted_tool_output', 'delivery_trace_mismatch'} for f in failures)
    recorded = sum(row['serialized_bytes'] or 0 for row in rows)
    return {'schema_version': 2, 'complete': complete, 'calls': rows,
            'tool_call_count': len(calls), 'recorded_payload_bytes': recorded,
            'complete_payload_bytes': recorded if complete else None,
            'source_bytes': sum(row['source_bytes'] for row in rows) if complete else None,
            'failures': failures, 'validated_results': delivered}
