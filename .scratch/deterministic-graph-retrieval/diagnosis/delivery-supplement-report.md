# W1.8.4.3 supplementary delivery correction

Status: implemented and verified against the three selected retained observations. This is a new interpretation layer only. It does not modify or rescore a frozen observation, assessment, review, answer, or comparison.

## Implementation

`benchmarks/ordinary_adoption_delivery_v3.py` accepts an existing normalized observation and returns `ordinary-adoption-delivery-v3`, kind `supplemental_delivery_interpretation`. It records the source observation hash, retained native identity, original `model_delivery` object/status, native result reference, and new supplementary status.

The adapter treats only a whole line that parses as strict JSON and is type-aware equal to the native `result` or `structuredContent` as exact. It also preserves strict whole-block equality for a pretty-printed JSON object when no complete JSON line matched. Line matches retain the original outer block reference plus one-based line number, zero-based line index, and UTF-8 start/end byte offsets; whole-block matches use the same block reference and bytes `0:<block length>`. It rejects duplicate object keys and non-finite constants. Boolean and numeric JSON values remain distinct; alternate spellings of the same JSON number, such as `1` and `1.0`, compare as the same number.

For a malformed line containing the host marker `…N tokens truncated…`, the adapter may record `unproven_clipped_exact_fragments` only when the retained prefix and suffix align exactly with one native candidate's wire serialization. That evidence remains unproven and never becomes `full_exact`. A warning elsewhere in the block or turn does not qualify an unrelated unmatched call as clipped.

Exact attribution is keyed by the emitted output location rather than candidate serialization hash. Thus two native candidates that differ only in equivalent JSON number spelling still remain `ambiguous_exact` when they match one visible value. The adapter does not use timing, request order, guessed parent calls, nonces, substrings, prefixes, or semantic similarity to promote exact delivery. It does not include raw outer block text in its supplements.

## Retained results

| Run / native MCP line | Original status | Supplement | Exact output provenance |
| --- | --- | --- | --- |
| 17 / 46 retrieve | `unknown_truncated` | `full_exact` | `outer:call_GGhtL2tNh2Np7kEySDHIGNZX:line:49:block:1`, JSON line 4, bytes 79:14968 |
| 17 / 47 retrieve | `unknown_truncated` | `unproven_clipped` | Same block, marker-bearing JSON line 5; 122 reported omitted tokens |
| 17 / 48 read | `unknown_truncated` | `full_exact` | Same block, JSON line 6, bytes 30622:40105 |
| 17 / 56 read error | `unknown_truncated` | `full_exact` | `outer:call_yamVZUPeXR1PwQVyQRMkIag3:line:57:block:1`, JSON line 71, bytes 3990:4090 |
| 20 / 30 retrieve | `ambiguous_exact` | `ambiguous_exact` | Shared exact line below |
| 20 / 37 retrieve | `ambiguous_exact` | `ambiguous_exact` | `outer:call_h9Sc3xAnaUndMN48A7ogW0An:line:38:block:1`, JSON line 1, bytes 0:16134 |
| 21 / 32 retrieve | `unknown_truncated` | `full_exact` | `outer:call_qkKVLYRjrmnDX2LayOOK3OVL:line:33:block:1`, JSON line 2, bytes 14260:30263 |
| 21 / 39 retrieve | `unknown_truncated` | `full_exact` | `outer:call_VKv7yNlsndeodUUS4v7FszAF:line:41:block:1`, JSON line 1, bytes 0:16151 |
| 21 / 40 retrieve | `unknown_truncated` | `full_exact` | Same block, JSON line 2, bytes 16152:32492 |
| 21 / 47 read | `full_exact` | `full_exact` | `outer:call_s52i6Sg78e76hDtsFpPIjq8z:line:48:block:1`, JSON line 1, bytes 0:5362 |
| 21 / 54 retrieve | `unknown_truncated` | `unproven_clipped` | `outer:call_c619cHNVbBvp4PA7RZxrqHnO:line:57:block:1`, marker-bearing JSON line 5; 2,257 reported omitted tokens |
| 21 / 55 retrieve | `unknown_truncated` | `full_exact` | Same block, JSON line 4, bytes 79:16452 |
| 21 / 56 retrieve | `unknown_truncated` | `full_exact` | Same block, JSON line 6, bytes 23728:40106 |

The generated supplements are:

- `diagnosis/delivery-supplement-run-17.json` — SHA-256 `4fd12678e3bfc9e66d52c2f90b725f835ce697dba191b25917b211ca6bda676a`
- `diagnosis/delivery-supplement-run-20.json` — SHA-256 `b296cfee9796c361df0abab579da05228b92c19e123a4434822b198f2c9110d3`
- `diagnosis/delivery-supplement-run-21.json` — SHA-256 `c3099c8896aba4a1c4fc1eaf7ce616816a8ca79d3a15053fb4db029b8e63b2f0`

No other ordinary rows were interpreted.

## Verification

`tests/test_ordinary_adoption_delivery_v3.py` covers exact structured/result JSON lines, strict pretty-printed whole-block JSON, block/line/byte provenance, locally aligned truncation fragments, input immutability, identical/equivalent-number result ambiguity, quoted and fenced JSON, prefixed examples, partial and malformed lines, mismatched payloads, unrelated warnings, boolean/number confusion, duplicate keys, non-finite constants, equivalent JSON number spelling, and the complete retained run-17/run-20/run-21 matrix.

Direct check after the attribution and whole-block follow-up: `.venv/bin/python -m pytest -q tests/test_ordinary_adoption_delivery_v3.py` — 19 passed.

The preceding adjacent-adapter compatibility run passed 61 tests before this local follow-up. The affected delivery-v3 suite was rerun after the follow-up; frozen adapter suites were not needlessly repeated.

## External boundary

This supplement proves that a complete parsed JSON line was model-visible at a particular outer block location. It does not prove cognition, exclusive provenance for identical invocations, or what omitted bytes a host may retain elsewhere. Loci still cannot force Code Mode printing, control arbitrary aggregate output caps, recover a result discarded by caller code, or synthesize a trusted nested-to-outer host identity. Content markers, text projections, locator changes, and new usage guidance remain outside this correction.
