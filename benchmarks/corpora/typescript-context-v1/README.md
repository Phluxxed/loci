# TypeScript context corpus v1

This package fixes the tasks and expected source information for comparing Loci
retrieval. It contains 14 adversarial/control cases and three real contract
comprehension and regression-design tasks from Anvil. The answers were authored
from source before the endpoint preflight; no retrieval-arm output generated
the gold requirements. This package completes corpus/gold preflight only.

## Tasks and source snapshots

| Group | Cases | What they establish |
| --- | ---: | --- |
| Type context | 7 | Local/imported interfaces and aliases, renamed re-exports, explicit heritage |
| Safety | 3 | Correct origin with a wrong-file distractor, honest star ambiguity, local generic shadowing |
| Endpoint controls | 4 | Arrow, default-identifier, named-function and inline-default exports |
| Maintained Anvil tasks | 3 | Temporal query/argument contract, imported retrieval-limit contracts, renderer intersection result |

Anvil is pinned at `4d5afbcb54ab9d4bbb12e39357108b3caa4f6874` from
<https://github.com/Phluxxed/Anvil>. `anvil.tar.gz` preserves all 187 tracked files
under `src`, `test`, `bin`, `scripts`, plus package/lock/TypeScript configuration
and LICENSE. These are complete unmodified files with surrounding code and
unrelated declarations retained. Documentation and operational state are outside
this declared snapshot boundary. No external checkout or network is needed to
restore the source. The snapshot was taken from a clean checkout.

`fixtures.tar.gz` preserves the 14 exact source fixtures from
`tests/reproductions/typescript_context_gaps.py` at Loci
`9acd3e3589ddc034cade36e03c26c4508e9d4434`. Each fixture is a separate repository.
The historical W2.1.1 output packet remains unchanged. The comparison starting
engine includes all three prerequisite repairs (extractor version 24).

This v1 has one maintained repository and three real analysis tasks. It is not
representative evidence for arbitrary repositories, languages or code-edit
success. Report maintained tasks, mechanism cases and endpoint controls
separately; do not let tiny control files dominate an agent-efficiency claim.

## Gold and deterministic answers

`corpus.json` contains the task prompts, expected JSON facts, exact source spans,
source hashes, semantic relationships, forbidden proven relationships and allowed
unresolved outcomes. Spans use UTF-8 byte offsets with an exclusive end. Each
required span records its task relevance and optional expected symbol identity.
These source identities were authored without Loci symbol IDs. Graph vocabulary
in `relationships` describes source semantics, not a demand for existing edge
names or a claim that those edges already exist.

The structured answer checker compares the declared facts: object key order is
ignored; array order follows each explicit prompt; JSON numbers compare by value
and booleans are distinct. Extra/missing keys or wrong facts fail. Each prompt
states its JSON fields. This evaluates the specified comprehension/regression
planning task; a code patch and its tests are not the output contract in v1.

The generic case forbids treating the imported Payload as the generic's type.
The star-ambiguity case must not select either origin as a uniquely proven
parameter target. Reading a distractor to rule it out is not itself a false
relationship. Required context is task-specific, not a transitive dump of every
type mentioned in a declaration.

**Keep gold evaluator-only.** Later agents receive the case prompt and the
materialized source snapshot, never this package's answers, required spans or
preflight output. Index the materialized snapshot root, not the corpus package.
Agent interaction isolation, fixed model/tool settings, resource limits and
repeated-run counts belong to the following controls task.

## Integrity and replay

Run from the Loci development checkout:

```sh
.venv/bin/python -m benchmarks.typescript_context_corpus
.venv/bin/python -m benchmarks.typescript_context_corpus --preflight-output /tmp/typescript-preflight.json
.venv/bin/python -m benchmarks.typescript_context_corpus --case generic_shadow --answer /tmp/answer.json
.venv/bin/python -m pytest tests/test_typescript_context_corpus.py -q
```

`load_corpus()` verifies the manifest checksum, archive checksums, complete file
inventories and every required source span. `materialize_snapshot()` restores one
snapshot to an absent/empty directory and refuses overwrite. `check_answer()` is
the deterministic task-success boundary. `preflight()` indexes each snapshot in
a temporary isolated store and reports each expected endpoint as indexed,
missing or ambiguous; authored import/export evidence without a symbol is marked
source_only. It never changes gold, drops a case or converts a missing endpoint
into an allowed answer. Existing store environment variables are restored.

The committed `preflight.json` found all 55 expected symbols and retained 14
source-only evidence spans across 17 tasks. This proves endpoint availability,
not relationship extraction, context delivery or task success by an agent.
`runtime-controls.json` records independent execution of the behavioral portions
of the three real answers against the saved snapshot: temporal CLI arguments,
retrieval-limit message order, and renderer result/project routing. Node
v26.5.0 was the observed local runtime for this check, not a frozen agent-runtime
selection or a TypeScript typecheck claim. Type facts were inspected directly in
the saved declarations; the generic number/string control also retains its
previous strict TypeScript 6.0.3 evidence in the W2.1.1 packet.

Fourteen focused acceptance tests passed, including corrupt manifest/archive/gold
rejection, complete snapshot restore, wrong-origin/alias/generic-answer rejection,
and a deliberately missing endpoint that remains reported without gold mutation.

`corpus.sha256` freezes this v1 manifest, which in turn hashes every snapshot and
source file. A later corpus or answer change requires a new version and explicit
rationale; do not regenerate it from retrieval results. Preflight reports are
observations tied to their engine and corpus hashes, not new task truth.
