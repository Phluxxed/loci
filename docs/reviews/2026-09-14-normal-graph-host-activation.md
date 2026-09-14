# Normal graph retrieval: actual-host activation

After Vik restarted Codex, actual deferred discovery exposed exactly
`loci_retrieve` and `loci_read`. Both primary and fresh Terra/high delegate
requests now execute `normal-graph-v1` without graph-selection flags.

## Native evidence

The verification entry point is
`.scratch/deterministic-graph-retrieval/host-acceptance/verify_host_acceptance.py`.
It reads the original local native rollouts, correlates exact model-visible
output, checks complete native-result bytes, and compares every selected source
span and file hash with the current checkout. Raw selected results, actual
native item/output identifiers and normalized readouts are retained beside it.
Private whole-session logs are not published.

| Host | Normal requests | Delivered relationships | Retrieve source / result bytes | Read source / result bytes | Native correlation |
| --- | ---: | ---: | --- | --- | --- |
| Primary | 1 retrieve + 1 read | 2 | 3339 / 16224 | 7979 / 8962 | Both full_exact |
| Fresh delegate, single execution | 1 retrieve + 1 read | 2 | 3339 / 16224 | 7979 / 8962 | Both full_exact |

The query was `retrieve_context` in the Loci checkout. Each retrieval reported
84 traversals and returned an incoming static call plus an authored type use,
with selected proof. Results remain partial and non-exhaustive, with candidate,
node, neighbor, unresolved, preview and output-budget omissions. Both reads
expanded the selected complete function. Reported and independently computed
source/result bytes agree exactly.

An earlier delegate functional check returned zero relationships and valid
source. That worker repeated a retrieval/read pair while persisting evidence,
contrary to its one-pair scope. All four native calls remain retained: both
retrieval deliveries are ambiguous_exact, its first preview read is full_exact,
and its later full read is unknown. This is not accepted as uniquely attributed
normal graph delivery. A separate directed acceptance assignment changed the
recording procedure to store and emit each result immediately, with exactly one
retrieve/read pair. It supplied the accepted fresh-delegate row above. Neither
functional assignment is a reserved ordinary trial or a replacement for one.

The ongoing primary turn has no invented completion boundary or per-case
provider-cost sample. These checks establish actual host delivery, not
unprimed adoption, answer benefit or a population usage rate. Private Claude
hosts remain unverified.

## Review and measurement corrections

An independent bounded review found one required defect in the initial normal
adapter: it could accept false declared byte counts. Normal adapter v2 now
recomputes the union of source extents and the complete captured result size;
missing or mismatched counts cannot certify host proof. Overlapping proof
snippets are counted once for the normal unique-evidence metric. Historical
v1 source-byte sums remain unchanged and must not be silently compared with
this new unique-evidence field.

A real Anvil native response also exposed an omitted optional `isError` field
that the frozen observer rejected. The separate native-v2 reader accepts an
absent flag while rejecting invalid present values. It preserves the original
result shape for exact byte accounting and model-output correlation and reuses
the frozen interval/correlation helpers. It does not alter the raw rollout or
create a terminal boundary. Normal-v2 now uses that reader.

The combined normal-v2/native-v2/frozen observer/review checks pass **58/58**.
The actual primary and accepted delegate packets pass the same integrated
readout and exact source assertions. The original observer, reviewer, all
baseline rows and the reserved post template remain unchanged. Product source
and installed normal tool contract are unchanged from `90068fa`; these last
corrections affect audit interpretation only.

The independent review and primary dispositions are retained at
`.scratch/deterministic-graph-retrieval/host-acceptance/independent-review.md`
and in the worklog. W1.6.3, W1.8.1 and W1.8.2 have their required evidence.
W1.8.3 and W1.8.4 still own the separately frozen post comparison and final
correctness, use and cost verdict.
