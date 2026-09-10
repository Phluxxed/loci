# W2.1.6 — Causal read measurement

`benchmarks.typescript_context_trace.ReadTrace` records one frozen task, session,
arm and repetition. Its artifacts bind corpus and comparison-control hashes and
retain exact delivered JSON, arguments, source slices, read intent and latency.
This is an evaluator component, outside production telemetry. W2.1.7 owns the
agent launch/tool adapter, runtime isolation, budget enforcement and baseline
runs. These trace tests are not agent-efficiency results.

## Adapter contract

Create the recorder with the loaded corpus, corpus case ID, unique session ID,
arm A/B/C and repetition 1/2/3. Before each call the agent declares `reason`, a
short `detail`, and optional `because` identifying an earlier operation. The
adapter retains these declarations, rather than inventing intent from timing.
Use one record per logical search/get/graph/file/grep/outline operation. Expansion
work belongs to its outer operation, including all delivered source and elapsed
time; it must not become free work or extra agent read counts.

Pass `record` the exact UTF-8 JSON string delivered, original tool arguments,
elapsed milliseconds and all delivered source occurrences as
`{file, start_byte, text}`. Paths and offsets come from the tool's source
provenance, never a same-name or same-text file guess. Extract each occurrence
once, including context, graph evidence and fallback; do not duplicate overlapping
annotations of one occurrence. Repeated deliveries in distinct responses count
again. Source metadata alone, hashes and names do not deliver source.
The recorder verifies each slice against the frozen snapshot and an actual JSON
string in that response. The adapter still owns complete source extraction and
correct source provenance; this is not a generic JSON source detector.

For search, deliver the normal logical result with its existing `search_id`.
For a deliberate selected get, retain `selected_from_search_id` and `symbol_ids`
in the actual service arguments. The service keeps its existing repository and
selection validation; the recorder additionally requires the search in this
run. A selected symbol may be outside the visible search envelope, as the
existing Loci contract permits. Direct, hydration and mixed-purpose gets must
not fabricate selection lineage. Split mixed purposes into separate operations.
Search selection and a declaration of missing context are separate facts.

All declarations and raw outputs remain outside the agent source workspace.
The agent sees operation IDs for subsequent causal references but no gold IDs,
required spans, answers, classification or intermediate gold-recall feedback.
`artifact(answer, usage=..., usage_semantics=..., outcome=...)` is called by the
evaluator after the run; never expose its result as an agent tool.

## Classification

`task_context` identifies an initial attempt to obtain task context.
`missing_context` explicitly declares a follow-up caused by a previous result.
`hydration`, `verification`, `setup` and `unrelated` are excluded from avoidable
read counts, even when adjacent to a retrieval or delivering required context.
Every operation retains its full cost.

A missing-context chain counts only when:

1. Each causal parent is an earlier event in the same task/session run.
2. The chain begins at `task_context` that delivered at least some verified
   source within a required gold span.
3. A read in the chain completes a required gold span not previously delivered.
   Only missing-context ancestors of that recovery receive attribution.

Each operation counts at most once even if it recovers several requirements.
A search then selected get can count as two reads when both explicitly belong
to the recovered gap. A linked graph response containing only an edge does not
supply the type body; its gap remains unproven unless its descendant recovers
required source. Nearby or sibling operations cannot inherit causality.

A declared gap without a valid root, complete recovery, or new required source
is `unproven`. The report retains the proven subtotal but makes the primary
`avoidable_reads` null and `lineage_status` inconclusive. It cannot pass an
efficiency comparison as zero. Missing attribution is not imputed from timestamps
or correctness. This conservative method measures declared, source-supported
recovery effort; it does not prove the agent's private reasoning or that a future
retrieval policy can eliminate every counted operation.

Required-context recall uses complete exact gold byte intervals, allowing their
union across reads. The initiating result need only overlap required source:
an ordinary function get can omit its export wrapper or trailing newline while
still initiating a real dependency question. The integration check demonstrates
this distinction against the existing search/get service; gold is unchanged.

## Cost, correctness and replay

Reports include all read counts, complete serialized UTF-8 tool-output bytes,
source bytes including duplicates, tool elapsed milliseconds, required-context
recall and the corpus's exact JSON-fact correctness check. Noncompleted outcomes
cannot be successful answers. No failed attempt is discarded.

Provider usage is separate from the labelled `ceil(source_bytes / 4)` estimate.
Supply gross `input_tokens`, `cached_input_tokens`, `output_tokens` and the
provider's inclusion semantics. Optional provider fields remain intact; no
reasoning subtotal is added twice and no dollar price is inferred. Missing
usage is unavailable, never zero. Tool timing is not end-to-end model latency;
W2.1.7 must record full run timing and enforce the frozen budgets.

Save the JSON artifact outside the source snapshot and replay it with:

```sh
.venv/bin/python -m benchmarks.typescript_context_trace /path/to/trace.json
```

Replay revalidates identities, controls, source delivery, lineage, byte totals
and classifications. It rejects mismatches instead of trusting saved summaries.
These are integrity checks, not cryptographic attestation of a trusted host.

Acceptance: `.venv/bin/python -m pytest tests/test_typescript_context_trace.py -q`
passes 26 focused cases, including real service selection, causal search/get,
excluded work, missing/foreign links, duplicate source, incomplete fragments,
name-only graphs, source forgery, exact-answer failure, retained timeout costs,
unavailable/provider tokens and replay tampering.
