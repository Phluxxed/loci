# loci

A code symbol indexer for LLM agents. loci parses your codebase into a byte-precise symbol index so an agent can fetch exactly the code it needs — no full-file reads, no grep loops.

**60–90% token savings** on typical codebase navigation tasks.

## How it works

loci uses [tree-sitter](https://tree-sitter.github.io/tree-sitter/) to parse source files into an AST, extracts symbols (functions, classes, methods, constants) with their byte offsets, and stores them in a local index. Retrieval is a direct byte-range read — no scanning.

The `outline → get` workflow replaces 15–20 iterative Read/Grep calls with two:

```bash
loci outline /path/to/repo          # all symbols + IDs in one shot
loci get ID1 ID2 --repo /path/to/repo  # fetch source for exactly those symbols
```

## Supported languages

Python, TypeScript, JavaScript, Go, Rust

## Install

```bash
pip install loci
```

Or from source:

```bash
git clone https://github.com/phluxxed/loci
cd loci
pip install -e .
```

## Usage

```bash
# Index a repo (run once, then --incremental after edits)
loci index /path/to/repo
loci index /path/to/repo --incremental

# Get all symbols + IDs
loci outline /path/to/repo
loci outline /path/to/repo --file src/foo.py   # single file

# Fetch symbol source by ID
loci get abc123 def456 --repo /path/to/repo
loci get abc123 --repo /path/to/repo --context 5  # +5 lines surrounding context

# Search by name or concept
loci search "parse file" --repo /path/to/repo
loci search "auth" --repo /path/to/repo --kind function --lang python

# Read a non-symbol file (config, docs, etc.)
loci file pyproject.toml --repo /path/to/repo
loci file src/foo.py --repo /path/to/repo --start 10 --end 40

# Search file contents by regex
loci grep "TODO|FIXME" --repo /path/to/repo

# Index health
loci verify /path/to/repo          # check for content drift
loci list                           # all indexed repos
loci invalidate /path/to/repo      # clear stale cache

# Auto-summarize symbols (run after every index)
loci summarize /path/to/repo       # check for unsummarized symbols
loci summarize /path/to/repo --apply summaries.json  # write generated summaries back

# Token savings analytics
loci stats
loci stats --pretty
loci stats --repo /path/to/repo

# Self-improvement audit (finds search blind spots, ranking issues)
loci analyze
loci analyze --pretty
loci analyze --since 7             # last N days
```

## Symbol fields

Every symbol carries: `id`, `name`, `qualified_name`, `kind`, `language`, `file_path`, `byte_offset`, `byte_length`, `line`, `end_line`, `signature`, `docstring`, `summary`, `keywords`, `decorators`, `content_hash`.

## Analytics

loci logs every search and get to a session file. The `analyze` command reads that log and surfaces actionable findings:

| Finding type | What it means |
|---|---|
| `search_miss` | Symbol exists but search returned nothing — fix keyword extraction |
| `search_blind_spot` | A symbol kind is never surfaced by search |
| `search_ranking_poor` | Correct symbol exists but ranked too low |
| `poor_extraction` | High refetch rate on a symbol kind |
| `refetch_hotspot` | Same symbol fetched repeatedly in a session |
| `kind_dead_weight` | A symbol kind is indexed but never retrieved |

## Claude Code integration

loci is most useful inside Claude Code, where it auto-indexes your repo at session start and injects context into subagent prompts. The hooks that wire this up live in `.claude/` in this repo.

**Prerequisites**

- loci installed (`pip install loci`)
- Claude Code with the [loci skill](https://marketplace.claude.ai) installed

**Install**

```bash
python3 .claude/install-hooks.sh
```

This symlinks the hooks into `~/.claude/hooks/` and patches `~/.claude/settings.json` to register them. Restart Claude Code after running it.

**What the hooks do**

| Hook | Trigger | Effect |
|---|---|---|
| `loci-session-start.sh` | Session open/resume | Runs `loci index --incremental` and injects a context line telling Claude the repo is indexed |
| `loci-agent-inject.sh` | Before any `Agent` tool call | Injects the loci skill content into subagent prompts so subagents can also navigate via loci |

## Development

```bash
# Install with dev deps
pip install -e ".[dev]"

# Run tests
python -m pytest tests/
```

## License

MIT
