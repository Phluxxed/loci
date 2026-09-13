# W4.7 frozen-report audit

Cross-checked the frozen report against every retained attempt, its independent replay record, and the published freeze. No provider call, rescore, or source mutation was performed.

## Verified identities and retention

- Freeze plan: 114 unique scheduled attempt IDs; report rows, raw result directories, and replay attempt IDs each contain that same set exactly once.
- Replay: 114/114 verified, complete, with zero replay failures.
- Every raw result/provenance retained the freeze hash, freeze commit, corpus hash, controls hash, and model-catalog hash matching `freeze.json`.
- All 193 frozen file hashes and all 74 harness-hash entries match the current frozen files; corpus and controls bytes match the freeze identities.

## Global retained counts

- A: 57 recorded; 16 complete observations; 21 correct answers; 3 full passes; 539 observed calls.
- B: 57 recorded; 35 complete observations; 23 correct answers; 8 full passes; 454 observed calls.
- Replay is complete, but 63/114 raw observations have incomplete source/output accounting. The report preserves null complete-only metrics and reports subtotal values rather than treating them as complete.

## Slice cross-check

| Slice | Cases | Attempts | Complete evidence | B full passes | Report disposition |
|---|---:|---:|---:|---:|---|
| go | 4 | 24 | 9 | 0/12 | withheld |
| javascript | 4 | 24 | 7 | 3/12 | withheld |
| markdown_navigation_control | 1 | 6 | 6 | 3/3 | workflow_supported |
| python_combined | 5 | 30 | 11 | 0/15 | withheld |
| python_maintained_single_module | 1 | 6 | 6 | 0/3 | measured_limitation |
| python_synthetic | 4 | 24 | 5 | 0/12 | withheld |
| rust | 4 | 24 | 12 | 0/12 | withheld |
| tsx_control | 1 | 6 | 6 | 2/3 | measured_limitation |

For each slice, independently recomputed the per-case three-run denominator and complete-only metric median from the report rows, then compared every reported per-case metric object. All matched. All ten predeclared gate statuses match their retained scope state: incomplete scopes retain `null` gate outcomes; complete Markdown, TSX, and maintained-Python scopes preserve their recorded boolean outcomes.

## Limitation

The report’s global and incomplete-slice quality/efficiency gates are inconclusive because it does not silently complete missing accounting. Its `withheld` disposition is driven by retained accounting/delivery-boundary trust defects. It does not assert a false engine-source conclusion. Rust semantic interpretation remains outside this audit.
