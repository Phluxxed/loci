# Delivery-boundary diagnosis

Scope: W1.8.4.1, based only on the retained run-17, run-20, and run-21 first-turn observations and current implicated source. No provider/model trial was run, and the frozen adapters and comparison results were not changed. The machine-readable measurements are in `delivery-boundary-measurements.json`.

## Finding

The 16,384-byte Loci result budget is operating as specified. Actual loss occurs when an outer Code Mode program concatenates several near-limit results and the host reduces the combined output at roughly its default 10,000-token boundary. Loci cannot observe that outer aggregation or its cap. The current benchmark observer then over-applies the truncation: it parses each entire output block as one JSON value and treats a truncation warning in any block in the turn as grounds to label every otherwise-unmatched call `unknown_truncated`.

The three observed failure modes therefore have different owners:

| Symptom | Immediate boundary | Actual cause | Deterministic owner |
| --- | --- | --- | --- |
| Middle JSON result is replaced by a truncation marker | Outer Code Mode result | Several valid Loci results were joined into one output larger than the host's unpragmatized default | Host/agent usage; Loci cannot guarantee arbitrary aggregation |
| Blank first retrieval followed by the same request | Loci success envelope, then agent program | Normal success has `content=[]`; the program printed only `r.content`, discarded `structuredContent`, then repeated | Agent/skill usage; Loci may add a bounded compatibility marker but cannot duplicate the full body within the same cap |
| Both identical calls are `ambiguous_exact` | Native-to-outer correlator | Deterministic identical requests have byte-identical results, while nested MCP events carry no enclosing outer call ID | Host instrumentation for per-invocation proof; observer can retain equivalence-class evidence only |
| Many intact calls are `unknown_truncated` | Frozen observer | Whole-block JSON parsing misses newline-framed values, and `has_truncation` is turn-global | Supplementary benchmark instrumentation |
| `INVALID_SOURCE_REF` after a read | Agent input validation | The returned `offset:8192,start:0` locator was manually replaced with `offsett:1760,start:21760` | Agent usage; Loci correctly rejected it |

## Retained examples

Run 17's outer request at `observation.outer_code_mode[4]` (`request_line=44`, output reference `outer:call_GGhtL2tNh2Np7kEySDHIGNZX:line:49:block:1`) launched two retrieves and one read in parallel, then printed three `structuredContent` JSON values separated by newlines. Their compact payload total is 40,490 bytes. The unpragmatized outer call reports 10,122 original tokens and returns a 40,105-byte block with its truncation marker in the middle JSON line. Exact per-line comparison against the retained native results shows:

- MCP line 46, query `bin/anvil.ts`: complete structured result retained.
- MCP line 47, query `runBrowserCli`: middle JSON line clipped.
- MCP line 48, exact read: complete structured result retained.

The frozen observer labels all three `unknown_truncated`. It cannot parse a block containing warning text plus several JSON documents, even though the first and third JSON lines remain exact. The later malformed-read error at MCP line 56 is also present exactly in `outer:call_yamVZUPeXR1PwQVyQRMkIag3:line:57:block:1`; it receives the same frozen label solely because another block in the turn had a warning. The source-reference failure is independent of delivery: the agent changed both the extent start and the required `offset` key instead of passing `next_source_ref` unchanged.

Run 20 isolates the repeat. Outer request line 28 executes one retrieve and prints `r.content.map(...)`; current normal success deliberately returns an empty content list and authoritative `structuredContent` (`src/loci/mcp_server.py:749-754`), so output line 31 contains zero payload bytes. Outer request line 35 repeats the identical query and prints `JSON.stringify(r.structuredContent)`. Both native results are 16,185 bytes with the same snapshot and SHA-256. The exact output at `outer:call_h9Sc3xAnaUndMN48A7ogW0An:line:38:block:1` therefore matches either invocation. Adding a nonce, timestamp, or transport ID to Loci would resolve the audit ambiguity by breaking the product's deterministic repeatability contract; that is not an acceptable repair.

Run 21 contains three distinct delivery situations. Request line 29 produces a 30,263-byte untruncated multi-value block containing MCP line 32 exactly. Request line 37 produces a 32,492-byte untruncated two-result block containing MCP lines 39 and 40 exactly. Request line 45 produces the already-recognized 5,362-byte `full_exact` read. Request line 52 joins three full results totaling 49,028 bytes; the host reports 12,257 original tokens and returns 40,106 bytes, retaining MCP lines 55 and 56 as exact first/last JSON lines while clipping the middle result at MCP line 54. Thus the evidence supports five exact retrieves and one clipped retrieve, plus one exact read. "All six retrieves truncated" is a frozen-observer underclaim, not an observed host fact.

## Boundary decisions

