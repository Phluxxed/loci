# Retained provider-round diagnosis

W1.8.4.1, 14 September 2026. This is passive accounting over the eight
selected retained runs. It starts no provider attempts and does not change or
regrade a frozen benchmark artifact.

## Finding

The binding-case `2.7236x` total-input result is real provider accounting, and
all of it reconciles per response. It is best explained as amplification from
replaying a growing context across more serialized provider responses. The
evidence does not identify a causal token share for Loci, a particular field,
or a particular result byte.

For binding, the baseline/post medians are:

| Metric | Baseline | Post | Ratio |
|---|---:|---:|---:|
| Provider input tokens | 249,298 | 678,996.5 | 2.7236x |
| Cached input tokens | 212,352 | 614,784 | 2.8951x |
| Uncached input tokens | 36,946 | 64,212.5 | 1.7380x |
| Provider usage snapshots | 6.5 | 12.5 | 1.9231x |
| Outer Code Mode round trips | 5.5 | 11.5 | 2.0909x |
| Model-visible outer-output bytes | 122,871.5 | 157,496 | 1.2818x |

Of the 429,698.5-token median increase, 402,432 tokens (93.65%) are in the
provider's cached-input category and 27,266.5 (6.35%) are uncached. That is an
exact arithmetic decomposition of the medians, not attribution of cause or
price.

Each run makes the repeated-context mechanism visible. The provider input
total is the sum of the response snapshots, while the input carried by an
individual response grows through the turn:

| Run | Cohort | Snapshots | First to final response input | Mean input per response | Total input |
|---|---|---:|---:|---:|---:|
| run-02 | baseline | 6 | 23,977 to 58,004 | 37,091 | 222,546 |
| run-07 | baseline | 7 | 23,977 to 55,174 | 39,436 | 276,050 |
| run-16 | post | 16 | 24,437 to 84,719 | 57,811 | 924,970 |
| run-21 | post | 9 | 24,437 to 75,468 | 48,114 | 433,023 |

The later rounds are material without being a savings estimate. Binding
baseline runs have at most seven provider snapshots. In post run-16, rounds
8-16 contain 676,990 input tokens, 73.19% of that run's total. In post run-21,
rounds 8-9 contain 149,918, or 34.62%. Removing or combining a round changes
the later context, so these values must not be interpreted as tokens that a
repair would necessarily save.

The workflow trace shows why those extra rounds occurred. Run-16 has eight
consecutive MCP-only delivery windows. Its seven `loci_retrieve` envelopes are
15,369-16,373 bytes each despite carrying 1,321-3,334 bytes of source content;
the zero-relationship packet is 15,369 bytes with 3,122 source bytes. Run-21's
six retrieve envelopes are 16,003-16,378 bytes; one zero-relationship packet is
16,275 bytes with 1,521 source bytes. The lead's separate primary-packet
inspection reports that source locators alone occupy 3.9-5.35 KB of roughly
16 KB responses while selected source occupies 1,177/2,248/1,094/3,946 bytes.
That corroborates repeated serialization weight. It remains byte accounting,
not provider-token attribution.

Temporal buckets reinforce the boundary on the claim. Provider input in a
response after a Loci terminal event is 478,461 (51.73%) for run-16 and 205,687
(47.50%) for run-21. Baseline run-07 is also 151,995 (55.06%), while run-02 has
no Loci event. Those overlapping shares say when a response occurred relative
to a tool result. Native nested MCP events do not carry an outer invocation id,
so they do not prove which bytes the provider consumed or what caused a token.

## Checkpoint case

Checkpoint overhead has a different shape:

| Metric | Baseline | Post | Change |
|---|---:|---:|---:|
| Provider input tokens | 701,821.5 | 826,103.5 | +17.71% |
| Cached input tokens | 633,344 | 746,624 | +17.89% |
| Uncached input tokens | 68,477.5 | 79,479.5 | +16.07% |
| Provider usage snapshots | 14 | 13.5 | -3.57% |
| Outer Code Mode round trips | 13 | 12.5 | -3.85% |
| Model-visible outer-output bytes | 195,180.5 | 222,332.5 | +13.91% |

The increased input therefore is not accounted for by more outer rounds. The
per-run mean input per response is 46,830 for baseline run-01, 55,230 for
baseline run-08, 59,208 for post run-15, and 62,781 for post run-22. The post
responses replay larger contexts.

