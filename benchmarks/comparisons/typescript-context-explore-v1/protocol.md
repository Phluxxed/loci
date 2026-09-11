# Delivered exploration workflow qualification

This is a new W2.5 comparison, `typescript-context-explore-v1`. It qualifies
whether making the delivered `loci_explore` workflow available reduces observed
retrieval work while preserving the existing correctness and cost gates.
Historical A/B and A/B/C runs did not expose this tool and remain unchanged.

## Intervention and source

Both arms use production source commit
`36f5e2b1662c2d6bbe2449c3189430469e8c013f`, extractor version 25. The runner
checks every source file against that commit before each attempt. A receives
the original 13 typed retrieval and graph tools. B receives the identical 13
tools plus the real `loci_explore` service entry point, with `locate`,
`type_dependencies`, and `impact` intents. Neither arm automatically expands
`get`. The three source-free host resource helpers remain visible and counted.

The intervention is workflow availability. Tool selection remains the model's
choice. Actual exploration calls and attempts with no exploration call are
reported. This comparison does not isolate new edge semantics: both arms have
the same current index. It does not establish benefits across other languages;
the Manifest's multilingual work remains separate.

## Immutable tasks and controls

The original `typescript-context-v3` corpus is retained byte for byte: fourteen
fixtures and three source-comprehension tasks from the maintained Anvil
repository. Every task prompt, common prompt, answer gold, context interval,
negative relationship, and numeric acceptance threshold is unchanged.

There are exactly 102 attempts: 17 cases × 3 repetitions × 2 arms. Cases follow
corpus order; repetitions follow 1, 2, 3. Pair order alternates AB, BA across
the complete sequence, beginning with AB. Concurrency is one. Every attempt
has a fresh Codex session, immutable snapshot and freshly built index. Index
construction and offline request inspection are outside the retrieval timer.
There are no correctness retries, deleted failures, adaptive task changes,
selective replacement blocks or early stopping for a favorable result.
`--resume` continues after a fully recorded prefix. A hard interruption leaving
an incomplete attempt is retained as an incomplete, inconclusive batch; it is
not retried or overwritten by this runner.

The model remains GPT-5.6 Luna with high reasoning effort through Codex CLI
0.154.0 and ChatGPT authentication. Original environment validation remains in
force. A freshly read model catalog is retained, including its provenance;
the provider's backend snapshot is not exposed or claimed to be pinned.
No dollar conversion is inferred from ChatGPT authentication.

## Boundaries and accounting

The original operation and run byte, span, token, call and elapsed-time limits
are unchanged. The explore adapter binds the repository and freshness policy;
the model cannot supply `repo` or `ensure_fresh`. Query and seed validation
follow the product contract. Exposed hop requests are capped at the original
three-hop limit; output and evidence requests are capped at the original
32,768-byte and 16,384-byte limits. Common run limits remain 24 top-level calls,
262,144 output bytes, 131,072 source bytes, 180 seconds, 200,000 reported input
tokens and 8,192 reported output tokens. Each source-bearing operation is
limited to 64 spans and the original 4,096 estimated evidence tokens.

The existing graph tool's neighbor cap remains 16. Native explore retains the
product's internal neighbor selection cap of 32 and result item cap of 12;
these are declared product behavior rather than changes to graph tool
arguments. An explore result examining more than 32 nodes is rejected by the
measurement adapter's common node guard. Limits and omissions remain visible.

Every top-level host-observed call counts, including schema errors and resource
helpers. Every exact model-visible payload byte counts. Source accounting
includes all shared exploration sources, including relationship proof, with
duplicates counted on each delivery. The product's union-of-intervals evidence
usage and native packet byte count are retained separately. Evaluation
correlation metadata is added after the native packet is built and counts in
full toward the observed payload and common operation/run output limits.
Each credited span must match frozen snapshot
bytes and appear in the exact delivered JSON. Raw traces name the operation
`explore`; it is never relabeled as a graph read.

## Relationship and acceptance interpretation

The new scorer recognizes relationships in exploration capsules and expanded
get containers as well as existing graph responses. Delivered edges must
match proven index edges exactly. Exploration relationships must deliver their
complete independently joined persisted proof, with matching source bytes and
hashes. Integrity violations count against the zero-false-relationship gate.
`uses_type` and `references_type` can receive generic endpoint dependency
credit; they do not establish a precise parameter, property or alias subtype.
`extends`, `implements` and `calls` require their exact kind. Authored negatives
and delivery-integrity checks are bounded evidence, not exhaustive truth.

The original gate evaluator is reused unchanged: 42/42 candidate fixture full
passes; at least 8/9 maintained full passes; no per-task success regression;
at least two maintained tasks fully successful in all three runs of both
arms; at least 20% reduction in the sum of eligible task median observed
calls; at least two tasks saving one median call; no maintained source-recall
regression; output-byte and gross-input-token sums of task medians no greater
than A; and maintained nearest-rank p95 latency no more than 1.25× A.
Unavailable required measurements yield an inconclusive result.

## Freeze and evidence

Before measured calls, focused tests, fresh endpoint checks and real Codex/MCP
loopback transport probes must pass. The probes verify both visible tool sets,
identical shared schemas, strict argument rejection, complete source/proof
delivery and exact payload transmission to the next model request. No provider
model is called by these probes. The code, protocol, catalog and evidence are
committed, then their hashes and the exact schedule are separately frozen and
committed. Each measured request is audited against its arm's schema hash.

All raw events, source traces, request audits, outcomes, errors, costs and
provenance are retained. A separate replay rebuilds fresh indexes, validates
source and proof delivery, and recomputes every measurement and relationship
score from the retained host events. Reported success requires this replay as
well as the unchanged numerical gates. A failed trial leaves W2.5's unmet
acceptance criteria open; it does not trigger a silent threshold change.
