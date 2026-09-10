# TypeScript context A-only baseline report

This report aggregates the saved current-retrieval baseline artifacts. It contains no candidate comparison or improvement claim.

## Batch and eligibility

- Batch: **complete**; 51/51 unique planned case/repetition identities.
- Parsed result files: 51; recorded cost fields are retained. Complete accounting: no.
- Eligible cases: 7/17; eligibility requires correctness 3/3.

## Group medians

| Group | Cases | Runs | Eligible | Context recall | Avoidable reads | JSON bytes | Source bytes | Delivered links |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| fixture14 | 14 | 42 | 6 | 0.458333 | unavailable | unavailable | 330.5 | 0 |
| maintained3 | 3 | 9 | 1 | 0 | unavailable | unavailable | 5303 | 0 |

## Costs and latency

- Recorded JSON subtotal: 319486 bytes; incomplete delivery accounting prevents a complete total.
- JSON tool-output bytes: unavailable; source bytes: 65660; duplicate source bytes: 12998.
- Provider tokens: gross input 2463293, cached input 1739776, output 47634; missing values remain unavailable.
- Index latency median: 0.0147737 s; end-to-end median: 30.6578 s.
- Maintained end-to-end p95: 110.23417275000247 s (nearest_rank, sample 9/9, failures included).

## Context, causality, and relationships

- Context recall median: 0; avoidable-read median: unavailable.
- Runs with null or inconclusive avoidable-read accounting: 47; these values are not treated as zero.
- Available dependency links median: 0; delivered dependency links median: 0.
- Proven forbidden relationships median: 0. This counts authored frozen negative checks only and is not exhaustive unsupported-edge truth.

## Per-case outcomes

| Case | Group | Runs | Correct | Eligible | Outcomes | Context recall median | Avoidable reads median |
| --- | --- | ---: | ---: | --- | --- | ---: | ---: |
| imported_interface | fixture14 | 3 | 2/3 | no | completed=2, tool_failure=1 | 1 | unavailable |
| local_interface | fixture14 | 3 | 3/3 | yes | completed=3 | 0 | unavailable |
| local_alias_chain | fixture14 | 3 | 3/3 | yes | completed=3 | 1 | unavailable |
| imported_alias_chain | fixture14 | 3 | 3/3 | yes | completed=3 | 1 | unavailable |
| named_type_reexport_chain | fixture14 | 3 | 2/3 | no | completed=2, tool_failure=1 | 0.25 | unavailable |
| same_name_wrong_file | fixture14 | 3 | 3/3 | yes | completed=3 | 0 | unavailable |
| local_heritage | fixture14 | 3 | 2/3 | no | completed=2, tool_failure=1 | 1 | unavailable |
| imported_heritage | fixture14 | 3 | 2/3 | no | completed=2, tool_failure=1 | 1 | unavailable |
| ambiguous_star_exports | fixture14 | 3 | 3/3 | yes | completed=3 | 1 | unavailable |
| generic_shadow | fixture14 | 3 | 3/3 | yes | completed=3 | 0 | unavailable |
| exported_arrow | fixture14 | 3 | 1/3 | no | completed=3 | 0 | unavailable |
| default_identifier | fixture14 | 3 | 0/3 | no | completed=1, tool_failure=2 | 1 | unavailable |
| named_function_control | fixture14 | 3 | 1/3 | no | completed=3 | 1 | unavailable |
| inline_default_control | fixture14 | 3 | 0/3 | no | completed=2, tool_failure=1 | 0 | unavailable |
| anvil_temporal_arguments | maintained3 | 3 | 3/3 | yes | completed=3 | 0 | unavailable |
| anvil_retrieval_limits | maintained3 | 3 | 0/3 | no | budget_exhausted=1, completed=1, tool_failure=1 | 0 | unavailable |
| anvil_renderer_result_contract | maintained3 | 3 | 1/3 | no | budget_exhausted=2, completed=1 | 0 | unavailable |

## Failure categories

`{"budget_exhausted": 5, "incorrect_answer": 8, "invalid_trace": 9, "unaccounted_tool_output": 11}`

Raw measurements, provider usage (when present), failure objects, causal classifications, relationship blocks, and source events are retained per run in `summary.json` under `runs`.
