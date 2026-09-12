"""Recompute the routing comparison from retained host events.

The routing comparison keeps the immutable v1 delivery trace and v2
relationship scorer, then adds an independently checked routing identity and
the observed routing summary. Replay never calls a provider and never edits a
retained attempt.
"""
from __future__ import annotations

import argparse
import json
from collections.abc import Mapping
from pathlib import Path
import tempfile
from typing import Any

from benchmarks.typescript_context_adapter import wire
from benchmarks.typescript_context_routing_v2 import POLICY_PATH, VERSION, build_prompt, prompt_manifest
from benchmarks.typescript_context_routing_v2_run import (
    COMPARISON, COMPARISON_ROOT, CORPUS_ROOT, TOOLS_MODULE, save, sha, validate_freeze,
)
from benchmarks.typescript_context_corpus import _isolated_store, load_controls, load_corpus, materialize_snapshot
from benchmarks.typescript_context_explore_transport import HELPERS, tool_names
from benchmarks.typescript_context_routing_v2_observed import (
    PROTOCOL as OBSERVED_PROTOCOL,
    RAW_PROTOCOL,
    measure,
)


MEASUREMENT_PROTOCOL = VERSION
PROTOCOL = VERSION
EXPECTED_RUNS = 102


def _validate_current_protocol(result: Mapping[str, Any], raw: Mapping[str, Any]) -> None:
    """Keep the routing-v2 result envelope over the historical raw trace."""

    if OBSERVED_PROTOCOL != VERSION:
        raise ValueError("routing observer is not owned by the current protocol")
    if result.get("protocol") != VERSION:
        raise ValueError("measurement protocol is not typescript-context-routing-v2")
    if raw.get("protocol") not in {None, RAW_PROTOCOL}:
        raise ValueError("raw Explore trace uses an incompatible protocol")


def _validate_provenance(
    result: Mapping[str, Any],
    provenance: Mapping[str, Any],
    raw: Mapping[str, Any],
    run: Mapping[str, Any],
    plan: Mapping[str, Any],
    corpus: Mapping[str, Any],
    freeze: Mapping[str, Any],
    folder: Path,
) -> None:
    """Check that retained source and routing identity belong to this v2 run."""

    if result.get("provenance") != dict(provenance):
        raise ValueError("result provenance differs from provenance.json")
    if result.get("attempt_id") != plan["attempt_id"] or result.get("arm") != plan["arm"]:
        raise ValueError("result differs from planned attempt")
    if provenance.get("attempt_id") != plan["attempt_id"]:
        raise ValueError("provenance attempt identity differs from plan")
    if raw.get("identity") != result.get("identity"):
        raise ValueError("trace identity differs from result identity")
    expected_engine = {
        key: freeze["engine"][key]
        for key in ("commit", "source_tree", "extractor_version")
    }
    source = provenance.get("source")
    root = Path(str(corpus["_root"]))
    expected_snapshot = corpus["snapshots"][plan["snapshot"]]["files"]
    if (
        not isinstance(source, Mapping)
        or source.get("engine") != expected_engine
        or source.get("freeze_json_sha256") != freeze.get("freeze_json_sha256")
        or provenance.get("snapshot_files") != expected_snapshot
        or provenance.get("corpus_sha256") != sha((root / "corpus.json").read_bytes())
        or provenance.get("controls_sha256") != sha((root / "comparison-controls.json").read_bytes())
        or provenance.get("adapter_module") != TOOLS_MODULE
    ):
        raise ValueError("attempt source provenance differs from the frozen inputs")
    routing = provenance.get("routing")
    if (
        not isinstance(routing, Mapping)
        or routing.get("version") != VERSION
        or routing.get("condition") != plan["arm"]
        or routing.get("capability_arm") != "B"
    ):
        raise ValueError("provenance routing identity is not current routing-v2")
    if not isinstance(result.get("routing"), Mapping):
        raise ValueError("result routing observations are missing")
    expected_identity = {
        "task_id": plan["case_id"],
        "repetition": plan["repetition"],
        "arm": plan["arm"],
    }
    identity = result.get("identity")
    if not isinstance(identity, Mapping) or any(
        identity.get(key) != value for key, value in expected_identity.items()
    ):
        raise ValueError("trace, result and plan identities disagree")
    if run.get("attempt_id") != plan["attempt_id"] or run.get("case_id") != plan["case_id"]:
        raise ValueError("run identity differs from planned attempt")
    if run.get("arm") != plan["arm"] or run.get("repetition") != plan["repetition"]:
        raise ValueError("run identity differs from planned attempt")
    if provenance.get("snapshot") != plan["snapshot"]:
        raise ValueError("provenance snapshot differs from planned attempt")
    if provenance.get("case_id") != plan["case_id"]:
        raise ValueError("provenance case differs from planned attempt")
    if provenance.get("repetition") != plan["repetition"] or provenance.get("arm") != plan["arm"]:
        raise ValueError("provenance identity differs from planned attempt")
    trace_path = provenance.get("trace_path")
    if trace_path is not None and Path(str(trace_path)).name != "adapter-trace.json":
        raise ValueError("provenance trace path is not the retained adapter trace")


