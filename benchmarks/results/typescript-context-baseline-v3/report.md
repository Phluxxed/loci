# V3 observed-call baseline

Descriptive baseline only. V1/v2 use different protocols and are not paired comparators. No B or C implementation or improvement is measured.

Answers correct: 51/51. Full passes: 51/51. Complete measurement: 51/51.

| Maintained task | Full passes | Calls, median | Source recall, median | Output bytes, median | Gross input, median |
|---|---:|---:|---:|---:|---:|
| anvil_temporal_arguments | 3/3 | 5 | 0.8 | 11419 | 40778 |
| anvil_retrieval_limits | 3/3 | 7 | 1.0 | 20641 | 67681 |
| anvil_renderer_result_contract | 3/3 | 10 | 1.0 | 30667 | 102444 |

Maintained p95 latency (all nine attempts): 50.258 seconds.

Fully successful maintained tasks: 3/3; sum of their median calls: 22.
Observed work, including planned work. This does not identify avoidable calls or prove a candidate can reduce them. Future matched comparisons must rerun A.

All errors and failed attempts retain their costs. Reported provider input is gross; cached input is a subset. Source estimates are separate from provider tokens. Relationship negatives cover only the authored forbidden relationships.

## All planned attempts

| Attempt | Answer | Full pass | Accounting | Calls | Output bytes | Source recall | Outcome |
|---|---|---|---|---:|---:|---:|---|
| imported_interface-r1 | True | True | True | 4 | 3052 | 1.000 | completed |
| imported_interface-r2 | True | True | True | 4 | 3052 | 1.000 | completed |
| imported_interface-r3 | True | True | True | 4 | 3052 | 1.000 | completed |
| local_interface-r1 | True | True | True | 4 | 3123 | 1.000 | completed |
| local_interface-r2 | True | True | True | 4 | 2971 | 1.000 | completed |
| local_interface-r3 | True | True | True | 4 | 3066 | 1.000 | completed |
| local_alias_chain-r1 | True | True | True | 6 | 5291 | 1.000 | completed |
| local_alias_chain-r2 | True | True | True | 8 | 5889 | 1.000 | completed |
| local_alias_chain-r3 | True | True | True | 6 | 5108 | 1.000 | completed |
| imported_alias_chain-r1 | True | True | True | 6 | 4943 | 1.000 | completed |
| imported_alias_chain-r2 | True | True | True | 6 | 4943 | 1.000 | completed |
| imported_alias_chain-r3 | True | True | True | 6 | 4024 | 1.000 | completed |
| named_type_reexport_chain-r1 | True | True | True | 8 | 3829 | 1.000 | completed |
| named_type_reexport_chain-r2 | True | True | True | 7 | 4803 | 1.000 | completed |
| named_type_reexport_chain-r3 | True | True | True | 6 | 5627 | 0.750 | completed |
| same_name_wrong_file-r1 | True | True | True | 4 | 3769 | 1.000 | completed |
| same_name_wrong_file-r2 | True | True | True | 4 | 3486 | 1.000 | completed |
| same_name_wrong_file-r3 | True | True | True | 4 | 3486 | 1.000 | completed |
| local_heritage-r1 | True | True | True | 5 | 6658 | 1.000 | completed |
| local_heritage-r2 | True | True | True | 2 | 3498 | 1.000 | completed |
| local_heritage-r3 | True | True | True | 2 | 1367 | 1.000 | completed |
| imported_heritage-r1 | True | True | True | 6 | 6261 | 1.000 | completed |
| imported_heritage-r2 | True | True | True | 3 | 1909 | 1.000 | completed |
| imported_heritage-r3 | True | True | True | 5 | 5435 | 0.800 | completed |
| ambiguous_star_exports-r1 | True | True | True | 9 | 7011 | 1.000 | completed |
| ambiguous_star_exports-r2 | True | True | True | 8 | 7651 | 1.000 | completed |
| ambiguous_star_exports-r3 | True | True | True | 11 | 11128 | 1.000 | completed |
| generic_shadow-r1 | True | True | True | 5 | 3341 | 1.000 | completed |
| generic_shadow-r2 | True | True | True | 4 | 2522 | 1.000 | completed |
| generic_shadow-r3 | True | True | True | 4 | 3031 | 1.000 | completed |
| exported_arrow-r1 | True | True | True | 4 | 3354 | 0.750 | completed |
| exported_arrow-r2 | True | True | True | 4 | 3354 | 0.750 | completed |
| exported_arrow-r3 | True | True | True | 3 | 1014 | 1.000 | completed |
| default_identifier-r1 | True | True | True | 4 | 3576 | 1.000 | completed |
| default_identifier-r2 | True | True | True | 4 | 3576 | 1.000 | completed |
| default_identifier-r3 | True | True | True | 5 | 5135 | 0.500 | completed |
| named_function_control-r1 | True | True | True | 4 | 3397 | 0.750 | completed |
| named_function_control-r2 | True | True | True | 4 | 3397 | 0.750 | completed |
| named_function_control-r3 | True | True | True | 4 | 3936 | 0.750 | completed |
| inline_default_control-r1 | True | True | True | 4 | 3395 | 0.750 | completed |
| inline_default_control-r2 | True | True | True | 3 | 1022 | 1.000 | completed |
| inline_default_control-r3 | True | True | True | 6 | 6475 | 0.750 | completed |
| anvil_temporal_arguments-r1 | True | True | True | 5 | 11419 | 0.800 | completed |
| anvil_temporal_arguments-r2 | True | True | True | 4 | 9997 | 0.800 | completed |
| anvil_temporal_arguments-r3 | True | True | True | 5 | 14371 | 1.000 | completed |
| anvil_retrieval_limits-r1 | True | True | True | 7 | 20641 | 0.875 | completed |
| anvil_retrieval_limits-r2 | True | True | True | 8 | 23278 | 1.000 | completed |
| anvil_retrieval_limits-r3 | True | True | True | 6 | 19355 | 1.000 | completed |
| anvil_renderer_result_contract-r1 | True | True | True | 8 | 27345 | 0.800 | completed |
| anvil_renderer_result_contract-r2 | True | True | True | 10 | 31978 | 1.000 | completed |
| anvil_renderer_result_contract-r3 | True | True | True | 10 | 30667 | 1.000 | completed |
