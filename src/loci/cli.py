from __future__ import annotations
import argparse
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

import pathspec

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


def _load_gitignore(repo_path: Path) -> "pathspec.PathSpec | None":
    gitignore = repo_path / ".gitignore"
    if not gitignore.exists():
        return None
    lines = gitignore.read_text(encoding="utf-8", errors="replace").splitlines()
    return pathspec.PathSpec.from_lines("gitwildmatch", lines)


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
    zero_symbol_warnings: list[dict] = []
    gitignore = _load_gitignore(repo_path)

    for src_file in sorted(repo_path.rglob("*")):
        if not src_file.is_file():
            continue
        if any(part in SKIP_DIRS for part in src_file.parts):
            continue
        if _should_skip_file(src_file):
            continue

        rel_path = str(src_file.relative_to(repo_path))
        if gitignore and gitignore.match_file(rel_path):
            continue
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
        else:
            # Warn on non-trivial files with known extensions that yield 0 symbols
            try:
                line_count = len(src_file.read_bytes().splitlines())
            except OSError:
                line_count = 0
            if line_count > 10:
                zero_symbol_warnings.append({
                    "file": rel_path,
                    "lines": line_count,
                    "reason": "0 symbols extracted",
                })

    store.write(repo_path, all_symbols, file_hashes=new_file_hashes)

    output: dict = {
        "path": str(repo_path),
        "symbols_indexed": len(all_symbols),
        "files_skipped": files_skipped,
        "languages": dict(language_counts),
    }
    if zero_symbol_warnings:
        output["warnings"] = zero_symbol_warnings

    print(json.dumps(output))
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
    index = store.load(repo_path)
    single = len(args.symbol_ids) == 1
    context_lines: int = getattr(args, "context", 0) or 0

    def _fetch(symbol_id: str) -> dict:
        if index is None:
            return {"id": symbol_id, "error": "Repo not indexed"}
        meta = next((s for s in index["symbols"] if s["id"] == symbol_id), None)
        if meta is None:
            return {"id": symbol_id, "error": f"Symbol not found: {symbol_id}"}
        content = store.get_symbol_content(repo_path, symbol_id)
        if content is None:
            return {"id": symbol_id, "error": f"Symbol not found: {symbol_id}"}
        symbol_bytes = len(content.encode("utf-8"))
        file_bytes = store.get_symbol_file_size(repo_path, symbol_id)
        if file_bytes is not None:
            store.log_retrieval(symbol_id, symbol_bytes, file_bytes, repo_path=str(repo_path))
        result: dict = {
            "id": symbol_id,
            "source": content,
            **{k: meta.get(k) for k in ("byte_offset", "byte_length", "line", "end_line", "signature", "kind", "language")},  # type: ignore[union-attr]
        }
        if meta.get("decorators"):
            result["decorators"] = meta["decorators"]
        if context_lines > 0:
            ctx = store.get_symbol_context(repo_path, symbol_id, context_lines)
            if ctx:
                result["context_before"] = ctx["context_before"]
                result["context_after"] = ctx["context_after"]
        return result

    if single:
        result = _fetch(args.symbol_ids[0])
        if "error" in result:
            print(json.dumps(result), file=sys.stderr)
            return 1
        print(json.dumps(result))
        return 0

    results = [_fetch(sid) for sid in args.symbol_ids]
    print(json.dumps(results))
    return 0


def cmd_file(args: argparse.Namespace) -> int:
    repo_path = Path(args.repo).resolve()
    store = _get_store()
    result = store.get_file_content(
        repo_path, args.file_path, start_line=args.start, end_line=args.end
    )
    if result is None:
        print(json.dumps({"error": f"File not found in cache: {args.file_path}"}), file=sys.stderr)
        return 1
    symbol_bytes = len(result["content"].encode("utf-8"))
    file_bytes = result.pop("file_bytes")
    store.log_retrieval(args.file_path, symbol_bytes, file_bytes, repo_path=str(repo_path))
    print(json.dumps(result))
    return 0


