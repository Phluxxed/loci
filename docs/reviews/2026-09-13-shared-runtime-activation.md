# W5.5 shared runtime activation

Vik authorized runtime activation on 13 September 2026. The verified target is
the existing shared `loci-mcp` launcher and the restarted Codex host using its
explicit `codex` namespace and index store. W5.5 is
`task_7b37dbd0d2e578949b7d38bc5160f305`.

## Activation and identity

`~/.local/bin/loci-mcp` resolves to the tracked canonical
`.shared/loci-mcp-wrapper.sh`, which executes the repository's
`.venv/bin/loci-mcp`. Installed distribution `loci 0.2.0` is editable and points
to `/Users/brummerv/loci`. The source is integration merge
`5845bd89dca33b4d99ae458534c0fc25dbd23375`; the pre-activation canonical HEAD is
`08229e5438120f2b4d650fdcf6dea70f5417d4a1`, whose later change is Manifest only.
Product source, wrappers and package configuration still match the merge.

The old session did not expose `loci_explore`. Vik corrected the handling of
that boundary: flag the required host restart and stop before doing more
activation work. Vik restarted Codex. The first resumed check found 21 Loci
tools, including `loci_explore`; a call through this session returned canonical
source with exact hashes, spans and serialized output bytes. No separate agent
or standalone MCP process substituted for this host check.

The existing installation and configuration already targeted canonical source,
so activation required the host restart rather than a reinstall or config
replacement. Canonical index markers are schema 7, extractor 30 and graph
resolver 1, matching installed source. Normal tool freshness updates touched
indexes; no blanket rebuild or deletion of other repository indexes was used.

## Actual-host acceptance

The bounded fixture/verifier is
`tests/reproductions/exploration/runtime_activation.py`. It materializes exact
frozen source snapshots into disposable roots, emits requests for the primary
agent to make through its actual host tools, and checks the captured complete
MCP results. The verifier itself does not start a substitute MCP server.

All bounded acceptance checks pass. The retained record contains 16 actual-host
acceptance responses: the canonical restart probe, 12 initial fixture calls
(including the setup limitations below), and three freshness calls.

| Supported task | Verified delivered relationship |
| --- | --- |
| Python | `Alias` → imported `Payload`, with original repository-root imports |
| JavaScript | `run` → `make` and `add`, with authored call/import proof |
| Go | `Build` → `AliasID`, `Page`, `UserID`; `Page` → `Number` |
| Rust | `build` → `Envelope`, `Render`, `UserId`; `Render` → `Format` |
| TypeScript/TSX | `Badge` → imported `Props` |

The Rust workspace request separately preserves `declared_possible` on
`use_it` → `Thing`, with its Cargo control sources. Go and Cargo exact reads
match the complete fixture bytes. A zero-evidence request returns no source or
relationships within its 2,048-byte output limit.

After changing disposable TSX source and the Go module declaration, ordinary
`loci_file` and `loci_explore` calls return the new bytes and content hash without
manual reindexing. The verifier checks unique source intervals, file hashes,
exact byte spans, path/source closure, declaration endpoints, configuration
uncertainty, requested/returned bounds and exact MCP SDK wire-byte accounting.
Both the initial and freshness verifier stages pass.

Retained evidence:

- [Installed identity and current cache versions](evidence/2026-09-13-runtime-activation/loci-w55-runtime-identity.json)
- [Restarted host tool surface](evidence/2026-09-13-runtime-activation/loci-w55-host-surface.json)
- [Initial request plan](evidence/2026-09-13-runtime-activation/loci-w55-host-requests.json)
  and [verification receipt](evidence/2026-09-13-runtime-activation/loci-w55-initial-verification.json)
- [Freshness mutations/requests](evidence/2026-09-13-runtime-activation/loci-w55-fresh-requests.json)
  and [verification receipt](evidence/2026-09-13-runtime-activation/loci-w55-fresh-verification.json)
- [Hashes of all retained evidence files](evidence/2026-09-13-runtime-activation/sha256.json)

Each request plan identifies its complete raw response by basename in the same
evidence directory. To reproduce, run the fixture's `prepare` stage, make its
planned calls through the restarted host, save those results, then run `verify`.
Run `freshen`, make the freshness calls, then run `verify --fresh`. The commands
use `.venv/bin/python tests/reproductions/exploration/runtime_activation.py`.
Verification of the initial source state precedes the intentional mutations.

Two Python fixture limitations are retained explicitly. The initial combined
root nested files whose imports assume a repository-root `barrel` and `schema`;
those requests could not establish the intended imported Payload relationship.
Requesting the nested Python directory as a separate root then correctly failed
with `REPOSITORY_ROOT_OVERLAP`. The valid representative uses an independent,
non-overlapping root with the original Python import layout. Neither limitation
required a product change, weakening root ownership or deleting an index.

## Scope and remaining limits

This verifies the restarted Codex host and the existing shared launcher. Other
already-running sessions still need their own restart before claiming adoption
of new tools. New sessions using this launcher load canonical source.

Language semantics remain bounded: supported authored/static relationships,
explicit unresolved cases and configuration uncertainty, compact selected source
and independent evidence/output budgets. `partial` and omission reports remain
valid outcomes. Rust `declared_possible` does not claim an active feature or
runtime configuration. Exact-source checks do not imply exhaustive context or
better workflow efficiency.

All frozen corpora, prompts, bundles, scores and results remain unchanged. No
provider comparison, historical rescore or optional W3 capability build ran.
README now states the restart boundary and links this activation record.
