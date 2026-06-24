from __future__ import annotations
import argparse
import datetime
import json
import sys
import uuid
from collections import defaultdict
from pathlib import Path

import pathspec

from loci.parser.extractor import parse_file
from loci.parser.languages import EXTENSION_MAP, MARKDOWN_SUFFIXES
from loci.parser.symbols import Symbol
from loci.service import (
    get_store as get_service_store,
    reset_session_stats,
    session_stats,
)
from loci.storage.index_store import IndexStore

SKIP_DIRS = {
    ".git", "node_modules", "__pycache__", ".venv", "venv",
    ".tox", "dist", "build", ".mypy_cache", ".pytest_cache",
    ".ruff_cache", ".uv-cache", "uv-cache", "__tests__", "tests",
}
TEST_FILE_SUFFIXES = (
    ".test.ts", ".test.tsx", ".test.js", ".test.jsx",
    ".spec.ts", ".spec.tsx", ".spec.js", ".spec.jsx",
)
SKIP_FILES = {".env", ".env.local", "credentials.json", "secrets.json"}
SKIP_EXTENSIONS = {
    ".pyc", ".pyo", ".so", ".dylib", ".dll", ".exe",
    ".bin", ".pem", ".key", ".p12",
}


def _get_store() -> IndexStore:
    return get_service_store()


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
    name = path.name
    if name.startswith("test_") or name.endswith("_test.py") or name.endswith("_test.go"):
        return True
    if any(name.endswith(s) for s in TEST_FILE_SUFFIXES):
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
                file_bytes = src_file.read_bytes()
            except OSError:
                file_bytes = b""
            line_count = len(file_bytes.splitlines())
            is_nonempty_markdown = (
                src_file.suffix.lower() in MARKDOWN_SUFFIXES
                and bool(file_bytes.strip())
            )
            if line_count > 10 or is_nonempty_markdown:
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
    if results:
        search_id = str(uuid.uuid4())
        result_ids = [r["id"] for r in results]
        store.log_search(search_id, args.query, str(repo_path), result_ids)
    else:
        store.log_miss("search_empty", repo_path=str(repo_path), query=args.query)
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
            store.log_miss("get_not_found", repo_path=str(repo_path), symbol_id=symbol_id)
            return {"id": symbol_id, "error": "Repo not indexed"}
        meta = next((s for s in index["symbols"] if s["id"] == symbol_id), None)
        if meta is None:
            store.log_miss("get_not_found", repo_path=str(repo_path), symbol_id=symbol_id)
            return {"id": symbol_id, "error": f"Symbol not found: {symbol_id}"}
        content = store.get_symbol_content(repo_path, symbol_id)
        if content is None:
            store.log_miss("get_not_found", repo_path=str(repo_path), symbol_id=symbol_id)
            return {"id": symbol_id, "error": f"Symbol not found: {symbol_id}"}
        symbol_bytes = len(content.encode("utf-8"))
        file_bytes = store.get_symbol_file_size(repo_path, symbol_id)
        if file_bytes is not None:
            search_id, search_rank = store.resolve_search_correlation(symbol_id, repo=str(repo_path))
            store.log_retrieval(
                symbol_id,
                symbol_bytes,
                file_bytes,
                repo_path=str(repo_path),
                kind=meta.get("kind"),
                language=meta.get("language"),
                search_id=search_id,
                search_rank=search_rank,
            )
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
    language = EXTENSION_MAP.get(Path(args.file_path).suffix)
    store.log_retrieval(
        args.file_path, symbol_bytes, file_bytes, repo_path=str(repo_path), language=language
    )
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


def _fmt_bytes(n: int) -> str:
    if n >= 1_048_576:
        return f"{n / 1_048_576:.1f}M"
    if n >= 1024:
        return f"{n / 1024:.1f}K"
    return f"{n}B"


# ANSI color helpers — no-ops when colors disabled
import re as _re
_ANSI_RE = _re.compile(r"\033\[[0-9;]*m")


def _store_label(stats: dict) -> str:
    store = stats.get("store") or {}
    base_dir = store.get("base_dir")
    if not base_dir:
        return ""
    source = store.get("source", "unknown")
    return f"Store: {base_dir} ({source})"

def _ansi(code: str, text: str, use_color: bool) -> str:
    return f"\033[{code}m{text}\033[0m" if use_color else text

def _cyan(text: str, c: bool) -> str:    return _ansi("96", text, c)
def _dim(text: str, c: bool) -> str:     return _ansi("2", text, c)
def _ratio_color(pct: int, text: str, c: bool) -> str:
    if not c:
        return text
    code = "92" if pct >= 70 else "93" if pct >= 50 else "91"
    return f"\033[{code}m{text}\033[0m"

def _vlen(s: str) -> int:
    """Visible length: strip ANSI escape codes before measuring."""
    return len(_ANSI_RE.sub("", s))

def _ljust(s: str, w: int) -> str:
    return s + " " * max(0, w - _vlen(s))

def _rjust(s: str, w: int) -> str:
    return " " * max(0, w - _vlen(s)) + s

