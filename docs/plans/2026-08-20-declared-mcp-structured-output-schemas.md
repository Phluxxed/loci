# Plan: Declare Structured Output Schemas for Every Loci MCP Tool

**Status:** Ready for implementation  
**Date:** 2026-08-20  
**Repository:** `/Users/brummerv/loci`

## Objective

Make every applicable Loci MCP tool advertise and enforce its established
structured result contract. The current server registers 20 tools and the MCP
SDK reports `output_schema=None` for all 20 because their handlers are annotated
only as `CallToolResult`.

Completion means all 20 tools expose a non-null `outputSchema` from
`tools/list`, successful `structuredContent` is validated against the declared
tool-specific Pydantic model, and the existing error result remains an
object-root payload of this exact shape:

```json
{"error":{"code":"...","message":"...","details":{}}}
```

The first checkpoint is a complete `loci_file` vertical slice. It must prove
schema advertisement, validation of a real success payload, validation of the
real structured error payload, and a typed `CallToolResult` visible to an MCP
client before the pattern is applied to the other 19 tools.

## Boundaries

### Included

- Strict Pydantic output models for every stable object, list item, and
  envelope returned by the 20 MCP tools.
- MCP SDK 2.x `Annotated[CallToolResult, OutputModel]` handler annotations.
- One shared structured error model and a per-tool object-root union of that
  error envelope with the tool's success envelope.
- Focused contract, handler, stdio, and host-visible acceptance tests.
- Narrow contract documentation updates if the model inventory reveals a
  payload fact not already documented.

### Excluded

- Tool names, inputs, descriptions, success payload keys, error keys, and
  error semantics.
- Service, storage, indexing, graph, CLI, or transport redesign.
- Converting handlers to return Pydantic objects instead of the existing
  explicit `CallToolResult` wire values.
- Optional `TypedDict` output models. MCP Python SDK 2.0 currently
  materializes omitted optional `TypedDict` fields as `null`; use strict
  Pydantic models so omitted and nullable remain distinct.
- Independent review, broad regression testing, or implementation work beyond
  this plan. Those require separate authorization.

## Current evidence and governing SDK behavior

- `pyproject.toml` declares `mcp>=2,<3`; the current environment resolves
  `mcp==2.0.0`.
- `src/loci/mcp_server.py:create_server` registers exactly 20 functions with
  `@mcp.tool()`. Every function returns an explicit `CallToolResult` through
  `_handle_loci_error()` and `_success()`.
- `_success()` places the service dictionary unchanged in
  `structured_content`; `_handle_loci_error()` returns `is_error=True` and
  `structured_content={"error": exc.to_dict()}`.
- In MCP Python SDK 2.0, a bare `CallToolResult` disables output schema
  derivation. `Annotated[CallToolResult, SomePydanticModel]` supplies the model
  used both for `tools/list.outputSchema` and result conversion/validation
  while preserving explicit `CallToolResult` pass-through.
- The output annotation therefore has to describe both possible
  `structuredContent` roots. Annotating only the success model would make a
  legitimate Loci error fail server-side output validation.
- Existing service and MCP tests are the executable wire-contract authority;
  the Loci tool-contract documentation supplies the bounded-evidence semantics.

Before editing, re-run the 20-tool inventory and inspect the installed SDK's
`func_metadata()` / result conversion behavior. If a newer 2.x SDK deliberately
changes the `Annotated[CallToolResult, Model]` contract, adapt to that supported
mechanism without changing Loci's wire payloads.

## Files and symbols

Expected production changes:

- Add `src/loci/mcp_output_models.py` for the strict output-contract model tree,
  shared JSON value aliases, `LociErrorBody`, `LociErrorOutput`, success
  envelopes, and per-tool success-or-error aliases.
- Update `src/loci/mcp_server.py:create_server` return annotations for all 20
  nested tool functions. Preserve `LociMCP.call_tool`,
  `_normalize_repository_arguments`, `_handle_loci_error`, and `_success`
  behavior.

Expected focused test changes:

- Add `tests/test_mcp_output_schemas.py` for model validation, `tools/list`
  output schemas, real tool calls, and the exhaustive no-missing-schema
  assertion.
