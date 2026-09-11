# Existing-edge type-context comparison

Frozen-gate verdict: **reject**.

Fresh A/B runs use the same v3 tasks, tool schemas, prompt, model and controls. B enables bounded existing type context on get. Historical A-only results are not paired here.

| Arm | Full passes | Complete measurements | Calls | Output bytes | Gross input tokens |
|---|---:|---:|---:|---:|---:|
| A | 51/51 | 51/51 | 285 | 381153 | 2197468 |
| B | 50/51 | 51/51 | 252 | 433384 | 2047856 |

## Maintained tasks

| Task | Arm | Full passes | Calls, median | Source recall, median | Output bytes, median | Gross input, median |
|---|---|---:|---:|---:|---:|---:|
| anvil_temporal_arguments | A | 3/3 | 8 | 1.0 | 17374 | 68876 |
| anvil_temporal_arguments | B | 3/3 | 7 | 1.0 | 20367 | 64317 |
| anvil_retrieval_limits | A | 3/3 | 12 | 1.0 | 27720 | 125482 |
| anvil_retrieval_limits | B | 2/3 | 12 | 1.0 | 33556 | 127233 |
| anvil_renderer_result_contract | A | 3/3 | 8 | 0.8 | 27815 | 77012 |
| anvil_renderer_result_contract | B | 3/3 | 8 | 1.0 | 30065 | 85761 |

## Frozen acceptance gates

| Gate | Passed | Actual | Required |
|---|---|---|---|
| complete_measurements | True | {"A": 51, "B": 51} | {"A": 51, "B": 51} |
| fixture_full_passes | True | 42 | 42 |
| authored_false_relationships | True | 0 | 0 |
| repaired_endpoints | True | true | true |
| maintained_full_passes | True | 8 | 8 |
| per_task_success | False | ["anvil_retrieval_limits"] | [] |
| eligible_paired_tasks | True | 2 | 2 |
| positive_comparator | True | 16 | "> 0" |
| observed_call_reduction | False | 0.0625 | 0.2 |
| tasks_with_fewer_calls | False | ["anvil_temporal_arguments"] | 2 |
| per_task_source_recall | True | {"A": {"anvil_temporal_arguments": 1.0, "anvil_retrieval_limits": 1.0, "anvil_renderer_result_contract": 0.8}, "B": {"anvil_temporal_arguments": 1.0, "anvil_retrieval_limits": 1.0, "anvil_renderer_result_contract": 1.0}} | "B median >= A median for each maintained task" |
| serialized_tool_output_bytes | False | {"sums_of_task_medians": {"A": 72909, "B": 83988}, "ratio": 1.15195654857425} | 1.0 |
| input_tokens | False | {"sums_of_task_medians": {"A": 271370, "B": 277311}, "ratio": 1.0218926189335593} | 1.0 |
| maintained_p95_latency | True | {"seconds": {"A": 57.42589716600196, "B": 60.57576295900799}, "ratio": 1.0548509635626704} | 1.25 |

All errors and failed attempts retain costs. Gross input includes cached input as a subset. Latency uses nearest-rank p95 across all nine maintained attempts per arm. Relationship negatives cover the authored forbidden cases; canonical edge values are preserved when recognizing the added response container.

These three source-comprehension tasks from one maintained repository do not establish broad coding or code-edit gains.

## All attempts

