# Multilingual workflow measurement and delivery decisions

W4.7 (`task_ecbfc0ce724b713f2599830d21438a46`) retains all **114 scheduled
attempts**. Independent replay reproduces all 114 frozen results with no replay
failures. **Only the single Markdown navigation control passes every workflow
gate.** This batch establishes no programming-language efficiency recommendation.
The implemented language slices remain available for isolated, bounded source
inspection; their shared interface does not establish general task usefulness.

## Published experiment

The original 19 cases, source snapshots, answer gold and source judgments are
unchanged. Preparation `c910c5ac252a7c982f784d87d61bc4c50fc0c0ec` and separate
freeze `14cdf4c3061a74060e51cd7c682b56a40b9f1f9e` were published before the first
provider request. Both arms use accepted W4.6 engine `4f26681`, extractor 30 and
graph state 14. A exposes exact retrieval and graph tools; B adds actual
`loci_explore` and the frozen guide. This measures the combined workflow package.

The host is ChatGPT-authenticated Codex 0.154.0 with Luna/high/default. Its
binary, effective schemas/prompts, catalog, environment, scorer, budgets and
alternating serial schedule are pinned. The host rejects built-in retry
overrides, so native transport recovery remains unchanged in both arms. There
were zero scheduled retries, replacements, score changes or batch extensions.
The backend model snapshot is not exposed. Provider usage is reported usage,
not a dollar or subscription-credit estimate.

- [Frozen protocol](../../benchmarks/comparisons/multilingual-context-workflow-v1/protocol.md)
  and [freeze](../../benchmarks/comparisons/multilingual-context-workflow-v1/freeze.json).
- [Every result and metric vector](../../benchmarks/results/multilingual-context-workflow-v1/report-summary.json)
  and [frozen generated report](../../benchmarks/results/multilingual-context-workflow-v1/report.md).
- [Independent raw replay and artifact hashes](../../benchmarks/results/multilingual-context-workflow-v1/replay-verification.json).
- [Evaluator and exact-retrieval defects](2026-09-13-multilingual-measurement-defects.md).
- Independent bounded audits of [Python/JavaScript](../../benchmarks/results/multilingual-context-workflow-v1/independent-reviews/python-javascript.md),
  [Go](../../benchmarks/results/multilingual-context-workflow-v1/independent-reviews/go.md),
  [Rust](../../benchmarks/results/multilingual-context-workflow-v1/independent-reviews/rust.md)
  and [report identities, metrics and gates](../../benchmarks/results/multilingual-context-workflow-v1/independent-reviews/report.md).

## Per-language disposition

Counts are frozen outcomes. Complete accounting is distinct from replay: a
failed or incomplete measurement can replay exactly. Python combined overlaps
its two required subgroups and must not be added to their denominators.

| Scope | Complete accounting | Exact answers A / B | Full passes B | Frozen disposition and practical limit |
| --- | ---: | ---: | ---: | --- |
| Python combined, 5 cases | 11/30 | 4/15 / 3/15 | 0/15 | Withheld comparison; inspect bounded authored source, with completeness and efficiency unproven |
| Python synthetic, 4 cases | 5/24 | 1/12 / 0/12 | 0/12 | Withheld accounting; alias paths, workflow choices and exact-answer encoding limit outcomes |
| Python maintained single module | 6/6 | 3/3 / 3/3 | 0/3 | Measured limitation: correct answers/full source, incomplete relationship coverage and no cost benefit |
| JavaScript, 4 cases | 7/24 | 7/12 / 5/12 | 3/12 | Withheld comparison; useful delivered base/call proof, with alternate-path and source omissions |
| Go, 4 cases | 9/24 | 4/12 / 6/12 | 0/12 | Withheld comparison; required control access is asymmetric and compact selection omits available relationships |
| Rust, 4 cases | 12/24 | 3/12 / 4/12 | 0/12 | Withheld comparison; inspect bounded authored/Cargo proof and explicit omissions, without an efficiency claim |
| TypeScript/TSX props control | 6/6 | 0/3 / 2/3 | 2/3 | Measured limitation: full source and B relation proof, one origin-encoding mismatch and no cost improvement |
| Markdown navigation control | 6/6 | 3/3 / 3/3 | 3/3 | Workflow supported only for this one heading/section task |

Overall there are 51 complete measurements, 44 exact answers, 11 full passes
and 993 observed calls. These totals do not override any language decision.
Sixty-three rows have incomplete graph accounting. One timed-out JavaScript
attempt has no terminal provider-usage event; its usage remains unavailable.
The frozen report retains all hard-budget failures and every null metric.

## Source value and remaining limits

Actual packets retain their source hashes, authored meaning and complete selected
proof paths. The frozen relationship objects record no forbidden proven edge or
delivery-integrity violation. Incomplete accounting prevents treating those zero
counts as exhaustive certification of every delivered graph response. Inspection
does not demonstrate invented or misattributed Loci source.

