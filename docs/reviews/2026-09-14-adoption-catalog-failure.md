# Adoption catalog failure ownership

Date: 14 September 2026  
Source revision checked: `50ad963ff9afccb94a2f224e1970f1d64b4ffafa`  
Scope: identify the smallest owner of `run-08`'s two
`REPOSITORY_CATALOG_REPAIR_REQUIRED` results and determine whether a legitimate
concurrent catalog mutation can produce them. This review does not authorize a
store repair or product change.

## Conclusion

The smallest owner is the shared repository-catalog mutation protocol in
`RepositoryCatalog`, exercised by `IndexStore.write`. The protocol uses one
store-wide pending-marker path for both live mutation exclusion and durable
crash evidence. `entries_for_mutation()` treats the marker's mere existence as
an interrupted mutation, without owner, age or liveness evidence
([repository_catalog.py](../../src/loci/storage/repository_catalog.py#L97)).
`begin_mutation()` writes only schema version, operation and optional cache key
with exclusive creation; a collision is also reported as repair-required
([repository_catalog.py](../../src/loci/storage/repository_catalog.py#L117)).
`finish_mutation()` unlinks the marker without checking ownership
([repository_catalog.py](../../src/loci/storage/repository_catalog.py#L159)).

A healthy concurrent writer can therefore produce exactly `run-08`'s error.
This is demonstrated, rather than hypothetical. The historical conclusion is
narrower: the retained timing and later recovery make a live `run-07` catalog
mutation the strongest explanation for `run-08`, but the marker format cannot
prove who owned the marker, so the cause of that historical marker remains an
inference.

## Owning call path

Both affected MCP handlers ask the service to refresh before retrieval:
`loci_search` calls `search_symbols_result(..., ensure_fresh=True)` and
`loci_grep` calls `grep_repo_result(..., ensure_fresh=True)`
([mcp_server.py](../../src/loci/mcp_server.py#L489),
[mcp_server.py](../../src/loci/mcp_server.py#L529)). The MCP boundary does not
invent the result; `_handle_loci_error` serializes the service error code,
message and details with `is_error=True`
([mcp_server.py](../../src/loci/mcp_server.py#L599)).

`ensure_fresh_index()` serializes refreshes with `refresh_lock_path(repo)` and
then calls `_index_repo_unlocked()` when the index is absent or stale
([service.py](../../src/loci/service.py#L521)). That lock lives inside the
repository-specific cache directory, so different cold roots use different
locks ([index_store.py](../../src/loci/storage/index_store.py#L199)). This
correctly prevents duplicate work on one repository but does not coordinate
two repositories that update the same catalog.

The indexing path reaches `store.write()` at
[service.py](../../src/loci/service.py#L456). `IndexStore.write()` reads the
catalog, creates the shared marker, mirrors all source files, writes the index
and repository metadata, commits the catalog, and only then removes the marker
([index_store.py](../../src/loci/storage/index_store.py#L252)). Thus another
repository's reader can observe a legitimate writer's marker for the duration
of substantial index work. There is no `try/finally` around this sequence,
which is intentional for crash visibility: a failed commit leaves the marker
and existing tests require subsequent reads to demand explicit repair
([test_repository_catalog.py](../../tests/storage/test_repository_catalog.py#L68)).

The defect is therefore not owned by search, grep, graph retrieval or deferred
tool discovery. It is the catalog protocol's inability to distinguish “live
writer owns this marker” from “writer died and repair is required,” combined
with per-repository refresh locks around a store-wide catalog resource.

## Isolated interleaving

One isolated `/tmp` check used a fresh `RepositoryCatalog`, with no access to
the configured store:

1. `entries_for_mutation()` returned an empty catalog.
2. Writer A called `begin_mutation("write", "active-writer")`; the marker
   existed while A was deliberately paused.
3. Reader B called `entries_for_mutation()` before A finished.
4. B received `REPOSITORY_CATALOG_REPAIR_REQUIRED` with reason
   `an interrupted catalog mutation is pending` and the repair command.
5. A called `finish_mutation()`; the marker disappeared and the next read
   succeeded without repair.

The observed result was:

```json
{
  "concurrent_reader_code": "REPOSITORY_CATALOG_REPAIR_REQUIRED",
  "concurrent_reader_message": "an interrupted catalog mutation is pending",
  "initial_entries": 0,
  "marker_exists_after_finish": false,
  "marker_exists_while_writer_active": true,
  "post_finish_entries": 0
}
```

This establishes that legitimate overlap alone is sufficient. It does not
establish which process created the historical marker.

## Historical `run-08` evidence

`run-07` and `run-08` were the paired cold-index attempts. `run-07`'s first
successful `loci_outline` call ran from `06:18:45.467` to `06:18:52.479` UTC.
Inside that interval, `run-08`'s `loci_search` failed from
`06:18:51.474` to `06:18:51.501`, followed by `loci_grep` from
`06:18:51.601` to `06:18:51.603`. Both native results contain the exact code
and reason reproduced above
([run-07 observed.json](../../benchmarks/comparisons/ordinary-adoption-v1/runs/run-07/observed.json),
[run-08 observed.json](../../benchmarks/comparisons/ordinary-adoption-v1/runs/run-08/observed.json)).

Later `run-09` and `run-10` retrieval calls succeeded; the first later success
began at `06:21:29.721` UTC. A primary query after that pair also succeeded,
and the coordinator observed the pending marker absent at `06:25:09` UTC
without invoking catalog repair. That transient recovery matches the isolated
live-writer sequence. It is inconsistent with the normal behavior of an
unattended orphan marker, which blocks reads until explicit repair.

The remaining uncertainty is material. The marker records no PID, process-start
identity, unique ownership token, creation timestamp or completion event, and
no marker snapshot was retained during the scored pair. The evidence cannot
exclude a different concurrent writer or prove the marker was never produced
by an actual interruption and later removed by some unobserved actor. The
historical attribution to `run-07` is therefore strong temporal inference, not
direct ownership proof.

## Bounded correction proposal

Required behavior:

- A marker held by a live catalog writer must produce bounded waiting/retry or
  a distinct retryable busy result. It must not instruct a reader to repair a
  healthy store.
- An abandoned, malformed or legacy marker must retain the current conservative
  repair-required behavior. Normal reads must not silently delete crash
  evidence.
- Only the marker owner may complete/remove its mutation marker.
- Concurrent cold indexing of two different repositories must not corrupt or
  lose either catalog entry.

A small implementation approach is to give the store-wide marker explicit
ownership and liveness semantics, then make catalog callers retry a live owner
for a bounded interval. The marker would include an ownership token and enough
process identity to distinguish a live writer; completion would require the
same token. Existing ownerless markers would remain repair-required. A separate
store-wide lock with crash-safe ownership can provide the same behavior. The
required outcome does not depend on choosing either mechanism.

Acceptance should exercise two deterministic cases in an isolated store:

1. Pause writer A after it owns the catalog mutation, start a cold index for a
   different repository, release A, and require both operations to finish with
   both catalog entries present and no repair-required result.
2. Inject failure after marker creation, prove ordinary reads remain
   repair-required, run the existing explicit repair path, and prove repair
   converges. Also reject removal using a non-owner token.

This preserves the existing crash-safety contract while removing the false
corruption diagnosis for legitimate concurrency. No evidence here supports
automatically repairing the live configured store or changing MCP error
mapping independently of the catalog owner.
