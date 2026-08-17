# Plan: Migrate Loci to MCP Python SDK v2

**Status:** Ready for implementation  
**Date:** 2026-08-17  
**Repository:** `/Users/brummerv/loci`

## Objective

Move Loci from `mcp>=1.27,<2` to the stable MCP Python SDK v2 line while
preserving its public tool schemas, structured success/error results, local
stdio deployment, store isolation, and advisory `path` compatibility.

Completion means the shipped `loci-mcp` process serves one representative
index/read/error workflow over stdio on the modern `2026-07-28` protocol and
still answers a focused legacy `initialize` client. Passing handler-level or
legacy-only tests is insufficient.

## Start here

1. Read this file and the live repository instructions, if any.
2. Inspect the current v2 API installed by the lock update before finalizing
   annotations or transport construction; use the official migration guide as
   the authority for SDK behavior.
3. Keep the migration inside the MCP boundary and its focused tests. Preserve
   service, store, graph, CLI, and tool contracts unless a v2 incompatibility
   directly requires a change.
4. Stop after the acceptance checks below pass. A separate review or broad
   regression phase requires Vik's explicit approval.

## Current state

- `pyproject.toml` pins `mcp>=1.27,<2`; `uv.lock` currently resolves `mcp`
  `1.28.0`.
- `src/loci/mcp_server.py` is a high-level decorator server, not a low-level
  JSON-RPC implementation.
- `LociMCP(FastMCP)` overrides `call_tool()` solely to normalize the advisory
  legacy `path` argument to canonical `repo` before schema validation.
- All tools return explicit `CallToolResult` values with structured payloads.
- The production transport is local stdio through `loci-mcp` / 
  `python -m loci.mcp_server`.
- `tests/test_mcp_server.py`, `tests/test_call_mcp.py`, and
  `tests/test_symbol_reference_mcp.py` use v1 `ClientSession` plus explicit
  `initialize()`. They prove the legacy protocol era, not `2026-07-28`.
- No Loci tool uses roots, sampling, elicitation, protocol logging, HTTP,
  OAuth, WebSockets, or the experimental Tasks API.
- The repository was clean and one commit ahead of `origin/master` when this
  plan was written. Recheck before editing and preserve any newer user work.

## Scope

### Included

- Upgrade the Python dependency and lockfile to `mcp>=2,<3`.
- Rename and re-import high-level server types for v2.
- Adapt `LociMCP.call_tool()` to the v2 signature and result contract without
  weakening pre-validation argument normalization.
- Move Python-side MCP model attribute access to snake_case.
- Update focused MCP subprocess tests and add a modern-protocol stdio proof.
- Update the existing MCP design note where it still describes v1 as the
  selected stable line.
- Verify the installed/local `loci-mcp` producer-consumer boundary.

### Excluded

- New tools or changes to existing tool names, arguments, or payload shapes.
- HTTP transport, remote serving, authentication, sessions, or daemon work.
- MRTR, `Resolve`, roots, sampling, elicitation, subscriptions, or Tasks.
- Store format, namespace, indexing, retrieval, graph, or retention changes.
- Removing advisory `path` compatibility.
- Refactoring the large MCP test module except where v2 requires it.
- Repository-wide review or reassurance testing after focused acceptance is
  green.

## Upstream facts that govern the migration

- SDK `2.0.0` is the Python package major; the wire protocol revision is
  date-versioned `2026-07-28`.
- `FastMCP` is now `MCPServer`; `mcp.server.fastmcp.*` moved to
  `mcp.server.mcpserver.*`.
- `ToolError` moves to `mcp.server.mcpserver.exceptions`.
- Python attributes on protocol models are snake_case: `structured_content`,
  `is_error`, and `input_schema`. Wire JSON remains camelCase. Old camelCase
  constructor keywords are accepted, but attribute access is not.
- High-level decorators and explicit `CallToolResult` pass-through remain
  supported.
- `MCPServer.call_tool()` now accepts optional `context` and returns a
  `CallToolResult` or, for input-requiring tools, `InputRequiredResult`.
- The same v2 server can serve modern and legacy protocol clients. A v2
  `Client` negotiates the modern era by default; direct `ClientSession` plus
  `initialize()` exercises the legacy era.
- Synchronous tool handlers now run in worker threads and may run
  concurrently. Loci's handlers call store/service code synchronously, so the
  migration must prove the representative real workflow rather than assume
  the scheduling change is harmless.

Primary sources:

- [Python SDK README](https://github.com/modelcontextprotocol/python-sdk/blob/main/README.md)
- [What's new in v2](https://github.com/modelcontextprotocol/python-sdk/blob/main/docs/whats-new.md)
- [v1-to-v2 migration guide](https://github.com/modelcontextprotocol/python-sdk/blob/main/docs/migration.md)
- [`2026-07-28` protocol versioning](https://github.com/modelcontextprotocol/modelcontextprotocol/blob/main/docs/specification/2026-07-28/basic/versioning.mdx)

## Files expected to change

- `pyproject.toml`
- `uv.lock`
- `src/loci/mcp_server.py`
- `tests/test_mcp_server.py`
- `tests/test_call_mcp.py`
- `tests/test_symbol_reference_mcp.py`
- `docs/design/2026-06-23-mcp-native-loci-design.md`

Add a small focused test file only if separating modern/legacy transport proof
materially improves clarity. Do not split existing tests merely to make the
diff look cleaner.

## Implementation sequence

### 1. Lock the v2 dependency

Change the declared range to `mcp>=2,<3` and update only the dependency state
needed to resolve it.

Suggested command:

```bash
uv lock --upgrade-package mcp
uv sync
```

Completion criterion: `uv run python -c 'import mcp; print(mcp.__version__)'`
or equivalent package metadata inspection reports a 2.x version, and the
lockfile no longer carries the `<2` constraint.

### 2. Add the modern/legacy protocol acceptance seam

Before making the server pass, add or adapt focused tests so they distinguish:

- **modern:** launch the real `python -m loci.mcp_server` subprocess over
  stdio with the v2 high-level `Client` in its default/auto mode; assert the
  negotiated protocol is `2026-07-28`;
- **legacy:** retain one `ClientSession` + `initialize()` subprocess case and
  assert the existing public behavior still works.

The modern case must call, at minimum:

1. `loci_index` against a disposable repository and explicitly isolated
   `LOCI_BASE_DIR`/`LOCI_STORE_NAMESPACE`;
2. `loci_outline` or `loci_get` and validate its structured payload after wire
   serialization;
3. one invalid call, such as an unindexed repository or invalid regex, and
   validate `is_error` plus `structured_content.error.code`.

Use the v2 client API that launches a real stdio subprocess. An in-process
`Client(create_server())` may be an additional unit test, but it does not
replace the shipped transport proof.

Completion criterion: the new modern test initially fails for a migration-
specific reason and the retained legacy test still describes the required
compatibility boundary.

### 3. Port the server boundary

In `src/loci/mcp_server.py`:

- replace `FastMCP` with `MCPServer` and update imports;
- update `ToolError` to its v2 module;
- preserve the named server identity and stdio entrypoint;
- adapt `LociMCP.call_tool()` to accept and forward v2's optional context;
- return the result from `super().call_tool()` unchanged;
- keep `_normalize_repository_arguments()` ahead of v2 schema validation;
- use snake_case fields in locally maintained model construction for clarity,
  even where v2 accepts camelCase aliases.

Do not replace the high-level server with the low-level `Server`. Loci depends
on the high-level decorator schema and result-wrapping contract, and v2 retains
that surface.

Completion criterion: importing `loci.mcp_server` succeeds under SDK v2, tool
listing advertises the same names and schemas, canonical `repo` calls work,
legacy `path` calls still normalize, and sending both names returns the same
structured failure.

### 4. Port first-party client and test accessors

Across the three focused MCP test files, replace protocol-model attribute
access:

- `.structuredContent` -> `.structured_content`
- `.isError` -> `.is_error`
- `.inputSchema` -> `.input_schema`

Retain direct `ClientSession` usage only where the test deliberately proves
legacy behavior. Prefer the v2 high-level `Client` for new modern-path tests.

Completion criterion: no maintained Python source or focused MCP test accesses
the three removed camelCase attributes, and the assertions still validate the
same wire-level tool schemas and structured payloads.

### 5. Reconcile the design record

Update `docs/design/2026-06-23-mcp-native-loci-design.md` narrowly:

- record that the later audit occurred on 2026-08-17;
- state that the stable v2 SDK line is now selected;
- preserve the local-stdio-only architecture and all established tool
  contracts.

Treat the original v1 decision as implementation history rather than silently
rewriting why it was reasonable in June.

Completion criterion: the design no longer instructs future agents to pin the
live implementation below v2, while its historical starting-state claims
remain honest.

## Focused verification

Run the smallest directly relevant checks:

```bash
uv run python -m compileall -q src tests
uv run pytest -q \
  tests/test_mcp_server.py \
  tests/test_call_mcp.py \
  tests/test_symbol_reference_mcp.py
```

Then run one explicit shipped-boundary smoke using the actual `loci-mcp`
entrypoint or `python -m loci.mcp_server`, a disposable repository/store, and
the v2 client:

- negotiated protocol: `2026-07-28`;
- `loci_index` succeeds;
- one read result survives serialization and validation;
- one structured tool error survives serialization and validation;
- the server exits cleanly when the client closes.

If the focused checks expose a migration defect, fix it and rerun only the
same focused check. An unexpected failure outside this migration boundary is a
pause point: preserve the state, report the evidence, and ask Vik before
widening scope.

## Acceptance criteria

- `pyproject.toml` and `uv.lock` resolve MCP Python SDK 2.x with `<3`.
- `loci-mcp` starts without v1 compatibility imports.
- All existing Loci tool names and advertised schemas remain stable.
- Success results retain their established structured payloads.
- `LociError` failures remain model-visible `CallToolResult(is_error=True)`
  results with `structured_content.error`.
- Canonical `repo`, advisory legacy `path`, and duplicate-argument rejection
  behave as before.
- A real stdio v2 client negotiates `2026-07-28` and completes the representative
  index/read/error workflow.
- A focused legacy `initialize` client still completes a representative call.
- Test processes use disposable explicit stores and cannot touch an operator
  store.
- The server closes cleanly without leaking a subprocess.
- The focused compile and MCP test commands pass.

## Handoff prompt for a fresh session

> Implement `docs/plans/2026-08-17-mcp-python-sdk-v2-migration.md` in this
> repository. Use current repository evidence and the linked official MCP
> sources. Preserve public Loci tool contracts and store isolation. Stop after
> the plan's focused acceptance checks pass; do not start an independent review
> or broad regression phase without Vik's approval.
