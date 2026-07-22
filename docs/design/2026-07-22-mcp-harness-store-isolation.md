# Spec: MCP Harness Store Isolation

## Objective

Bind every Loci MCP server process to one explicit storage namespace owned by
its launching coding harness. Codex and Claude must not silently read or write
one another's stores, while operators may still configure an intentional shared
store through an explicit common namespace.

## Tech Stack

- Python 3.10+
- MCP Python SDK over local stdio
- JSON metadata and filesystem-backed per-repository indexes
- pytest for unit, subprocess, and MCP integration coverage

## Commands

- Focused tests: `.venv/bin/python -m pytest -q tests/storage/test_store_resolver.py tests/storage/test_store_identity.py tests/test_wrapper_routing.py tests/test_mcp_server.py`
- Service tests: `.venv/bin/python -m pytest -q tests/test_service.py`
- Full tests: `.venv/bin/python -m pytest -q`
- Changed-boundary type check: `uvx pyright --pythonversion 3.11
  src/loci/storage/store_identity.py src/loci/storage/store_resolver.py
  src/loci/mcp_server.py src/loci/cli.py src/loci/service.py`
- Baseline diagnostic: `uvx pyright` (the repository has no configured
  pyright dependency or settings; unrelated existing findings are recorded,
  not folded into this storage change)
- Compile: `.venv/bin/python -m compileall -q src tests`
- Package: `uv build`
- Lockfile: `uv lock --check`

## Project Structure

- `src/loci/storage/`: store selection, identity, and index persistence
- `src/loci/mcp_server.py`: fail-closed MCP process bootstrap
- `src/loci/cli.py`: explicit one-time store initialization/adoption
- `.shared/`: tracked MCP and CLI launch wrappers
- `tests/storage/`: storage contract tests
- `tests/test_mcp_server.py`: fresh-process MCP integration tests
- `tests/test_service.py`: indexing and locking behavior
- `README.md` and `skills/loci/SKILL.md`: supported host registration contract

## Code Style

Use typed dataclasses for immutable validated configuration and structured
machine-readable errors at process and tool boundaries:

```python
@dataclass(frozen=True, slots=True)
class StoreIdentity:
    namespace: str
    store_id: str
```

Keep CLI convenience resolution separate from the stricter MCP bootstrap. Do
not add store-selection parameters to individual MCP tools.

## Testing Strategy

- Unit-test path, namespace, marker, mismatch, and adoption validation.
- Start real stdio MCP subprocesses to prove missing configuration fails and
  distinct namespaces use distinct stores.
- Exercise the tracked wrappers without relying on ambient harness variables.
- Prove direct explicit indexing shares the existing per-repository lock with
  automatic freshness refreshes.
- Run the full repository suite and package/type/compile gates.

## Threat Model

- **Spoofing:** ambient `CLAUDECODE` or Codex configuration impersonates the
  launching harness. Mitigate with explicit namespace configuration.
- **Tampering:** two processes race on one repository index or identity marker.
  Mitigate with exclusive creation, per-repository locking, and atomic replace.
- **Information disclosure:** a harness opens another harness's store. Mitigate
  with a persistent namespace marker and mismatch refusal.
- **Denial of service:** missing, malformed, inaccessible, or unsafe roots fail
  late. Validate at startup and return actionable bounded diagnostics.
- **Elevation of privilege:** a tool call changes the server's storage root.
  Do not expose any per-call root or namespace override.

## Boundaries

- Always: require absolute canonical MCP roots, validate the namespace and
  marker, preserve atomic writes, expose the resolved store identity in stats,
  and test fresh-process behavior.
- Ask first: deleting indexes, rewriting an existing marker, or automatically
  migrating data between stores.
- Never: inspect another harness's config from MCP mode, infer ownership from
  ambient host variables, silently adopt a non-empty unmarked store, or accept
  per-tool storage overrides.

## Success Criteria

1. MCP startup requires both `LOCI_BASE_DIR` and `LOCI_STORE_NAMESPACE` and
   exits non-zero with a structured actionable error when either is absent.
2. A store marker records schema version, namespace, and stable store ID;
   namespace mismatch fails closed.
3. Empty roots initialize safely; non-empty unmarked roots require an explicit
   CLI adoption command. No files are moved or deleted.
4. Codex and Claude registration examples use distinct roots and namespaces;
   the MCP wrapper performs no ambient-host guessing.
5. Explicit `loci_index` and freshness refresh cannot write the same repository
   concurrently.
6. Existing CLI store discovery remains available outside MCP mode.
7. Focused and full tests, changed-boundary type checking, compile, lockfile,
   package, and fresh-process checks pass. Any repo-wide unconfigured type
   baseline is reported separately rather than hidden or expanded into scope.

## Open Questions

None. Vik approved the production isolation direction in the preceding design
review. Intentional sharing is represented by configuring the same root and the
same non-harness namespace in both MCP registrations.
