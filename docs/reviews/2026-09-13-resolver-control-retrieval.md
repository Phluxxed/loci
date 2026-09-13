# W5.1 exact resolver-control retrieval

Task `task_1e585a3ff7bc30b6b2dc90d5d768925a` is implemented on the isolated
`feat/evidence-backed-exploration` branch. Exact retrieval now returns tracked
`go.mod`, `go.work`, and `Cargo.toml` source without making controls indexed
language source. Canonical Manifest authority remains `/Users/brummerv/loci`;
source integration and installed-runtime promotion retain their separate gates.

## Reproduction and mechanism

Before the service change, an actual stdio MCP session indexed temporary Go and
Rust repositories successfully, then returned `FILE_NOT_FOUND` / `File not found
in cache` for their existing `go.mod` and `Cargo.toml`. The isolated reproduction
used cache `/tmp/loci-control-red-repro.JUWBwl/cache`, namespace `red`, and
`python -m loci.mcp_server`. This confirms the normal-surface limitation described
in the retained [W4.7 defects](2026-09-13-multilingual-measurement-defects.md).

`service.get_cached_file` now recognizes canonical relative Go/Cargo control
paths and requires a corresponding resolver input in the validated graph state.
It reads through the existing contained regular-file reader with the resolver's
1 MiB limit, checks both relative identity and SHA-256 against the indexed input,
then decodes strict UTF-8. A changed file cannot be delivered as indexed evidence,
including when it changes after the freshness check. Normal MCP refreshes the
index before retrieval. Service/CLI calls that skip freshness refuse changed
input until the caller refreshes.

The public file/content/total_lines/start_line/end_line envelope is unchanged.
Line slicing preserves existing clamping and exact newline bytes. Retrieval
accounting uses selected UTF-8 bytes and full raw-file bytes. Empty or
syntactically invalid but readable, hash-matching controls remain retrievable;
source access makes no claim that their resolver syntax is valid.

Missing or untracked controls return `FILE_NOT_FOUND`. Unsafe/unreadable,
oversized, stale or non-UTF-8 controls return `CONTROL_SOURCE_UNAVAILABLE` with
a structured reason. The route supports only the named tracked controls, not
arbitrary configuration files. Existing indexed-source retrieval is unchanged.

## Acceptance evidence

The consolidated directly relevant check passes **18 tests**:

```text
.venv/bin/python -m pytest \
  tests/test_resolver_control_source.py \
  tests/test_resolver_control_mcp.py \
  tests/test_resolver_control_adapter.py \
  tests/test_service.py::test_service_index_outline_get_round_trip \
  tests/test_service.py::test_service_search_file_grep_verify_list \
  tests/test_mcp_server.py::test_mcp_repository_scoped_tools_use_one_root_parameter -q
```

- Service checks cover indexed-hash mismatch, a change after freshness,
  exact selected/full-byte accounting, empty and invalid-syntax controls,
  strict UTF-8, untracked controls and Go workspace access.
- Normal stdio MCP checks cover exact full Go/Cargo contents and ranges,
  UTF-8/CRLF preservation, refreshed contents for both controls, missing and
  existing unsupported paths, absolute/traversal/directory/symlink rejection,
  and a structured 1 MiB refusal without returned source.
- The future multilingual comparison adapter's actual `file` dispatch is
  exercised for both A and B using temporary Go/Cargo snapshots. Both arms
  deliver exact content, byte spans and source hashes, preserve serialized and
  source-budget accounting, and deliver zero source for stale controls.
  Existing adapter wrapping reports `LociError` plus the truthful message;
  it does not preserve service error codes/details. This legacy envelope is
  unchanged. The test constructs an isolated adapter around temporary source
  rather than starting a provider campaign or modifying a frozen snapshot.
- Existing source retrieval and repository-parameter/schema checks pass.
  `git diff --check` passes.

Only service/CLI/MCP descriptions, README, three new test files and this report
change. No comparison adapter production code, corpus, comparison input, frozen
engine/harness bundle or result artifact changes. All 114 historical outcomes
and their verdicts remain as measured. This repair establishes equal exact-file
access for future work; it calculates no replacement benchmark result.

Next is W5.2 compact-selection assessment/repair,
`task_ad3b550457fb0b586f7ec1474a867fe5`. W5.3 deterministic evaluator/tool
contracts and explicitly directed source integration/runtime promotion remain.