- Extend the existing real-stdio seam in `tests/test_mcp_server.py` only for
  the representative client-visible `loci_file` result and error assertions.
- Reuse payload fixtures/assertions from `tests/test_mcp_server.py`,
  `tests/test_call_mcp.py`, and `tests/test_symbol_reference_mcp.py`; change
  those files only if their focused helpers are the clearest place to validate
  the corresponding real payload.
- Update `skills/loci/references/tool-contracts.md` only if needed to record a
  contract detail exposed by the schemas; do not duplicate generated JSON
  Schema there.

## Modeling rules

1. Base every object model on one local strict base with
   `ConfigDict(extra="forbid", strict=True)`. Declare every established key;
   do not use `dict[str, Any]` as an escape hatch for a known object.
2. Use `Field(default_factory=list)` only where the wire contract always emits
   a list and construction needs a default. Use `T | None` only where `null` is
   a valid emitted value. An omittable field must remain omittable rather than
   being synthesized as `null`.
3. Model deliberately open JSON bags only at their actual contract seam, such
   as `error.details` or graph extension attributes, with a recursive
   `JSONValue` alias or a dedicated `RootModel`; strictness still applies to
   the containing known object.
4. Define `LociErrorBody(code: str, message: str, details: dict[str,
   JSONValue])` and `LociErrorOutput(error: LociErrorBody)` once.
5. For each tool define a named success model and a named union alias, for
   example `LociFileOutput = LociFileSuccess | LociErrorOutput`. Annotate the
   handler as `Annotated[CallToolResult, LociFileOutput]`. The resulting JSON
   Schema must be an object-root `anyOf`/`oneOf` whose branches are the exact
   success object and the exact `{error: ...}` object. Do not introduce a
   `result` wrapper or a discriminator key.
6. Keep reusable nested contracts reusable: coverage/exclusions, graph nodes
   and edges, diagnostics, pagination, bounds, record resolution/support,
   symbols, repositories, and store descriptors should each have one model
   definition shared by the applicable envelopes.
7. Validate models against representative payloads produced by the real
   service/tool paths, including empty collections and nullable/omitted cases;
   schema generation alone is not proof of wire compatibility.

## Complete 20-tool contract inventory

The implementation must map every row to a named success model plus
`LociErrorOutput`. Inspect the cited service function and its existing focused
tests to enumerate every nested field before writing the model; completion of
a row means a real representative payload validates with no coercion and an
unknown known-object field is rejected.

| Tool | Success root / reusable contract | Contract authority |
| --- | --- | --- |
| `loci_file` | file path, content, returned line bounds and byte/token metadata exactly as emitted | `service.get_cached_file`; file tests in `tests/test_mcp_server.py` |
| `loci_index` | index summary, extraction/graph counts and coverage data | `service.index_repo`; index assertions in MCP/service tests |
| `loci_outline` | `{files: [{file, symbols: [...]}]}` | `service.outline_repo`; outline MCP tests |
| `loci_get` | `{symbols: [...]}` with exact source/location/signature metadata | `service.get_symbols`; get MCP tests |
| `loci_search` | `{symbols: [...], coverage: Coverage}` | `service.search_symbols_result`; scoped-search tests |
| `loci_grep` | `{matches: [...], coverage: Coverage}` | `service.grep_repo_result`; grep tests |
| `loci_graph_anchors` | anchor selection, counts, budget, diagnostics | `service.graph_anchors`; graph anchor contracts/tests |
| `loci_graph_neighbors` | exact nodes/edges and diagnostics returned for seeds | `service.graph_neighbors`; neighbor tests |
| `loci_graph_traverse_neighbors` | filtered neighbor envelope, filters/bounds, omission diagnostics | `service.graph_traverse_neighbors`; traversal tests |
| `loci_graph_paths` | paths, exact evidence, counts/budget/pagination/diagnostics | `service.graph_paths`; path contract tests |
| `loci_graph_retrieve` | anchors plus accepted/rejected paths, answerability/budget diagnostics | `service.graph_retrieve`; retrieval tests |
| `loci_graph_health` | schema version, repo, status, profiles, graph counts, diagnostics | `service.graph_health`; health tests |
| `loci_graph_imports` | bounded import records, counts/support/pagination | `service.graph_imports`; import MCP/contract tests |
| `loci_graph_references` | bounded reference records, counts/support/pagination | `service.graph_references`; symbol-reference MCP/contract tests |
| `loci_graph_calls` | bounded call records, counts/support/pagination | `service.graph_calls`; call MCP/contract tests |
| `loci_verify` | integrity/freshness verification summary | `service.verify_repo`; verify MCP tests |
| `loci_list` | `{repos: [RepositorySummary, ...]}` | `service.list_repos`; list MCP tests |
| `loci_store_health` | status, complete, items, counts, pagination, bounds, diagnostics | `service.store_health`; `tests/storage/test_store_health.py` and MCP tests |
| `loci_stats` | period/store/retrieval/miss and savings statistics | `service.session_stats`; stats MCP tests |
| `loci_analyze` | usage-analysis period, summary, findings and recommendations | `service.analyze_usage`; analyze MCP/service tests |

