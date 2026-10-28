# Search and source-delivery ablation

Status: protocol frozen; outcome is recorded separately in RESULTS.md
Date: 2026-10-28

Vik authorized the proposed bounded ablation on its own branch so production remains safe. Terminal outcome: execute matched replay of real retained search queries and source requirements, determine which costs simpler search/read removes, and use agent comparisons only when they are needed for a remaining concrete decision. A supported negative or inconclusive result can complete this investigation.

Branch: `experiment/search-ablation`, worktree `/Users/brummerv/phluxxed/loci/.worktrees/search-ablation`, based on R1 `84d5179a42c5ee12d76031dd440c0ce8941d0e83`. Primary repository master starts at `ceecb0d2728c64827d005bd2e2f34d5ca481f86b`; original `/Users/brummerv/loci` master remains `9655a287ca28d758a8848b6622887c54f8f81a41`. Existing work and evidence remain untouched.

All experiment code, dependencies, stores, source copies and reports belong in this worktree. Do not change global Codex/Pi settings or the production entrypoint. Do not publish retained private source, raw tool responses, task prompts or oracles. Use Promptfoo's installed skills/shared CLI for this retrieval evaluation; cases and authoritative checks stay in this project. No paid model call is required for the mechanical stage.

## Acceptance and bounds

- Replay real search terms on the frozen 701-file source snapshot; preserve provenance and distinguish additional diagnostic cases.
- Compare ripgrep and a pinned tgrep release with equivalent search scope/matching/freshness and independently check result equality before timing. Retain cold build, warm search, current scan and post-edit behavior separately. Use seven interleaved measured repetitions after one warmup; freeze cases before timing. A search advantage must save at least 10 ms per query and 20% median latency to count as mechanically material for this local workload; it is not evidence of task-level benefit.
- For already located files, compare the existing R1 source delivery with ordinary path/line reads of the same required source spans. Record completeness, calls, source/output bytes and elapsed time. Preserve eligibility, containment, stale-source and truncation checks; never treat partial source as complete. Prefer reuse of existing mechanisms to adding a product API.
- Before measured trials, add the `direct_full_refresh` control: identical direct page output/reader with actual existing repository inventory refresh. Its comparison with `direct` isolates global inventory work. R1 versus this control still bundles preview/navigation/framing/paging differences; it is not described as paging-only. All four selected spans fit one direct page; broader multipage cases would require separate interpretation.
- Preserve failures and all selected cases. Do not expand repetitions or tune cases until a preferred outcome appears. Report whether an unresolved decision actually warrants further agent runs; replay is not evidence about voluntary adoption or whole-task efficiency.
- Leave focused reproducible checks and a concise result with limitations. No merge or production deployment is authorized by this experiment.

## Assignments

Primary owns worktree, protocol, Promptfoo integration, coordination and final interpretation. Independent scopes will be recorded before launch; workers must not revert each other's changes or spawn agents.

- `ablation_cases`: real query/span extraction from preserved R1 traces; writes only `private/cases.json` and `private/cases-notes.md`. Acceptance: bounded representative recorded queries and required source spans with exact artifact/row provenance and source hashes, plus explicit limitations; no execution or scoring. Model override Luna, medium reasoning, fork none.
- `ablation_backend`: isolated pinned tgrep installation and matched ripgrep/tgrep implementation; owns `evals/search_ablation/backend.py`, its focused test file, and `private/backend/`. Acceptance: actual CLI output equivalence, visible errors, startup/build/warm/current costs, safe daemon cleanup and replay API; no global configuration or product changes. Configured default subagent model, high reasoning, fork none.
- `ablation_delivery`: exact-source delivery comparison; owns `evals/search_ablation/delivery.py`, its focused test file, and `private/delivery/`. Acceptance: actual existing R1 delivery versus direct bounded reads for the same required spans, independent byte equality, calls/output/cost accounting and focused edge checks; no product changes. Configured default subagent model, high reasoning, fork none.

Primary records results/dispositions after return and owns Promptfoo configuration/provider, protocol and final result. Native tree showed previous assignments complete; three independent scopes fit available capacity.

Case extraction reused `/root/ablation_cases`'s retained task context to correct scope/case/glob fidelity before timing. Adopted seven search cases: five recorded rg queries and two explicitly adapted Loci symbol probes. Natural-language and exact-path Loci requests remain recorded but excluded from grep comparisons. Adopted four observed source spans; viewer lines 1-440 cover part of its 456-line file. Result locators: ignored `private/cases.json`, `private/cases-notes.md`.

Delivery implementation returned exact required-byte smoke equality and seven focused checks. Primary requested the full-refresh control to address confounding before measurements, then adopted it with the residual bundled-contrast limitation above. Backend implementation returned verified pinned install, exact 701-file membership, equality smoke, seven focused checks and a retained synthetic stale-index finding. Warm measured rounds have not yet run.
