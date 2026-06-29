from __future__ import annotations
import argparse
import datetime
import json
import re as _re
import sys
from pathlib import Path

from loci.service import (
    LociError,
    get_cached_file,
    get_symbols,
    get_store as get_service_store,
    grep_repo,
    index_repo,
    list_repos,
    outline_repo,
    reset_session_stats,
    search_symbols,
    session_stats,
    verify_repo,
)


def _print_loci_error(exc: LociError) -> None:
    print(
        json.dumps({
            "error": exc.message,
            "code": exc.code,
            "details": exc.details,
        }),
        file=sys.stderr,
    )


def cmd_index(args: argparse.Namespace) -> int:
    try:
        print(json.dumps(index_repo(args.path, incremental=args.incremental)))
        return 0
    except LociError as exc:
        _print_loci_error(exc)
        return 1


def cmd_search(args: argparse.Namespace) -> int:
    try:
        results = search_symbols(
            args.repo,
            args.query,
            kind=args.kind,
            lang=args.lang,
            limit=args.limit,
        )
        print(json.dumps(results))
        return 0
    except LociError as exc:
        _print_loci_error(exc)
        return 1


def cmd_get(args: argparse.Namespace) -> int:
    single = len(args.symbol_ids) == 1
    context_lines: int = getattr(args, "context", 0) or 0

    def _fetch(symbol_id: str) -> dict:
        try:
            return get_symbols(args.repo, [symbol_id], context=context_lines)[0]
        except LociError as exc:
            return {
                "id": symbol_id,
                "error": exc.message,
                "code": exc.code,
                "details": exc.details,
            }

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
    try:
        result = get_cached_file(
            args.repo,
            args.file_path,
            start_line=args.start,
            end_line=args.end,
        )
        print(json.dumps(result))
        return 0
    except LociError as exc:
        _print_loci_error(exc)
        return 1


def cmd_grep(args: argparse.Namespace) -> int:
    try:
        print(json.dumps(grep_repo(args.repo, args.pattern)))
        return 0
    except LociError as exc:
        if exc.code == "REPO_NOT_INDEXED":
            print(json.dumps([]))
            return 0
        _print_loci_error(exc)
        return 1


def cmd_verify(args: argparse.Namespace) -> int:
    try:
        result = verify_repo(args.path)
    except LociError as exc:
        _print_loci_error(exc)
        return 1
    has_failures = len(result["failed"]) > 0
    print(json.dumps(result))
    return 1 if has_failures else 0


def cmd_list(_args: argparse.Namespace) -> int:
    print(json.dumps(list_repos()))
    return 0


def cmd_invalidate(args: argparse.Namespace) -> int:
    repo_path = Path(args.path).resolve()
    store = get_service_store()
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

    def _render_nested(
        out: list,
        heading: str,
        repo_rows: list,
        file_rows: list,
        empty_label: str,
    ) -> None:
        out.append(_cyan(heading, use_color))
        out.append("─" * W)
        if not repo_rows:
            out.append(_dim(f"(no {empty_label} gets yet)", use_color))
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
        _render_table(right, "By File (markdown)", stats.get("by_doc", []))
    else:
        _render_nested(
            left,
            "By Repo (code)",
            stats.get("by_repo_code", []),
            stats.get("by_file_code", []),
            "code",
        )
        _render_nested(
            right,
            "By Repo (markdown)",
            stats.get("by_repo_doc", []),
            stats.get("by_doc", []),
            "markdown",
        )

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
    try:
        print(json.dumps(outline_repo(args.path, file=args.file)))
        return 0
    except LociError as exc:
        _print_loci_error(exc)
        return 1


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