## Ordered work packages

### 1. Freeze the live payload inventory

Create a temporary implementation checklist from the table above. For every
tool, trace its service return construction and at least one existing success
assertion. Record required, nullable, omittable, literal/enum, and deliberately
open fields, including empty and bounded/paginated forms. Compare graph nested
objects to their `to_dict()` implementations instead of guessing from names.

Completion criterion: all 20 success roots and every reused nested object have
an evidence location, and no model field is based only on an example that may
have omitted another valid branch.

### 2. Build the shared error contract and `loci_file` tracer bullet

Add the strict base, recursive JSON value type, shared error models, and the
complete `loci_file` success model in `src/loci/mcp_output_models.py`. Change
only `create_server.loci_file` to return
`Annotated[CallToolResult, LociFileOutput]`.

Add focused tests that:

- call `create_server().list_tools()` and assert `loci_file.output_schema` is
  non-null, object-root, and has both success and error branches;
- call `loci_file` against a real indexed disposable repository and validate
  its actual `structured_content` with `LociFileOutput`;
- force a real `LociError` (for example a missing cached file), assert
  `is_error is True`, and validate the unchanged
  `{error: {code, message, details}}` payload against the same output union;
- assert the client receives a `CallToolResult` whose
  `structured_content` is the typed-schema-conforming object and whose wire
  JSON contains `structuredContent` without a new wrapper;
- directly exercise SDK output conversion with a malformed success payload and
  assert server-side validation rejects it, proving the schema is enforced and
  not merely advertised.

Completion criterion: this slice passes through the real handler and MCP SDK
conversion path; both legitimate branches validate, malformed output fails,
and the wire contract is byte-for-key equivalent to the pre-schema shape.

### 3. Roll out repository retrieval contracts

Add and annotate `loci_index`, `loci_outline`, `loci_get`, `loci_search`,
`loci_grep`, `loci_verify`, and `loci_list`. Reuse symbol, coverage,
exclusion, repository, and verification models rather than cloning shapes.

Targeted tests must validate a real success payload per distinct envelope,
the existing error union on at least one tool in this group, and each listed
tool's non-null advertised schema.

Completion criterion: all seven handlers use their named
`Annotated[CallToolResult, OutputAlias]`, and their current focused MCP success
and error payloads validate strictly without service changes.

### 4. Roll out graph contracts

Add and annotate `loci_graph_anchors`, `loci_graph_neighbors`,
`loci_graph_traverse_neighbors`, `loci_graph_paths`, `loci_graph_retrieve`,
`loci_graph_health`, `loci_graph_imports`, `loci_graph_references`, and
`loci_graph_calls`.

Model graph nodes, attributes, edges/evidence, anchors/reasons, diagnostics,
budgets, filters, pagination, support, resolution records, accepted paths, and
rejected paths from their contract classes and `to_dict()` methods. Exercise
resolved, unresolved, empty, paginated, and diagnostic-bearing fixtures where
those are distinct valid shapes.

Completion criterion: all nine graph handlers advertise schemas and every
existing representative graph MCP payload validates, including imports,
references, and calls for both resolution states.

### 5. Roll out store and telemetry contracts

