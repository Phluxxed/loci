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

## Agent configuration

For loci to be useful, your agent needs to know it exists and how to use it. The full workflow guide is in `.claude/skills/loci/SKILL.md` — paste it into your system prompt or agent instructions.

The one-line version to add to any agent's instructions:

```
Use loci for all codebase navigation. Run `loci index <path>` once, then prefer
`loci outline → loci get` over reading files directly.
```

For Claude specifically, add this to your `CLAUDE.md`:

```
**MANDATORY**: Use the `loci` skill at the start of any non-trivial codebase task.
loci is auto-indexed at session start. Prefer `loci outline → get` over
Read/Grep/Explore for any indexed repo.
```

## Claude Code integration

loci is most useful inside Claude Code, where it auto-indexes your repo at session start and injects context into subagent prompts. The hooks and skill files that wire this up live in `.claude/` in this repo.

**Install**

```bash
python3 .claude/install-hooks.sh
```

This symlinks the hooks and skill files into `~/.claude/` and patches `~/.claude/settings.json` to register them. Restart Claude Code after running it.

**What gets installed**

| Component | Location | Effect |
|---|---|---|
| `loci-session-start.sh` | `~/.claude/hooks/` | Runs `loci index --incremental` on session open/resume |
| `loci-agent-inject.sh` | `~/.claude/hooks/` | Injects the skill into subagent prompts before `Agent` tool calls |
| `SKILL.md` | `~/.claude/skills/loci/` | The agent workflow guide Claude loads via the `loci` skill |
| `summarizer-prompt.md` | `~/.claude/skills/loci/` | Prompt used by the auto-summarize workflow |

## Codex integration

loci can also auto-index repos inside Codex so symbol navigation is ready before the first real code task. The Codex hooks live in `.codex/`.

**Prerequisites**

- loci installed (`pip install loci`)
- Codex using the default `~/.codex` home
- root direnv Python available at `~/.direnv/python-*`

**Install**

```bash
python3 .codex/install-hooks.py
```

This symlinks the repo hooks into `~/.codex/hooks/` and patches `~/.codex/hooks.json` to register the `SessionStart` hook. Restart Codex after running it.

The session-start hook sources the shared root direnv Python environment before resolving `loci`, so installing `loci` into that root environment is the intended setup.

**What gets installed**

| Component | Location | Effect |
|---|---|---|
| `loci-session-start.sh` | `~/.codex/hooks/` | Runs `loci index --incremental` and injects a context line telling Codex the repo is indexed |

## Development

```bash
# Install with dev deps
pip install -e ".[dev]"

# Run tests
python -m pytest tests/
```

## License

MIT
