# Explicit exploration routing: frozen measurement protocol

W2.5.1.3 (`task_2727497172e9ceadea5ab07538da0b31`) implements the policy
published at `b2c0362c837f65ce07d0eb2556c95f3d5a5534d4`. The existing
selection policy, prompt manifest and preparation evidence remain intact.

## Fixed intervention and inputs

Both A (exploration available) and B (explicit exploration routing) use the
same pinned engine, fourteen repository tools and three host helpers.
Only B receives the published selection-policy prefix. A retains the original
common and case prompt exactly; that same original prompt is B's unchanged
suffix. Every effective prompt hash is checked against the published manifest.
The adapter preserves A/B observation identity while allowing the B capability
surface for both. Exact `get` does not automatically attach type context.

The source is commit `36f5e2b1662c2d6bbe2449c3189430469e8c013f`, extractor 25.
The original seventeen-case v3 corpus, pinned snapshots, model/reasoning controls,
environment, limits, scoring and numeric thresholds are unchanged. Three
repetitions per case use globally alternating AB/BA order, starting AB: 102
serial attempts. All attempts, failures and costs remain in the batch; no
selective retry, replacement or exclusion is allowed.

## Observed exposure and outcomes

For each attempt, host call lifecycle and exact native results are reconciled
with the adapter's source trace. Source-free host helpers are recorded and
charged, but do not become the first repository retrieval. The observer records
that first retrieval, exploration intent, native status, anchor IDs, omissions,
source-bearing anchor receipt, clipping/completeness, and later fallback calls.
Malformed or incomplete evidence stays unknown.

The requested anchor must be a native anchor item linked uniquely to nonempty
source bytes at its pinned declaration, with matching file hash and content.
Merely naming the tool or returning a different symbol does not establish
exposure. Partial source can establish receipt and is separately marked
incomplete; the unchanged source-coverage gates still require the necessary
complete context. A failed or wrong first route cannot be repaired retrospectively
by a successful fallback.

The three maintained cases require all nine B attempts to start repository
retrieval with `type_dependencies` and receive their requested source anchor.
The report also discloses initial routing for all thirteen type-context cases,
actual exploration use for the four call-target controls, and the same evidence
for A. Case gold is used solely by the evaluator, never in provider prompts.

Numeric evaluation is delegated to the original frozen evaluator. A qualification
can be `keep` only with its numeric `keep`, all nine maintained B exposures, and
independent replay of all 102 attempts. Known exposure failure or numeric rejection
rejects an otherwise complete comparison. Missing measurement, unknown routing
or incomplete replay makes qualification inconclusive. Numeric and qualification
verdicts are reported separately.

## Premeasurement verification and publication

`measurement-transport-verification.json` exercises the actual `run_attempt`
entrypoint for A and B using real Codex/MCP and a scripted local Responses
endpoint. It verifies actual prompt transport, identical schemas, original A/B
identities, native payload delivery to the next request, and source observation.
Its deliberate terminal provider error means it is transport evidence, with
zero model-provider calls and no claim about model adoption.

The code and evidence are committed first. A separate `freeze.json` records that
code commit, exact source and harness hashes, corpus/comparison hashes, prompt
manifest and policy hashes, fresh model catalog, and the complete attempt plan.
The freeze is then committed and published before provider measurement starts.
Freeze validation rejects changed inputs. Independent replay reconstructs fresh
indexes, recalculates source, relationship, numeric and routing evidence, and
checks each prompt and condition against the freeze before final reporting.

Earlier availability trials and their rejected findings remain immutable. This
comparison measures the new prompt-routing intervention; it does not promote
code or change the shared runtime.
