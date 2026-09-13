"""Describe the frozen v3 A-only batch without making candidate gain claims."""
from __future__ import annotations

import argparse
import json
import math
import statistics
from collections import Counter
from pathlib import Path

from benchmarks.typescript_context_baseline import save
from benchmarks.typescript_context_corpus import load_corpus


def metric(values):
    known = [value for value in values if value is not None]
    complete = bool(values) and len(known) == len(values)
    return {'complete': complete, 'values': values,
            'sum': sum(known) if complete else None,
            'recorded_subtotal': sum(known),
            'median': statistics.median(known) if complete else None}


def source_occurrences(events):
    intervals = {}
    total = 0
    for event in events:
        for span in event['spans']:
            total += span['end_byte'] - span['start_byte']
            intervals.setdefault(span['file'], []).append((span['start_byte'], span['end_byte']))
    unique = 0
    for ranges in intervals.values():
        end = 0
        for left, right in sorted(ranges):
            unique += max(0, right - max(end, left))
            end = max(end, right)
    return {'recorded_source_bytes': total, 'unique_source_bytes': unique,
            'duplicate_source_bytes': total - unique}


def summarize(runs):
    return {
        'runs': len(runs),
        'answers_correct': sum(run['answer_correct'] for run in runs),
        'fully_successful': sum(run['task_correct'] for run in runs),
        'measurement_complete': sum(run['measurement_complete'] for run in runs),
        'outcomes': dict(Counter(run['outcome'] for run in runs)),
        'failure_runs': dict(Counter(category for run in runs for category in
                                    set(failure['category'] for failure in run['failures']))),
        'failure_events': dict(Counter(failure['category'] for run in runs for failure in run['failures'])),
        **{name: metric([run[name] for run in runs]) for name in
           ('read_count', 'validated_read_count', 'context_recall', 'serialized_tool_output_bytes',
            'source_bytes', 'unique_source_bytes', 'duplicate_source_bytes', 'recorded_payload_bytes',
            'input_tokens', 'cached_input_tokens', 'output_tokens', 'end_to_end_seconds', 'index_seconds')},
        'relationships': {name: sum(run['relationships'][name] for run in runs) for name in
                          ('required_semantic_dependencies_total', 'available_dependency_links_total',
                           'delivered_dependency_links_total', 'forbidden_proven_relationships')},
    }


def generate_report(output: Path, corpus_root: Path):
    corpus = load_corpus(corpus_root)
    if corpus['version'] != 'typescript-context-v3':
        raise ValueError('v3 corpus required')
    expected = {f"{case['id']}-r{rep}" for case in corpus['cases'] for rep in range(1, 4)}
    actual = {path.parent.name for path in output.glob('*/result.json')}
    if actual != expected:
        raise ValueError('report requires the exact complete planned batch')
    runs, per_task = [], []
    for case in corpus['cases']:
        task_runs = []
        for rep in range(1, 4):
            folder = output / f"{case['id']}-r{rep}"
            result = json.loads((folder / 'result.json').read_text())
            provenance = json.loads((folder / 'provenance.json').read_text())
            measurement, baseline = result['measurement'], result['baseline']
            if (result['identity']['task_id'], result['identity']['repetition']) != (case['id'], rep):
                raise ValueError('result identity does not match planned slot')
            run = {**measurement,
                   'group': case['group'], 'directory': folder.name,
                   'end_to_end_seconds': baseline['end_to_end_seconds'],
                   'index_seconds': provenance['index_seconds'],
                   'failures': baseline['failures'], 'relationships': baseline['relationships'],
                   'recorded_payload_bytes': baseline['output_accounting']['recorded_payload_bytes'],
                   **source_occurrences(result['events']),
                   **{key: (measurement['provider_usage'] or {}).get(key) for key in
                      ('input_tokens', 'cached_input_tokens', 'output_tokens')}}
            task_runs.append(run)
        runs.extend(task_runs)
        per_task.append({'task_id': case['id'], 'group': case['group'], **summarize(task_runs)})
    maintained = [run for run in runs if run['group'] == 'maintained_task']
    tasks = [task for task in per_task if task['group'] == 'maintained_task']
    eligible = [task for task in tasks if task['fully_successful'] == 3]
    denominator = sum(task['read_count']['median'] for task in eligible)
    latency = sorted(run['end_to_end_seconds'] for run in maintained)
    summary = {
        'schema_version': 3, 'arm': 'A', 'planned_runs': 51, 'recorded_runs': len(runs),
        'complete_batch': len(runs) == 51, 'method': 'all_observed_tool_calls',
        'overall': summarize(runs),
        'groups': {group: summarize([run for run in runs if run['group'] == group])
                   for group in sorted({run['group'] for run in runs})},
        'per_task': per_task, 'runs': runs,
        'maintained_latency_p95_seconds': latency[math.ceil(.95 * len(latency)) - 1],
        'baseline_eligibility': {
            'fully_successful_maintained_tasks': [task['task_id'] for task in eligible],
            'eligible_task_count': len(eligible),
            'sum_of_eligible_median_calls': denominator,
            'positive_measured_denominator': len(eligible) >= 2 and denominator > 0,
            'meaning': 'Observed work, including planned work. This does not identify avoidable calls or prove a candidate can reduce them. Future matched comparisons must rerun A.'},
        'meaning': 'Descriptive baseline only. V1/v2 use different protocols and are not paired comparators. No B or C implementation or improvement is measured.',
    }
    save(output / 'report-summary.json', summary)
    lines = ['# V3 observed-call baseline', '', summary['meaning'], '',
             f"Answers correct: {summary['overall']['answers_correct']}/51. Full passes: {summary['overall']['fully_successful']}/51. Complete measurement: {summary['overall']['measurement_complete']}/51.", '',
             '| Maintained task | Full passes | Calls, median | Source recall, median | Output bytes, median | Gross input, median |',
             '|---|---:|---:|---:|---:|---:|']
    for task in tasks:
        lines.append(f"| {task['task_id']} | {task['fully_successful']}/3 | {task['read_count']['median']} | {task['context_recall']['median']} | {task['serialized_tool_output_bytes']['median']} | {task['input_tokens']['median']} |")
    lines.extend(['', f"Maintained p95 latency (all nine attempts): {summary['maintained_latency_p95_seconds']:.3f} seconds.", '',
                  f"Fully successful maintained tasks: {len(eligible)}/3; sum of their median calls: {denominator}.",
                  summary['baseline_eligibility']['meaning'], '',
                  'All errors and failed attempts retain their costs. Reported provider input is gross; cached input is a subset. Source estimates are separate from provider tokens. Relationship negatives cover only the authored forbidden relationships.', '',
                  '## All planned attempts', '',
                  '| Attempt | Answer | Full pass | Accounting | Calls | Output bytes | Source recall | Outcome |',
                  '|---|---|---|---|---:|---:|---:|---|'])
    for run in runs:
        lines.append(f"| {run['directory']} | {run['answer_correct']} | {run['task_correct']} | {run['measurement_complete']} | {run['read_count']} | {run['serialized_tool_output_bytes']} | {run['context_recall']:.3f} | {run['outcome']} |")
    (output / 'report.md').write_text('\n'.join(lines) + '\n')
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--corpus-root', type=Path, required=True)
    args = parser.parse_args()
    result = generate_report(args.output.resolve(), args.corpus_root.resolve())
    print(json.dumps({'recorded_runs': result['recorded_runs'], 'full_passes': result['overall']['fully_successful'],
                      'measurement_complete': result['overall']['measurement_complete'],
                      'baseline_eligibility': result['baseline_eligibility']}))


if __name__ == '__main__':
    main()
