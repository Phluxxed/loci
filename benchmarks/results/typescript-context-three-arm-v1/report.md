# Three-arm type-context comparison

Candidate C/A verdict: **reject**. All-pairs diagnostic: **reject**.

The frozen v3 corpus, controls, 13 typed operations, source snapshots, ranking and budgets are shared by A, B and C. Pair gates use the frozen A/B evaluator with actual arm names restored.

C's new semantics benefit is established only when C/B passes the frozen read rule and gates; C/A alone is insufficient.

W2.4 `loci_explore` is not exposed by the frozen tool schema and is not measured.

## Arm totals

| Arm | Answers | Full passes | Complete measurements | Calls | Source bytes | Unique source bytes | Output bytes | Gross input | End-to-end p95 | Index time |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| A | 51/51 | 51/51 | 51/51 | 284 | 86554 | 54913 | 385153 | 2245727 | 60.41948749999574 | 0.04593845800263807 |
| B | 51/51 | 47/51 | 51/51 | 276 | 77519 | 50994 | 439949 | 2206260 | 50.2912378750043 | 0.046573999992688186 |
| C | 51/51 | 49/51 | 51/51 | 190 | 107840 | 54951 | 667720 | 1697736 | 45.14465729199583 | 0.043304874998284504 |

## Maintained task measurements

| Task | Arm | Answers | Full passes | Complete | Calls, median | Source bytes, median | Unique source, median | Recall, median | Output bytes, median | Gross input, median | Cached input, median | Output tokens, median | End-to-end, median | Index, median |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| imported_interface | A | 3/3 | 3/3 | 3/3 | 4 | 407 | 204 | 1.0 | 3148 | 27709 | 13568 | 397 | 16.40210516699881 | 0.046920584005420096 |
| imported_interface | B | 3/3 | 3/3 | 3/3 | 3 | 422 | 212 | 1.0 | 3329 | 21505 | 13568 | 280 | 14.286055874996237 | 0.04866112499439623 |
| imported_interface | C | 3/3 | 3/3 | 3/3 | 2 | 485 | 219 | 1.0 | 3809 | 16381 | 8704 | 382 | 13.392138124996563 | 0.04197891699732281 |
| local_interface | A | 3/3 | 3/3 | 3/3 | 4 | 314 | 139 | 1.0 | 2970 | 27516 | 13568 | 349 | 14.784745917000691 | 0.04369212499295827 |
| local_interface | B | 3/3 | 3/3 | 3/3 | 4 | 406 | 142 | 1.0 | 3788 | 27914 | 13568 | 338 | 16.803150916995946 | 0.04239229099766817 |
| local_interface | C | 3/3 | 3/3 | 3/3 | 2 | 368 | 149 | 1.0 | 3356 | 16229 | 8704 | 236 | 13.020020791998832 | 0.03762287499557715 |
| local_alias_chain | A | 3/3 | 3/3 | 3/3 | 6 | 474 | 196 | 1.0 | 5246 | 41837 | 30208 | 579 | 32.55524762500136 | 0.041584209000575356 |
| local_alias_chain | B | 3/3 | 3/3 | 3/3 | 5 | 749 | 196 | 1.0 | 5903 | 35296 | 19456 | 545 | 25.71011037500284 | 0.04168045800179243 |
| local_alias_chain | C | 3/3 | 3/3 | 3/3 | 2 | 521 | 205 | 1.0 | 6049 | 17082 | 8704 | 360 | 14.46180508400721 | 0.03795008300221525 |
| imported_alias_chain | A | 3/3 | 3/3 | 3/3 | 7 | 707 | 237 | 1.0 | 6094 | 48791 | 37120 | 800 | 31.12410370798898 | 0.04523879199405201 |
| imported_alias_chain | B | 3/3 | 3/3 | 3/3 | 6 | 665 | 239 | 1.0 | 7089 | 43984 | 27392 | 564 | 23.600341833007406 | 0.04404804100340698 |
| imported_alias_chain | C | 3/3 | 3/3 | 3/3 | 2 | 548 | 247 | 1.0 | 6324 | 17321 | 8704 | 391 | 15.967662374998326 | 0.050948750009411015 |
| named_type_reexport_chain | A | 3/3 | 3/3 | 3/3 | 4 | 511 | 280 | 1.0 | 4277 | 28258 | 23296 | 473 | 18.09537716700288 | 0.0495752909919247 |
| named_type_reexport_chain | B | 3/3 | 3/3 | 3/3 | 2 | 496 | 279 | 1.0 | 3649 | 16407 | 12544 | 414 | 16.983882374988752 | 0.04558583299512975 |
| named_type_reexport_chain | C | 3/3 | 3/3 | 3/3 | 3 | 638 | 286 | 1.0 | 4967 | 23331 | 10752 | 451 | 15.887395291996654 | 0.043466958988574333 |
| same_name_wrong_file | A | 3/3 | 3/3 | 3/3 | 4 | 448 | 245 | 1.0 | 3590 | 27950 | 23296 | 373 | 15.14191729099548 | 0.04559424999752082 |
| same_name_wrong_file | B | 3/3 | 3/3 | 3/3 | 2 | 422 | 212 | 1.0 | 3230 | 16192 | 12544 | 340 | 13.378636541005108 | 0.04505741699540522 |
| same_name_wrong_file | C | 3/3 | 3/3 | 3/3 | 2 | 485 | 219 | 1.0 | 3813 | 16423 | 12544 | 330 | 14.193517791994964 | 0.043304874998284504 |
| local_heritage | A | 3/3 | 3/3 | 3/3 | 3 | 887 | 249 | 1.0 | 3684 | 22440 | 13568 | 610 | 20.993293209001422 | 0.04234787500172388 |
| local_heritage | B | 3/3 | 3/3 | 3/3 | 7 | 838 | 242 | 1.0 | 7731 | 49897 | 38912 | 648 | 26.860268333999556 | 0.04070283300825395 |
| local_heritage | C | 3/3 | 3/3 | 3/3 | 2 | 1494 | 252 | 1.0 | 7910 | 18018 | 12544 | 439 | 14.69961029200931 | 0.037063625000882894 |
| imported_heritage | A | 3/3 | 3/3 | 3/3 | 4 | 1250 | 319 | 1.0 | 4853 | 30331 | 23296 | 438 | 23.2225655830116 | 0.04219162500521634 |
| imported_heritage | B | 3/3 | 3/3 | 3/3 | 6 | 1049 | 300 | 1.0 | 8924 | 45990 | 35072 | 529 | 21.375957875003223 | 0.046573999992688186 |
| imported_heritage | C | 3/3 | 3/3 | 3/3 | 4 | 1133 | 323 | 1.0 | 9700 | 31531 | 18432 | 387 | 15.711367458992754 | 0.041915124995284714 |
| ambiguous_star_exports | A | 3/3 | 3/3 | 3/3 | 9 | 561 | 336 | 1.0 | 9146 | 65117 | 47872 | 663 | 27.821927875003894 | 0.048698417012928985 |
| ambiguous_star_exports | B | 3/3 | 3/3 | 3/3 | 11 | 817 | 336 | 1.0 | 8272 | 79531 | 67584 | 743 | 33.6415256249893 | 0.044814917011535726 |
| ambiguous_star_exports | C | 3/3 | 3/3 | 3/3 | 11 | 598 | 329 | 1.0 | 11028 | 81566 | 62464 | 799 | 34.296021667003515 | 0.043181334011023864 |
| generic_shadow | A | 3/3 | 3/3 | 3/3 | 4 | 386 | 177 | 1.0 | 2563 | 27422 | 21248 | 445 | 17.639873292006087 | 0.03945683399797417 |
| generic_shadow | B | 3/3 | 3/3 | 3/3 | 4 | 386 | 177 | 1.0 | 3691 | 28151 | 14592 | 624 | 19.707230665997486 | 0.04095683300693054 |
| generic_shadow | C | 3/3 | 3/3 | 3/3 | 5 | 440 | 191 | 1.0 | 3752 | 33779 | 23296 | 518 | 20.342732334000175 | 0.036278708997997455 |
| exported_arrow | A | 3/3 | 3/3 | 3/3 | 3 | 292 | 127 | 0.75 | 1528 | 20977 | 16384 | 300 | 16.228094375008368 | 0.04368020800757222 |
| exported_arrow | B | 3/3 | 3/3 | 3/3 | 4 | 305 | 120 | 0.75 | 4414 | 28681 | 22272 | 411 | 15.337412707987824 | 0.04894712500390597 |
| exported_arrow | C | 3/3 | 3/3 | 3/3 | 4 | 339 | 120 | 0.75 | 4072 | 28666 | 21248 | 422 | 17.711886459001107 | 0.039925000004586764 |
| default_identifier | A | 3/3 | 3/3 | 3/3 | 4 | 353 | 158 | 1.0 | 4417 | 28748 | 23296 | 410 | 17.014781000005314 | 0.045762082998408005 |
| default_identifier | B | 3/3 | 3/3 | 3/3 | 4 | 399 | 150 | 1.0 | 4148 | 28551 | 23296 | 379 | 17.272186290996615 | 0.04974612499063369 |
| default_identifier | C | 3/3 | 3/3 | 3/3 | 3 | 352 | 150 | 1.0 | 3793 | 22537 | 16384 | 382 | 14.42225629099994 | 0.04444425000110641 |
| named_function_control | A | 3/3 | 3/3 | 3/3 | 4 | 337 | 135 | 0.75 | 3900 | 28422 | 20224 | 349 | 15.920278749996214 | 0.045573916999273933 |
| named_function_control | B | 3/3 | 3/3 | 3/3 | 4 | 384 | 135 | 0.75 | 4147 | 29114 | 23296 | 398 | 16.45195283299836 | 0.051895458993385546 |
| named_function_control | C | 3/3 | 3/3 | 3/3 | 5 | 337 | 135 | 0.75 | 4912 | 35197 | 27136 | 477 | 21.65870004199678 | 0.04100470799312461 |
| inline_default_control | A | 3/3 | 3/3 | 3/3 | 5 | 380 | 131 | 0.75 | 3507 | 34146 | 19456 | 384 | 17.896058792000986 | 0.04937795799924061 |
| inline_default_control | B | 3/3 | 3/3 | 3/3 | 4 | 380 | 131 | 0.75 | 4305 | 28630 | 22272 | 376 | 19.802151333002257 | 0.04560545799904503 |
| inline_default_control | C | 3/3 | 3/3 | 3/3 | 5 | 380 | 131 | 0.75 | 4145 | 34422 | 25088 | 470 | 20.490109791993746 | 0.04512966600304935 |
| anvil_temporal_arguments | A | 3/3 | 3/3 | 3/3 | 7 | 2777 | 1690 | 1.0 | 16958 | 60092 | 48128 | 756 | 31.618932875004248 | 3.919959790990106 |
| anvil_temporal_arguments | B | 3/3 | 2/3 | 3/3 | 6 | 3124 | 1881 | 1.0 | 15991 | 51635 | 39168 | 1038 | 36.72742749999452 | 3.9409802919981303 |
| anvil_temporal_arguments | C | 3/3 | 3/3 | 3/3 | 2 | 1570 | 979 | 1.0 | 11067 | 19053 | 11520 | 555 | 20.966470915998798 | 5.095131375011988 |
| anvil_retrieval_limits | A | 3/3 | 3/3 | 3/3 | 12 | 8442 | 5377 | 1.0 | 28521 | 130449 | 108288 | 1281 | 50.326326499998686 | 3.927064749994315 |
| anvil_retrieval_limits | B | 3/3 | 0/3 | 3/3 | 10 | 6207 | 4795 | 1.0 | 27377 | 100390 | 72192 | 970 | 43.334276875000796 | 3.9244530409923755 |
| anvil_retrieval_limits | C | 3/3 | 1/3 | 3/3 | 6 | 11027 | 5520 | 1.0 | 63202 | 95876 | 70912 | 877 | 39.74484041699907 | 5.153947625003639 |
| anvil_renderer_result_contract | A | 3/3 | 3/3 | 3/3 | 8 | 10376 | 8841 | 0.8 | 26570 | 76293 | 60160 | 985 | 40.81551625000429 | 3.883381791994907 |
| anvil_renderer_result_contract | B | 3/3 | 3/3 | 3/3 | 8 | 8105 | 6873 | 1.0 | 27640 | 86041 | 68352 | 877 | 42.66991379200772 | 3.8414077079942217 |
| anvil_renderer_result_contract | C | 3/3 | 3/3 | 3/3 | 4 | 13754 | 8800 | 1.0 | 65917 | 65166 | 37888 | 742 | 33.86439566699846 | 5.080258542002412 |

