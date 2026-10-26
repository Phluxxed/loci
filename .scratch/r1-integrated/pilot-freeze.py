"""Capture actual tool catalogs/settings and freeze before any scored invocation."""
import asyncio
import argparse
import json
from importlib.metadata import version
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import tomllib

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from benchmarks.complete_work import r0, r1
from benchmarks.complete_work.evaluate import write_json

root=Path(__file__).resolve().parent/'pilot'
repo=Path(__file__).resolve().parents[2]
python=Path('/Users/brummerv/phluxxed/loci/.venv/bin/python')
config=Path('/Users/brummerv/.codex/config.toml')
settings=tomllib.loads(config.read_text())
assert settings.get('model_provider','openai')=='openai'
assert not settings.get('model_providers',{}).get('openai',{}).get('base_url')
rollout=Path('/Users/brummerv/.codex/sessions/2026/10/26/rollout-2026-10-26T14-18-06-01a1766e-0e48-77d3-8e31-ec1e54a22527.jsonl')
protection=None
for line in rollout.read_text().splitlines():
    row=json.loads(line)
    if row.get('type')=='turn_context':
        protection={field:row['payload'].get(field) for field in r0.PROTECTION_FIELDS}
assert protection is not None

async def catalog(condition, env):
    with tempfile.TemporaryDirectory(prefix='loci-r1-catalog-') as directory:
        actual={**os.environ,**{key:value.replace('{store}',directory+'/store') for key,value in env.items()}}
        params=StdioServerParameters(command=str(python),args=['-m','loci.mcp_server' if condition=='eager' else 'loci.integrated_mcp'],env=actual)
        async with stdio_client(params) as (read,write):
            async with ClientSession(read,write) as session:
                await session.initialize()
                tools=await session.list_tools()
                return [tool.model_dump(mode='json',by_alias=True,exclude_none=True) for tool in tools.tools]

async def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--name',default='frozen')
    args=parser.parse_args()
    conditions={'native':{'tools':[],'catalog':[],'implementation_files':{}}}
    for name in ['path-only','integrated','eager']:
        source=root/'eager-src' if name=='eager' else repo/'src'
        env={'PYTHONPATH':str(source),'LOCI_BASE_DIR':'{store}','LOCI_STORE_NAMESPACE':'r1-pilot',
             'LOCI_MCP_STARTUP_TRACE':'{store}/startup.jsonl',
             'LOCI_R1_STORE':'{store}','LOCI_R1_SOURCE_ONLY':'1' if name=='path-only' else '0'}
        tools=await catalog(name,env)
        expected=['loci_read','loci_retrieve']+(['loci_proof','loci_semantic'] if name=='integrated' else [])
        assert sorted(t['name'] for t in tools)==sorted(expected),name
        conditions[name]={'command':str(python),'args':['-m','loci.mcp_server' if name=='eager' else 'loci.integrated_mcp'],
                          'env':env,'tools':sorted(expected),'catalog':tools,
                          'implementation_files':{str(p):r0.digest(p) for p in sorted(source.rglob('*.py'))}}
    host=Path(shutil.which('codex')).resolve()
    host_tools=json.loads(subprocess.check_output([str(host),'mcp','list','--json']))
    # No credential material or arbitrary environment contents are retained.
    tools=[{'name':s['name'],'enabled':s['enabled'],'transport':s['transport']['type'],
            'config_identity':r1.identity(s)} for s in host_tools]
    extra_paths=[Path('/Users/brummerv/.codex/hooks.json'),
                 Path('/Users/brummerv/.codex/hooks/loci-session-start.sh'),
                 Path('/Users/brummerv/.codex/hooks/ambient-mcp-session-start.sh'),
                 Path('/Users/brummerv/loci/.shared/loci-session-start-core.sh'),
                 Path('/Users/brummerv/.codex/AGENTS.md'),repo/'AGENTS.md',
                 Path('/Users/brummerv/.codex/skills/loci/SKILL.md')]
    plan={'tasks':json.loads((root/'task-plan.json').read_text()),'model':'gpt-6.1-sol','effort':'high',
          'native_config':str(config),'native_protection':protection,'conditions':conditions,
          'timeout_seconds':600,
          'host':{'executable':str(host),'sha256':r0.digest(host),'version':subprocess.check_output([str(host),'--version'],text=True).strip(),
                  'auth':'existing ChatGPT subscription; forced_login_method=chatgpt; model_provider=openai; API env removed',
                  'non_loci_mcp_configuration':tools,'native_tools':'unchanged codex exec defaults and loaded configuration; no disabled native tools',
                  'startup_context_files':{str(p):r0.digest(p) for p in extra_paths},
                  'orchestration_files':{str(p):r0.digest(p) for p in [repo/'benchmarks/complete_work'/name for name in ['r0.py','r1.py','accounting.py','evaluate.py']]+[Path(__file__).resolve(),Path(__file__).resolve().parent/'pilot-execute.py']},
                  'installed_runtime':{name:version(name) for name in ['mcp','tree-sitter-language-pack','pathspec','pydantic']},
                  'startup_indexing':'run exported copies outside Git; unchanged Loci hook exits before list/index; shared ambient Loci hints remain',
                  'docs':['https://learn.chatgpt.com/docs/non-interactive-mode','https://learn.chatgpt.com/docs/auth']}}
    write_json(root/'plan.json',plan)
    frozen=r1.freeze(root/'plan.json',root/args.name)
    print(json.dumps({'freeze_sha256':frozen['freeze_sha256'],'schedule':len(frozen['schedule']),'tools':{n:c['tools'] for n,c in conditions.items()}}))

asyncio.run(main())
