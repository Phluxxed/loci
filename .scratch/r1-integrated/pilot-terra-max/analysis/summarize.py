"""Summarize retained R0.1 accounting and raw native tool receipts; launches nothing."""
import collections
import csv
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
ANALYSIS = ROOT / 'analysis'

def read(path):
    return json.loads(path.read_text())

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def write(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n')

index = read(ROOT / 'execution-index.json')
frozen = read(ROOT / 'freeze.json')
rows, commands, attribution = [], [], []
for entry in index['runs']:
    evaluation = entry['evaluation']
    accounting = evaluation['accounting']
    archive = Path(entry['archive'])
    trace = archive / 'observer/qualification/native-rollout.jsonl'
    native_rows = [json.loads(line) for line in trace.open()]
    calls, outputs = [], []
    for ordinal, row in enumerate(native_rows, 1):
        payload = row.get('payload', {})
        if row.get('type') != 'response_item':
            continue
        if payload.get('type') in ('function_call', 'custom_tool_call'):
            calls.append({'row': ordinal, 'call_id': payload.get('call_id'),
                          'name': payload.get('name'),
                          'input': payload.get('input', payload.get('arguments', ''))})
        elif payload.get('type') in ('function_call_output', 'custom_tool_call_output'):
            output = payload.get('output')
            if isinstance(output, str):
                text = output
            elif isinstance(output, list) and all(isinstance(x, dict) and isinstance(x.get('text'), str) for x in output):
                text = ''.join(x['text'] for x in output)
            else:
                raise ValueError(f'unknown tool output shape: {trace}:{ordinal}')
            outputs.append({'row': ordinal, 'call_id': payload.get('call_id'),
                            'text_bytes': len(text.encode('utf-8'))})
    patterns = {
        'loci_invocation': r'(?:tools\.|functions\.|mcp__)[A-Za-z0-9_]*loci[A-Za-z0-9_]*\s*\(',
        'tool_discovery': r'ALL_TOOLS|tool_search|search_tools|list_tools',
        'local_loci_import': r'from loci|import loci|loci\.integrated|loci\.mcp_server|loci_semantic\s*\(|loci_proof\s*\(',
    }
    matches = {key: [{'row': call['row'], 'call_id': call['call_id'],
                      'matches': re.findall(pattern, call['input'])}
                     for call in calls if re.search(pattern, call['input'])]
               for key, pattern in patterns.items()}
    # Preserve calls for audit. Regex findings alone do not prove reliance or exhaustive absence.
    attribution.append({'run_id': entry['run_id'], 'trace_sha256': digest(trace),
                        'calls': calls, 'tool_outputs': outputs, 'matches': matches,
                        'additional_tools_loci_mentions': sum(
                            len(re.findall('loci', json.dumps(row['payload'])))
                            for row in native_rows if row.get('type') == 'response_item'
                            and row.get('payload', {}).get('type') == 'additional_tools')})
    shell = [item for stage in accounting['stages'] for item in stage.get('items', [])
             if item.get('type') == 'commandExecution']
    for item in shell:
        commands.append({'run_id': entry['run_id'], 'id': item['id'],
                         'command': item.get('command'), 'cwd': item.get('cwd'),
                         'exit_code': item.get('exitCode', item.get('exit_code')),
                         'command_output_text_bytes': len(item.get('aggregated_output', '').encode('utf-8')),
                         'capture_completed': item.get('capture_completed')})
    operations = accounting['operation_totals']
    assert len(shell) == operations['shell_calls']
    row = {
        'run_id': entry['run_id'],
        'task': next(x['task'] for x in frozen['schedule'] if x['run_id'] == entry['run_id']),
        'condition': evaluation['condition'], 'correct': evaluation['correct'],
        'elapsed_ms': entry['execution']['elapsed_ms'],
        'native_turn_elapsed_ms': sum(s['elapsed_ms'] for s in accounting['stages']),
        **accounting['usage'], **operations,
        'outer_tool_calls': len(calls),
        'completed_response_lower_bound': sum(s['observed_completed_model_requests'] for s in accounting['stages']),
        'observed_tool_response_text_bytes': sum(x['text_bytes'] for x in outputs),
        'command_output_text_bytes': sum(len(x.get('aggregated_output', '').encode('utf-8')) for x in shell),
        'tool_discovery_calls_observed': len(matches['tool_discovery']),
        'loci_calls_observed': operations['mcp_calls'],
        'semantic_requests_observed': 0 if not any(matches.values()) and operations['mcp_calls'] == 0 else None,
        'proof_requests_observed': 0 if not any(matches.values()) and operations['mcp_calls'] == 0 else None,
        'loci_source_bytes_observed': 0 if not any(matches.values()) and operations['mcp_calls'] == 0 else None,
        'native_source_only_bytes': None,
        'qualification': evaluation['qualification_status'],
        'usage_status': accounting['usage_status'],
        'unexpected_changes': evaluation['unexpected_changes'],
        'frozen_oracle_passed': evaluation['oracle_stderr'] == '',
        'thread_id': evaluation['thread_id'],
    }
    rows.append(row)
summary = {}
for condition in ('native', 'path-only', 'integrated', 'eager'):
    subset = [r for r in rows if r['condition'] == condition]
    numeric = ['elapsed_ms', 'inputTokens', 'cachedInputTokens', 'uncachedInputTokens',
               'outputTokens', 'reasoningOutputTokens', 'totalTokens', 'outer_tool_calls',
               'shell_calls', 'file_change_calls', 'failed_shell_calls', 'mcp_calls',
               'observed_tool_response_text_bytes', 'command_output_text_bytes']
    summary[condition] = {'correct': sum(r['correct'] for r in subset), 'attempted': len(subset),
                          **{key: sum(r[key] for r in subset) for key in numeric}}
limitations = [
    'Official correctness is frozen exact-answer equality plus file allowlist; unchanged.',
    'All counts concern observed completed native traces; invisible retries and complete billing remain unknown.',
    'totalTokens = inputTokens + outputTokens; cached input is a subset of input, reasoning is a subset of output.',
    'Operation elapsed is original native subprocess launch-to-exit; includes startup/task execution, excludes offline grading and replay. Retrospective total wall time through grading is unknown.',
    'Tool-response text bytes sum raw recorded output text parts, excluding metadata and transport wrappers. They mix source, command metadata and checks and are not unique context or source-only bytes.',
    'Shell-output bytes and tool-response bytes overlap and must not be added. Parallel subprocess durations must not be added to elapsed.',
    'Zero observed semantic/proof requests is supported by native operation counts plus retained raw call bodies; runtime deferred catalogs were not queried and tool availability/discoverability remains unverified.',
    'Four eager startup receipts show store binding/stdio entry only; they do not demonstrate graph construction or tool use.',
    'No causal cross-condition benefit can be attributed to unused Loci capabilities; four constructed tasks give no population claim.',
    'Global configuration differed from older Sol freeze; do not pool those attempts or infer model effects.',
    'Acquisition-only time, exact native source bytes, exhaustive repeated reads and invisible model requests remain unknown; command index preserves reviewable evidence.',
]
write(ANALYSIS / 'metrics.json', {'schema_version': 1, 'freeze_sha256': frozen['freeze_sha256'],
      'execution_index_sha256': digest(ROOT / 'execution-index.json'), 'rows': rows,
      'condition_totals': summary, 'limitations': limitations})
write(ANALYSIS / 'tool-attribution.json', attribution)
write(ANALYSIS / 'command-index.json', commands)
with (ANALYSIS / 'metrics.csv').open('w') as stream:
    writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
print(json.dumps({'status': 'summarized', 'runs': len(rows), 'totals': summary,
                  'mcp_calls_observed': sum(r['mcp_calls'] for r in rows)}))