def cmd_grep(args: argparse.Namespace) -> int:
    repo_path = Path(args.repo).resolve()
    store = _get_store()
    try:
        results = store.grep_files(repo_path, args.pattern)
    except ValueError as e:
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        return 1
    print(json.dumps(results))
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    repo_path = Path(args.path).resolve()
    store = _get_store()
    result = store.verify_index(repo_path)
    if "error" in result:
        print(json.dumps(result), file=sys.stderr)
        return 1
    has_failures = len(result["failed"]) > 0
    print(json.dumps(result))
    return 1 if has_failures else 0


def cmd_list(_args: argparse.Namespace) -> int:
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


def _fmt_bytes(n: int) -> str:
    if n >= 1_048_576:
        return f"{n / 1_048_576:.1f}M"
    if n >= 1024:
        return f"{n / 1024:.1f}K"
    return f"{n}B"


# ANSI color helpers — no-ops when colors disabled
def _ansi(code: str, text: str, use_color: bool) -> str:
    return f"\033[{code}m{text}\033[0m" if use_color else text

def _cyan(text: str, c: bool) -> str:    return _ansi("96", text, c)
def _dim(text: str, c: bool) -> str:     return _ansi("2", text, c)
def _ratio_color(pct: int, text: str, c: bool) -> str:
    if not c:
        return text
    code = "92" if pct >= 90 else "93" if pct >= 70 else "91"
    return f"\033[{code}m{text}\033[0m"

def _two_tone_bar(ratio: float, width: int, use_color: bool) -> str:
    """Two-segment bar: filled (savings) + empty (retrieved)."""
    filled = max(0, min(width, int(ratio * width)))
    empty = width - filled
    if use_color:
        return f"\033[42m{' ' * filled}\033[0m\033[100m{' ' * empty}\033[0m"
    return "█" * filled + "░" * empty

def _solid_bar(ratio: float, width: int, use_color: bool) -> str:
    filled = max(0, min(width, int(ratio * width)))
    bar = "█" * filled
    return _ansi("96", bar, use_color) if filled else ""


