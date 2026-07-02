# loci

A local MCP server for LLM agent code navigation. loci parses your codebase into a byte-precise symbol index so an agent can fetch exactly the code it needs — no full-file reads, no grep loops.

**60–90% token savings** on typical codebase navigation tasks.

## How it works

loci uses [tree-sitter](https://tree-sitter.github.io/tree-sitter/) to parse source files into an AST, extracts symbols (functions, classes, methods, constants) with their byte offsets, and stores them in a local index. Retrieval is a direct byte-range read — no scanning.

The MCP workflow replaces 15–20 iterative Read/Grep calls with a small tool chain:

```text
loci_index -> loci_outline/loci_search/loci_grep -> loci_get/loci_file -> loci_verify
```

The CLI still exists for debugging, scripts, and migration safety, but MCP is the production interface.

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

For repo-local dogfooding, install the tracked wrappers so both commands are
globally resolvable. The wrappers honor an explicit `LOCI_BASE_DIR`; otherwise
Claude Code uses `~/.claude/loci-index` via `CLAUDECODE=1`, and bare terminal
calls fall through to the Python store resolver. Codex and Claude MCP configs
should pass their agent-specific stores explicitly:

```bash
mkdir -p ~/.local/bin
ln -sf "$PWD/.shared/loci-wrapper.sh" ~/.local/bin/loci
ln -sf "$PWD/.shared/loci-mcp-wrapper.sh" ~/.local/bin/loci-mcp
```

This installs both command entrypoints:

| Command | Status | Purpose |
|---|---|---|
| `loci-mcp` | Primary | Local stdio MCP server for agents |
| `loci` | Legacy/debug | CLI for manual checks, scripts, and migration safety |

## MCP Setup

### Codex

Codex has a built-in MCP server manager. After installing loci, register the local stdio server:

```bash
codex mcp add --env LOCI_BASE_DIR="$HOME/.codex/loci-index" loci -- loci-mcp
codex mcp get --json loci
```

If `loci-mcp` is not on `PATH`, fix the install first. For repo-local
dogfooding, `~/.local/bin/loci-mcp` should symlink to
`.shared/loci-mcp-wrapper.sh`.

Direct `python -m loci.mcp_server` registration is useful for diagnostics, but
it should not be the permanent local config because it bypasses the tracked
wrapper.

Custom cache location:

```bash
codex mcp add --env LOCI_BASE_DIR=/absolute/path/to/.codeindex loci -- loci-mcp
```

### Claude Code

Claude Code has a built-in MCP server manager. After installing loci, register the local stdio server:

```bash
claude mcp add loci -s local -e LOCI_BASE_DIR="$HOME/.claude/loci-index" -- loci-mcp
claude mcp get loci
```

If `loci-mcp` is not on `PATH`, fix the install first. For repo-local
dogfooding, `~/.local/bin/loci-mcp` should symlink to
`.shared/loci-mcp-wrapper.sh`.

Direct `python -m loci.mcp_server` registration is useful for diagnostics, but
it should not be the permanent local config because it bypasses the tracked
wrapper.

Claude can also load MCP servers from config JSON. For a one-off launch:

```bash
claude --mcp-config '{"mcpServers":{"loci":{"command":"loci-mcp","args":[],"env":{"LOCI_BASE_DIR":"/absolute/path/to/.claude/loci-index"}}}}'
```

Or put the same config in a JSON file and pass the file path:

```json
{
  "mcpServers": {
    "loci": {
      "command": "loci-mcp",
      "args": [],
      "env": {
        "LOCI_BASE_DIR": "/absolute/path/to/.claude/loci-index"
      }
    }
  }
}
```

```bash
claude --mcp-config /absolute/path/to/loci-mcp.json
```

The diagnostic JSON form for the Python module is:

```json
{
  "mcpServers": {
    "loci": {
      "command": "/absolute/path/to/python",
      "args": ["-m", "loci.mcp_server"]
    }
  }
}
```

### Generic stdio MCP clients

For clients that use `mcpServers` JSON, configure the server as a local stdio process:

```json
{
  "mcpServers": {
    "loci": {
      "command": "loci-mcp",
      "args": [],
      "env": {
        "LOCI_BASE_DIR": "/absolute/path/to/.codeindex"
      }
    }
  }
}
```

`LOCI_BASE_DIR` is optional. If omitted, loci first looks for a configured
Codex MCP `LOCI_BASE_DIR`, then an existing `~/.codex/loci-index`, then falls
back to `~/.codeindex`.

### MCP Tools

MCP read tools refresh stale indexes before returning cached data. `loci_index`
still performs explicit indexing, while `loci_outline`, `loci_search`,
`loci_get`, `loci_file`, and `loci_grep` first check the indexed file hashes
against the current repository and run a locked incremental refresh if needed.

| Tool | Purpose |
|---|---|
| `loci_index` | Index a local repo path, optionally incrementally |
| `loci_outline` | Return indexed symbols grouped by file |
| `loci_search` | Search indexed symbols by query |
| `loci_get` | Return exact source for one or more symbol IDs |
| `loci_file` | Return cached file content with optional line range |
| `loci_grep` | Regex-search cached files |
| `loci_verify` | Verify index integrity and content drift |
| `loci_list` | List indexed repos |
| `loci_stats` | Return structured retrieval savings stats |
| `loci_analyze` | Return structured search and extraction diagnostics |

## CLI Usage

The CLI is retained as legacy/debug tooling. New production agent workflows should use MCP.

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

# Human token savings analytics
loci stats
loci stats --pretty
loci stats --repo /path/to/repo
```

## Symbol fields

Every symbol carries: `id`, `name`, `qualified_name`, `kind`, `language`, `file_path`, `byte_offset`, `byte_length`, `line`, `end_line`, `signature`, `docstring`, `summary`, `keywords`, `decorators`, `content_hash`.

## Analytics

loci logs every search and get to a session file. The `loci_analyze` MCP tool
reads that log and surfaces actionable findings:

| Finding type | What it means |
|---|---|
| `search_miss` | Symbol exists but search returned nothing — fix keyword extraction |
| `search_blind_spot` | A symbol kind is never surfaced by search |
| `search_ranking_poor` | Correct symbol exists but ranked too low |
| `poor_extraction` | High refetch rate on a symbol kind |
| `refetch_hotspot` | Same symbol fetched repeatedly in a session |
| `kind_dead_weight` | A symbol kind is indexed but never retrieved |

For a shell or tmux stats readout, use `loci stats --pretty`. Without
`LOCI_BASE_DIR`, CLI stats prefer the configured Codex MCP store when it is
discoverable. Set `LOCI_BASE_DIR=/path/to/store` to inspect a specific store.

## Agent configuration

For loci to be useful, your agent needs to know it exists and how to use it. The full workflow guide is in `skills/loci/SKILL.md` — paste it into your system prompt or agent instructions if your agent does not load skills automatically.

The one-line version to add to any agent's instructions:

```
Use loci for codebase navigation. Prefer MCP tools (`loci_index`,
`loci_outline`/`loci_search`, then `loci_get`) over reading files directly.
If MCP is unavailable, configure the local stdio MCP server first. Use the
`loci` CLI only as a temporary bridge until the agent runtime can see the MCP
tools.
```

For Claude specifically, add this to your `CLAUDE.md`:

```
**MANDATORY**: Use the `loci` skill at the start of any non-trivial codebase task.
Prefer the local `loci` MCP server. If MCP tools are not visible, configure
loci first with `claude mcp add loci -s local -e LOCI_BASE_DIR="$HOME/.claude/loci-index" -- loci-mcp` and `claude mcp get loci`.
Tell the user a fresh Claude session may be required before the new `loci_*`
tools are visible. Use `loci` CLI fallback only as a temporary bridge.
```

## Claude Code integration

loci is most useful inside Claude Code, where it auto-indexes your repo at session start and injects context into subagent prompts. The hooks live in `.claude/`; the reusable skill lives in `skills/loci/` and is symlinked into Claude.

The Claude hooks do not silently mutate Claude MCP config during session start. They keep CLI bridge tooling available, and they instruct Claude to configure MCP first when the `loci_*` tools are not visible.

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

## Codex integration

loci can run as a local MCP server inside Codex. This is the preferred Codex integration.

```bash
codex mcp add --env LOCI_BASE_DIR="$HOME/.codex/loci-index" loci -- loci-mcp
codex mcp get --json loci
```

The older Codex hooks in `.codex/` can still auto-index repos and inject a context line, but they are now optional CLI-era compatibility tooling.

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
| `loci-session-start.sh` | `~/.codex/hooks/` | Runs CLI `loci index --incremental` and injects a context line telling Codex the repo is indexed |

## Development

```bash
# Install with dev deps
pip install -e ".[dev]"

# Run tests
python -m pytest tests/
```

## License

MIT