| Attempt | Answer | Full pass | Accounting | Calls | Output bytes | Source recall | Outcome |
|---|---|---|---|---:|---:|---:|---|
| imported_interface-r1-A | True | True | True | 4 | 3148 | 1.0 | completed |
| imported_interface-r1-B | True | True | True | 2 | 3226 | 1.0 | completed |
| imported_interface-r2-A | True | True | True | 3 | 1233 | 1.0 | completed |
| imported_interface-r2-B | True | True | True | 3 | 4321 | 1.0 | completed |
| imported_interface-r3-A | True | True | True | 4 | 3148 | 1.0 | completed |
| imported_interface-r3-B | True | True | True | 3 | 3964 | 1.0 | completed |
| local_interface-r1-A | True | True | True | 4 | 3207 | 1.0 | completed |
| local_interface-r1-B | True | True | True | 4 | 3816 | 1.0 | completed |
| local_interface-r2-A | True | True | True | 4 | 3207 | 1.0 | completed |
| local_interface-r2-B | True | True | True | 3 | 2060 | 1.0 | completed |
| local_interface-r3-A | True | True | True | 4 | 3055 | 1.0 | completed |
| local_interface-r3-B | True | True | True | 3 | 2089 | 1.0 | completed |
| local_alias_chain-r1-A | True | True | True | 6 | 5429 | 1.0 | completed |
| local_alias_chain-r1-B | True | True | True | 5 | 5903 | 1.0 | completed |
| local_alias_chain-r2-A | True | True | True | 5 | 4866 | 1.0 | completed |
| local_alias_chain-r2-B | True | True | True | 9 | 8113 | 1.0 | completed |
| local_alias_chain-r3-A | True | True | True | 4 | 2968 | 1.0 | completed |
| local_alias_chain-r3-B | True | True | True | 3 | 3765 | 1.0 | completed |
| imported_alias_chain-r1-A | True | True | True | 8 | 6444 | 1.0 | completed |
| imported_alias_chain-r1-B | True | True | True | 6 | 6383 | 1.0 | completed |
| imported_alias_chain-r2-A | True | True | True | 6 | 5099 | 1.0 | completed |
| imported_alias_chain-r2-B | True | True | True | 5 | 6915 | 1.0 | completed |
| imported_alias_chain-r3-A | True | True | True | 8 | 6497 | 1.0 | completed |
| imported_alias_chain-r3-B | True | True | True | 5 | 6384 | 1.0 | completed |
| named_type_reexport_chain-r1-A | True | True | True | 5 | 3103 | 1.0 | completed |
| named_type_reexport_chain-r1-B | True | True | True | 2 | 3649 | 1.0 | completed |
| named_type_reexport_chain-r2-A | True | True | True | 6 | 5811 | 0.75 | completed |
| named_type_reexport_chain-r2-B | True | True | True | 4 | 1876 | 1.0 | completed |
| named_type_reexport_chain-r3-A | True | True | True | 4 | 1876 | 1.0 | completed |
| named_type_reexport_chain-r3-B | True | True | True | 3 | 4355 | 1.0 | completed |
| same_name_wrong_file-r1-A | True | True | True | 4 | 3590 | 1.0 | completed |
| same_name_wrong_file-r1-B | True | True | True | 2 | 3230 | 1.0 | completed |
| same_name_wrong_file-r2-A | True | True | True | 4 | 3873 | 1.0 | completed |
| same_name_wrong_file-r2-B | True | True | True | 2 | 3230 | 1.0 | completed |
| same_name_wrong_file-r3-A | True | True | True | 3 | 1239 | 1.0 | completed |
| same_name_wrong_file-r3-B | True | True | True | 2 | 3230 | 1.0 | completed |
| local_heritage-r1-A | True | True | True | 5 | 7209 | 1.0 | completed |
| local_heritage-r1-B | True | True | True | 4 | 4454 | 1.0 | completed |
| local_heritage-r2-A | True | True | True | 2 | 3538 | 1.0 | completed |
| local_heritage-r2-B | True | True | True | 8 | 9268 | 1.0 | completed |
| local_heritage-r3-A | True | True | True | 5 | 4834 | 1.0 | completed |
| local_heritage-r3-B | True | True | True | 6 | 7520 | 1.0 | completed |
| imported_heritage-r1-A | True | True | True | 6 | 5617 | 1.0 | completed |
| imported_heritage-r1-B | True | True | True | 4 | 7676 | 1.0 | completed |
| imported_heritage-r2-A | True | True | True | 7 | 7564 | 1.0 | completed |
| imported_heritage-r2-B | True | True | True | 2 | 5896 | 1.0 | completed |
| imported_heritage-r3-A | True | True | True | 2 | 3515 | 1.0 | completed |
| imported_heritage-r3-B | True | True | True | 4 | 8004 | 1.0 | completed |
| ambiguous_star_exports-r1-A | True | True | True | 9 | 6160 | 1.0 | completed |
| ambiguous_star_exports-r1-B | True | True | True | 5 | 4547 | 1.0 | completed |
| ambiguous_star_exports-r2-A | True | True | True | 11 | 9568 | 1.0 | completed |
| ambiguous_star_exports-r2-B | True | True | True | 5 | 4547 | 1.0 | completed |
| ambiguous_star_exports-r3-A | True | True | True | 7 | 3220 | 1.0 | completed |
| ambiguous_star_exports-r3-B | True | True | True | 9 | 10975 | 0.8 | completed |
| generic_shadow-r1-A | True | True | True | 5 | 2402 | 1.0 | completed |
| generic_shadow-r1-B | True | True | True | 3 | 1167 | 1.0 | completed |
| generic_shadow-r2-A | True | True | True | 6 | 4862 | 1.0 | completed |
| generic_shadow-r2-B | True | True | True | 6 | 3593 | 1.0 | completed |
| generic_shadow-r3-A | True | True | True | 7 | 4959 | 1.0 | completed |
| generic_shadow-r3-B | True | True | True | 4 | 3772 | 1.0 | completed |
| exported_arrow-r1-A | True | True | True | 4 | 3434 | 0.75 | completed |
| exported_arrow-r1-B | True | True | True | 5 | 5829 | 0.5 | completed |
| exported_arrow-r2-A | True | True | True | 4 | 3434 | 0.75 | completed |
| exported_arrow-r2-B | True | True | True | 5 | 4243 | 0.75 | completed |
| exported_arrow-r3-A | True | True | True | 4 | 4373 | 0.75 | completed |
| exported_arrow-r3-B | True | True | True | 3 | 2871 | 0.75 | completed |
| default_identifier-r1-A | True | True | True | 5 | 4759 | 1.0 | completed |
| default_identifier-r1-B | True | True | True | 4 | 4148 | 1.0 | completed |
| default_identifier-r2-A | True | True | True | 5 | 4759 | 1.0 | completed |
| default_identifier-r2-B | True | True | True | 4 | 4148 | 1.0 | completed |
| default_identifier-r3-A | True | True | True | 4 | 3510 | 1.0 | completed |
| default_identifier-r3-B | True | True | True | 4 | 2111 | 1.0 | completed |
| named_function_control-r1-A | True | True | True | 4 | 3670 | 0.75 | completed |
| named_function_control-r1-B | True | True | True | 4 | 4147 | 0.75 | completed |
| named_function_control-r2-A | True | True | True | 3 | 1247 | 1.0 | completed |
| named_function_control-r2-B | True | True | True | 4 | 4147 | 0.75 | completed |
| named_function_control-r3-A | True | True | True | 4 | 3509 | 0.75 | completed |
| named_function_control-r3-B | True | True | True | 5 | 5326 | 0.75 | completed |
| inline_default_control-r1-A | True | True | True | 3 | 2932 | 1.0 | completed |
| inline_default_control-r1-B | True | True | True | 4 | 4145 | 0.75 | completed |
| inline_default_control-r2-A | True | True | True | 7 | 7035 | 1.0 | completed |
| inline_default_control-r2-B | True | True | True | 4 | 4145 | 0.75 | completed |
| inline_default_control-r3-A | True | True | True | 4 | 2120 | 0.75 | completed |
| inline_default_control-r3-B | True | True | True | 4 | 4998 | 0.75 | completed |
| anvil_temporal_arguments-r1-A | True | True | True | 5 | 9978 | 1.0 | completed |
| anvil_temporal_arguments-r1-B | True | True | True | 6 | 14002 | 1.0 | completed |
| anvil_temporal_arguments-r2-A | True | True | True | 8 | 17374 | 1.0 | completed |
| anvil_temporal_arguments-r2-B | True | True | True | 7 | 20367 | 1.0 | completed |
| anvil_temporal_arguments-r3-A | True | True | True | 8 | 17550 | 1.0 | completed |
| anvil_temporal_arguments-r3-B | True | True | True | 9 | 23129 | 1.0 | completed |
| anvil_retrieval_limits-r1-A | True | True | True | 6 | 25979 | 1.0 | completed |
| anvil_retrieval_limits-r1-B | True | True | True | 14 | 34494 | 1.0 | completed |
| anvil_retrieval_limits-r2-A | True | True | True | 12 | 29446 | 1.0 | completed |
| anvil_retrieval_limits-r2-B | True | True | True | 6 | 24411 | 1.0 | completed |
| anvil_retrieval_limits-r3-A | True | True | True | 13 | 27720 | 1.0 | completed |
| anvil_retrieval_limits-r3-B | True | False | True | 12 | 33556 | 1.0 | budget_exhausted |
| anvil_renderer_result_contract-r1-A | True | True | True | 8 | 28189 | 0.8 | completed |
| anvil_renderer_result_contract-r1-B | True | True | True | 8 | 30065 | 1.0 | completed |
| anvil_renderer_result_contract-r2-A | True | True | True | 8 | 27815 | 0.8 | completed |
| anvil_renderer_result_contract-r2-B | True | True | True | 8 | 32660 | 1.0 | completed |
| anvil_renderer_result_contract-r3-A | True | True | True | 8 | 21079 | 0.8 | completed |
| anvil_renderer_result_contract-r3-B | True | True | True | 6 | 22514 | 0.8 | completed |