def _rel_time(ts: float | None) -> str:
    """Return a compact relative time string, e.g. '2h ago', '3d ago', 'Mar 24'."""
    if ts is None:
        return "—"
    import time as _time
    delta = _time.time() - ts
    if delta < 3600:
        return f"{int(delta / 60)}m ago"
    if delta < 86400:
        return f"{int(delta / 3600)}h ago"
    if delta < 7 * 86400:
        return f"{int(delta / 86400)}d ago"
    return datetime.datetime.fromtimestamp(ts).strftime("%b %-d")


def _two_tone_bar(ratio: float, width: int, use_color: bool) -> str:
    """Two-segment bar: filled (savings) + empty (retrieved)."""
    filled = max(0, min(width, int(ratio * width)))
    empty = width - filled
    if use_color:
        return f"\033[42m{' ' * filled}\033[0m\033[100m{' ' * empty}\033[0m"
    return "█" * filled + "░" * empty

def _ratio_bar(ratio_pct: int, width: int, use_color: bool) -> str:
    """Two-tone bar coloured by ratio: green/yellow/red fill + grey empty."""
    filled = max(0, min(width, int(ratio_pct / 100 * width)))
    empty = width - filled
    if use_color:
        bg = "42" if ratio_pct >= 70 else "43" if ratio_pct >= 50 else "41"
        return f"\033[{bg}m{' ' * filled}\033[0m\033[100m{' ' * empty}\033[0m"
    filled_char = "█" * filled
    empty_char = "░" * empty
    return filled_char + empty_char


def _format_stats_pretty(stats: dict, repo_filter: str = "", use_color: bool = True, since_days: int | None = None) -> str:
    W = 88            # width of a single panel
    GAP_VIS = 3       # visible width of the divider between the two panels
    TW = W * 2 + GAP_VIS
    gap = " " + _dim("│", use_color) + " "
    lines = []
    scope = f" ({repo_filter.split('/')[-1]})" if repo_filter else " (Global Scope)"
    window = f" — last {since_days}d" if since_days is not None else " — all time"

    code = stats.get("code", {})
    docs = stats.get("docs", {})

    lines.append(_cyan(f"loci Savings{scope}{window}", use_color))
    store_label = _store_label(stats)
    if store_label:
        lines.append(_dim(store_label, use_color))
    lines.append("─" * TW)
    lines.append("")

    def _last_str(ts: float | None) -> str:
        if ts is None:
            return "never"
        return datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")

    # Column widths (visible chars) — a data row sums to exactly W.
    NUM_W  = 7   # "  1.  " = 2+2+1+2 = 7 chars
    NAME_W = 28  # repo or file name, truncated
    GETS_W = 5
    SAVE_W = 7
    RATI_W = 4   # "91%" .. "100%"
    IMPACT_W = 20
    FILE_NW = NAME_W  # 7 spaces indent + NAME_W chars = same start as NUM_W + NAME_W

    def _summary(out: list, title: str, d: dict) -> None:
        ratio_str = d.get("savings_ratio", "0%")
        ratio_pct = int(ratio_str.rstrip("%")) if ratio_str != "0%" else 0
        lw = 14
        out.append(_cyan(title, use_color))
        out.append("─" * W)
        out.append(f"{'Outlines':<{lw}}{d.get('outlines', 0)}")
        out.append(f"{'Gets':<{lw}}{d.get('gets', 0)}")
        out.append(f"{'Last get':<{lw}}{_last_str(d.get('last_get_ts'))}")
        out.append(f"{'Tokens saved':<{lw}}{d.get('tokens_not_loaded', 0):,}  ({_ratio_color(ratio_pct, ratio_str, use_color)})")
        out.append(f"{'Savings meter':<{lw}}{_two_tone_bar(ratio_pct / 100, 20, use_color)}  {_ratio_color(ratio_pct, ratio_str, use_color)}")
        out.append("")

    def _row(num_str: str, name_str: str, name_w: int,
             gets: int, saved_bytes: int, ratio_pct: int, last_ts: float | None) -> str:
        ratio_raw = f"{ratio_pct}%"
        ratio_col = _ratio_color(ratio_pct, ratio_raw, use_color)
        impact = _ratio_bar(ratio_pct, IMPACT_W, use_color)
        return (
            num_str
            + _ljust(name_str, name_w)
            + "  "
            + _rjust(str(gets), GETS_W)
            + "  "
            + _rjust(_fmt_bytes(saved_bytes), SAVE_W)
            + "  "
            + _rjust(ratio_col, RATI_W)
            + "  "
            + impact
            + "  "
            + _rel_time(last_ts)
        )

    def _hdr(name_label: str) -> str:
        return (
            " " * NUM_W
            + _ljust(name_label, NAME_W) + "  "
            + _rjust("Gets", GETS_W) + "  "
            + _rjust("Saved", SAVE_W) + "  "
            + _rjust("Ratio", RATI_W) + "  "
            + _ljust("Impact", IMPACT_W) + "  "
            + "Last"
        )

    def _render_nested(out: list, heading: str, repo_rows: list, file_rows: list) -> None:
        out.append(_cyan(heading, use_color))
        out.append("─" * W)
        if not repo_rows:
            out.append(_dim("(no code gets yet)", use_color))
            out.append("─" * W)
            return

        # Group files under their repo, strip repo prefix. Sort by path length
        # descending so more specific paths (e.g. worktrees) match before parents.
        repos_by_specificity = sorted(repo_rows, key=lambda r: len(r["name"]), reverse=True)
        file_by_repo: dict[str, list] = {}
        for frow in file_rows:
            fname = frow["name"]
            for rrow in repos_by_specificity:
                prefix = rrow["name"] + "/"
                if fname.startswith(prefix):
                    file_by_repo.setdefault(rrow["name"], []).append(
                        {**frow, "rel": fname[len(prefix):]}
                    )
                    break

        out.append(_dim(_hdr("Repo"), use_color))
        out.append("─" * W)
        for i, rrow in enumerate(repo_rows, 1):
            repo_path = rrow["name"]
            repo_name = repo_path.split("/")[-1]
            repo_display = _cyan(
                repo_name if len(repo_name) <= NAME_W else repo_name[:NAME_W],
                use_color,
            )
            out.append(_row(f"  {i:>2}.  ", repo_display, NAME_W,
                            rrow["gets"], rrow["saved_bytes"], rrow["ratio_pct"], rrow.get("last_ts")))
            for frow in file_by_repo.get(repo_path, []):
                rel = frow["rel"]
                rel_display = _dim(
                    rel if len(rel) <= FILE_NW else "..." + rel[-(FILE_NW - 3):],
                    use_color,
                )
                out.append(_row(" " * 7, rel_display, FILE_NW,
                                frow["gets"], frow["saved_bytes"], frow["ratio_pct"], frow.get("last_ts")))
        out.append("─" * W)

    def _render_table(out: list, heading: str, rows: list) -> None:
        out.append(_cyan(heading, use_color))
        out.append("─" * W)
        if not rows:
            out.append(_dim("(no markdown gets yet)", use_color))
            out.append("─" * W)
            return
        out.append(_dim(_hdr("File"), use_color))
        out.append("─" * W)
        for i, row in enumerate(rows[:20], 1):
            name = row["name"]
            display = _cyan(
                name if len(name) <= NAME_W else "..." + name[-(NAME_W - 3):],
                use_color,
            )
            out.append(_row(f"  {i:>2}.  ", display, NAME_W,
                            row["gets"], row["saved_bytes"], row["ratio_pct"], row.get("last_ts")))
        out.append("─" * W)

    # Build the two panels independently, then stitch them side by side.
    left: list[str] = []
    right: list[str] = []
    _summary(left, "Code", code)
    _summary(right, "Markdown", docs)
    if repo_filter:
        _render_table(left, "By File (code)", stats.get("by_file_code", []))
    else:
        _render_nested(left, "By Repo (code)", stats.get("by_repo_code", []), stats.get("by_file_code", []))
    _render_table(right, "By Doc (markdown)", stats.get("by_doc", []))

    for i in range(max(len(left), len(right))):
        l = left[i] if i < len(left) else ""
        r = right[i] if i < len(right) else ""
        lines.append(_ljust(l, W) + gap + r)

    return "\n".join(lines)


