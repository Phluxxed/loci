# Actual loci_explore workflow comparison

Qualification verdict: **reject**. Frozen numerical gates: **reject**. Independent replay complete: **True**.

The 17 original frozen cases, prompts, model, tool limits, source/index binding and numerical acceptance gates are shared by both conditions. A is current exact retrieval; B also makes the actual `loci_explore` implementation available. Tool choice remains the model's decision.

## Actual B workflow usage

B recorded 3 actual `loci_explore` calls across 3/51 B attempts; per-attempt usage accounting complete: **True**.

## Arm totals

| Arm | Workflow | Answers | Full passes | Complete measurements | Calls | Output bytes | Gross input | Maintained p95 | Explore calls |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| A | current exact retrieval | 51/51 | 50/51 | 51/51 | 276 | 390957 | 2170964 | 49.90933870799199 | 0 |
| B | exact retrieval plus loci_explore | 51/51 | 51/51 | 51/51 | 291 | 441517 | 2314519 | 50.207983374988544 | 3 |

## Maintained task measurements

| Task | Arm | Workflow | Answers | Full passes | Complete | Calls, median | Source bytes, median | Recall, median | Output bytes, median | Gross input, median |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| anvil_temporal_arguments | A | current exact retrieval | 3/3 | 3/3 | 3/3 | 7 | 2935 | 1.0 | 16697 | 65099 |
| anvil_temporal_arguments | B | exact retrieval plus loci_explore | 3/3 | 3/3 | 3/3 | 6 | 5018 | 0.8 | 20882 | 57188 |
| anvil_retrieval_limits | A | current exact retrieval | 3/3 | 2/3 | 3/3 | 11 | 7833 | 1.0 | 25577 | 107128 |
| anvil_retrieval_limits | B | exact retrieval plus loci_explore | 3/3 | 3/3 | 3/3 | 7 | 9315 | 1.0 | 30950 | 78117 |
| anvil_renderer_result_contract | A | current exact retrieval | 3/3 | 3/3 | 3/3 | 8 | 10491 | 0.8 | 27362 | 78238 |
| anvil_renderer_result_contract | B | exact retrieval plus loci_explore | 3/3 | 3/3 | 3/3 | 8 | 11063 | 0.8 | 26591 | 80123 |

## Frozen acceptance gates

| Gate | Passed | Actual | Required |
|---|---|---|---|
| complete_measurements | True | {"A": 51, "B": 51} | {"A": 51, "B": 51} |
| fixture_full_passes | True | 42 | 42 |
| authored_false_relationships | True | 0 | 0 |
| repaired_endpoints | True | true | true |
| maintained_full_passes | True | 9 | 8 |
| per_task_success | True | [] | [] |
| eligible_paired_tasks | True | 2 | 2 |
| positive_comparator | True | 15 | "> 0" |
| observed_call_reduction | False | 0.06666666666666665 | 0.2 |
| tasks_with_fewer_calls | False | ["anvil_temporal_arguments"] | 2 |
| per_task_source_recall | False | {"A": {"anvil_temporal_arguments": 1.0, "anvil_retrieval_limits": 1.0, "anvil_renderer_result_contract": 0.8}, "B": {"anvil_temporal_arguments": 0.8, "anvil_retrieval_limits": 1.0, "anvil_renderer_result_contract": 0.8}} | "B median >= A median for each maintained task" |
| serialized_tool_output_bytes | False | {"sums_of_task_medians": {"A": 69636, "B": 78423}, "ratio": 1.1261847320351541} | 1.0 |
| input_tokens | True | {"sums_of_task_medians": {"A": 250465, "B": 215428}, "ratio": 0.8601121913241371} | 1.0 |
| maintained_p95_latency | True | {"seconds": {"A": 49.90933870799199, "B": 50.207983374988544}, "ratio": 1.0059837432177543} | 1.25 |

## Retained failures