def _schema_hash(freeze: Mapping[str, Any], arm: str) -> str:
    value = freeze["canonical_tool_schemas_sha256"]
    if isinstance(value, Mapping):
        value = value[arm]
    if not isinstance(value, str):
        raise ValueError("freeze has no canonical tool schema hash")
    return value


def validate_policy_contract(corpus: dict[str, Any], controls: dict[str, Any], freeze: dict[str, Any]) -> dict[str, Any]:
    """Validate the committed routing policy and its prompt manifest."""

    manifest_path = COMPARISON_ROOT / "prompt-manifest.json"
    if not POLICY_PATH.is_file() or not manifest_path.is_file():
        raise ValueError("routing policy and prompt manifest are required")
    policy_bytes = POLICY_PATH.read_bytes()
    manifest_bytes = manifest_path.read_bytes()
    if (freeze.get("policy_sha256") != sha(policy_bytes)
            or freeze.get("prompt_manifest_sha256") != sha(manifest_bytes)):
        raise ValueError("routing policy or prompt manifest hash differs from the freeze")
    try:
        declared = json.loads(manifest_bytes)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("routing prompt manifest is not valid JSON") from exc
    expected = prompt_manifest(corpus, controls)
    if declared != expected:
        raise ValueError("effective routing prompts differ from the published manifest")
    if (declared.get("version") != VERSION
            or declared.get("candidate_prefix_utf8_bytes") != 1155
            or declared.get("tool_arm") != {"A": "B", "B": "B"}):
        raise ValueError("routing prompt manifest has incompatible policy settings")
    if len(policy_bytes) != 1154:
        raise ValueError("routing policy byte length differs from the frozen declaration")
    return declared


def expected_routing_identity(
    corpus: dict[str, Any],
    controls: dict[str, Any],
    case_id: str,
    arm: str,
    freeze: dict[str, Any],
) -> dict[str, Any]:
    """Build the independently expected provenance routing identity."""

    manifest_path = COMPARISON_ROOT / "prompt-manifest.json"
    if (not POLICY_PATH.is_file() or not manifest_path.is_file()
            or sha(POLICY_PATH.read_bytes()) != freeze.get("policy_sha256")
            or sha(manifest_path.read_bytes()) != freeze.get("prompt_manifest_sha256")):
        raise ValueError("routing policy or prompt manifest differs from the freeze")
    base_prompt = build_prompt(corpus, controls, case_id, "A")
    effective_prompt = build_prompt(corpus, controls, case_id, arm)
    prefix = len(effective_prompt.encode("utf-8")) - len(base_prompt.encode("utf-8"))
    expected_prefix = 1155 if arm == "B" else 0
    if prefix != expected_prefix:
        raise ValueError("effective routing prompt has the wrong policy prefix")
    return {
        "version": VERSION,
        "condition": arm,
        "policy_sha256": freeze["policy_sha256"] if arm == "B" else None,
        "base_prompt_sha256": sha(base_prompt.encode("utf-8")),
        "effective_prompt_sha256": sha(effective_prompt.encode("utf-8")),
        "candidate_prefix_utf8_bytes": expected_prefix,
        "capability_arm": "B",
    }


