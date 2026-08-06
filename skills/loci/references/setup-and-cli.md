# Setup and CLI fallback

## Contents

- MCP host setup and store identity
- Temporary CLI commands and limitations

Prefer MCP for normal work. Configure it before relying on the CLI.

## MCP host setup

For Claude Code:

```bash
loci store init --base-dir "$HOME/.claude/loci-index" --namespace claude
claude mcp add loci -s local -e LOCI_BASE_DIR="$HOME/.claude/loci-index" LOCI_STORE_NAMESPACE=claude -- loci-mcp
claude mcp get loci
```

For Codex:

```bash
loci store init --base-dir "$HOME/.codex/loci-index" --namespace codex
codex mcp add --env LOCI_BASE_DIR="$HOME/.codex/loci-index" --env LOCI_STORE_NAMESPACE=codex loci -- loci-mcp
codex mcp get --json loci
```

MCP storage is process-bound. Set both `LOCI_BASE_DIR` and
`LOCI_STORE_NAMESPACE`; the namespace must match the store's versioned
identity marker. The server refuses missing configuration, cross-namespace
reuse, and silent adoption of a populated legacy store. After verifying
ownership of an existing unmarked store, initialize it once with:

```bash
loci store init --base-dir <absolute-path> --namespace <name> --adopt-existing
```

If `loci-mcp` is not on `PATH`, fix the install or wrapper symlink first. For
the repo-local install, `~/.local/bin/loci-mcp` should resolve to
`.shared/loci-mcp-wrapper.sh`. Use `/absolute/path/to/python -m
loci.mcp_server` only as a diagnostic fallback, never as permanent MCP
client configuration.

After adding MCP, tell the user that a fresh agent session may be required
before new `loci_*` tools become visible.

When MCP tools are not visible, announce once:

```text
loci MCP is not configured in this session; I am adding it as a local stdio MCP server with command `loci-mcp`. A fresh agent session may be required before the `loci_*` tools are visible.
```

## CLI fallback

Use these only while MCP was just configured but is not visible, when MCP
configuration fails, or when the user explicitly asks to continue without a
restart. Choose the actual repository/workspace path.

| Command | Use when |
| --- | --- |
| `loci index <path> [--incremental]` | First indexing or explicit CLI refresh |
| `loci outline <path> [--file <rel>]` | Getting symbols and IDs |
| `loci get <id> [<id> ...] --repo <path> [--context N]` | Fetching symbol source |
| `loci search <query> --repo <path> [--kind K] [--lang L]` | Finding symbols by name or concept |
| `loci file <rel_path> --repo <path> [--start N] [--end N]` | Reading non-symbol files |
| `loci grep <pattern> --repo <path>` | Hunting string literals, errors, or config keys |
| `loci verify <path>` | Checking index integrity and content drift |
| `loci stats [--repo <path>] [--pretty]` | Checking token savings |
| `loci list` | Listing indexed repos |
| `loci invalidate <path>` | Clearing stale cache |
| `loci store health [--offset N] [--limit N] [--max-catalog-bytes N] [--max-index-bytes N] [--max-probe-paths N] [--max-probe-bytes N]` | Diagnosing store health without repair, refresh, rewrite, prune, or cleanup |
| `loci store repair-catalog [--max-repositories N] [--max-total-index-bytes N]` | Explicitly repairing legacy, corrupt, or interrupted inventory |

There is no CLI import, reference, or call command. Use the graph MCP tools
for dependency, symbol-reference, and call traversal and diagnostics.

Use the MCP utility `loci_list` to list repositories present in the active
store; use `loci_stats` for structured retrieval/savings statistics and
`loci_verify` for index integrity/content-drift checks.
