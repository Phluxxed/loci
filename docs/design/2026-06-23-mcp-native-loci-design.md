# loci: MCP-native local server — Design

**Goal:** Make loci a first-class local MCP server for agent code navigation. MCP is the production interface; the CLI is legacy/debug tooling and must not shape the new contract.

**Architecture:** Add a local stdio-only MCP server over a small core service layer. The service layer owns indexing, outline, retrieval, search, file reads, grep, and verification as typed Python functions that return structured values. The MCP server exposes those functions as tools with explicit input/output/error schemas. The CLI remains as legacy/debug tooling, but it is no longer the design center.

**Tech Stack:** Python (existing). MCP transport = local stdio only. MCP SDK = official Python SDK pinned to the stable v1 line (`mcp>=1.27,<2`) unless a later audit says v2 is stable and worth adopting. No HTTP server, daemon lifecycle, auth layer, or remote multi-user model.

---

## Why this doc exists

loci is already agent-owned navigation infrastructure, but its public surface is a command-line interface. That makes agents pay a process/JSON/argv tax and encourages CLI-shaped behavior such as stderr errors, command parsing, and human-oriented compatibility concerns.

The intended production shape is different: an MCP client should launch loci locally over stdio and invoke a small set of tools directly. The model should see stable tool names, clear schemas, and structured failures. The implementation can reuse existing parser/storage machinery, but the public contract should be MCP-native.

## Non-goals

- No remote or HTTP transport.
- No daemon process shared between users or workspaces.
- No authentication or account model.
- No attempt to preserve CLI flags/output as the MCP contract.
- No silent auto-indexing before read tools.
- No broad graph/relationship work in this migration.

## Starting state (audit, 2026-06-23)

Confirmed by source audit before the MCP migration:

- The package exposes only one script entrypoint: `loci = "loci.cli:main"` in `pyproject.toml`.
- There is no MCP implementation in the repo.
- Most read behavior already lives below the CLI in `IndexStore`: `search`, `get_symbol_content`, `get_symbol_context`, `get_file_content`, `grep_files`, `verify_index`, `list_repos`, `analyze`, `apply_summaries`.
- The indexing workflow is still embedded in `cmd_index` in `src/loci/cli.py`.
- CLI commands emit JSON to stdout on success and JSON-ish errors to stderr on failure. MCP should replace this with structured tool results and exceptions.
- Existing tests primarily exercise the CLI subprocess surface. They are useful migration evidence, but they are not the new public contract.

## Implementation state (2026-06-23)

Implemented:

- `pyproject.toml` exposes `loci-mcp = "loci.mcp_server:main"`.
- `src/loci/service.py` owns the MCP-native service layer.
- `src/loci/mcp_server.py` exposes local stdio MCP tools.
- `tests/test_mcp_server.py` launches the server through a real stdio MCP client and verifies tool calls plus structured tool errors.
- The production MCP tool set is `loci_index`, `loci_outline`, `loci_search`, `loci_get`, `loci_file`, `loci_grep`, `loci_verify`, and `loci_list`.
- The CLI remains available as legacy/debug tooling and migration safety, but new production agent workflow should target MCP first.

## Design principles

1. **MCP is the product surface.** Tool names, arguments, outputs, and error semantics are the public API.
2. **Local-only by construction.** The server is launched by the MCP client over stdio and operates on local filesystem paths. Any future remote mode must be a separate design, not a latent requirement.
3. **Core first, interface thin.** Parsing, storage, indexing, and retrieval belong in importable service functions. MCP handlers should validate inputs, call the service, and return results.
4. **Explicit indexing.** Read tools operate on the current cache. If the repo is not indexed or is stale, return a structured error or verification result; do not silently crawl the filesystem.
5. **Structured failures.** Errors must have stable codes and useful context. Avoid stderr-style free text as the only signal.
6. **Small vertical slices.** Ship `index -> outline -> get` first, then fill in the rest of the established workflow.

## Proposed MCP tools

Tool names are prefixed with `loci_` to stay readable in mixed MCP tool lists.