def verify_request(audit, provenance, prompt, arm, schema_hash):
    request = audit['request']
    visible_tools = [(namespace['name'], tool['name']) for item in request['input']
                     if item['type'] == 'additional_tools' for namespace in item['tools']
                     for tool in namespace['tools']]
    # Both routing conditions expose the same B-capability schema.  The
    # condition is retained in the trace identity, while capability is a
    # shared transport control.
    expected = {('mcp__evaluation', name) for name in tool_names('B')} | HELPERS
    if len(visible_tools) != len(expected) or set(visible_tools) != expected:
        raise ValueError('request exposed a different tool set')
    if request['model'] != 'gpt-5.6-luna' or request['reasoning']['effort'] != 'high':
        raise ValueError('request model or reasoning effort changed')
    if request['input'][-1].get('content') != [{'type': 'input_text', 'text': prompt}]:
        raise ValueError('retained request prompt differs from the frozen task')
    for item in request['input']:
        for part in item.get('content', []):
            if any(marker in part.get('text', '') for marker in ('# AGENTS.md instructions',
                    '## Brain Context', 'Anvil Continuity Frame', '<skills_instructions>', 'LOCI_ADAPTER_READY')):
                raise ValueError('ambient context appears in retained request')
    actual = sha(wire({'tools': [item['tools'] for item in request['input']
                                 if item['type'] == 'additional_tools']}).encode())
    if not (actual == schema_hash == audit['canonical_tool_schemas_sha256']
            == provenance['canonical_tool_schemas_sha256']):
        raise ValueError('retained request schemas differ from frozen transport proof')
    if sha(wire(request).encode()) != audit['request_sha256']:
        raise ValueError('retained request digest mismatch')
    if (sha(prompt.encode()) != provenance['prompt_sha256']
            or sha(wire(provenance['config']).encode()) != provenance['config_sha256']):
        raise ValueError('provenance prompt/config digest mismatch')


def replay_attempt(folder, corpus, case, plan, freeze, index):
    result = json.loads((folder / 'result.json').read_text())
    run = json.loads((folder / 'run.json').read_text())
    provenance = json.loads((folder / 'provenance.json').read_text())
    raw = json.loads((folder / 'adapter-trace.json').read_text())
    if raw != json.loads((folder / 'adapter-trace-copy.json').read_text()):
        raise ValueError('retained trace copies differ')
    _validate_current_protocol(result, raw)
    identity = result['identity']
    if (identity['task_id'], identity['repetition'], identity['arm']) != (
            case['id'], plan['repetition'], plan['arm']):
        raise ValueError('result differs from planned identity')
    if (raw['identity'] != identity or run['session_id'] != identity['session_id']
            or result['attempt_id'] != plan['attempt_id'] or run['attempt_id'] != plan['attempt_id']
            or result['arm'] != plan['arm'] or provenance['snapshot'] != plan['snapshot']
            or (run['case_id'], run['arm'], run['repetition']) != (
                plan['case_id'], plan['arm'], plan['repetition'])
            or (provenance['case_id'], provenance['arm'], provenance['repetition'], provenance['attempt_id']) != (
                plan['case_id'], plan['arm'], plan['repetition'], plan['attempt_id'])
            or result['provenance'] != provenance):
        raise ValueError('trace, run, result and provenance identities disagree')
    controls = load_controls(corpus)
    validate_policy_contract(corpus, controls, freeze)
    expected_routing = expected_routing_identity(
        corpus, controls, case['id'], plan['arm'], freeze,
    )
    if provenance.get('routing') != expected_routing:
        raise ValueError('provenance routing identity differs from the frozen policy')
    _validate_provenance(result, provenance, raw, run, plan, corpus, freeze, folder)
    prompt = build_prompt(corpus, controls, case['id'], plan['arm'])
    if (folder / 'request-audit.json').exists():
        verify_request(json.loads((folder / 'request-audit.json').read_text()), provenance,
                       prompt, plan['arm'], _schema_hash(freeze, plan['arm']))
    elif not result.get('runner_failures'):
        raise ValueError('successful attempt has no audited request')
    events = [json.loads(line) for line in (folder / 'events.jsonl').read_text().splitlines() if line.strip()]
    if events != json.loads((folder / 'events.json').read_text()):
        raise ValueError('raw host events differ from retained parsed events')
    run = {**run, 'trace_path': str(folder / 'adapter-trace.json')}
    baseline = result['baseline']
    if 'relationships' not in baseline:
        raise ValueError('relationship score is unavailable; full replay cannot be certified')
    recomputed = measure(corpus, case, run, events, baseline['actual_process_seconds'],
                         baseline['exit_code'], result['measurement']['outcome'] == 'timeout',
                         index)
    if not result.get('protocol') == recomputed.get('protocol') == MEASUREMENT_PROTOCOL:
        raise ValueError('measurement protocol differs from typescript-context-routing-v2')
    failures = result.get('runner_failures', [])
    if failures:
        recomputed['measurement']['measurement_complete'] = False
        recomputed['measurement']['task_correct'] = False
        recomputed['baseline']['tool_delivery_verified'] = False
        for failure in failures:
            if failure not in recomputed['baseline']['failures']:
                recomputed['baseline']['failures'].append(failure)
    if result.get('routing') != recomputed.get('routing'):
        raise ValueError('independent replay differs in routing')
    for name in ('identity', 'events', 'measurement'):
        if result[name] != recomputed[name]:
            raise ValueError('independent replay differs in ' + name)
    for name, value in recomputed['baseline'].items():
        if baseline.get(name) != value:
            raise ValueError('independent replay differs in baseline.' + name)
    return {'attempt_id': plan['attempt_id'], 'verified': True,
            'measurement_complete': recomputed['measurement'].get('measurement_complete'),
            'task_correct': recomputed['measurement']['task_correct']}