def _format_stats_pretty(stats: dict, repo_filter: str = "", use_color: bool = True) -> str:
    W = 72
    lines = []
    scope = f" ({repo_filter.split('/')[-1]})" if repo_filter else " (Global Scope)"

    lines.append(_cyan(f"loci Symbol Savings{scope}", use_color))
    lines.append("─" * W)
    lines.append("")

    total = stats["total_gets"]
    sb = stats["symbol_bytes_retrieved"]
    fb_total = sb + stats["file_bytes_not_loaded"]
    not_loaded = stats["file_bytes_not_loaded"]
    tokens = stats["tokens_not_loaded"]
    ratio_str = stats["savings_ratio"]
    ratio_f = float(ratio_str.rstrip("%")) / 100 if ratio_str != "0%" else 0.0
    ratio_pct = int(ratio_f * 100)

    label_w = 18
    lines.append(f"{'Total gets:':<{label_w}}{total}")
    lines.append(f"{'Bytes retrieved:':<{label_w}}{_fmt_bytes(sb)}  (of {_fmt_bytes(fb_total)} file bytes)")
    lines.append(f"{'Tokens saved:':<{label_w}}{tokens:,}  ({_ratio_color(ratio_pct, ratio_str, use_color)})")
    meter = _two_tone_bar(ratio_f, 20, use_color)
    lines.append(f"{'Savings meter:':<{label_w}}{meter}  {_ratio_color(ratio_pct, ratio_str, use_color)}")
    lines.append("")

    REPO_W = 32
    FILE_W = 46
    IMPACT_W = 12

    def _render_nested(repo_rows: list, file_rows: list) -> None:
        if not repo_rows:
            return

        # Group files under their repo, strip repo prefix
        file_by_repo: dict[str, list] = {}
        for frow in file_rows:
            fname = frow["name"]
            for rrow in repo_rows:
                prefix = rrow["name"] + "/"
                if fname.startswith(prefix):
                    file_by_repo.setdefault(rrow["name"], []).append(
                        {**frow, "rel": fname[len(prefix):]}
                    )
                    break

        lines.append(_cyan("By Repo", use_color))
        lines.append("─" * W)
        hdr = (f"  {'#':>2}  {'Repo':<{REPO_W}}  {'Gets':>5}  {'Saved':>7}  {'Ratio':>6}  Impact")
        lines.append(_dim(hdr, use_color))
        lines.append("─" * W)

        max_saved = repo_rows[0]["saved_bytes"] if repo_rows else 1
        for i, rrow in enumerate(repo_rows, 1):
            repo_path = rrow["name"]
            repo_name = repo_path.split("/")[-1]
            repo_display = repo_name if len(repo_name) <= REPO_W else repo_name[:REPO_W]
            ratio_txt = _ratio_color(rrow["ratio_pct"], f"{rrow['ratio_pct']}%", use_color)
            impact = _solid_bar(rrow["saved_bytes"] / max_saved, IMPACT_W, use_color)
            lines.append(
                f"  {i:>2}.  {_cyan(repo_display, use_color):<{REPO_W + (9 if use_color else 0)}}  "
                f"{rrow['gets']:>5}  {_fmt_bytes(rrow['saved_bytes']):>7}  {ratio_txt:>6}  {impact}"
            )
            for frow in file_by_repo.get(repo_path, []):
                rel = frow["rel"]
                rel_display = rel if len(rel) <= FILE_W else "..." + rel[-(FILE_W - 3):]
                fratio = _ratio_color(frow["ratio_pct"], f"{frow['ratio_pct']}%", use_color)
                fimpact = _solid_bar(frow["saved_bytes"] / max_saved, IMPACT_W, use_color)
                lines.append(
                    f"       {_dim(rel_display, use_color):<{FILE_W + (9 if use_color else 0)}}  "
                    f"{frow['gets']:>5}  {_fmt_bytes(frow['saved_bytes']):>7}  {fratio:>6}  {fimpact}"
                )
        lines.append("─" * W)

    def _render_table(heading: str, rows: list, name_width: int) -> None:
        if not rows:
            return
        lines.append(_cyan(heading, use_color))
        lines.append("─" * W)
        hdr = f"  {'#':>2}  {'File':<{name_width}}  {'Gets':>5}  {'Saved':>7}  {'Ratio':>6}  Impact"
        lines.append(_dim(hdr, use_color))
        lines.append("─" * W)
        max_saved = rows[0]["saved_bytes"] if rows else 1
        for i, row in enumerate(rows[:20], 1):
            name = row["name"]
            display = name if len(name) <= name_width else "..." + name[-(name_width - 3):]
            ratio_txt = _ratio_color(row["ratio_pct"], f"{row['ratio_pct']}%", use_color)
            impact = _solid_bar(row["saved_bytes"] / max_saved, IMPACT_W, use_color)
            lines.append(
                f"  {i:>2}.  {_cyan(display, use_color):<{name_width + (9 if use_color else 0)}}  "
                f"{row['gets']:>5}  {_fmt_bytes(row['saved_bytes']):>7}  {ratio_txt:>6}  {impact}"
            )
        lines.append("─" * W)

    if repo_filter:
        _render_table("By File", stats.get("by_file", []), 50)
    else:
        _render_nested(stats.get("by_repo", []), stats.get("by_file", []))

    return "\n".join(lines)


def cmd_stats(args: argparse.Namespace) -> int:
    store = _get_store()
    if args.reset:
        store.reset_session()
    repo_filter = str(Path(args.repo).resolve()) if args.repo else ""
    stats = store.get_session_stats(repo_filter=repo_filter or None)
    if args.pretty:
        print(_format_stats_pretty(stats, repo_filter=repo_filter, use_color=sys.stdout.isatty()))
    else:
        print(json.dumps(stats))
    return 0