Python base/forward-name and call-impact packets supply the required relations.
Alias selection can omit an available alternate path. JavaScript supplies direct
base and known-call proof, while the value-dependency case consistently delivers
2/3 relations: selecting `add` directly from `run` omits the available alternate
`make -> add` path and reports `alternative_path`. Four JavaScript workflows
also miss required source. These are coverage limits, not invented relationships.

Go embedding packets deliver all four required relations; uncertainty packets
retain the positive `Keep -> Request` relation and omit unproven calls. Alias and
API-impact cases omit available paths or use an intent/seed selection that does
not deliver them. Exact file/grep cannot read the required non-indexed `go.mod`
source; only explore supplies that control in this comparison. All twelve A rows
miss the module interval. This baseline access restriction precludes a fair Go
efficiency interpretation independently of the graph accounting defect.

Rust packets deliver full workspace re-export and uncertainty proof, with
`declared_possible` preserving configuration uncertainty. Authored trait/impl
coverage is 9/11, 3/11 and 5/11 in B; known-call coverage is 0/3, 1/3 and 1/3.
Those omissions remain explicit. Exact retrieval also cannot return required
Cargo manifests: ten file calls fail, all twelve A rows miss manifest source,
and eleven B rows obtain controls through explore. One workspace B answer names
the entry function rather than the requested re-exported declaration despite
full source and proof. Two malformed model-supplied search IDs are correctly
rejected; they are unrelated to false source. Five Rust input-token failures
remain in the denominator.

The maintained Python task has complete source and correct answers in both arms.
B delivers 2/4, 2/4 and 0/4 required relationships. Its packets disclose
`not_selected`, alternate-path, anchor and hop omissions; the last repetition
uses locate and disconnected inferred anchors. Exact follow-up reads recover
the answer's declarations without delivering the missing relationship proofs.
Correct facts therefore do not make these full passes.

TSX delivers `Badge`, `Props`, authored fields and the negative JSX-call fact.
All B runs deliver the required relation. The first B answer uses
`props.ts::Props` where gold requires `props.ts`; A uses the authored import
specifier `./props`. These are exact-answer mismatches without demonstrated
wrong-source attribution. This one control makes no broad TypeScript claim.

The ordinary prompts name fields but do not uniformly prescribe gold's value
shapes, endpoint granularity or normalized path spelling. Many failed answers
therefore establish exact-contract failures rather than factual misunderstanding.
Actual wrong expressions and false exact-target or promoted-dispatch certainty
are separate observed model errors. Keep all scores; this interpretation limit
does not authorize rescoring or a model-reliability study.

## Costs and accepted recommendation

Complete-accounting scopes have the following frozen case medians. Latency is
nearest-rank p95 over each arm's three attempts. Full provider input, cached-input
subset, output including reasoning, separately reported reasoning, source/output
byte vectors and all case medians remain in the generated report.

| Scope | Calls A → B | Full output bytes A → B | Gross input tokens A → B | p95 seconds A → B |
| --- | ---: | ---: | ---: | ---: |
| Maintained Python | 4 → 4 | 12,182 → 13,030 | 35,072 → 35,132 | 26.53 → 24.28 |
| TSX | 4 → 4 | 4,147 → 5,032 | 28,790 → 33,029 | 26.09 → 28.04 |
| Markdown | 3 → 1 | 2,042 → 1,321 | 21,538 → 11,174 | 20.55 → 16.47 |

Markdown passes the full quality/cost rule: all B attempts fully pass, median
calls fall by two, output and gross input decline, and p95 latency remains within
the 1.25 ratio. This supports the isolated compact navigation workflow for the
measured section task only. Its result cannot stand in for a programming language.

Withheld languages retain direct counts and usage where available, but null
complete output/source metrics stay null. Recorded subtotals and trace-derived
unique/duplicate byte values cannot replace complete observed accounting. Lower
diagnostic call counts in those groups do not support an efficiency claim.

## Delivery boundary

Retain the implemented authored-language capabilities documented by W4.2–W4.6,
with their existing uncertainty, configuration and non-exhaustive-impact limits.
Inspect packet omissions and retrieve missing source/proof before relying on a
complete contract. The workflow cannot currently promise all available alternate
relationships, and exact indexed retrieval does not cover every resolver control.

The graph-name reconciliation, hidden schema bounds and control-file access
defects remain explicit deferred repair items. Their deterministic repair and
any future separately frozen measurement are distinct scope decisions. Historical
W2.5 artifacts/verdicts, both original corpora and the discontinued diagnostic
remain unchanged. This result authorizes no new batch, integration, shared-runtime
promotion or automatic W3 implementation.
