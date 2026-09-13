"""W2.1.1: capture current TypeScript endpoints, relations and delivered evidence.

Run with the development worktree's Python; all fixture indexes live in a
temporary store. This is a reproduction packet, not the frozen agent eval.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import subprocess
import tempfile


PAYLOAD = "export interface Payload {\n  requestId: string;\n  amount: number;\n}\n"
CONSUMER = (
    'import type { Payload as ImportedPayload } from "./types.js";\n'
    'export function processOrder(value: ImportedPayload): string {\n'
    '  return value.requestId;\n}\n'
)


def fixtures() -> dict[str, dict]:
    return {
        "imported_interface": {
            "files": {"types.ts": PAYLOAD, "consumer.ts": CONSUMER},
            "anchor": "consumer.ts::processOrder#function",
            "query": "processOrder",
            "targets": ["types.ts::Payload#interface"],
        },
        "local_interface": {
            "files": {"consumer.ts": PAYLOAD +
                'export function processOrder(value: Payload): string {\n'
                '  return value.requestId;\n}\n'},
            "anchor": "consumer.ts::processOrder#function",
            "query": "processOrder",
            "targets": ["consumer.ts::Payload#interface"],
        },
        "local_alias_chain": {
            "files": {"consumer.ts": PAYLOAD +
                'export type First = Payload;\nexport type Second = First;\n'
                'export function processOrder(value: Second): string {\n'
                '  return value.requestId;\n}\n'},
            "anchor": "consumer.ts::processOrder#function",
            "query": "processOrder",
        },
        "imported_alias_chain": {
            "files": {"types.ts": PAYLOAD +
                'export type First = Payload;\nexport type Second = First;\n',
                "consumer.ts":
                'import type { Second } from "./types.js";\n'
                'export function processOrder(value: Second): string {\n'
                '  return value.requestId;\n}\n'},
            "anchor": "consumer.ts::processOrder#function",
            "query": "processOrder",
        },
        "named_type_reexport_chain": {
            "files": {"types.ts": PAYLOAD,
                "barrel.ts": 'export type { Payload as PublicPayload } from "./types.js";\n',
                "consumer.ts":
                'import type { PublicPayload as ImportedPayload } from "./barrel.js";\n'
                'export function processOrder(value: ImportedPayload): string {\n'
                '  return value.requestId;\n}\n'},
            "anchor": "consumer.ts::processOrder#function",
            "query": "processOrder",
            "targets": ["types.ts::Payload#interface"],
        },
        "local_heritage": {
            "files": {"consumer.ts":
                'interface Contract { requestId: string; }\n'
                'interface ChildContract extends Contract { amount: number; }\n'
                'class Base { requestId: string = "base"; }\n'
                'export class Processor extends Base implements Contract {\n'
                '  process(): string { return this.requestId; }\n}\n'},
            "anchor": "consumer.ts::Processor#class",
            "query": "Processor",
        },
        "imported_heritage": {
            "files": {"types.ts":
                'export interface Contract { requestId: string; }\n'
                'export class Base { requestId: string = "base"; }\n',
                "consumer.ts":
                'import { Base, type Contract } from "./types.js";\n'
                'export interface ChildContract extends Contract { amount: number; }\n'
                'export class Processor extends Base implements Contract {\n'
                '  process(): string { return this.requestId; }\n}\n'},
            "anchor": "consumer.ts::Processor#class",
            "query": "Processor",
        },
        "same_name_wrong_file": {
            "files": {"types.ts": PAYLOAD, "consumer.ts": CONSUMER,
                "wrong.ts": 'export interface Payload { unrelated: boolean; }\n'},
            "anchor": "consumer.ts::processOrder#function",
            "query": "processOrder",
            "targets": ["types.ts::Payload#interface"],
        },
        "ambiguous_star_exports": {
            "files": {"left.ts": PAYLOAD, "right.ts": PAYLOAD,
                "barrel.ts": 'export * from "./left.js";\nexport * from "./right.js";\n',
                "consumer.ts": CONSUMER.replace('./types.js', './barrel.js')},
            "anchor": "consumer.ts::processOrder#function",
            "query": "processOrder",
        },
        "generic_shadow": {
            "files": {"types.ts": PAYLOAD,
                "consumer.ts":
                'import type { Payload } from "./types.js";\n'
                'export function processOrder<Payload>(value: Payload): Payload {\n'
                '  return value;\n}\n'},
            "anchor": "consumer.ts::processOrder#function",
            "query": "processOrder",
        },
        "exported_arrow": {
            "files": {"number.ts": 'export const num = (v: unknown): number => Number(v);\n',
                "consumer.ts": 'import { num } from "./number.js";\n'
                'export function useNumber(): number { return num(1); }\n'},
            "anchor": "consumer.ts::useNumber#function", "query": "useNumber",
        },
        "default_identifier": {
            "files": {"number.ts": 'function num(v: unknown): number { return Number(v); }\nexport default num;\n',
                "consumer.ts": 'import num from "./number.js";\n'
                'export function useNumber(): number { return num(1); }\n'},
            "anchor": "consumer.ts::useNumber#function", "query": "useNumber",
        },
        "named_function_control": {
            "files": {"number.ts": 'export function num(v: unknown): number { return Number(v); }\n',
                "consumer.ts": 'import { num } from "./number.js";\n'
                'export function useNumber(): number { return num(1); }\n'},
            "anchor": "consumer.ts::useNumber#function", "query": "useNumber",
        },
        "inline_default_control": {
            "files": {"number.ts": 'export default function num(v: unknown): number { return Number(v); }\n',
                "consumer.ts": 'import num from "./number.js";\n'
                'export function useNumber(): number { return num(1); }\n'},
            "anchor": "consumer.ts::useNumber#function", "query": "useNumber",
        },
    }


def capture(repo: Path, base: Path, case: dict) -> dict:
    from loci import service
    from loci.storage.index_store import IndexStore

    repo.mkdir()
    for name, content in case["files"].items():
        (repo / name).write_text(content, encoding="utf-8")
    indexed = service.index_repo(repo, incremental=False)
    index = IndexStore(base_dir=base).load(repo.resolve())
    assert index is not None
    search = service.search_symbols_result(repo, case["query"], limit=5, ensure_fresh=True)
    assert case["anchor"] in {item["id"] for item in search["symbols"]}
    selected_source = service.get_symbols(repo, [case["anchor"]], ensure_fresh=True,
        selected_from_search_id=search["search_id"])
    exact_sources = service.get_symbols(repo,
        [item["id"] for item in index["symbols"] if item["kind"] != "file"],
        ensure_fresh=True)
    references = service.graph_references(repo, ensure_fresh=True)
    assert references["pagination"]["next_offset"] is None
    graph = index["graph"]
    retrieval = {}
    requests = {
        "inferred": None,
        "function_or_class_anchor": [case["anchor"]],
        "file_anchor": ["consumer.ts::__file__#file"],
    }
    if case.get("targets"):
        requests["explicit_file_to_type"] = ["consumer.ts::__file__#file", *case["targets"]]
    for label, seeds in requests.items():
        retrieval[label] = service.graph_retrieve(repo,
            f'What dependencies does {case["query"]} have?', seeds,
            max_hops=3, max_nodes=64, max_paths=8,
            max_evidence_bytes=32768, max_estimated_tokens=8192,
            ensure_fresh=True)
    retrieval["alternate_question_explicit_anchor"] = service.graph_retrieve(repo,
        f'What types does {case["query"]} depend on?', [case["anchor"]],
        ensure_fresh=True)
    if case.get("targets"):
        retrieval["explicit_symbol_to_type"] = service.graph_retrieve(repo,
            f'What types does {case["query"]} depend on?',
            [case["anchor"], *case["targets"]], ensure_fresh=True)
        retrieval["alternate_question_file_anchor"] = service.graph_retrieve(repo,
            f'What types does {case["query"]} depend on?',
            ["consumer.ts::__file__#file"], edge_types=["references_type"],
            ensure_fresh=True)
    return {
        "fixture": case,
        "indexed": indexed,
        "file_hashes": index["file_hashes"],
        "symbols": index["symbols"],
        "exact_sources": exact_sources,
        "exports": graph["exports"],
        "reference_output": references,
        "edges": graph["edges"],
        "search_output": search,
        "selected_get_output": selected_source,
        "graph_retrieve_output": retrieval,
    }


def normalize(value, temp: Path):
    if isinstance(value, str):
        return value.replace(str(temp), "<temporary-reproduction-root>")
    if isinstance(value, list):
        return [normalize(item, temp) for item in value]
    if isinstance(value, dict):
        return {key: normalize(item, temp) for key, item in value.items()}
    return value


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--typescript-compiler', type=Path,
        help='Optional existing tsc executable for the generic-shadow language oracle')
    args = parser.parse_args()
    worktree = Path(__file__).resolve().parents[2]
    with tempfile.TemporaryDirectory(prefix='loci-w211-') as directory:
        temp = Path(directory).resolve()
        base = temp / 'store'
        os.environ['LOCI_BASE_DIR'] = str(base)
        os.environ['LOCI_STORE_NAMESPACE'] = 'w211-reproduction'
        results = {name: capture(temp / name, base, case) for name, case in fixtures().items()}
        compiler_check = {"status": "not_run"}
        if args.typescript_compiler:
            compiler = str(args.typescript_compiler.resolve())
            check_repo = temp / 'generic_shadow'
            (check_repo / 'check.ts').write_text(
                'import { processOrder } from "./consumer.js";\n'
                'const numberResult: number = processOrder(42);\n'
                'const stringResult: string = processOrder("ok");\n', encoding='utf-8')
            command = [compiler, '--noEmit', '--strict', '--skipLibCheck',
                '--target', 'ES2022', '--module', 'NodeNext',
                '--moduleResolution', 'NodeNext', 'types.ts', 'consumer.ts', 'check.ts']
            checked = subprocess.run(command, cwd=check_repo, text=True,
                capture_output=True, timeout=30)
            compiler_check = {"command": command,
                "version": subprocess.check_output([compiler, '--version'], text=True).strip(),
                "check_source": (check_repo / 'check.ts').read_text(),
                "exit_code": checked.returncode, "stdout": checked.stdout,
                "stderr": checked.stderr, "status": "passed" if checked.returncode == 0 else "failed"}
            assert checked.returncode == 0, compiler_check
        packet = {
            'purpose': 'W2.1.1 current-checkout reproduction; not frozen agent evaluation or a measured read-reduction result',
            'source_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=worktree, text=True).strip(),
            'runner_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'python': platform.python_version(),
            'packages': {name: importlib.metadata.version(name) for name in ['loci', 'tree-sitter', 'tree-sitter-language-pack']},
            'generic_shadow_language_oracle': compiler_check,
            'cases': normalize(results, temp),
        }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(packet, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print(json.dumps({'output': str(args.output), 'cases': len(results),
        'references': {name: result['reference_output']['counts'] for name, result in results.items()}}))


if __name__ == '__main__':
    main()