def cmd_outline(args: argparse.Namespace) -> int:
    repo_path = Path(args.path).resolve()
    store = _get_store()
    index = store.load(repo_path)
    if index is None:
        print(json.dumps({"error": "Repo not indexed"}), file=sys.stderr)
        return 1

    grouped: dict[str, list[dict]] = {}
    for s in index["symbols"]:
        fp = s["file_path"]
        if args.file and fp != args.file:
            continue
        entry: dict = {
            "id": s.get("id", ""),
            "name": s.get("name", ""),
            "kind": s.get("kind", ""),
            "line": s.get("line", 0),
            "end_line": s.get("end_line", 0),
            "signature": s.get("signature", ""),
            "summary": s.get("summary", ""),
        }
        if s.get("decorators"):
            entry["decorators"] = s["decorators"]
        grouped.setdefault(fp, []).append(entry)

    result = [{"file": fp, "symbols": syms} for fp, syms in sorted(grouped.items())]
    print(json.dumps(result))
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
    p_get.add_argument("symbol_ids", nargs="+", help="Symbol ID(s)")
    p_get.add_argument("--repo", required=True, help="Path to indexed repo")
    p_get.add_argument("--context", type=int, default=0, metavar="N",
                       help="Include N lines of context before and after each symbol")

    p_file = sub.add_parser("file", help="Get cached file content")
    p_file.add_argument("file_path", help="Relative file path (as indexed, e.g. src/foo.py)")
    p_file.add_argument("--repo", required=True, help="Path to indexed repo")
    p_file.add_argument("--start", type=int, default=None, help="Start line (1-indexed, inclusive)")
    p_file.add_argument("--end", type=int, default=None, help="End line (1-indexed, inclusive)")

    p_grep = sub.add_parser("grep", help="Search text across cached files")
    p_grep.add_argument("pattern", help="Regex pattern to search for")
    p_grep.add_argument("--repo", required=True, help="Path to indexed repo")

    sub.add_parser("list", help="List indexed repos")

    p_inv = sub.add_parser("invalidate", help="Clear cache for a path")
    p_inv.add_argument("path", help="Path to repo")

    p_sum = sub.add_parser("summarize", help="Output/apply symbol summaries")
    p_sum.add_argument("path", help="Path to repo")
    p_sum.add_argument("--apply", help="JSON file with summaries to apply")

    p_out = sub.add_parser("outline", help="Show all symbols grouped by file")
    p_out.add_argument("path", help="Path to repo")
    p_out.add_argument("--file", help="Filter to a single file (relative path)", default=None)

    p_stats = sub.add_parser("stats", help="Show session retrieval savings")
    p_stats.add_argument("--repo", default=None, help="Filter to a specific repo path")
    p_stats.add_argument("--reset", action="store_true", help="Clear session log")
    p_stats.add_argument("--pretty", action="store_true", help="Human-readable formatted output")

    p_verify = sub.add_parser("verify", help="Verify byte offsets for all indexed symbols")
    p_verify.add_argument("path", help="Path to repo")

    args = parser.parse_args()

    if args.command == "index":
        sys.exit(cmd_index(args))
    elif args.command == "search":
        sys.exit(cmd_search(args))
    elif args.command == "get":
        sys.exit(cmd_get(args))
    elif args.command == "file":
        sys.exit(cmd_file(args))
    elif args.command == "grep":
        sys.exit(cmd_grep(args))
    elif args.command == "list":
        sys.exit(cmd_list(args))
    elif args.command == "invalidate":
        sys.exit(cmd_invalidate(args))
    elif args.command == "summarize":
        sys.exit(cmd_summarize(args))
    elif args.command == "outline":
        sys.exit(cmd_outline(args))
    elif args.command == "stats":
        sys.exit(cmd_stats(args))
    elif args.command == "verify":
        sys.exit(cmd_verify(args))
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