Add and annotate `loci_store_health`, `loci_stats`, and `loci_analyze`. Cover
healthy, unhealthy, incomplete, stale/missing/corrupt/overlapping store-health
branches already represented by focused fixtures. Preserve deliberate open
detail bags while strictly modeling their enclosing reason, probe, item,
count, pagination, bound, period, finding, and recommendation objects.

Completion criterion: all three handlers advertise schemas and real payloads
for their contract branches validate without null materialization or new keys.

### 6. Prove exhaustive advertisement and the shipped boundary

Add one inventory assertion derived from `create_server().list_tools()`:

```python
assert len(tools) == 20
assert {tool.name for tool in tools} == EXPECTED_LOCI_TOOLS
assert not [tool.name for tool in tools if tool.output_schema is None]
```

Also assert each output schema accepts an object at its root and contains the
error branch. Launch the actual `python -m loci.mcp_server` / `loci-mcp` stdio
entrypoint with an isolated disposable store and use the MCP 2.x client to list
tools and call the representative `loci_file` success and error paths.

Completion criterion: the real stdio server advertises the same 20 non-null
schemas and returns unchanged typed-schema-conforming `CallToolResult` values
for `loci_file` success and error.

### 7. Fresh-host acceptance, only for host typing

After the subprocess acceptance is green, start a fresh Codex host/session
only if the active host caches MCP tool metadata. Reconnect the installed local
`loci-mcp`, inspect the freshly fetched `tools/list`, and make one `loci_file`
call. Confirm Codex exposes the result as typed structured content rather than
an untyped/null-schema result. Do not use a host restart as a substitute for
the deterministic SDK and stdio tests.

Completion criterion: fresh-host tool metadata shows `loci_file.outputSchema`
and the host-visible call result retains its typed object fields. If the host
does not cache metadata, record that the stdio acceptance already proves the
boundary and skip the restart.

## Targeted verification

Run only the directly relevant checks:

```bash
uv run pytest -q tests/test_mcp_output_schemas.py
uv run pytest -q \
  tests/test_mcp_server.py \
  tests/test_call_mcp.py \
  tests/test_symbol_reference_mcp.py
```

The first command owns exhaustive schema/model coverage. The existing focused
MCP files prove that declared validation did not change established payloads.
Use the isolated real-stdio case from work package 6 as the shipped-boundary
acceptance. If one of these checks exposes a concrete schema mismatch, correct
the model or a proven deliberate wire-contract migration and rerun only the
same targeted check. Stop when these pass; do not initiate an independent
review or broader suite.

## Acceptance criteria

- Exactly 20 expected Loci MCP tools are registered, and no applicable tool has
  `outputSchema=None`.
- Every handler uses the supported MCP SDK 2.x
  `Annotated[CallToolResult, OutputModel]` mechanism.
- Every declared schema covers both its exact success object root and the exact
  `LociErrorOutput` object root.
- Existing success `structuredContent` keys, nesting, omission/null behavior,
  values, and list/object roots are unchanged.
- Existing failures remain `CallToolResult(is_error=True)` with text content
  plus `structuredContent.error.code`, `.message`, and `.details`.
- Pydantic models are strict for known objects; deliberately extensible JSON
  bags are open only at documented contract seams.
- A malformed real success result is rejected by server-side SDK output
  validation.
- Representative real success payloads for all 20 tools validate against their
  declared models, including distinct graph and store-health branches.
- The shipped stdio server advertises all 20 schemas and returns a typed,
  unchanged `loci_file` success and error result to an MCP client.
- A fresh Codex host observes typed output when metadata caching makes that
  additional check necessary.
- Only the focused schema and MCP acceptance checks are required; independent
  review is outside this plan.

## Handoff prompt

> Implement
> `docs/plans/2026-08-20-declared-mcp-structured-output-schemas.md`. Start with
> the `loci_file` tracer bullet and prove both success and structured error
> validation before rolling the exact pattern across all remaining tools.
> Preserve every existing wire contract, use strict Pydantic models and MCP SDK
> 2.x `Annotated[CallToolResult, OutputModel]`, and stop after the plan's
> targeted acceptance checks pass. Do not start an independent review.