| Tool | Purpose | Initial phase |
|---|---|---|
| `loci_index` | Index a local repo path, optionally incrementally | 1 |
| `loci_outline` | Return indexed symbols grouped by file, optionally filtered to one file | 1 |
| `loci_get` | Return one or more indexed symbol bodies by id | 1 |
| `loci_search` | Rank symbols by query, with optional kind/language filters | 2 |
| `loci_file` | Return cached file content by relative path and optional line range | 2 |
| `loci_grep` | Regex-search cached files | 2 |
| `loci_verify` | Verify index integrity and content drift | 2 |
| `loci_list` | List indexed repositories | 2 |

Maintenance/debug tools are deferred:

- `loci_stats`
- `loci_summarize`
- `loci_analyze`
- `loci_invalidate`

These may belong in MCP, but they are not part of the first production workflow.

## Tool contracts

### `loci_index`

Input:

```json
{
  "path": "/absolute/or/relative/repo/path",
  "incremental": true
}
```

Output:

```json
{
  "path": "/absolute/repo/path",
  "symbols_indexed": 340,
  "files_skipped": 27,
  "languages": {"python": 10, "markdown": 18},
  "warnings": [
    {"file": "src/example.py", "lines": 42, "reason": "0 symbols extracted"}
  ]
}
```

### `loci_outline`

Input:

```json
{
  "path": "/absolute/or/relative/repo/path",
  "file": "optional/relative/path.py"
}
```

Output:

```json
{
  "files": [
    {
      "file": "src/example.py",
      "symbols": [
        {
          "id": "src/example.py::Example#class",
          "name": "Example",
          "kind": "class",
          "line": 10,
          "end_line": 50,
          "signature": "class Example",
          "summary": ""
        }
      ]
    }
  ]
}
```

### `loci_get`

Input:

```json
{
  "repo": "/absolute/or/relative/repo/path",
  "symbol_ids": ["src/example.py::Example#class"],
  "context": 2
}
```

Output:

```json
{
  "symbols": [
    {
      "id": "src/example.py::Example#class",
      "source": "class Example:\n    ...",
      "line": 10,
      "end_line": 50,
      "byte_offset": 120,
      "byte_length": 500,
      "signature": "class Example",
      "kind": "class",
      "language": "python",
      "context_before": [],
      "context_after": []
    }
  ]
}
```

`loci_get` always returns a `symbols` list, even for one id. This is intentionally different from the CLI, whose single-id output is an object. MCP callers benefit from one stable shape. `loci_outline` similarly returns a `files` list. These explicit object wrappers avoid relying on FastMCP's generic list wrapping behavior.

### `loci_search`

Input:

```json
{
  "repo": "/absolute/or/relative/repo/path",
  "query": "add",
  "kind": "function",
  "lang": "python",
  "limit": 20
}
```

Output:

```json
{
  "symbols": [
    {
      "id": "src/example.py::add#function",
      "name": "add",
      "kind": "function",
      "language": "python",
      "score": 42.0
    }
  ]
}
```

### `loci_file`

Input:

```json
{
  "repo": "/absolute/or/relative/repo/path",
  "file_path": "src/example.py",
  "start_line": 10,
  "end_line": 20
}
```

Output:

```json
{
  "file": "src/example.py",
  "content": "def add(x, y):\n    return x + y\n",
  "total_lines": 80,
  "start_line": 10,
  "end_line": 20
}
```

### `loci_grep`

Input:

```json
{
  "repo": "/absolute/or/relative/repo/path",
  "pattern": "def add"
}
```

Output:

```json
{
  "matches": [
    {
      "file": "src/example.py",
      "line": 10,
      "match": "def add(x, y):",
      "context_before": [],
      "context_after": []
    }
  ]
}
```

### `loci_verify`

Input:

```json
{
  "path": "/absolute/or/relative/repo/path"
}
```

Output:

```json
{
  "repo": "/absolute/repo/path",
  "checked": 340,
  "passed": 340,
  "failed": []
}
```

### `loci_list`

Input:

```json
{}
```

Output:

```json
{
  "repos": [
    {
      "cache_key": "repo-cache-key",
      "symbols": 340,
      "path": "/absolute/repo/path"
    }
  ]
}
```

## Error contract

MCP handlers should return tool error results with a stable code and context in `structuredContent.error`. The internal service should raise errors shaped like:

```json
{
  "code": "REPO_NOT_INDEXED",
  "message": "Repository is not indexed",
  "details": {"repo": "/absolute/repo/path"}
}
```

The user-visible text content may summarize the failure, but clients should consume `structuredContent.error` for recovery. Initial error codes:

| Code | Meaning |
|---|---|
| `PATH_NOT_FOUND` | Requested repo/path does not exist |
| `REPO_NOT_INDEXED` | Cache does not contain an index for the repo |
| `SYMBOL_NOT_FOUND` | A requested symbol id is absent from the index |
| `FILE_NOT_FOUND` | A requested cached file is absent |
| `INVALID_REGEX` | Grep pattern cannot compile |
| `INVALID_INPUT` | Tool input fails validation |
| `INDEX_READ_ERROR` | Cache/index data cannot be read |

## Local safety boundaries

- Repo paths are resolved to absolute local paths before indexing or cache lookup.
- File reads through `loci_file` are restricted to the cached `sources/` mirror for the indexed repo.
- `loci_index` keeps the existing skip rules for secrets, virtualenvs, caches, dependency directories, and root `.gitignore` rules.
- MCP never runs shell commands supplied by the caller.
- MCP never writes outside loci's configured cache except when indexing reads source files and mirrors them into the cache.
- `LOCI_BASE_DIR` remains the local cache override for tests and custom installations.

## Project structure

Proposed files:

```text
src/loci/service.py       # MCP-native core operations and errors
src/loci/mcp_server.py    # stdio MCP server and tool registration
tests/test_mcp_server.py  # MCP tool smoke/contract tests
```

Optional later cleanup:

```text
src/loci/cli.py           # legacy adapter, debug-only, or removed
```

## Migration plan

### Phase 1: MCP vertical slice - complete

Implement:

- `loci_index`
- `loci_outline`
- `loci_get`
- service-layer extraction for index, outline, and get
- MCP client smoke test for `index -> outline -> get`

Acceptance:

- A local MCP client can launch the server over stdio.
- The client can index a temp repo, outline it, select a symbol id, and retrieve source.
- Existing parser/storage tests still pass.

### Phase 2: Complete core navigation tools - complete

Implement:

- `loci_search`
- `loci_file`
- `loci_grep`
- `loci_verify`
- `loci_list`

Acceptance:

- MCP tools cover the current agent workflow without invoking the CLI.
- Tool outputs use stable MCP-native shapes.
- Invalid inputs and missing cache cases produce structured errors.

### Phase 3: CLI demotion decision - accepted

Decision:

- Keep CLI as legacy/debug tooling and migration safety.
- Prefer MCP for all new production agent workflows.
- Do not let CLI output shape MCP contracts.
- Add new core production navigation behavior to the service/MCP layer first; CLI parity is optional and explicit.

Acceptance:

- The decision is documented.
- Tests reflect the chosen supported surface.
- README and skill docs point agents at MCP first.

## Testing strategy

- Unit-test service functions directly with `LOCI_BASE_DIR` pointed at a temp directory.
- Add MCP smoke tests using the Python SDK client over stdio.
- Keep parser and storage tests unchanged unless the service extraction reveals real bugs.
- Use CLI tests only as migration safety checks, not as the definition of the new contract.

Verification commands:

```bash
python -m pytest
loci index /Users/brummerv/loci --incremental
loci verify /Users/brummerv/loci
```

After Phase 1 exists, add:

```bash
python -m pytest tests/test_mcp_server.py
```

## Success criteria

- MCP is installable and launchable locally via stdio.
- The core production workflow works without CLI subprocesses: `loci_index -> loci_outline/loci_search/loci_grep -> loci_get/loci_file -> loci_verify/loci_list`.
- Tool schemas are documented and tested.
- Errors are structured and machine-readable.
- No HTTP, daemon, remote, auth, or multi-user complexity is introduced.
- CLI compatibility does not constrain MCP design.

## Open questions

- Should `loci_get` return partial successes for mixed valid/invalid symbol ids, or should any missing symbol fail the whole call?
- Should `loci_index` include a maximum warning count to avoid very large MCP responses?
- Should deferred maintenance tools be exposed under MCP with an explicit `maintenance` naming prefix, or remain CLI-only/debug-only?