## Pair verdicts

| Pair | Verdict | Failed gates | Unknown gates | Eligible maintained tasks | Comparator median-call sum | Candidate median-call sum |
|---|---|---|---|---:|---:|---:|
| B/A | reject | ["maintained_full_passes", "per_task_success", "eligible_paired_tasks", "observed_call_reduction", "tasks_with_fewer_calls"] | [] | 1 | 8 | 8 |
| C/B | reject | ["maintained_full_passes", "eligible_paired_tasks", "tasks_with_fewer_calls", "serialized_tool_output_bytes"] | [] | 1 | 8 | 4 |
| C/A | reject | ["maintained_full_passes", "per_task_success", "serialized_tool_output_bytes"] | [] | 2 | 15 | 6 |

## Frozen gates

### B/A

| Gate | Passed | Actual | Required |
|---|---|---|---|
| complete_measurements | True | {"A": 51, "B": 51} | {"A": 51, "B": 51} |
| fixture_full_passes | True | 42 | 42 |
| authored_false_relationships | True | 0 | 0 |
| repaired_endpoints | True | true | true |
| maintained_full_passes | False | 5 | 8 |
| per_task_success | False | ["anvil_temporal_arguments", "anvil_retrieval_limits"] | [] |
| eligible_paired_tasks | False | 1 | 2 |
| positive_comparator | True | 8 | "> 0" |
| observed_call_reduction | False | 0.0 | 0.2 |
| tasks_with_fewer_calls | False | [] | 2 |
| per_task_source_recall | True | {"A": {"anvil_temporal_arguments": 1.0, "anvil_retrieval_limits": 1.0, "anvil_renderer_result_contract": 0.8}, "B": {"anvil_temporal_arguments": 1.0, "anvil_retrieval_limits": 1.0, "anvil_renderer_result_contract": 1.0}} | "B median >= A median for each maintained task" |
| serialized_tool_output_bytes | True | {"sums_of_task_medians": {"A": 72049, "B": 71008}, "ratio": 0.985551499673833} | 1.0 |
| input_tokens | True | {"sums_of_task_medians": {"A": 266834, "B": 238066}, "ratio": 0.8921876522482143} | 1.0 |
| maintained_p95_latency | True | {"seconds": {"A": 60.41948749999574, "B": 50.2912378750043}, "ratio": 0.8323678328951043} | 1.25 |

### C/B

