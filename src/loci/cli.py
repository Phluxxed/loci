from __future__ import annotations
import argparse
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

from loci.parser.extractor import parse_file
from loci.parser.languages import EXTENSION_MAP
from loci.parser.symbols import Symbol
from loci.storage.index_store import IndexStore

SKIP_DIRS = {
    ".git", "node_modules", "__pycache__", ".venv", "venv",
    ".tox", "dist", "build", ".mypy_cache", ".pytest_cache",
}
SKIP_FILES = {".env", ".env.local", "credentials.json", "secrets.json"}
SKIP_EXTENSIONS = {
    ".pyc", ".pyo", ".so", ".dylib", ".dll", ".exe",
    ".bin", ".pem", ".key", ".p12",
}


def _get_store() -> IndexStore:
    base = os.environ.get("LOCI_BASE_DIR")
    return IndexStore(base_dir=Path(base)) if base else IndexStore()


def _should_skip_file(path: Path) -> bool:
    if path.name in SKIP_FILES:
        return True
    if path.suffix in SKIP_EXTENSIONS:
        return True
    if path.suffix not in EXTENSION_MAP:
        return True
    return False


def cmd_index(args: argparse.Namespace) -> int:
    repo_path = Path(args.path).resolve()
    if not repo_path.exists():
        print(json.dumps({"error": f"Path not found: {repo_path}"}), file=sys.stderr)
        return 1

    store = _get_store()
    existing = store.load(repo_path) if args.incremental else None
    existing_hashes: dict[str, str] = existing.get("file_hashes", {}) if existing else {}
    existing_symbols: list[dict] = existing.get("symbols", []) if existing else []

    all_symbols: list[Symbol] = []
    new_file_hashes: dict[str, str] = dict(existing_hashes)
    files_skipped = 0
    language_counts: dict[str, int] = defaultdict(int)

    for src_file in sorted(repo_path.rglob("*")):
        if not src_file.is_file():
            continue
        if any(part in SKIP_DIRS for part in src_file.parts):
            continue
        if _should_skip_file(src_file):
            continue

        rel_path = str(src_file.relative_to(repo_path))
        file_hash = store.hash_file(src_file)

        if args.incremental and existing_hashes.get(rel_path) == file_hash:
            kept = [Symbol.from_dict(s) for s in existing_symbols if s["file_path"] == rel_path]
            all_symbols.extend(kept)
            files_skipped += 1
            lang = EXTENSION_MAP.get(src_file.suffix, "unknown")
            language_counts[lang] += 1
            continue

        symbols = parse_file(src_file)
        for sym in symbols:
            sym.file_path = rel_path
            sym.id = f"{rel_path}::{sym.qualified_name}#{sym.kind}"
        all_symbols.extend(symbols)
        new_file_hashes[rel_path] = file_hash
        lang = EXTENSION_MAP.get(src_file.suffix, "unknown")
        if symbols:
            language_counts[lang] += 1

    store.write(repo_path, all_symbols, file_hashes=new_file_hashes)

    print(json.dumps({
        "path": str(repo_path),
        "symbols_indexed": len(all_symbols),
        "files_skipped": files_skipped,
        "languages": dict(language_counts),
    }))
    return 0


def cmd_search(args: argparse.Namespace) -> int:
    repo_path = Path(args.repo).resolve()
    store = _get_store()
    results = store.search(
        repo_path,
        args.query,
        kind=args.kind,
        lang=args.lang,
        limit=args.limit,
    )
    print(json.dumps(results))
    return 0


def cmd_get(args: argparse.Namespace) -> int:
    repo_path = Path(args.repo).resolve()
    store = _get_store()
    content = store.get_symbol_content(repo_path, args.symbol_id)
    if content is None:
        print(json.dumps({"error": f"Symbol not found: {args.symbol_id}"}), file=sys.stderr)
        return 1
    index = store.load(repo_path)
    meta = next((s for s in index["symbols"] if s["id"] == args.symbol_id), {})
    result = {
        "id": args.symbol_id,
        "source": content,
        **{k: meta.get(k) for k in ("byte_offset", "byte_length", "signature", "kind", "language")},
    }
    print(json.dumps(result))
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    store = _get_store()
    repos = store.list_repos()
    print(json.dumps(repos))
    return 0


def cmd_invalidate(args: argparse.Namespace) -> int:
    repo_path = Path(args.path).resolve()
    store = _get_store()
    store.invalidate(repo_path)
    print(json.dumps({"invalidated": str(repo_path)}))
    return 0


def cmd_summarize(args: argparse.Namespace) -> int:
    repo_path = Path(args.path).resolve()
    store = _get_store()

    if args.apply:
        summaries = json.loads(Path(args.apply).read_text())
        count = store.apply_summaries(repo_path, summaries)
        print(json.dumps({"summaries_applied": count}))
        return 0

    index = store.load(repo_path)
    if index is None:
        print(json.dumps({"error": "Repo not indexed"}), file=sys.stderr)
        return 1

    unsummarized = [
        {
            "id": s["id"],
            "signature": s.get("signature", ""),
            "docstring": s.get("docstring", ""),
            "summary": s.get("summary", ""),
        }
        for s in index["symbols"]
        if not s.get("summary")
    ]
    print(json.dumps(unsummarized))
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(prog="loci", description="Code symbol indexer")
    sub = parser.add_subparsers(dest="command")

    p_index = sub.add_parser("index", help="Index a repository")
    p_index.add_argument("path", help="Path to repository")
    p_index.add_argument("--incremental", action="store_true", help="Skip unchanged files")

    p_search = sub.add_parser("search", help="Search symbols")
    p_search.add_argument("query", help="Search query")
    p_search.add_argument("--repo", required=True, help="Path to indexed repo")
    p_search.add_argument("--kind", help="Filter by kind")
    p_search.add_argument("--lang", help="Filter by language")
    p_search.add_argument("--limit", type=int, default=20, help="Max results")

    p_get = sub.add_parser("get", help="Get symbol source by ID")
    p_get.add_argument("symbol_id", help="Symbol ID")
    p_get.add_argument("--repo", required=True, help="Path to indexed repo")

    sub.add_parser("list", help="List indexed repos")

    p_inv = sub.add_parser("invalidate", help="Clear cache for a path")
    p_inv.add_argument("path", help="Path to repo")

    p_sum = sub.add_parser("summarize", help="Output/apply symbol summaries")
    p_sum.add_argument("path", help="Path to repo")
    p_sum.add_argument("--apply", help="JSON file with summaries to apply")

    args = parser.parse_args()

    if args.command == "index":
        sys.exit(cmd_index(args))
    elif args.command == "search":
        sys.exit(cmd_search(args))
    elif args.command == "get":
        sys.exit(cmd_get(args))
    elif args.command == "list":
        sys.exit(cmd_list(args))
    elif args.command == "invalidate":
        sys.exit(cmd_invalidate(args))
    elif args.command == "summarize":
        sys.exit(cmd_summarize(args))
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