- `anvil_retrieval_limits-r1-A` (A): {"attempt_id": "anvil_retrieval_limits-r1-A-c0a74303-1101-4f6a-9472-cde7bbb96b4a/attempt/1", "event_id": "anvil_retrieval_limits-r1-A-c0a74303-1101-4f6a-9472-cde7bbb96b4a:1", "category": "budget_exhausted", "limits": ["max_evidence_spans", "max_evidence_bytes", "max_estimated_evidence_tokens", "max_serialized_output_bytes_per_operation", "max_serialized_output_bytes_per_run"]}

Failed attempts retain their observed costs. Missing measurements remain unavailable and keep affected gates unknown. Gross provider input includes cached input as a subset.

## All planned attempts

| Attempt | Arm | Answer | Full pass | Complete | Calls | Output bytes | Source bytes | Source recall | Gross input | Cached input | Output tokens | End-to-end s | Index s | Explore calls | Outcome | Raw failures |
|---|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| imported_interface-r1-A | A | True | True | True | 6 | 4329 | 346 | 0.6666666666666666 | 40792 | 32000 | 421 | 18.076938792000874 | 0.03592287500214297 | 0 | completed | [] |
| imported_interface-r1-B | B | True | True | True | 4 | 3148 | 407 | 1.0 | 28859 | 15616 | 441 | 16.797343250000267 | 0.017651750007644296 | 0 | completed | [] |
| imported_interface-r2-A | A | True | True | True | 4 | 3148 | 407 | 1.0 | 27745 | 21248 | 396 | 19.040917958001955 | 0.016862958000274375 | 0 | completed | [] |
| imported_interface-r2-B | B | True | True | True | 4 | 3148 | 407 | 1.0 | 28894 | 18432 | 418 | 20.23579962500662 | 0.011194291990250349 | 0 | completed | [] |
| imported_interface-r3-A | A | True | True | True | 4 | 3148 | 407 | 1.0 | 27784 | 13568 | 399 | 19.04177070799051 | 0.020080207992577925 | 0 | completed | [] |
| imported_interface-r3-B | B | True | True | True | 5 | 3607 | 407 | 1.0 | 35308 | 25344 | 614 | 22.252601208005217 | 0.011009124995325692 | 0 | completed | [] |
| local_interface-r1-A | A | True | True | True | 2 | 1413 | 233 | 0.5 | 15628 | 8704 | 309 | 13.411299665996921 | 0.015036041004350409 | 0 | completed | [] |
| local_interface-r1-B | B | True | True | True | 4 | 3182 | 432 | 1.0 | 28786 | 15616 | 455 | 17.9212132919929 | 0.015396125003462657 | 0 | completed | [] |
| local_interface-r2-A | A | True | True | True | 4 | 3207 | 457 | 1.0 | 27842 | 22272 | 410 | 17.121245957998326 | 0.01581024999904912 | 0 | completed | [] |
| local_interface-r2-B | B | True | True | True | 4 | 3084 | 378 | 1.0 | 28748 | 14592 | 350 | 17.0395829170011 | 0.01793233300850261 | 0 | completed | [] |
| local_interface-r3-A | A | True | True | True | 2 | 1413 | 233 | 0.5 | 15577 | 12544 | 315 | 12.547821375002968 | 0.019563291993108578 | 0 | completed | [] |
| local_interface-r3-B | B | True | True | True | 4 | 3178 | 431 | 1.0 | 28790 | 22272 | 352 | 14.863375125001767 | 0.024828458001138642 | 0 | completed | [] |
| local_alias_chain-r1-A | A | True | True | True | 4 | 3335 | 626 | 1.0 | 27530 | 13568 | 432 | 19.804433582990896 | 0.010649999996530823 | 0 | completed | [] |
| local_alias_chain-r1-B | B | True | True | True | 6 | 5246 | 766 | 1.0 | 43117 | 35072 | 544 | 23.06803079099336 | 0.027057333994889632 | 0 | completed | [] |
| local_alias_chain-r2-A | A | True | True | True | 6 | 5226 | 749 | 1.0 | 41607 | 25344 | 549 | 20.845777084003203 | 0.01953945800778456 | 0 | completed | [] |
| local_alias_chain-r2-B | B | True | True | True | 5 | 5091 | 749 | 1.0 | 36049 | 23296 | 538 | 19.811276625012397 | 0.014967750001233071 | 0 | completed | [] |
| local_alias_chain-r3-A | A | True | True | True | 3 | 4104 | 702 | 1.0 | 22214 | 13568 | 449 | 14.810005542007275 | 0.010734666997450404 | 0 | completed | [] |
| local_alias_chain-r3-B | B | True | True | True | 6 | 8484 | 1061 | 1.0 | 43946 | 36096 | 761 | 29.184884916990995 | 0.011748250006348826 | 1 | completed | [] |
| imported_alias_chain-r1-A | A | True | True | True | 6 | 4985 | 640 | 1.0 | 40768 | 24320 | 687 | 24.24530170900107 | 0.01717120899411384 | 0 | completed | [] |
| imported_alias_chain-r1-B | B | True | True | True | 4 | 6875 | 852 | 1.0 | 31225 | 21504 | 578 | 18.25682541599963 | 0.029904375012847595 | 1 | completed | [] |
| imported_alias_chain-r2-A | A | True | True | True | 6 | 5128 | 666 | 1.0 | 41380 | 34048 | 745 | 24.630057917005615 | 0.03127270798722748 | 0 | completed | [] |
| imported_alias_chain-r2-B | B | True | True | True | 9 | 10509 | 829 | 1.0 | 67114 | 55808 | 1031 | 37.9699192919943 | 0.021867875009775162 | 1 | completed | [] |
| imported_alias_chain-r3-A | A | True | True | True | 2 | 2100 | 387 | 0.8 | 15859 | 8704 | 344 | 13.385198125004536 | 0.012637125008041039 | 0 | completed | [] |
| imported_alias_chain-r3-B | B | True | True | True | 8 | 8094 | 755 | 1.0 | 60577 | 47104 | 706 | 30.513567582995165 | 0.020035624998854473 | 0 | completed | [] |
| named_type_reexport_chain-r1-A | A | True | True | True | 7 | 4576 | 474 | 1.0 | 47655 | 30208 | 638 | 30.7883509999956 | 0.014629041004809551 | 0 | completed | [] |
| named_type_reexport_chain-r1-B | B | True | True | True | 7 | 3829 | 474 | 1.0 | 48393 | 31232 | 607 | 27.457343208006932 | 0.017271666001761332 | 0 | completed | [] |
| named_type_reexport_chain-r2-A | A | True | True | True | 6 | 3686 | 474 | 1.0 | 40010 | 30208 | 640 | 24.807668041990837 | 0.019226208998588845 | 0 | completed | [] |
| named_type_reexport_chain-r2-B | B | True | True | True | 6 | 3485 | 474 | 1.0 | 41467 | 27136 | 565 | 22.01292537500558 | 0.014264124998589978 | 0 | completed | [] |
| named_type_reexport_chain-r3-A | A | True | True | True | 7 | 4219 | 621 | 1.0 | 47137 | 39936 | 653 | 25.659513125006924 | 0.014567624995834194 | 0 | completed | [] |
| named_type_reexport_chain-r3-B | B | True | True | True | 6 | 3686 | 474 | 1.0 | 41412 | 33024 | 464 | 23.64850724999269 | 0.030227000010199845 | 0 | completed | [] |
| same_name_wrong_file-r1-A | A | True | True | True | 4 | 3873 | 530 | 1.0 | 28120 | 8704 | 418 | 17.95679687500524 | 0.013799667009152472 | 0 | completed | [] |
| same_name_wrong_file-r1-B | B | True | True | True | 4 | 3590 | 448 | 1.0 | 29114 | 24320 | 427 | 16.43874929199228 | 0.04219316699891351 | 0 | completed | [] |
| same_name_wrong_file-r2-A | A | True | True | True | 3 | 3350 | 414 | 0.6666666666666666 | 21758 | 17408 | 263 | 12.067188459011959 | 0.03379720800148789 | 0 | completed | [] |
| same_name_wrong_file-r2-B | B | True | True | True | 4 | 3590 | 448 | 1.0 | 28967 | 24320 | 377 | 23.94963195899618 | 0.028247709007700905 | 0 | completed | [] |
| same_name_wrong_file-r3-A | A | True | True | True | 4 | 3590 | 448 | 1.0 | 27994 | 14592 | 430 | 19.89398683400941 | 0.016460041006212123 | 0 | completed | [] |
| same_name_wrong_file-r3-B | B | True | True | True | 5 | 4897 | 448 | 1.0 | 36358 | 28160 | 504 | 22.53953537500638 | 0.01654841699928511 | 0 | completed | [] |
| local_heritage-r1-A | A | True | True | True | 6 | 5477 | 1042 | 1.0 | 42302 | 31232 | 681 | 24.751551249995828 | 0.013161707989638671 | 0 | completed | [] |
| local_heritage-r1-B | B | True | True | True | 5 | 6466 | 1090 | 1.0 | 38411 | 30208 | 627 | 22.765611666007317 | 0.012977791993762366 | 0 | completed | [] |
| local_heritage-r2-A | A | True | True | True | 2 | 3288 | 1365 | 1.0 | 16160 | 12544 | 302 | 16.14812583300227 | 0.010836834000656381 | 0 | completed | [] |
| local_heritage-r2-B | B | True | True | True | 6 | 6890 | 920 | 1.0 | 44475 | 33280 | 512 | 22.00970191700617 | 0.026245665998430923 | 0 | completed | [] |
| local_heritage-r3-A | A | True | True | True | 4 | 3816 | 853 | 1.0 | 28491 | 16384 | 539 | 20.938994166004704 | 0.010335042010410689 | 0 | completed | [] |
| local_heritage-r3-B | B | True | True | True | 4 | 7247 | 1562 | 1.0 | 30890 | 14592 | 479 | 17.461812375011505 | 0.012053166996338405 | 0 | completed | [] |
| imported_heritage-r1-A | A | True | True | True | 2 | 3515 | 1250 | 1.0 | 16321 | 11520 | 421 | 14.643324709002627 | 0.015100499993423 | 0 | completed | [] |
| imported_heritage-r1-B | B | True | True | True | 4 | 5852 | 1301 | 1.0 | 30407 | 22272 | 472 | 19.721497499995166 | 0.03540512500330806 | 0 | completed | [] |
| imported_heritage-r2-A | A | True | True | True | 2 | 3515 | 1250 | 1.0 | 16338 | 12544 | 410 | 16.888072375004413 | 0.013557166996179149 | 0 | completed | [] |
| imported_heritage-r2-B | B | True | True | True | 4 | 5415 | 804 | 0.8 | 30256 | 24320 | 526 | 18.596034832997248 | 0.02684374999080319 | 0 | completed | [] |
| imported_heritage-r3-A | A | True | True | True | 4 | 6129 | 1294 | 1.0 | 29254 | 23296 | 466 | 19.80746437498601 | 0.0343992080015596 | 0 | completed | [] |
| imported_heritage-r3-B | B | True | True | True | 3 | 4839 | 1250 | 1.0 | 23328 | 14592 | 361 | 14.411659917008365 | 0.012949374999152496 | 0 | completed | [] |
| ambiguous_star_exports-r1-A | A | True | True | True | 9 | 13051 | 681 | 1.0 | 68021 | 45056 | 660 | 29.797021209000377 | 0.038899332997971214 | 0 | completed | [] |
| ambiguous_star_exports-r1-B | B | True | True | True | 8 | 7707 | 561 | 1.0 | 58453 | 41984 | 664 | 24.759451167003135 | 0.015574124990962446 | 0 | completed | [] |
| ambiguous_star_exports-r2-A | A | True | True | True | 11 | 10962 | 539 | 1.0 | 78323 | 64512 | 804 | 33.012935375008965 | 0.028657082992140204 | 0 | completed | [] |
| ambiguous_star_exports-r2-B | B | True | True | True | 8 | 10436 | 654 | 1.0 | 60554 | 47872 | 610 | 27.052156167002977 | 0.014825000005657785 | 0 | completed | [] |
| ambiguous_star_exports-r3-A | A | True | True | True | 12 | 9993 | 851 | 1.0 | 89839 | 73728 | 854 | 36.60545437500696 | 0.0352352920017438 | 0 | completed | [] |
| ambiguous_star_exports-r3-B | B | True | True | True | 9 | 8773 | 561 | 1.0 | 66444 | 52736 | 691 | 27.98118762500235 | 0.018703333000303246 | 0 | completed | [] |
| generic_shadow-r1-A | A | True | True | True | 4 | 2602 | 386 | 1.0 | 27571 | 21248 | 469 | 20.477747375000035 | 0.01903162500821054 | 0 | completed | [] |
| generic_shadow-r1-B | B | True | True | True | 6 | 3805 | 527 | 1.0 | 41402 | 34048 | 521 | 20.969789833994582 | 0.014347709002322517 | 0 | completed | [] |
| generic_shadow-r2-A | A | True | True | True | 6 | 3062 | 512 | 1.0 | 40029 | 34048 | 531 | 29.553554415993858 | 0.010993499992764555 | 0 | completed | [] |
| generic_shadow-r2-B | B | True | True | True | 6 | 3929 | 569 | 1.0 | 42399 | 34048 | 711 | 24.827961582996068 | 0.026733209000667557 | 0 | completed | [] |
| generic_shadow-r3-A | A | True | True | True | 4 | 3111 | 386 | 1.0 | 27831 | 21248 | 459 | 18.828666957997484 | 0.02777274999243673 | 0 | completed | [] |
| generic_shadow-r3-B | B | True | True | True | 6 | 5159 | 462 | 1.0 | 43266 | 30208 | 917 | 26.874349334000726 | 0.0243339169974206 | 0 | completed | [] |
| exported_arrow-r1-A | A | True | True | True | 2 | 1528 | 292 | 0.75 | 15719 | 12544 | 305 | 12.061346458009211 | 0.013728834004723467 | 0 | completed | [] |
| exported_arrow-r1-B | B | True | True | True | 4 | 3434 | 339 | 0.75 | 29316 | 22272 | 356 | 15.495783582999138 | 0.012002915987977758 | 0 | completed | [] |
| exported_arrow-r2-A | A | True | True | True | 5 | 4231 | 292 | 0.75 | 34740 | 28160 | 423 | 18.672549374998198 | 0.030472875005216338 | 0 | completed | [] |
| exported_arrow-r2-B | B | True | True | True | 2 | 2441 | 292 | 0.75 | 17033 | 8704 | 276 | 13.094440834000125 | 0.031472415997995995 | 0 | completed | [] |
| exported_arrow-r3-A | A | True | True | True | 4 | 3609 | 253 | 0.75 | 28317 | 22272 | 360 | 17.17558833300427 | 0.028362916986225173 | 0 | completed | [] |
| exported_arrow-r3-B | B | True | True | True | 5 | 4687 | 339 | 0.75 | 36535 | 26112 | 470 | 23.058370250000735 | 0.03225200000451878 | 0 | completed | [] |
| default_identifier-r1-A | A | True | True | True | 5 | 4759 | 399 | 1.0 | 35064 | 27136 | 408 | 18.500497125001857 | 0.010851166996872053 | 0 | completed | [] |
| default_identifier-r1-B | B | True | True | True | 4 | 3510 | 399 | 1.0 | 29304 | 15616 | 396 | 16.544885082999826 | 0.022456165999756195 | 0 | completed | [] |
| default_identifier-r2-A | A | True | True | True | 4 | 3510 | 399 | 1.0 | 28213 | 17408 | 375 | 16.808474707999267 | 0.012560792005388066 | 0 | completed | [] |
| default_identifier-r2-B | B | True | True | True | 5 | 5387 | 399 | 1.0 | 37245 | 30208 | 459 | 22.928536459003226 | 0.030957374998251908 | 0 | completed | [] |
| default_identifier-r3-A | A | True | True | True | 4 | 3671 | 298 | 1.0 | 28331 | 23296 | 380 | 22.47775095900579 | 0.014679291998618282 | 0 | completed | [] |
| default_identifier-r3-B | B | True | True | True | 2 | 2509 | 352 | 1.0 | 17142 | 12544 | 381 | 13.06947216700064 | 0.032524458001716994 | 0 | completed | [] |
| named_function_control-r1-A | A | True | True | True | 4 | 3670 | 283 | 0.75 | 28341 | 23296 | 378 | 16.470626666996395 | 0.01965541699610185 | 0 | completed | [] |
| named_function_control-r1-B | B | True | True | True | 8 | 7583 | 384 | 0.75 | 58177 | 39168 | 661 | 28.430427915998735 | 0.01652937500330154 | 0 | completed | [] |
| named_function_control-r2-A | A | True | True | True | 4 | 3509 | 384 | 0.75 | 28225 | 23296 | 380 | 15.227603624996846 | 0.01259091698739212 | 0 | completed | [] |
| named_function_control-r2-B | B | True | True | True | 6 | 6651 | 384 | 0.75 | 44246 | 34048 | 593 | 22.289634083994315 | 0.016197958000702783 | 0 | completed | [] |
| named_function_control-r3-A | A | True | True | True | 4 | 3670 | 283 | 0.75 | 28309 | 23296 | 343 | 15.486419084001682 | 0.01585508300922811 | 0 | completed | [] |
| named_function_control-r3-B | B | True | True | True | 5 | 5390 | 384 | 0.75 | 36597 | 24320 | 465 | 20.16622416699829 | 0.012670500000240281 | 0 | completed | [] |
| inline_default_control-r1-A | A | True | True | True | 5 | 3831 | 286 | 0.75 | 34808 | 25344 | 459 | 18.721722125002998 | 0.012078291008947417 | 0 | completed | [] |
| inline_default_control-r1-B | B | True | True | True | 5 | 4760 | 380 | 0.75 | 36255 | 30208 | 386 | 18.34285145800095 | 0.01520141698711086 | 0 | completed | [] |
| inline_default_control-r2-A | A | True | True | True | 4 | 3507 | 380 | 0.75 | 28213 | 19456 | 386 | 19.06780574998993 | 0.026717792003182694 | 0 | completed | [] |
| inline_default_control-r2-B | B | True | True | True | 5 | 4760 | 380 | 0.75 | 36452 | 28160 | 528 | 22.46241204199032 | 0.016381333000026643 | 0 | completed | [] |
| inline_default_control-r3-A | A | True | True | True | 5 | 4760 | 380 | 0.75 | 35083 | 22272 | 422 | 18.3218877499894 | 0.014701000007335097 | 0 | completed | [] |
| inline_default_control-r3-B | B | True | True | True | 6 | 6033 | 533 | 1.0 | 43101 | 35072 | 469 | 20.609503582993057 | 0.02691545798734296 | 0 | completed | [] |
| anvil_temporal_arguments-r1-A | A | True | True | True | 7 | 16697 | 2824 | 1.0 | 61476 | 41216 | 891 | 32.71866191700974 | 5.145582292010658 | 0 | completed | [] |
| anvil_temporal_arguments-r1-B | B | True | True | True | 6 | 20882 | 5955 | 0.8 | 57188 | 45312 | 947 | 34.66457054199418 | 5.213792750000721 | 0 | completed | [] |
| anvil_temporal_arguments-r2-A | A | True | True | True | 8 | 16565 | 2935 | 1.0 | 69713 | 58112 | 940 | 38.15142158301023 | 5.194486207998125 | 0 | completed | [] |
| anvil_temporal_arguments-r2-B | B | True | True | True | 9 | 21280 | 5018 | 1.0 | 85690 | 72192 | 1165 | 50.207983374988544 | 5.197195708999061 | 0 | completed | [] |
| anvil_temporal_arguments-r3-A | A | True | True | True | 7 | 20272 | 6103 | 0.8 | 65099 | 49408 | 969 | 37.305785167001886 | 5.217923082993366 | 0 | completed | [] |
| anvil_temporal_arguments-r3-B | B | True | True | True | 6 | 16119 | 2363 | 0.8 | 51560 | 37120 | 693 | 33.20410108400392 | 5.215461291008978 | 0 | completed | [] |
| anvil_retrieval_limits-r1-A | A | True | False | True | 11 | 25261 | 7833 | 1.0 | 107128 | 82944 | 1167 | 45.626944084011484 | 5.155767250005738 | 0 | budget_exhausted | [{"attempt_id": "anvil_retrieval_limits-r1-A-c0a74303-1101-4f6a-9472-cde7bbb96b4a/attempt/1", "event_id": "anvil_retrieval_limits-r1-A-c0a74303-1101-4f6a-9472-cde7bbb96b4a:1", "category": "budget_exhausted", "limits": ["max_evidence_spans", "max_evidence_bytes", "max_estimated_evidence_tokens", "max_serialized_output_bytes_per_operation", "max_serialized_output_bytes_per_run"]}] |
| anvil_retrieval_limits-r1-B | B | True | True | True | 7 | 19613 | 10486 | 1.0 | 63282 | 41472 | 1074 | 36.260433125004056 | 5.177234375005355 | 0 | completed | [] |
| anvil_retrieval_limits-r2-A | A | True | True | True | 9 | 25577 | 6510 | 1.0 | 91192 | 72192 | 1056 | 42.62796016600623 | 5.2547422500065295 | 0 | completed | [] |
| anvil_retrieval_limits-r2-B | B | True | True | True | 7 | 30950 | 9071 | 1.0 | 78117 | 63488 | 1095 | 40.92245358299988 | 5.211812249996001 | 0 | completed | [] |
| anvil_retrieval_limits-r3-A | A | True | True | True | 14 | 30552 | 8300 | 1.0 | 153834 | 128256 | 1204 | 49.90933870799199 | 5.360218207992148 | 0 | completed | [] |
| anvil_retrieval_limits-r3-B | B | True | True | True | 12 | 31320 | 9315 | 1.0 | 129681 | 106240 | 1132 | 46.85038237500703 | 5.3052238340023905 | 0 | completed | [] |
| anvil_renderer_result_contract-r1-A | A | True | True | True | 8 | 27362 | 11964 | 0.8 | 78238 | 56064 | 1004 | 41.092743125002016 | 5.225482291003573 | 0 | completed | [] |
| anvil_renderer_result_contract-r1-B | B | True | True | True | 9 | 33120 | 13482 | 0.8 | 95790 | 76288 | 1013 | 39.641008916994906 | 5.184641208004905 | 0 | completed | [] |
| anvil_renderer_result_contract-r2-A | A | True | True | True | 10 | 29846 | 10347 | 1.0 | 100187 | 78080 | 998 | 38.60395783399872 | 5.003855832997942 | 0 | completed | [] |
| anvil_renderer_result_contract-r2-B | B | True | True | True | 8 | 26591 | 11063 | 0.8 | 80123 | 66304 | 1121 | 44.62673404200177 | 5.249960665998515 | 0 | completed | [] |
| anvil_renderer_result_contract-r3-A | A | True | True | True | 6 | 21219 | 10491 | 0.6 | 52854 | 41216 | 827 | 33.94837470901257 | 5.008826000004774 | 0 | completed | [] |
| anvil_renderer_result_contract-r3-B | B | True | True | True | 6 | 21256 | 10334 | 0.6 | 54276 | 40192 | 793 | 29.629902917004074 | 5.000441500000306 | 0 | completed | [] |