| Gate | Passed | Actual | Required |
|---|---|---|---|
| complete_measurements | True | {"B": 51, "C": 51} | {"B": 51, "C": 51} |
| fixture_full_passes | True | 42 | 42 |
| authored_false_relationships | True | 0 | 0 |
| repaired_endpoints | True | true | true |
| maintained_full_passes | False | 7 | 8 |
| per_task_success | True | [] | [] |
| eligible_paired_tasks | False | 1 | 2 |
| positive_comparator | True | 8 | "> 0" |
| observed_call_reduction | True | 0.5 | 0.2 |
| tasks_with_fewer_calls | False | ["anvil_renderer_result_contract"] | 2 |
| per_task_source_recall | True | {"B": {"anvil_temporal_arguments": 1.0, "anvil_retrieval_limits": 1.0, "anvil_renderer_result_contract": 1.0}, "C": {"anvil_temporal_arguments": 1.0, "anvil_retrieval_limits": 1.0, "anvil_renderer_result_contract": 1.0}} | "C median >= B median for each maintained task" |
| serialized_tool_output_bytes | False | {"sums_of_task_medians": {"B": 71008, "C": 140186}, "ratio": 1.9742282559711581} | 1.0 |
| input_tokens | True | {"sums_of_task_medians": {"B": 238066, "C": 180095}, "ratio": 0.7564918972049768} | 1.0 |
| maintained_p95_latency | True | {"seconds": {"B": 50.2912378750043, "C": 45.14465729199583}, "ratio": 0.8976644679973881} | 1.25 |

### C/A

| Gate | Passed | Actual | Required |
|---|---|---|---|
| complete_measurements | True | {"A": 51, "C": 51} | {"A": 51, "C": 51} |
| fixture_full_passes | True | 42 | 42 |
| authored_false_relationships | True | 0 | 0 |
| repaired_endpoints | True | true | true |
| maintained_full_passes | False | 7 | 8 |
| per_task_success | False | ["anvil_retrieval_limits"] | [] |
| eligible_paired_tasks | True | 2 | 2 |
| positive_comparator | True | 15 | "> 0" |
| observed_call_reduction | True | 0.6 | 0.2 |
| tasks_with_fewer_calls | True | ["anvil_temporal_arguments", "anvil_renderer_result_contract"] | 2 |
| per_task_source_recall | True | {"A": {"anvil_temporal_arguments": 1.0, "anvil_retrieval_limits": 1.0, "anvil_renderer_result_contract": 0.8}, "C": {"anvil_temporal_arguments": 1.0, "anvil_retrieval_limits": 1.0, "anvil_renderer_result_contract": 1.0}} | "C median >= A median for each maintained task" |
| serialized_tool_output_bytes | False | {"sums_of_task_medians": {"A": 72049, "C": 140186}, "ratio": 1.945703618370831} | 1.0 |
| input_tokens | True | {"sums_of_task_medians": {"A": 266834, "C": 180095}, "ratio": 0.6749327297121056} | 1.0 |
| maintained_p95_latency | True | {"seconds": {"A": 60.41948749999574, "C": 45.14465729199583}, "ratio": 0.7471870278939227} | 1.25 |

## Raw failures

- `imported_heritage-r2-B`: {"attempt_id": "imported_heritage-r2-B-175a9cf7-2888-4288-8d54-e1d08daa4371/attempt/6", "category": "tool_error", "message": "Selected-from search lineage is invalid"}
- `imported_heritage-r2-B`: {"attempt_id": "imported_heritage-r2-B-175a9cf7-2888-4288-8d54-e1d08daa4371/attempt/6", "category": "invalid_trace", "message": "selection must reference an earlier search in this run"}
- `imported_heritage-r2-B`: {"attempt_id": "imported_heritage-r2-B-175a9cf7-2888-4288-8d54-e1d08daa4371/attempt/7", "category": "tool_error", "message": "Selected-from search lineage is invalid"}
- `imported_heritage-r2-B`: {"attempt_id": "imported_heritage-r2-B-175a9cf7-2888-4288-8d54-e1d08daa4371/attempt/7", "category": "invalid_trace", "message": "selection must reference an earlier search in this run"}
- `imported_heritage-r2-B`: {"attempt_id": "imported_heritage-r2-B-175a9cf7-2888-4288-8d54-e1d08daa4371/attempt/8", "category": "tool_error", "message": "Selected-from search lineage is invalid"}
- `imported_heritage-r2-B`: {"attempt_id": "imported_heritage-r2-B-175a9cf7-2888-4288-8d54-e1d08daa4371/attempt/8", "category": "invalid_trace", "message": "selection must reference an earlier search in this run"}
- `imported_heritage-r2-B`: {"attempt_id": "imported_heritage-r2-B-175a9cf7-2888-4288-8d54-e1d08daa4371/attempt/9", "category": "tool_error", "message": "Selected-from search lineage is invalid"}
- `imported_heritage-r2-B`: {"attempt_id": "imported_heritage-r2-B-175a9cf7-2888-4288-8d54-e1d08daa4371/attempt/9", "category": "invalid_trace", "message": "selection must reference an earlier search in this run"}
- `default_identifier-r1-B`: {"attempt_id": "default_identifier-r1-B-16a58fd6-97d3-4dd8-8164-c498a3325ab9/attempt/2", "category": "tool_error", "message": "IDs must belong to this snapshot index"}
- `anvil_temporal_arguments-r2-B`: {"attempt_id": "anvil_temporal_arguments-r2-B-6ad3d0f1-516b-4130-9f23-eb5cb87a142b/attempt/3", "event_id": "anvil_temporal_arguments-r2-B-6ad3d0f1-516b-4130-9f23-eb5cb87a142b:3", "category": "budget_exhausted", "limits": ["max_evidence_spans"]}
- `anvil_retrieval_limits-r1-B`: {"attempt_id": "anvil_retrieval_limits-r1-B-f071a784-cf7a-4443-aa9e-3ca0b280209f/attempt/1", "event_id": "anvil_retrieval_limits-r1-B-f071a784-cf7a-4443-aa9e-3ca0b280209f:1", "category": "budget_exhausted", "limits": ["max_evidence_spans", "max_evidence_bytes", "max_estimated_evidence_tokens", "max_serialized_output_bytes_per_operation", "max_serialized_output_bytes_per_run"]}
- `anvil_retrieval_limits-r1-C`: {"attempt_id": "anvil_retrieval_limits-r1-C-7cd3474b-1822-42fa-8e85-ced13ba5cff0/attempt/1", "event_id": "anvil_retrieval_limits-r1-C-7cd3474b-1822-42fa-8e85-ced13ba5cff0:1", "category": "budget_exhausted", "limits": ["max_evidence_spans", "max_evidence_bytes", "max_estimated_evidence_tokens", "max_serialized_output_bytes_per_operation", "max_serialized_output_bytes_per_run"]}
- `anvil_retrieval_limits-r2-B`: {"attempt_id": "anvil_retrieval_limits-r2-B-6573c0de-fe5f-47d0-9a36-7205608654f0/attempt/1", "event_id": "anvil_retrieval_limits-r2-B-6573c0de-fe5f-47d0-9a36-7205608654f0:1", "category": "budget_exhausted", "limits": ["max_evidence_spans"]}
- `anvil_retrieval_limits-r2-C`: {"attempt_id": "anvil_retrieval_limits-r2-C-49da489c-626d-4291-b8b2-da7ac2f9c938/attempt/1", "event_id": "anvil_retrieval_limits-r2-C-49da489c-626d-4291-b8b2-da7ac2f9c938:1", "category": "budget_exhausted", "limits": ["max_evidence_spans", "max_evidence_bytes", "max_estimated_evidence_tokens", "max_serialized_output_bytes_per_operation", "max_serialized_output_bytes_per_run"]}
- `anvil_retrieval_limits-r2-C`: {"attempt_id": "anvil_retrieval_limits-r2-C-49da489c-626d-4291-b8b2-da7ac2f9c938/attempt/2", "event_id": "anvil_retrieval_limits-r2-C-49da489c-626d-4291-b8b2-da7ac2f9c938:2", "category": "budget_exhausted", "limits": ["max_evidence_spans"]}
- `anvil_retrieval_limits-r3-B`: {"attempt_id": "anvil_retrieval_limits-r3-B-d9d977d8-f55e-433a-8d6c-001fe690524a/attempt/1", "event_id": "anvil_retrieval_limits-r3-B-d9d977d8-f55e-433a-8d6c-001fe690524a:1", "category": "budget_exhausted", "limits": ["max_evidence_spans"]}
- `anvil_renderer_result_contract-r3-B`: {"attempt_id": "anvil_renderer_result_contract-r3-B-85ac7cf4-d0cc-443e-97f0-dba3f9af507f/attempt/2", "category": "tool_error", "message": "Selected-from search lineage is invalid"}
- `anvil_renderer_result_contract-r3-B`: {"attempt_id": "anvil_renderer_result_contract-r3-B-85ac7cf4-d0cc-443e-97f0-dba3f9af507f/attempt/2", "category": "invalid_trace", "message": "selection must reference an earlier search in this run"}

