# Normal discovery and named-identity repair — W1.8.4.4

Vik selected this implementation after the two binding attempts retained a
1.4328x input-token cost and one attempt failed to discover either normal tool.
The work uses those failures as local regressions. No additional provider trial
or frozen-result rescore is included.

## Discovery

The configured normal server already exposes only `loci_retrieve` and
`loci_read`. Attempt 2 searched broad words across the host's tool descriptions,
producing a reported 120,493-token dump. Neither Loci name survived in its
retained 40,112 bytes. This was unsuccessful discovery, not demonstrated server
unavailability.

The skill now contains an executable exact-operation-name lookup. Its first
pass emits only matching names and a count; the next pass reads one exact live
tool contract. The startup hook names the two normal entrypoints and points to
that procedure. Setup now distinguishes a zero-match discovery result from an
absent registration before changing configuration or requesting a restart.

The installed skill and hook are symlinks to these tracked sources. Running
the installed hook emits both names. The same lookup in the live Code Mode
catalog finds both tools without returning unrelated descriptions. Its local
regression executes the actual skill recipe with 2,000 unrelated tools and
description getters that throw if accessed. Missing tools, unprefixed names
and multiple registrations are also checked; the name list is capped at eight.
All 18 discovery, hook and repository-guidance checks pass.

This is a deterministic lookup procedure, not enforcement that every agent
executes it. The installed Codex 0.154.0 uses deferred MCP discovery. No
supported setting to expose only these two tools eagerly was established in
the installed surface or the current [configuration reference](https://learn.chatgpt.com/docs/config-file/config-reference).
The documented MCP allow list controls which tools are available, not proof
of how they are surfaced to this Code Mode session. Global host feature flags
were not changed. Reliable ordinary uptake and token savings remain unproven.

Evidence:

- [Installed hook/skill receipt](../../.scratch/deterministic-graph-retrieval/diagnosis/discovery-installed-20260915.json)
- [Actual Code Mode catalog receipt](../../.scratch/deterministic-graph-retrieval/diagnosis/discovery-live-catalog-20260915.json)
- [Original two-attempt result](2026-09-15-binding-repair-token-result.md)

## Anchor and proof selection

The exact retained query is
`captureCommandResult work context binding accepted type imported public contract`.
Before this repair it selects the full binding, its public view and a planning
document, omitting the named function and its options-to-binding relationship.

Case-sensitive camel/Pascal-case and underscore identifiers now give exact
code-name matches priority over prose. Duplicate matching declarations remain
alternatives; plain-language document questions keep their metadata ranking.
This is not an arbitrary-name or Unicode identifier resolver.

Anchor priority alone was insufficient in the local replay. The scheduler
packed a body-call proof before the function's declared type dependency. The
repair therefore prioritizes shared declaration nodes connected to at least
two selected anchors by supported type-family edges. Targets are ordered by
their connected anchor indexes, then node identity. Their type proofs are
attempted consecutively before ordinary family queues, under the existing
neighbor, node, hop and byte limits. Direct explicit-anchor relationships keep
their earlier priority. Calls to the same shared target receive no special
priority, and every edge still passes normal source/proof validation.

The final local replay selects the function, full binding and public view. It
delivers both required type relationships with complete proof, including the
options import, public barrel and binding definition. Its full MCP envelope is
16,251 bytes against the unchanged 16,384 limit, with 3,099 evidence bytes
against 8,192. It remains partial and non-exhaustive: three relationships are
delivered and output-budget omissions are retained.

All 49 targeted anchor, retrieval and normal-MCP checks pass. The browser
control remains 14,417 bytes with forward and reverse proof; the renderer
control remains 16,117 bytes with calls, types and imports. All 638 source files
still match the frozen manifest. The original two binding attempts and both
frozen comparisons are unchanged.

See the [source diagnosis](../../.scratch/deterministic-graph-retrieval/diagnosis/anchor-identity-report.md)
and [replay receipt](../../.scratch/deterministic-graph-retrieval/diagnosis/anchor-identity-replay.json).

## Disposition and next action

Vik restarted Codex. The first actual normal MCP request with the exact retained
query now returns the repaired function/Binding/View anchors and both required
type relationships. Its complete result equals the accepted local packet:
16,251 bytes, 3,099 evidence bytes and three relationships, with the same
snapshot and explicit omissions. The native log contains one matching retrieval
and one complete outer delivery; no repeat request was used for this check.

See the [actual result](../../.scratch/deterministic-graph-retrieval/anchor-host-acceptance-20260915/raw-call.json),
[primary proof review](../../.scratch/deterministic-graph-retrieval/anchor-host-acceptance-20260915/primary-semantic-read.json)
and [native validation receipt](../../.scratch/deterministic-graph-retrieval/anchor-host-acceptance-20260915/receipt.json).

The restart boundary is resolved for this repair. This directed host check does
not establish that a fresh ordinary agent follows the discovery procedure or
uses the evidence correctly. The previous 1.4328x input result and negative
ordinary acceptance remain unchanged; no additional provider trial ran.

**Next: W1.8.4.4 — select and freeze a fresh two-binding comparison against the
unchanged baseline and 1.25x thresholds.** Include separately versioned exact
wrapper accounting before launch. This is the recommended next measurement;
the completed two-attempt campaign is not reopened or rescored.