Run-22 is the preserved fan-out anomaly: 26 MCP terminals and 311,778 bytes of
native MCP result envelopes are distributed over eight MCP delivery windows
inside 14 outer calls, with four or five MCP terminals in several windows.
Run-15 has five MCP terminals and 63,608 result-envelope bytes. The post pair's
median therefore hides large route variance. Baseline anomalies run in the
other direction: run-01 has a 1,480,664-byte native MCP envelope total but only
146,581 model-visible outer-output bytes; run-08 has 1,237,889 shell-output
bytes but only 243,780 model-visible outer-output bytes. Inner terminal bytes
and visible bytes must remain separate because wrapping and truncation prevent
one from standing in for the other.

The frozen review qualifications remain in force. In particular, run-22 keeps
its recorded source-scope deviation and incomplete answer; this accounting
does not alter that judgment.

## Reconciliation and provenance

All eight runs pass every reconciliation check:

- each cumulative `turn_token_usage` delta equals the same record's
  per-response `usage` object;
- the per-response sums equal the last cumulative snapshot and the frozen
  input/cached/output totals;
- outer request counts, MCP/shell terminal counts, and model-visible output
  bytes equal the frozen observer totals;
- retained interval bytes, SHA-256, record count, original line bounds,
  thread, turn, final-answer order, and terminal boundary agree.

The exact retained intervals are:

| Run | Original lines | Interval SHA-256 |
|---|---:|---|
| run-02 | 2-63 | `4f98f55c007cc7a2ad085a1b7acffffa3365e017dd9dece24a88a90f1c6c9cd9` |
| run-07 | 2-68 | `9ae581b5ed54e6f26f6f8ae0bdb19ce3cdf2216f51d7099219289959dd17bef9` |
| run-16 | 2-126 | `6046728ebe2458ffa09ed2302902e0a1322b664b11fdda19870a6d06f4dcd363` |
| run-21 | 2-81 | `d5e2eb634b70e75fa79bcc7664d31f936937ad5fdb0dd9dbab9dae9a70ff0022` |
| run-01 | 2-137 | `f74435cb604fd8669d703cf98d54db883f41bde3cb1b8061e375241bffd22e6a` |
| run-08 | 2-105 | `66c39498e1ccb005f8aec6d04147f38a93c67b08003dbc7d2c9095ce96e3b202` |
| run-15 | 2-99 | `c26096236432ff3a4b15654d8a5a61347c6cffabbf88440de330938115952ef6` |
| run-22 | 2-139 | `69e21b5e5becb17eb2dc2b72b32233a3f9a80d0b010f9e6718d45dd61b93a560` |

`token-results.json` contains the exact thread/turn/native-rollout locator for
each interval, every per-response usage snapshot, normalized operation ledgers,
byte/hash receipts, temporal operation references, frozen qualifications, and
all checks. Raw native records remain only in the already-local retained files;
none are copied into this diagnosis.

## Concrete repair acceptance suggestions

1. Make the binding scenario pass strict correctness in two retained attempts
   with at most seven provider snapshots and six outer round trips per attempt,
   matching the maximum baseline trajectory. Preserve the same per-round
   reconciliation so fewer rounds cannot be obtained by dropping accounting.
2. Bound normal retrieval serialization independently of tokens. For the
   binding fixture, require cumulative normal-result output at or below 60 KB
   and require a zero-relationship result with no more than 4 KB of source to
   remain below 8 KB total. Keep source, relationship proof, omissions, and
   continuation behavior correct under that budget.
3. For the checkpoint scenario, require all four frozen facts, no access-scope
   deviation, no more than ten normal public invocations, and no more than 128
   KB of cumulative normal-result output in each of two attempts. Reject
   repeated broad retrieval once exact source identities or continuation refs
   are available.
4. Preserve the accounting contract in future measurements: store every
   per-response provider snapshot, cumulative-delta check, outer call id,
   terminal operation id, visible-output byte/hash, and exact retained interval
   receipt. Continue to label temporal token shares as descriptive only.

The numeric gates above are repair candidates grounded in the selected traces,
not causal estimates. The lead should adopt or adjust them with the architecture
contract and correctness requirements.

## Sources

- `.scratch/deterministic-graph-retrieval/diagnosis/token-results.json`
- `.scratch/deterministic-graph-retrieval/diagnosis/token-metadata.json`
- `.scratch/deterministic-graph-retrieval/diagnosis/token-baseline-linkage.json`
- `.scratch/deterministic-graph-retrieval/diagnosis/token-schedule.json`
- `benchmarks/comparisons/ordinary-adoption-v1/results.json`
- `benchmarks/comparisons/ordinary-adoption-normal-v1/results.json`
- `benchmarks/comparisons/ordinary-adoption-normal-v1/baseline-linkage.json`
- `benchmarks/ordinary_adoption_observed.py` lines 1-7, 478-547, 550-647,
  and 769-790 (temporal-parent limitation, outer/terminal collection, and
  cumulative provider-usage semantics)