These three source-comprehension tasks from one maintained repository do not establish broad coding or code-edit gains.

## All planned attempts

| Attempt | Arm | Answer | Full pass | Complete | Calls | Output bytes | Source bytes | Source recall | Gross input | Cached input | Output tokens | End-to-end s | Index s | Outcome | Raw failures |
|---|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| imported_interface-r1-A | A | True | True | True | 4 | 3148 | 407 | 1.0 | 27570 | 13568 | 334 | 15.507938542010379 | 0.043193249992327765 | completed | [] |
| imported_interface-r1-B | B | True | True | True | 3 | 3329 | 510 | 1.0 | 21505 | 13568 | 280 | 14.286055874996237 | 0.04334595899854321 | completed | [] |
| imported_interface-r1-C | C | True | True | True | 3 | 4537 | 564 | 1.0 | 22997 | 8704 | 412 | 14.175559958006488 | 0.04491658299230039 | completed | [] |
| imported_interface-r2-A | A | True | True | True | 4 | 3148 | 407 | 1.0 | 27929 | 13568 | 422 | 16.40210516699881 | 0.046920584005420096 | completed | [] |
| imported_interface-r2-B | B | True | True | True | 3 | 4410 | 422 | 1.0 | 22364 | 13568 | 317 | 15.080601792011294 | 0.051966667000669986 | completed | [] |
| imported_interface-r2-C | C | True | True | True | 2 | 3809 | 485 | 1.0 | 16381 | 8704 | 382 | 13.347826833007275 | 0.04197891699732281 | completed | [] |
| imported_interface-r3-A | A | True | True | True | 4 | 3148 | 407 | 1.0 | 27709 | 8704 | 397 | 18.296756166993873 | 0.05201400000078138 | completed | [] |
| imported_interface-r3-B | B | True | True | True | 2 | 3226 | 422 | 1.0 | 16165 | 8704 | 244 | 12.573965916992165 | 0.04866112499439623 | completed | [] |
| imported_interface-r3-C | C | True | True | True | 2 | 3809 | 485 | 1.0 | 16321 | 8704 | 264 | 13.392138124996563 | 0.04124679199594539 | completed | [] |
| local_interface-r1-A | A | True | True | True | 4 | 2970 | 314 | 1.0 | 27516 | 13568 | 349 | 14.784745917000691 | 0.0439705829921877 | completed | [] |
| local_interface-r1-B | B | True | True | True | 4 | 3793 | 411 | 1.0 | 28003 | 13568 | 387 | 16.803150916995946 | 0.04239229099766817 | completed | [] |
| local_interface-r1-C | C | True | True | True | 2 | 3356 | 368 | 1.0 | 16229 | 8704 | 236 | 14.429472666000947 | 0.03762287499557715 | completed | [] |
| local_interface-r2-A | A | True | True | True | 2 | 1413 | 233 | 0.5 | 15594 | 11520 | 345 | 12.440347582989489 | 0.04252079100115225 | completed | [] |
| local_interface-r2-B | B | True | True | True | 4 | 3121 | 406 | 1.0 | 27588 | 13568 | 336 | 17.669198167001014 | 0.038805624993983656 | completed | [] |
| local_interface-r2-C | C | True | True | True | 2 | 3356 | 368 | 1.0 | 16301 | 8704 | 312 | 13.020020791998832 | 0.03743508399929851 | completed | [] |
| local_interface-r3-A | A | True | True | True | 4 | 3207 | 457 | 1.0 | 27771 | 13568 | 415 | 18.71679533299175 | 0.04369212499295827 | completed | [] |
| local_interface-r3-B | B | True | True | True | 4 | 3788 | 406 | 1.0 | 27914 | 22272 | 338 | 16.261032415990485 | 0.04382845899090171 | completed | [] |
| local_interface-r3-C | C | True | True | True | 2 | 3528 | 283 | 1.0 | 16213 | 8704 | 228 | 11.414752874989063 | 0.04252566699869931 | completed | [] |
| local_alias_chain-r1-A | A | True | True | True | 8 | 6073 | 474 | 1.0 | 55462 | 37120 | 627 | 32.55524762500136 | 0.053454374996363185 | completed | [] |
| local_alias_chain-r1-B | B | True | True | True | 4 | 3709 | 489 | 1.0 | 27936 | 13568 | 544 | 20.86605550000968 | 0.05178866699861828 | completed | [] |
| local_alias_chain-r1-C | C | True | True | True | 2 | 6049 | 521 | 1.0 | 17051 | 7680 | 357 | 14.46180508400721 | 0.03795008300221525 | completed | [] |
| local_alias_chain-r2-A | A | True | True | True | 6 | 5246 | 766 | 1.0 | 41837 | 30208 | 579 | 32.63716991600813 | 0.03998058299475815 | completed | [] |
| local_alias_chain-r2-B | B | True | True | True | 6 | 6183 | 749 | 1.0 | 42636 | 20480 | 697 | 27.95150791699416 | 0.04168045800179243 | completed | [] |
| local_alias_chain-r2-C | C | True | True | True | 2 | 6049 | 521 | 1.0 | 17082 | 11520 | 360 | 14.99867900001118 | 0.0385766249964945 | completed | [] |
| local_alias_chain-r3-A | A | True | True | True | 3 | 1822 | 429 | 1.0 | 21328 | 16384 | 400 | 15.819410875003086 | 0.041584209000575356 | completed | [] |
| local_alias_chain-r3-B | B | True | True | True | 5 | 5903 | 902 | 1.0 | 35296 | 19456 | 545 | 25.71011037500284 | 0.04023129200504627 | completed | [] |
| local_alias_chain-r3-C | C | True | True | True | 2 | 6069 | 538 | 1.0 | 17099 | 8704 | 374 | 13.898677958000917 | 0.0371029170055408 | completed | [] |
| imported_alias_chain-r1-A | A | True | True | True | 6 | 5180 | 712 | 1.0 | 41620 | 26112 | 895 | 47.815785375001724 | 0.045675542001845315 | completed | [] |
| imported_alias_chain-r1-B | B | True | True | True | 5 | 6245 | 756 | 1.0 | 36526 | 26368 | 562 | 21.473577374999877 | 0.042881708999630064 | completed | [] |
| imported_alias_chain-r1-C | C | True | True | True | 2 | 6324 | 548 | 1.0 | 17321 | 4864 | 391 | 15.967662374998326 | 0.050948750009411015 | completed | [] |
| imported_alias_chain-r2-A | A | True | True | True | 8 | 6474 | 707 | 1.0 | 56156 | 37120 | 708 | 31.12410370798898 | 0.04523879199405201 | completed | [] |
| imported_alias_chain-r2-B | B | True | True | True | 6 | 7089 | 451 | 1.0 | 43984 | 36096 | 830 | 32.49974995800585 | 0.06441170799371321 | completed | [] |
| imported_alias_chain-r2-C | C | True | True | True | 2 | 6324 | 548 | 1.0 | 17280 | 8704 | 347 | 13.981917041994166 | 0.051840500003891066 | completed | [] |
| imported_alias_chain-r3-A | A | True | True | True | 7 | 6094 | 660 | 1.0 | 48791 | 38912 | 800 | 28.21371066699794 | 0.0411456250003539 | completed | [] |
| imported_alias_chain-r3-B | B | True | True | True | 6 | 7115 | 665 | 1.0 | 44352 | 27392 | 564 | 23.600341833007406 | 0.04404804100340698 | completed | [] |
| imported_alias_chain-r3-C | C | True | True | True | 3 | 7577 | 548 | 1.0 | 23496 | 13568 | 400 | 17.75875391700538 | 0.04352645800099708 | completed | [] |
| named_type_reexport_chain-r1-A | A | True | True | True | 4 | 4277 | 291 | 0.5 | 28258 | 23296 | 427 | 15.512656374994549 | 0.05097570799989626 | completed | [] |
| named_type_reexport_chain-r1-B | B | True | True | True | 2 | 3649 | 496 | 1.0 | 16311 | 12544 | 395 | 16.983882374988752 | 0.04558583299512975 | completed | [] |
| named_type_reexport_chain-r1-C | C | True | True | True | 3 | 4967 | 638 | 1.0 | 23331 | 17408 | 451 | 15.887395291996654 | 0.043466958988574333 | completed | [] |
| named_type_reexport_chain-r2-A | A | True | True | True | 9 | 7406 | 1006 | 1.0 | 63121 | 50688 | 712 | 31.252428958003293 | 0.0495752909919247 | completed | [] |
| named_type_reexport_chain-r2-B | B | True | True | True | 2 | 3649 | 496 | 1.0 | 16407 | 12544 | 414 | 14.409303749998799 | 0.05736391700338572 | completed | [] |
| named_type_reexport_chain-r2-C | C | True | True | True | 3 | 5168 | 638 | 1.0 | 23748 | 10752 | 773 | 22.458247917005792 | 0.04765475000021979 | completed | [] |
| named_type_reexport_chain-r3-A | A | True | True | True | 4 | 2456 | 511 | 1.0 | 27453 | 18432 | 473 | 18.09537716700288 | 0.04547462500340771 | completed | [] |
| named_type_reexport_chain-r3-B | B | True | True | True | 3 | 4216 | 603 | 1.0 | 22149 | 16384 | 527 | 20.783017499998095 | 0.042085167006007396 | completed | [] |
| named_type_reexport_chain-r3-C | C | True | True | True | 2 | 4334 | 578 | 1.0 | 16518 | 7680 | 337 | 12.184925584006123 | 0.042372249998152256 | completed | [] |
| same_name_wrong_file-r1-A | A | True | True | True | 4 | 3590 | 448 | 1.0 | 27950 | 23296 | 389 | 18.644337207995704 | 0.04450287501094863 | completed | [] |
| same_name_wrong_file-r1-B | B | True | True | True | 2 | 3230 | 422 | 1.0 | 16192 | 12544 | 272 | 11.004204250013572 | 0.04505741699540522 | completed | [] |
| same_name_wrong_file-r1-C | C | True | True | True | 2 | 3813 | 485 | 1.0 | 16368 | 3840 | 332 | 13.773507499994594 | 0.043300208999426104 | completed | [] |
| same_name_wrong_file-r2-A | A | True | True | True | 4 | 3590 | 448 | 1.0 | 27972 | 23296 | 373 | 15.14191729099548 | 0.04992404198856093 | completed | [] |
| same_name_wrong_file-r2-B | B | True | True | True | 2 | 3230 | 422 | 1.0 | 16185 | 7680 | 340 | 13.947864166009822 | 0.04938154200499412 | completed | [] |
| same_name_wrong_file-r2-C | C | True | True | True | 2 | 3813 | 485 | 1.0 | 16423 | 12544 | 291 | 19.122646292002173 | 0.0460202499962179 | completed | [] |
| same_name_wrong_file-r3-A | A | True | True | True | 4 | 2291 | 352 | 1.0 | 27164 | 22272 | 345 | 14.60344345899648 | 0.04559424999752082 | completed | [] |
| same_name_wrong_file-r3-B | B | True | True | True | 2 | 3230 | 422 | 1.0 | 16243 | 12544 | 340 | 13.378636541005108 | 0.04228224999678787 | completed | [] |
| same_name_wrong_file-r3-C | C | True | True | True | 3 | 4543 | 564 | 1.0 | 22934 | 16384 | 330 | 14.193517791994964 | 0.043304874998284504 | completed | [] |
| local_heritage-r1-A | A | True | True | True | 3 | 3684 | 853 | 1.0 | 22123 | 13568 | 403 | 15.429654791994835 | 0.039409792007063515 | completed | [] |
| local_heritage-r1-B | B | True | True | True | 5 | 6585 | 754 | 1.0 | 35564 | 27136 | 361 | 17.688013999999384 | 0.04045220800617244 | completed | [] |
| local_heritage-r1-C | C | True | True | True | 2 | 7678 | 1612 | 1.0 | 17665 | 12544 | 328 | 13.351609582998208 | 0.03675662500609178 | completed | [] |
| local_heritage-r2-A | A | True | True | True | 8 | 7899 | 1439 | 1.0 | 58564 | 39936 | 753 | 33.990520125007606 | 0.04234787500172388 | completed | [] |
| local_heritage-r2-B | B | True | True | True | 7 | 7731 | 838 | 1.0 | 49897 | 38912 | 648 | 26.860268333999556 | 0.04070283300825395 | completed | [] |
| local_heritage-r2-C | C | True | True | True | 2 | 7910 | 1223 | 1.0 | 18018 | 7680 | 459 | 14.69961029200931 | 0.037063625000882894 | completed | [] |
| local_heritage-r3-A | A | True | True | True | 3 | 2879 | 887 | 1.0 | 22440 | 12544 | 610 | 20.993293209001422 | 0.05279766699823085 | completed | [] |
| local_heritage-r3-B | B | True | True | True | 8 | 8605 | 1421 | 1.0 | 58507 | 45824 | 690 | 27.02996533300029 | 0.04178591699746903 | completed | [] |
| local_heritage-r3-C | C | True | True | True | 4 | 9362 | 1494 | 1.0 | 31263 | 17408 | 439 | 16.696093499995186 | 0.04466350001166575 | completed | [] |
| imported_heritage-r1-A | A | True | True | True | 2 | 3515 | 1250 | 1.0 | 16270 | 12544 | 364 | 15.562792832992272 | 0.04107895799097605 | completed | [] |
| imported_heritage-r1-B | B | True | True | True | 6 | 8167 | 868 | 1.0 | 44031 | 33024 | 528 | 20.622881250004866 | 0.046573999992688186 | completed | [] |
| imported_heritage-r1-C | C | True | True | True | 4 | 10291 | 1576 | 1.0 | 31741 | 13568 | 431 | 15.711367458992754 | 0.04875762500159908 | completed | [] |
| imported_heritage-r2-A | A | True | True | True | 4 | 6853 | 1454 | 1.0 | 30331 | 23296 | 438 | 23.594653875014046 | 0.05175270799372811 | completed | [] |
| imported_heritage-r2-B | B | True | True | True | 10 | 11861 | 1690 | 1.0 | 78326 | 62720 | 1030 | 36.384998000008636 | 0.04493062499386724 | completed | [{"attempt_id": "imported_heritage-r2-B-175a9cf7-2888-4288-8d54-e1d08daa4371/attempt/6", "category": "tool_error", "message": "Selected-from search lineage is invalid"}, {"attempt_id": "imported_heritage-r2-B-175a9cf7-2888-4288-8d54-e1d08daa4371/attempt/6", "category": "invalid_trace", "message": "selection must reference an earlier search in this run"}, {"attempt_id": "imported_heritage-r2-B-175a9cf7-2888-4288-8d54-e1d08daa4371/attempt/7", "category": "tool_error", "message": "Selected-from search lineage is invalid"}, {"attempt_id": "imported_heritage-r2-B-175a9cf7-2888-4288-8d54-e1d08daa4371/attempt/7", "category": "invalid_trace", "message": "selection must reference an earlier search in this run"}, {"attempt_id": "imported_heritage-r2-B-175a9cf7-2888-4288-8d54-e1d08daa4371/attempt/8", "category": "tool_error", "message": "Selected-from search lineage is invalid"}, {"attempt_id": "imported_heritage-r2-B-175a9cf7-2888-4288-8d54-e1d08daa4371/attempt/8", "category": "invalid_trace", "message": "selection must reference an earlier search in this run"}, {"attempt_id": "imported_heritage-r2-B-175a9cf7-2888-4288-8d54-e1d08daa4371/attempt/9", "category": "tool_error", "message": "Selected-from search lineage is invalid"}, {"attempt_id": "imported_heritage-r2-B-175a9cf7-2888-4288-8d54-e1d08daa4371/attempt/9", "category": "invalid_trace", "message": "selection must reference an earlier search in this run"}] |
| imported_heritage-r2-C | C | True | True | True | 4 | 9700 | 1133 | 1.0 | 31531 | 18432 | 387 | 15.698554582995712 | 0.03825974999926984 | completed | [] |
| imported_heritage-r3-A | A | True | True | True | 6 | 4853 | 687 | 0.6 | 41342 | 27136 | 631 | 23.2225655830116 | 0.04219162500521634 | completed | [] |
| imported_heritage-r3-B | B | True | True | True | 6 | 8924 | 1049 | 1.0 | 45990 | 35072 | 529 | 21.375957875003223 | 0.04672137500892859 | completed | [] |
| imported_heritage-r3-C | C | True | True | True | 4 | 2724 | 412 | 1.0 | 27567 | 22272 | 379 | 16.416238207995775 | 0.041915124995284714 | completed | [] |
| ambiguous_star_exports-r1-A | A | True | True | True | 11 | 9506 | 539 | 1.0 | 79475 | 58624 | 678 | 27.821927875003894 | 0.04781808299594559 | completed | [] |
| ambiguous_star_exports-r1-B | B | True | True | True | 12 | 12602 | 817 | 1.0 | 98265 | 82688 | 920 | 39.72853070800193 | 0.04694616699998733 | completed | [] |
| ambiguous_star_exports-r1-C | C | True | True | True | 11 | 11028 | 561 | 1.0 | 81566 | 62464 | 929 | 34.296021667003515 | 0.044681708997813985 | completed | [] |
| ambiguous_star_exports-r2-A | A | True | True | True | 9 | 9146 | 561 | 1.0 | 65117 | 47872 | 663 | 29.14426333300071 | 0.048698417012928985 | completed | [] |
| ambiguous_star_exports-r2-B | B | True | True | True | 7 | 7654 | 1023 | 1.0 | 49152 | 38912 | 573 | 26.56817758300167 | 0.04155545799585525 | completed | [] |
| ambiguous_star_exports-r2-C | C | True | True | True | 5 | 4461 | 598 | 1.0 | 35231 | 27136 | 384 | 18.35441670801083 | 0.042047584007377736 | completed | [] |
| ambiguous_star_exports-r3-A | A | True | True | True | 6 | 2614 | 770 | 1.0 | 38733 | 30976 | 307 | 17.40106120800192 | 0.050482582999393344 | completed | [] |
| ambiguous_star_exports-r3-B | B | True | True | True | 11 | 8272 | 446 | 1.0 | 79531 | 67584 | 743 | 33.6415256249893 | 0.044814917011535726 | completed | [] |
| ambiguous_star_exports-r3-C | C | True | True | True | 11 | 11476 | 598 | 1.0 | 81943 | 66560 | 799 | 39.83253087499179 | 0.043181334011023864 | completed | [] |
| generic_shadow-r1-A | A | True | True | True | 4 | 2602 | 386 | 1.0 | 27701 | 21248 | 500 | 20.235581041997648 | 0.038958958990406245 | completed | [] |
| generic_shadow-r1-B | B | True | True | True | 4 | 3691 | 310 | 1.0 | 28122 | 13568 | 475 | 19.707230665997486 | 0.04095683300693054 | completed | [] |
| generic_shadow-r1-C | C | True | True | True | 4 | 3752 | 386 | 1.0 | 28214 | 23296 | 518 | 20.342732334000175 | 0.03821287500613835 | completed | [] |
| generic_shadow-r2-A | A | True | True | True | 3 | 1167 | 316 | 1.0 | 20848 | 17408 | 445 | 17.639873292006087 | 0.04058779199840501 | completed | [] |
| generic_shadow-r2-B | B | True | True | True | 5 | 3081 | 451 | 1.0 | 33082 | 27136 | 624 | 24.873696499998914 | 0.0452462499961257 | completed | [] |
| generic_shadow-r2-C | C | True | True | True | 5 | 4679 | 692 | 1.0 | 34613 | 23296 | 478 | 19.707720624996 | 0.035545374994399026 | completed | [] |
| generic_shadow-r3-A | A | True | True | True | 4 | 2563 | 386 | 1.0 | 27422 | 22272 | 396 | 16.467539375007618 | 0.03945683399797417 | completed | [] |
| generic_shadow-r3-B | B | True | True | True | 4 | 3772 | 386 | 1.0 | 28151 | 14592 | 626 | 19.68227345800551 | 0.03967995900893584 | completed | [] |
| generic_shadow-r3-C | C | True | True | True | 5 | 2734 | 440 | 1.0 | 33779 | 26112 | 642 | 21.85843449999811 | 0.036278708997997455 | completed | [] |
| exported_arrow-r1-A | A | True | True | True | 2 | 1528 | 292 | 0.75 | 15733 | 11520 | 275 | 14.306364457996096 | 0.04358354200667236 | completed | [] |
| exported_arrow-r1-B | B | True | True | True | 4 | 4072 | 339 | 0.75 | 28624 | 22272 | 411 | 15.337412707987824 | 0.04894712500390597 | completed | [] |
| exported_arrow-r1-C | C | True | True | True | 4 | 4942 | 308 | 0.75 | 28956 | 23296 | 420 | 15.804096332998597 | 0.03895604200079106 | completed | [] |
| exported_arrow-r2-A | A | True | True | True | 5 | 3544 | 427 | 0.75 | 34451 | 23296 | 546 | 21.366897416999564 | 0.04368020800757222 | completed | [] |
| exported_arrow-r2-B | B | True | True | True | 4 | 4414 | 292 | 0.75 | 28681 | 21248 | 343 | 14.865464624992455 | 0.042242707990226336 | completed | [] |
| exported_arrow-r2-C | C | True | True | True | 4 | 4072 | 339 | 0.75 | 28666 | 21248 | 422 | 19.32976295800472 | 0.039925000004586764 | completed | [] |
| exported_arrow-r3-A | A | True | True | True | 3 | 1074 | 232 | 1.0 | 20977 | 16384 | 300 | 16.228094375008368 | 0.06634395799483173 | completed | [] |
| exported_arrow-r3-B | B | True | True | True | 5 | 5829 | 305 | 0.5 | 36167 | 29184 | 541 | 21.507433208986185 | 0.05355562501063105 | completed | [] |
| exported_arrow-r3-C | C | True | True | True | 4 | 4072 | 339 | 0.75 | 28597 | 21248 | 425 | 17.711886459001107 | 0.044478292009443976 | completed | [] |
| default_identifier-r1-A | A | True | True | True | 5 | 5387 | 399 | 1.0 | 35737 | 29184 | 434 | 17.014781000005314 | 0.04608775000087917 | completed | [] |
| default_identifier-r1-B | B | True | True | True | 6 | 4463 | 483 | 1.0 | 40107 | 33024 | 460 | 19.1351510000095 | 0.04974612499063369 | completed | [{"attempt_id": "default_identifier-r1-B-16a58fd6-97d3-4dd8-8164-c498a3325ab9/attempt/2", "category": "tool_error", "message": "IDs must belong to this snapshot index"}] |
| default_identifier-r1-C | C | True | True | True | 3 | 3793 | 352 | 1.0 | 22537 | 16384 | 486 | 16.7261956250004 | 0.04463074999512173 | completed | [] |
| default_identifier-r2-A | A | True | True | True | 3 | 1255 | 318 | 1.0 | 21110 | 17408 | 329 | 13.354216167004779 | 0.045762082998408005 | completed | [] |
| default_identifier-r2-B | B | True | True | True | 4 | 4148 | 399 | 1.0 | 28551 | 21248 | 379 | 17.272186290996615 | 0.042689124995376915 | completed | [] |
| default_identifier-r2-C | C | True | True | True | 3 | 1100 | 245 | 1.0 | 20999 | 16384 | 358 | 13.497343374998309 | 0.04444425000110641 | completed | [] |
| default_identifier-r3-A | A | True | True | True | 4 | 4417 | 353 | 1.0 | 28748 | 23296 | 410 | 17.146645208005793 | 0.045105040990165435 | completed | [] |
| default_identifier-r3-B | B | True | True | True | 4 | 4148 | 399 | 1.0 | 28449 | 23296 | 341 | 14.225004541993258 | 0.053127167004277 | completed | [] |
| default_identifier-r3-C | C | True | True | True | 4 | 4148 | 399 | 1.0 | 28568 | 17408 | 382 | 14.42225629099994 | 0.04050262499367818 | completed | [] |
| named_function_control-r1-A | A | True | True | True | 5 | 4416 | 337 | 0.75 | 34966 | 25088 | 525 | 21.08974200001103 | 0.04757633300323505 | completed | [] |
| named_function_control-r1-B | B | True | True | True | 5 | 3125 | 489 | 1.0 | 33877 | 28160 | 475 | 18.267610249997233 | 0.051895458993385546 | completed | [] |
| named_function_control-r1-C | C | True | True | True | 5 | 4912 | 303 | 0.5 | 35197 | 28160 | 531 | 24.950115249986993 | 0.045142458999180235 | completed | [] |
| named_function_control-r2-A | A | True | True | True | 4 | 3900 | 202 | 0.5 | 28422 | 20224 | 349 | 15.920278749996214 | 0.045573916999273933 | completed | [] |
| named_function_control-r2-B | B | True | True | True | 4 | 4672 | 236 | 0.75 | 29114 | 23296 | 398 | 16.45195283299836 | 0.050478999997721985 | completed | [] |
| named_function_control-r2-C | C | True | True | True | 5 | 5778 | 337 | 0.75 | 35966 | 18432 | 467 | 21.65870004199678 | 0.03974066599039361 | completed | [] |
| named_function_control-r3-A | A | True | True | True | 2 | 1588 | 337 | 0.75 | 15762 | 12544 | 295 | 11.787969334007357 | 0.044445749997976236 | completed | [] |
| named_function_control-r3-B | B | True | True | True | 4 | 4147 | 384 | 0.75 | 28564 | 23296 | 381 | 16.117583667000872 | 0.062481874992954545 | completed | [] |
| named_function_control-r3-C | C | True | True | True | 5 | 3834 | 452 | 1.0 | 34072 | 27136 | 477 | 20.833238708000863 | 0.04100470799312461 | completed | [] |
| inline_default_control-r1-A | A | True | True | True | 5 | 3940 | 617 | 1.0 | 34298 | 23296 | 449 | 22.11846399999922 | 0.04941658300231211 | completed | [] |
| inline_default_control-r1-B | B | True | True | True | 4 | 4305 | 279 | 0.75 | 28630 | 15616 | 347 | 15.620014000000083 | 0.04560545799904503 | completed | [] |
| inline_default_control-r1-C | C | True | True | True | 4 | 4145 | 380 | 0.75 | 28713 | 22272 | 435 | 19.472419166006148 | 0.04054962498776149 | completed | [] |
| inline_default_control-r2-A | A | True | True | True | 4 | 3507 | 380 | 0.75 | 28220 | 16384 | 349 | 17.896058792000986 | 0.04937795799924061 | completed | [] |
| inline_default_control-r2-B | B | True | True | True | 4 | 4145 | 380 | 0.75 | 28532 | 22272 | 376 | 19.802151333002257 | 0.04446512499998789 | completed | [] |
| inline_default_control-r2-C | C | True | True | True | 5 | 5338 | 286 | 0.75 | 35799 | 28160 | 554 | 20.61374524999701 | 0.04512966600304935 | completed | [] |
| inline_default_control-r3-A | A | True | True | True | 5 | 3465 | 333 | 0.75 | 34146 | 19456 | 384 | 17.634647041995777 | 0.04593845800263807 | completed | [] |
| inline_default_control-r3-B | B | True | True | True | 5 | 6773 | 435 | 0.75 | 36824 | 30208 | 474 | 19.938894165999955 | 0.05777854200277943 | completed | [] |
| inline_default_control-r3-C | C | True | True | True | 5 | 3952 | 486 | 1.0 | 34422 | 25088 | 470 | 20.490109791993746 | 0.04591112499474548 | completed | [] |
| anvil_temporal_arguments-r1-A | A | True | True | True | 7 | 16958 | 2773 | 1.0 | 60092 | 48128 | 756 | 31.618932875004248 | 3.919959790990106 | completed | [] |
| anvil_temporal_arguments-r1-B | B | True | True | True | 6 | 15991 | 3124 | 1.0 | 51635 | 39168 | 1038 | 36.72742749999452 | 3.889317833003588 | completed | [] |
| anvil_temporal_arguments-r1-C | C | True | True | True | 2 | 11019 | 1570 | 1.0 | 19000 | 12544 | 460 | 19.201784375007264 | 5.166485000008834 | completed | [] |
| anvil_temporal_arguments-r2-A | A | True | True | True | 8 | 18756 | 2777 | 1.0 | 70487 | 49920 | 863 | 35.085928875007085 | 3.882422666007187 | completed | [] |
| anvil_temporal_arguments-r2-B | B | True | False | True | 4 | 6705 | 3318 | 1.0 | 29932 | 20480 | 528 | 21.848490959004266 | 3.9409802919981303 | budget_exhausted | [{"attempt_id": "anvil_temporal_arguments-r2-B-6ad3d0f1-516b-4130-9f23-eb5cb87a142b/attempt/3", "event_id": "anvil_temporal_arguments-r2-B-6ad3d0f1-516b-4130-9f23-eb5cb87a142b:3", "category": "budget_exhausted", "limits": ["max_evidence_spans"]}] |
| anvil_temporal_arguments-r2-C | C | True | True | True | 2 | 11067 | 1609 | 1.0 | 19053 | 11520 | 555 | 20.966470915998798 | 5.095131375011988 | completed | [] |
| anvil_temporal_arguments-r3-A | A | True | True | True | 5 | 15730 | 4195 | 1.0 | 42038 | 32256 | 663 | 26.24868316599168 | 3.9692091250035446 | completed | [] |
| anvil_temporal_arguments-r3-B | B | True | True | True | 9 | 19786 | 2498 | 1.0 | 83504 | 64000 | 1073 | 50.2912378750043 | 4.146854374994291 | completed | [] |
| anvil_temporal_arguments-r3-C | C | True | True | True | 2 | 11847 | 1365 | 1.0 | 19507 | 11520 | 569 | 23.533289749990217 | 5.073865625003236 | completed | [] |
| anvil_retrieval_limits-r1-A | A | True | True | True | 12 | 30366 | 8442 | 1.0 | 125772 | 108288 | 1057 | 47.30634462500166 | 3.927064749994315 | completed | [] |
| anvil_retrieval_limits-r1-B | B | True | False | True | 10 | 27377 | 5853 | 0.875 | 100390 | 72192 | 1015 | 42.52002408300177 | 3.9244530409923755 | budget_exhausted | [{"attempt_id": "anvil_retrieval_limits-r1-B-f071a784-cf7a-4443-aa9e-3ca0b280209f/attempt/1", "event_id": "anvil_retrieval_limits-r1-B-f071a784-cf7a-4443-aa9e-3ca0b280209f:1", "category": "budget_exhausted", "limits": ["max_evidence_spans", "max_evidence_bytes", "max_estimated_evidence_tokens", "max_serialized_output_bytes_per_operation", "max_serialized_output_bytes_per_run"]}] |
| anvil_retrieval_limits-r1-C | C | True | False | True | 7 | 89692 | 15943 | 1.0 | 125876 | 78080 | 939 | 45.14465729199583 | 5.114342874992872 | budget_exhausted | [{"attempt_id": "anvil_retrieval_limits-r1-C-7cd3474b-1822-42fa-8e85-ced13ba5cff0/attempt/1", "event_id": "anvil_retrieval_limits-r1-C-7cd3474b-1822-42fa-8e85-ced13ba5cff0:1", "category": "budget_exhausted", "limits": ["max_evidence_spans", "max_evidence_bytes", "max_estimated_evidence_tokens", "max_serialized_output_bytes_per_operation", "max_serialized_output_bytes_per_run"]}] |
| anvil_retrieval_limits-r2-A | A | True | True | True | 15 | 28521 | 6157 | 1.0 | 156412 | 135168 | 1281 | 60.41948749999574 | 3.940297458000714 | completed | [] |
| anvil_retrieval_limits-r2-B | B | True | False | True | 7 | 26003 | 6207 | 1.0 | 67964 | 43264 | 954 | 43.334276875000796 | 3.8736756250000326 | budget_exhausted | [{"attempt_id": "anvil_retrieval_limits-r2-B-6573c0de-fe5f-47d0-9a36-7205608654f0/attempt/1", "event_id": "anvil_retrieval_limits-r2-B-6573c0de-fe5f-47d0-9a36-7205608654f0:1", "category": "budget_exhausted", "limits": ["max_evidence_spans"]}] |
| anvil_retrieval_limits-r2-C | C | True | False | True | 6 | 61400 | 10872 | 1.0 | 74993 | 51456 | 877 | 38.05984449999232 | 5.153947625003639 | budget_exhausted | [{"attempt_id": "anvil_retrieval_limits-r2-C-49da489c-626d-4291-b8b2-da7ac2f9c938/attempt/1", "event_id": "anvil_retrieval_limits-r2-C-49da489c-626d-4291-b8b2-da7ac2f9c938:1", "category": "budget_exhausted", "limits": ["max_evidence_spans", "max_evidence_bytes", "max_estimated_evidence_tokens", "max_serialized_output_bytes_per_operation", "max_serialized_output_bytes_per_run"]}, {"attempt_id": "anvil_retrieval_limits-r2-C-49da489c-626d-4291-b8b2-da7ac2f9c938/attempt/2", "event_id": "anvil_retrieval_limits-r2-C-49da489c-626d-4291-b8b2-da7ac2f9c938:2", "category": "budget_exhausted", "limits": ["max_evidence_spans"]}] |
| anvil_retrieval_limits-r3-A | A | True | True | True | 12 | 27921 | 10639 | 1.0 | 130449 | 103424 | 1292 | 50.326326499998686 | 3.875883166998392 | completed | [] |
| anvil_retrieval_limits-r3-B | B | True | False | True | 12 | 34734 | 7301 | 1.0 | 127935 | 109312 | 970 | 48.826787790996605 | 3.993343082998763 | budget_exhausted | [{"attempt_id": "anvil_retrieval_limits-r3-B-d9d977d8-f55e-433a-8d6c-001fe690524a/attempt/1", "event_id": "anvil_retrieval_limits-r3-B-d9d977d8-f55e-433a-8d6c-001fe690524a:1", "category": "budget_exhausted", "limits": ["max_evidence_spans"]}] |
| anvil_retrieval_limits-r3-C | C | True | True | True | 6 | 63202 | 11027 | 1.0 | 95876 | 70912 | 833 | 39.74484041699907 | 5.231672791996971 | completed | [] |
| anvil_renderer_result_contract-r1-A | A | True | True | True | 10 | 30278 | 10376 | 1.0 | 103776 | 81408 | 1100 | 42.78364070800308 | 3.9389509160100715 | completed | [] |
| anvil_renderer_result_contract-r1-B | B | True | True | True | 8 | 30078 | 9149 | 1.0 | 86041 | 54528 | 923 | 42.74153212500096 | 3.889382207999006 | completed | [] |
| anvil_renderer_result_contract-r1-C | C | True | True | True | 4 | 65917 | 13754 | 1.0 | 65166 | 31488 | 742 | 31.887828125007218 | 5.080258542002412 | completed | [] |
| anvil_renderer_result_contract-r2-A | A | True | True | True | 8 | 26570 | 11052 | 0.8 | 76271 | 54016 | 985 | 40.81551625000429 | 3.883381791994907 | completed | [] |
| anvil_renderer_result_contract-r2-B | B | True | True | True | 8 | 27334 | 8041 | 1.0 | 84594 | 70400 | 877 | 37.0095190830034 | 3.8414077079942217 | completed | [] |
| anvil_renderer_result_contract-r2-C | C | True | True | True | 4 | 64248 | 13707 | 1.0 | 64172 | 40704 | 737 | 33.86439566699846 | 5.1136949170031585 | completed | [] |
| anvil_renderer_result_contract-r3-A | A | True | True | True | 8 | 23218 | 7359 | 0.8 | 76293 | 60160 | 972 | 37.90017083300336 | 3.8329640409938293 | completed | [] |
| anvil_renderer_result_contract-r3-B | B | True | True | True | 9 | 27640 | 8105 | 1.0 | 91771 | 68352 | 875 | 42.66991379200772 | 3.7958264170010807 | completed | [{"attempt_id": "anvil_renderer_result_contract-r3-B-85ac7cf4-d0cc-443e-97f0-dba3f9af507f/attempt/2", "category": "tool_error", "message": "Selected-from search lineage is invalid"}, {"attempt_id": "anvil_renderer_result_contract-r3-B-85ac7cf4-d0cc-443e-97f0-dba3f9af507f/attempt/2", "category": "invalid_trace", "message": "selection must reference an earlier search in this run"}] |
| anvil_renderer_result_contract-r3-C | C | True | True | True | 4 | 66022 | 13877 | 1.0 | 65377 | 37888 | 885 | 36.82036012499884 | 5.042092042000149 | completed | [] |
