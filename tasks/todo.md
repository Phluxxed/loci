# Loci MCP Harness Store Isolation

- [x] Task 1: Store identity foundation
  - Acceptance: explicit namespace marker; mismatch refusal; explicit legacy adoption.
  - Verify: `.venv/bin/python -m pytest -q tests/storage/test_store_identity.py tests/storage/test_store_resolver.py`
  - Files: `src/loci/storage/store_identity.py`, `src/loci/storage/store_resolver.py`, storage tests.

- [x] Task 2: MCP and registration boundary
  - Acceptance: startup fails without explicit root/namespace; wrapper does not guess; host docs configure distinct stores.
  - Verify: `.venv/bin/python -m pytest -q tests/test_wrapper_routing.py tests/test_mcp_server.py`
  - Files: `src/loci/mcp_server.py`, `.shared/loci-mcp-wrapper.sh`, MCP/wrapper tests, README and skill.

- [x] Task 3: Same-harness write serialization
  - Acceptance: explicit indexing and freshness refresh use the same repository lock without deadlock.
  - Verify: `.venv/bin/python -m pytest -q tests/test_service.py`
  - Files: `src/loci/service.py`, `tests/test_service.py`.

- [x] Task 4: Production qualification and review
  - Acceptance: all spec success criteria and Definition of Done gates pass.
  - Verify: full pytest, pyright, compileall, lockfile check, package build, and MCP smoke tests.
  - Files: verification evidence only unless review finds a required correction.

## Qualification

- Full suite: `1216 passed in 54.77s`.
- Changed source: pyright `0 errors`; repo-wide unconfigured diagnostic retains
  263 unrelated existing findings.
- Compile, lockfile, package build, wrapper syntax, installed MCP smoke, Loci
  index verification, and graph health passed.
- Manifest task `work_df7cca19-c64c-441a-9790-b5c79d50dd17` completed with
  commit, test, design, and live-registration evidence.