Loci's result construction is internally sound for these examples. Each native result stays at or below the published complete-result ceiling, and `usage.output_bytes` is computed on the MCP result boundary. The contract explicitly budgets one complete MCP result, not an outer program that prints an arbitrary number of results (`contract.md:132-139,208-218`). Lowering the product cap enough to fit three results would not solve four-result batching, would reduce source/relationship value, and would require a new policy version. Product code also cannot set the outer Code Mode cap or decide how the caller prints results.

The empty compatibility content is a real usability seam. The recommended v1 response is stronger normal-use instructions/examples plus, at most, a fixed marker; do not add a supposedly useful text projection to the existing policy. Replacing `content=[]` with one ASCII `{"type":"text","text":...}` block adds `N+25` serialized bytes for `N` text bytes, before extra JSON escaping. The concrete marker `Result available in structuredContent.` adds exactly 63 bytes. Observed results reach 16,378 bytes, leaving only six bytes of headroom, so even this marker must be included in the packer's complete-envelope accounting and reserve. Its minimum capacity cost is 63 bytes; deterministic atomic packing may omit a larger whole bundle to make room.

A 1KiB text projection costs at least 1,049 bytes plus escaping, creates a second lossy semantic contract, and still may not contain the evidence the caller needs. Putting the full JSON in both `content` and `structuredContent` would add roughly another 16KB for near-limit results and cannot meet the 16,384-byte ceiling. A marker would make the run-20 mistake visible, but it cannot recover the discarded structured body or eliminate a retry after a caller has already printed only `content`. The minimal effective no-repeat repair is to print `JSON.stringify(r.structuredContent ?? r)` on the first invocation and avoid batching several near-limit results into one unpragmatized outer output. If content-only clients become a product requirement, define a new policy/schema with an explicit projection and rebalance the packet rather than adding an undocumented v1 summary.

Source-reference size is product-controllable, but it is separate from the host cap. Existing footprint evidence (`diagnosis/packet-footprint.json`) attributes about 3.9-5.35KB of four near-limit packets to repeated source-ref keys and values. A future compact versioned locator can remain stateless and deterministic, continue accepting legacy v1 locators, and preserve repository/file/hash/extent validation. Compacting references alone may let the existing packer spend the saved bytes on more evidence and still approach 16,384 bytes, so it does not guarantee a smaller outer result. It also does not justify accepting the run-17 malformed locator; `loci_read` correctly requires the returned next reference to be followed unchanged (`src/loci/mcp_server.py:250-267`, `contract.md:34-50`).

The observer has a deterministic supplementary repair. Keep the frozen adapter and frozen scores untouched. Add a versioned delivery adapter that:

1. Splits an outer text block into complete JSON-line candidates while retaining the original block reference and byte offsets.
2. Matches each parsed line exactly against native `result` and `structuredContent` values.
3. Applies truncation only to the block or line containing the marker; it must not use turn-global `any(block["truncated"])` for unrelated outputs.
4. Retains `ambiguous_exact` (or a clearer `shared_exact_identical_result`) when more than one native invocation has the same candidate hash. It may prove that the value was visible, but must not manufacture per-invocation attribution.

The host can fully solve the last ambiguity only by recording a trusted parent outer-call ID on each nested MCP event, or an equivalent execution ID propagated into both native records. Loci must not synthesize that provenance in its semantic result.

## Direct verification recipe

Verification can use the frozen observations without another model run:

1. Run the supplementary adapter over the three existing `observation.json` files and require the exact matrix in `delivery-boundary-measurements.json`: run 17 lines 46/48/56 exact and 47 clipped; run 21 lines 32/39/40/55/56 exact, 54 clipped, and read line 47 exact; run 20 both remain ambiguous at the invocation level.
2. Assert every promoted exact value parses as JSON and equals the retained native result or `structuredContent`; byte-prefix or semantic similarity is insufficient.
3. Assert the new adapter writes separate supplementary artifacts and never mutates frozen observations, assessments, reviews, or scores.
4. For any later normal-use instruction change, fixture the run-20 program shape and require the example to print `structuredContent` on the first call. For any bounded content marker, require the structured body to remain unchanged and the complete MCP envelope to remain at or below 16,384 bytes.
5. For any compact locator proposal, require deterministic round-trip across process restart, unchanged v1 acceptance, strict rejection of malformed/tampered fields, unchanged stale/hash/containment checks, and measured result-size reduction before claiming delivery benefit.

Material unknowns remain: the retained trace does not expose the host's exact reduction algorithm or trusted nested-to-outer call identity; a truncation marker proves reduction at the outer boundary but not which omitted bytes the model may have cached elsewhere. Per-line equality establishes visibility of intact values, not cognition or exclusive provenance.