def verify(output):
    from loci import service

    output = Path(output).resolve()
    corpus = load_corpus(CORPUS_ROOT)
    freeze = validate_freeze(COMPARISON_ROOT / 'freeze.json')
    controls = load_controls(corpus)
    validate_policy_contract(corpus, controls, freeze)
    manifest = json.loads((output / 'manifest.json').read_text())
    if (manifest['comparison'] != COMPARISON
            or manifest.get('protocol', manifest.get('comparison')) != VERSION
            or manifest['plan'] != freeze['plan']
            or manifest['freeze'] != freeze or manifest['planned_runs'] != EXPECTED_RUNS):
        raise ValueError('batch manifest differs from the frozen trial')
    expected = {plan['attempt_id'] for plan in freeze['plan']}
    if {path.parent.name for path in output.glob('*/result.json')} != expected:
        raise ValueError('replay requires every one of the exact 102 attempts')
    if sha((output / 'model-catalog.json').read_bytes()) != manifest['catalog_sha256']:
        raise ValueError('retained model catalog changed')
    cases = {case['id']: case for case in corpus['cases']}
    rows, failures = [], []
    with tempfile.TemporaryDirectory(prefix='loci-explore-replay-') as temporary:
        temp = Path(temporary)
        indexes = {}
        for snapshot in corpus['snapshots']:
            repo, store = temp / snapshot, temp / ('store-' + snapshot)
            materialize_snapshot(corpus, snapshot, repo)
            with _isolated_store(store):
                service.index_repo(repo, incremental=False)
                indexes[snapshot] = service.get_store().load(repo.resolve())
        for plan in freeze['plan']:
            try:
                row = replay_attempt(output / plan['attempt_id'], corpus, cases[plan['case_id']],
                                     plan, freeze, indexes[plan['snapshot']])
                rows.append(row)
            except (KeyError, TypeError, ValueError, OSError) as exc:
                failures.append({'attempt_id': plan['attempt_id'], 'error': str(exc)})
    inventory = {str(path.relative_to(output)): sha(path.read_bytes()) for path in output.rglob('*')
                 if path.is_file() and path.name not in {'replay-verification.json', 'replay-verification.md'}}
    report = {'schema_version': 1, 'comparison': COMPARISON, 'protocol': VERSION,
        'expected_runs': EXPECTED_RUNS,
        'verified_runs': len(rows), 'complete': len(rows) == EXPECTED_RUNS and not failures,
        'meaning': 'Fresh frozen-engine indexes; raw host events, exact delivered source, routing observations, relationship proofs and every measured score recomputed without provider calls.',
        'failures': failures, 'attempts': rows, 'artifact_sha256': inventory}
    save(output / 'replay-verification.json', report)
    if not report['complete']:
        raise ValueError('replay failed: ' + json.dumps(failures[:3]))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = verify(args.output)
    print(json.dumps({'verified_runs': report['verified_runs'], 'complete': report['complete']}))


if __name__ == '__main__':
    main()
