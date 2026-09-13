"""One actual Codex-host exercise of the normal W2.4 MCP surface.

Uses frozen fixture source, isolated MCP storage and an ephemeral restricted
host. This is integration acceptance, not the W2.5 agent comparison.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

from benchmarks.typescript_context_baseline import DISABLED_FEATURES, launch_args, prepare_catalog
from tests.reproductions.typescript_context_gaps import fixtures

ROOT = Path(__file__).resolve().parents[3]


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def exercise(output: Path) -> dict:
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='loci-w24-host-') as directory:
        temp = Path(directory)
        repo = temp / 'repo'
        repo.mkdir()
        case = fixtures()['imported_interface']
        for name, source in case['files'].items():
            (repo / name).write_text(source, encoding='utf-8')
        catalog = prepare_catalog(temp, 'gpt-5.6-luna')
        config = {
            'project_doc_max_bytes': 0, 'web_search': 'disabled',
            'skills.include_instructions': False, 'developer_instructions': '',
            'model_reasoning_effort': 'high', 'model_catalog_json': str(catalog),
            'approval_policy': 'on-request', 'approvals_reviewer': 'auto_review',
            'include_collaboration_mode_instructions': False,
            'tools.update_plan.enabled': False, 'tools.experimental_request_user_input.enabled': False,
            'features.skip_host_skill_discovery': True,
            'mcp_servers.loci.command': sys.executable,
            'mcp_servers.loci.args': ['-m', 'loci.mcp_server'],
            'mcp_servers.loci.cwd': str(ROOT),
            'mcp_servers.loci.env': {'LOCI_BASE_DIR': str(temp / 'store'),
                'LOCI_STORE_NAMESPACE': 'w24-host-acceptance', 'PYTHONPATH': str(ROOT / 'src')},
            'mcp_servers.loci.required': True,
            'mcp_servers.loci.default_tools_approval_mode': 'auto',
            'mcp_servers.loci.tool_timeout_sec': 30,
            'mcp_servers.loci.enabled_tools': ['loci_explore', 'loci_get', 'loci_graph_references'],
            'tool_output_token_limit': 8192,
        }
        config.update({'features.' + feature: False for feature in DISABLED_FEATURES})
        prompt = (
            'Complete this assignment directly. Do not spawn other agents. '
            f'Use only the connected Loci tools on repo {repo}. '
            'This is a bounded navigation acceptance exercise. First call loci_explore '
            'with intent=locate and query=processOrder. Using its returned symbol ID, '
            'call loci_explore with intent=type_dependencies and query="processOrder input contract", '
            'max_output_bytes=4096 and max_evidence_bytes=1024. Inspect the delivered source and '
            'relationship proof. Then repeat that type request with max_evidence_bytes=0 to '
            'exercise an exhausted evidence budget. Report the input type and its fields, '
            'the proven relationship and its resolution, and what the two type responses report '
            'for status, omissions and output bytes. Stop after these three calls. '
            'Use no other repository or data source and make no edits.'
        )
        args = launch_args(repo, config, prompt)
        completed = subprocess.run(args, cwd=repo, env=os.environ.copy(), capture_output=True,
                                   text=True, timeout=150)
        events = [json.loads(line) for line in completed.stdout.splitlines() if line.startswith('{')]
        calls = [event['item'] for event in events if event.get('type') == 'item.completed'
                 and event.get('item', {}).get('type') == 'mcp_tool_call']
        messages = [event['item']['text'] for event in events if event.get('type') == 'item.completed'
                    and event.get('item', {}).get('type') == 'agent_message']
        record = {
            'work_id': 'W2.4.3', 'meaning': 'Actual host-mediated MCP integration, not comparative evaluation.',
            'host': subprocess.check_output(['codex', '--version'], text=True).strip(),
            'model': 'gpt-5.6-luna', 'reasoning_effort': 'high', 'fixture': 'imported_interface',
            'fixture_sha256': {name: sha(source.encode('utf-8')) for name, source in case['files'].items()},
            'source_sha256': {name: sha((ROOT / name).read_bytes()) for name in (
                'src/loci/exploration.py', 'src/loci/_exploration_output.py',
                'src/loci/service.py', 'src/loci/mcp_server.py', 'src/loci/mcp_output_models.py')},
            'model_catalog_sha256': sha(catalog.read_bytes()), 'prompt': prompt,
            'exit_code': completed.returncode, 'calls': calls, 'final_messages': messages,
            'stderr': completed.stderr,
            'events': events,
        }
        # Keep failed host evidence reviewable before asserting acceptance.
        output.write_text(json.dumps(record, ensure_ascii=False, indent=2).replace(str(temp), '<temporary-host-root>') + '\n')
        assert completed.returncode == 0, f'Codex host failed; inspect {output}'
        assert len(calls) == 3, f'Expected three actual MCP calls; inspect {output}'
        for call in calls:
            assert call['tool'] == 'loci_explore' and call['arguments']['repo'] == str(repo), call
            assert call.get('error') is None, call
        types = validate_results(calls)
        record['passed'] = True
        output.write_text(json.dumps(record, ensure_ascii=False, indent=2).replace(str(temp), '<temporary-host-root>') + '\n')
        return {'passed': True, 'calls': len(calls), 'type_output_bytes': types['usage']['output_bytes'],
                'type_evidence_bytes': types['usage']['evidence_bytes'], 'output': str(output)}


def validate_results(calls: list[dict]) -> dict:
    # Codex JSONL uses snake_case; the MCP wire result uses structuredContent.
    results = [call['result']['structured_content'] for call in calls]
    assert results[0]['intent'] == 'locate' and results[0]['items']
    types = results[1]
    assert {item['name'] for item in types['items']} == {'processOrder', 'Payload'}
    assert any('requestId: string' in source['content'] and 'amount: number' in source['content']
               for source in types['sources'])
    assert types['relationships'][0]['edge']['resolution'] == 'import-resolved'
    assert results[2]['status'] == 'empty' and not results[2]['sources']
    for result in results:
        wire = json.dumps({'content': [], 'structuredContent': result, 'isError': False},
                          ensure_ascii=False, separators=(',', ':')).encode('utf-8')
        assert len(wire) == result['usage']['output_bytes'] <= result['limits']['max_output_bytes']
        assert result['usage']['evidence_bytes'] <= result['limits']['max_evidence_bytes']
    return types

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(exercise(args.output.resolve())))


if __name__ == '__main__':
    main()