def cmd_stats(args: argparse.Namespace) -> int:
    if args.reset:
        reset = reset_session_stats()
        print(json.dumps(reset), file=sys.stderr)
    repo_filter = str(Path(args.repo).resolve()) if args.repo else ""
    since_days = None if args.all_time else args.since
    stats = session_stats(repo=args.repo, since_days=since_days)
    if args.pretty:
        print(_format_stats_pretty(stats, repo_filter=repo_filter, use_color=sys.stdout.isatty(), since_days=since_days))
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
    languages: set[str] = set()
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
        if s.get("language"):
            languages.add(s["language"])

    result = [{"file": fp, "symbols": syms} for fp, syms in sorted(grouped.items())]
    symbol_count = sum(len(syms) for syms in grouped.values())
    store.log_outline(str(repo_path), symbol_count, file_filter=args.file or None,
                      languages=sorted(languages))
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

    p_out = sub.add_parser("outline", help="Show all symbols grouped by file")
    p_out.add_argument("path", help="Path to repo")
    p_out.add_argument("--file", help="Filter to a single file (relative path)", default=None)

    p_stats = sub.add_parser("stats", help="Show session retrieval savings")
    p_stats.add_argument("--repo", default=None, help="Filter to a specific repo path")
    p_stats.add_argument("--reset", action="store_true", help="Clear session log")
    p_stats.add_argument("--pretty", action="store_true", help="Human-readable formatted output")
    p_stats.add_argument("--since", type=int, default=7, metavar="DAYS",
                         help="Limit to last N days (default: 7)")
    p_stats.add_argument("--all", dest="all_time", action="store_true",
                         help="Show all-time stats (overrides --since)")

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
