# Loci R0.1 — evaluation harness qualification

**Superseded for the current R0 execution path by the user's correction:** see
[native qualification](2026-10-22-r0-1-native-qualification.md). Custom episode
profiles and supplementary Seatbelt checks below are historical evidence, not
R0 requirements or current blockers. This original audit is retained for provenance.

**2026-10-22 · Decision: NO-GO for the first measured pilot.** The harness has substantial reusable machinery and the focused deterministic repairs pass. Live host isolation still fails; native multi-turn telemetry has not been independently qualified. **R0.1 remains unqualified.** No measured model comparison, provider inference probe, retrieval-engine change, historical rescore, or campaign freeze was performed.

Audited checkout: `/Users/brummerv/phluxxed/loci`, branch `master`, base `f41b3eaa4c7871c68972de5f760572a6bcbe1760`, plus the benchmark-only changes described below. Existing unrelated dirty files were preserved. This is a dated audit and draft protocol, not an adopted experiment contract.

## Reusable inventory and present coverage

| Component | Reuse for R0 | Verified coverage and boundary |
| --- | --- | --- |
| [prepare.py](../../benchmarks/complete_work/prepare.py), source maps and dependency receipts | Isolated exports, pinned source, explicit dependency preparation, serving code outside writable targets | `test_complete_work_prepare.py`: target/source separation, excluded benchmark/history material, source pin, preparation transitions, rejection of dependency roots exposing observer inputs. Current preparation requires Loci preindexing and the historical schedule; native preparation is not implemented. |
| [runtime.py](../../benchmarks/complete_work/runtime.py) | Exclusive wire journal before reduction; bounded stdio transport; no implicit retries; unexpected approvals fail; process cleanup | `test_complete_work_runtime.py`: notifications, invalid wire messages, server requests and stream closure. Transport fixtures are not provider telemetry evidence. |
| [controller.py](../../benchmarks/complete_work/controller.py) | Fresh-thread execution, fixed continuation, deadlines, retained failed/not-reached stages, source history, freeze closure, exclusive output and campaign lock | `test_complete_work_controller.py`: exact prompts/thread/profile sequencing, timeout, reroute, orientation edit, refusal without freeze, late completion. Hard-coded Terra/high, three stages, eight rows and graph-on/off inventory are campaign-specific. |
| [isolation.py](../../benchmarks/complete_work/isolation.py) and controller canaries | Process-local deny-root profiles, dependency read grants, protected files, disabled ambient capabilities | `test_complete_work_isolation.py`: restrictive overrides, wrong effective profile/root/cwd, unavailable sandbox, excess and missing access. Source-read canary added. Tests verify rejection logic; they do not prove effective OS enforcement or equality of a future native/Loci pair. |
| [control.py](../../benchmarks/complete_work/control.py) | Retained full packets, exact source bytes, extent/hash validation, source-version history, failed calls | Real local stdio tests cover source changes, stale references, bad extents and out-of-scope repositories. The on branch calls current normal retrieval; off is a Loci direct-source control, **not native retrieval**. Preserve this historical contrast. |
| [evidence.py](../../benchmarks/complete_work/evidence.py) | Exact native-item/packet/argument join, ambiguity retained, repeated bytes counted only within the same full-file identity | `test_complete_work_evidence.py`: missing, ambiguous, duplicate, failed and extra native calls; corrupt packets; mixed/wrong control identity. This is a Loci-specific join, not a native shell read-attribution adapter. |
| [accounting.py](../../benchmarks/complete_work/accounting.py) | Cumulative token differencing; U/K/O separation; inner/outer operation distinction; exact expected run set; failures included; infinite per-correct cost at zero success | `test_complete_work_accounting.py`: missing/invalid/nonmonotonic usage, interruption, duplicate usage, failed rows and missing runs; added required-field negative controls. `known` means observations passed existing checks, **not proven terminal completeness**. Response completions are only a request lower bound. |
| [evaluate.py](../../benchmarks/complete_work/evaluate.py) and [oracles](../../benchmarks/complete_work/oracles) | Source replay outside trial time, independent behavioral fixtures, diffs, arm-blinded review still pending | Snapshot/blob corruption and stage substitution now fail before grading. Loci oracle tests reject unchanged and deliberately faulty candidates and accept a disposable reference patch. Anvil tests validate export, environment/error handling, fixture syntax and strict result shape; full Anvil behavioral reference controls were not rerun here. Overall `correct` remains unset pending review. |
| [cross-module fixture](../../tests/test_complete_work_integration.py) | Real local Loci MCP + scripted native turns + accounting/delivery + changed-source replay | Both on/off branches pass. This is deterministic assembly evidence, not a native-vs-Loci outcome or live model trace. |

Coverage is scoped to the complete-work suite, not the entire repository. The [worker audit](../../.scratch/loci-r0-1/audit-validity.md) records additional source/function and test locators. Its findings describe the pre-repair code; dispositions below describe the final changes.

Historical interpretation is unchanged. The [complete-work design](../../benchmarks/complete-work/design-v1/protocol.md) is an unlaunched graph-enrichment design. Earlier [ordinary-adoption results](2026-09-14-normal-graph-adoption-result.md) and [binding results](2026-09-15-schema-repair-token-result.md) used different controls and reported negative or incomplete results. None supplies a measured native-versus-current-Loci baseline. Tool delivery and graph proof do not establish internal model reliance.

## Native sandbox reproduction

The installed executable identifies as **codex-cli 0.163.0**. The new [probe script](../../.scratch/loci-r0-1/probe_host.py) uses the existing restrictive read/write profiles, disables the unused MCP server, and never calls `turn/start`. Its [wire journal and receipt](../../.scratch/loci-r0-1/host-probe-01/result.json) retain binary/config identities and all responses. It is a diagnostic reproduction, not a full prepared-episode preflight.

| No-generation operation | Current observation |
| --- | --- |
| App Server initialize and permission-profile list | Succeeded; named profiles advertised. Advertisement does not prove enforcement. |
| `command/exec` with `loci_episode_read` | Exit 71; empty stdout; `sandbox-exec: sandbox_apply: Operation not permitted`. Canaries could not execute. |
| Fresh `thread/start` with the same profile, fallback disabled | Failed loading AGENTS.md instructions because the filesystem sandbox helper exited 71 with the same error. |
| [Independent restrictive Seatbelt control](../../.scratch/loci-r0-1/seatbelt-control.json), invoking only `/usr/bin/true` | Same exit 71 and `sandbox_apply` error, outside the harness implementation. |
| Submitted model turns | **0**. |

This reproduces the [historical command failure](../../.scratch/deterministic-graph-retrieval/episode-runtime-capability/isolation-native.json) and [thread preflight failure](../../.scratch/deterministic-graph-retrieval/episode-runtime-capability/controller-preflight.json). The independent control localizes the failure to applying an OS sandbox in this execution environment, rather than prompt/scoring/Loci behavior. It does not identify the host's underlying entitlement or parent-sandbox cause. No access-control weakening, host configuration change, escalation, or approval-review rejection occurred in this run. Repeating the same launch condition would not resolve it.

The next relevant isolation check is the same restricted probe from an execution context capable of applying Seatbelt, retaining the exact profile and canaries. That context is not qualified by this report. The [installed schema extract](../../.scratch/loci-r0-1/runtime-contract.json) verifies request shapes only. Official [App Server documentation](https://learn.chatgpt.com/docs/app-server) describes version-specific generated schemas and usage/item notifications; it does not prove this host's event completeness.

## Focused repairs and deterministic results

Four narrow changes were justified by concrete acceptance gaps:

1. **Receipt identity:** delivery accounting rejects mixed control identities and the controller binds the join to its configured arm, target, store and control hash. Matching packet bytes alone no longer allow another control's receipts to be called known delivery.
2. **Snapshot readback:** replay recomputes the file-map identity; episode evaluation checks it against the captured stage identity before calling an oracle. Blob identity is also checked when generating diffs. Referencing a different, valid retained blob cannot silently change the evaluated candidate.
3. **Anvil oracle result completeness:** passing requires the exact eight independent check IDs once, boolean outcomes and no fixture errors. Empty, incomplete, duplicate or malformed results cannot pass. A genuine `fixture_runtime: false` remains an unsuccessful result.
4. **Required source access:** isolation canaries now read a protected file in the task root as well as the temporary canary. A profile that can use temporary space but cannot read task-root source fails the check.

All changes are in benchmark/evaluator code and focused tests. No serving retrieval code under `src/` changed. Historical inputs, contracts and stored results were not edited; these checks apply to future readback, not retrospective rescoring.

| Check | Result / retained evidence |
| --- | --- |
| Initial complete-work suite | [42 passed, 5 failed](../../.scratch/loci-r0-1/baseline-tests.txt); every failure required the absent historical Anvil export. |
| Fixture recovery | [638/638 file hashes match](../../.scratch/loci-r0-1/anvil-export-recovery.json). Reconstructed from local Anvil Git objects at `53bf29e60cece2335aa39fe301935a07e8e8d4e4`, checked against the existing evaluator map, installed only into the previously absent `/tmp/anvil-source-tasks-20260914/t21`. No historical export was overwritten. |
| Full suite after repairs and recovery | [65 passed, 11 subtests passed](../../.scratch/loci-r0-1/final-tests.txt), `.venv/bin/python -m pytest -q tests/test_complete_work_*.py`. |
| Final receipt/readback/integration check | [13 passed](../../.scratch/loci-r0-1/readback-tests.txt), including two additional episode-boundary rejection cases; real local MCP both arms still pass. |
| Missing resource fields | Every required native usage field independently removed: aggregate usage stays unknown and `arm_cost` stays unproven. Missing/repeated scheduled rows and unsuccessful attempts retain existing coverage. |
| Isolation and unequal access controls | Hidden evaluator exposure, read-only orientation writes, protected writes, missing task reads/writes, wrong effective profile/root/cwd and dependency grants exposing observer inputs all fail their relevant guard. **No actual native/Loci pair exists yet; a cross-arm effective-access comparator remains required.** |

The export recovery proves byte identity to the retained file map, not historical Git metadata, dependency installation or a live Anvil oracle execution. The recovery receipt retains its source and manifest hash.

A [deterministic partial-usage control](../../.scratch/loci-r0-1/telemetry-limit.json) deliberately supplies early usage followed by two response completions. Existing accounting returns `usage_status: known` for that early total. This establishes a conditional completeness gap, not that real host events actually arrive in that order. No event-order repair was invented without a live contract. Request/retry counts, terminal usage, truncation and outer-call capture must therefore be qualified separately before R0 efficiency results are valid.

## Draft R0 paired protocol

**Question:** Does providing current normal Loci help an agent complete the same task correctly with less total time, computation and effort than native repository tools alone?

**Arms:** N has ordinary native shell/file/edit tools and no Loci server, index, skill injection or retrieval hook. L has exactly those native tools plus current normal `loci_retrieve` and `loci_read`. Use the maintained normal implementation, not graph-off as N. Keep fallback native navigation in L and retain Loci non-use. This estimates the effect of the Loci availability/instruction package; it does not isolate graph enrichment or compel a tool-use policy.

**Equal conditions and identity.** Freeze a new R0 design without modifying design-v1. Pin the target commit/full export map separately from the serving Loci revision. Freeze exact task prompts and continuations, model/effort and fallback policy, CLI and dependency identities, limits, common instructions, arm-specific tool instructions/descriptors, effective access profiles, evaluator and complete scheduled run-ID set. Compare both arms' normalized effective filesystem/network/environment grants and common capabilities before launch, allowing only declared path substitutions and Loci-specific capability differences. Test deliberate permission inequality. A named profile alone is insufficient. Keep gold, prior answers, history and other runs outside trial access; test direct paths, symlinks and instruction discovery with evaluator-owned canaries. Both arms must execute the actual required Node/Python checks under those grants.

Each task/arm/repetition gets a fresh thread, writable source copy and distinct temporary/store state. Source bytes, dependency lock and common instructions match. The Loci backend is trusted observer infrastructure with only the assigned target accepted by its adapter; it must not return external source. Ambient memory, hooks, plugins, web and delegation are disabled equally. Record the effective instruction sources rather than relying only on requested configuration. Loci descriptors and discovery effort are treatment costs.

**Schedule.** Proposed developmental pilot: two historical full-work tasks, two repetitions each, two arms: eight attempts/four pairs. In order: Anvil rep1 N→L; Loci rep1 L→N; Anvil rep2 L→N; Loci rep2 N→L. Run serially. Reuse the three fixed prompts with 120/360/240-second caps only through a new explicit freeze. Keep the same follow-up regardless of quality, and stop later stages after terminal runtime failure. Do not replace failed trials with fresh successes. A failure before assignment consumes no measured row; a failure after assignment remains an attempted row, even if no model turn completes.

No model slug is selected or entitlement claimed here. The old controller's Terra/high pin is a historical constraint to replace explicitly in the new protocol, identically across arms. No R0 schedule or freeze has been created or executed.

**Independent evaluation.** Freeze terminal behavior and invariants before outputs exist. Run evaluator-owned behavioral fixtures against hash-verified retained candidate snapshots; agent-authored tests are supplementary. Freeze task-specific orientation criteria and material final-claim checks as well. A reviewer receives arm-masked answers, patches, independent test receipts and evidence; remove tool logs and arm names from that packet. Record whether remaining wording reveals the arm. A correct completion requires all required behavioral checks, no severe invariant violation and a passing material-claims review. Missing evaluator evidence means ungraded, not incorrect-by-assumption or correct. Tool errors recovered within a successful task remain in its resources. Oracle feedback never returns to the agent.

**Measurements and denominators:**

| Measurement | Definition and validity requirement |
| --- | --- |
| Completion | Correct terminal tasks / all assigned attempts, with incorrect, runtime failure, timeout, budget exhaustion and ungraded counts shown separately. No selection on Loci use or delivery. |
| Primary agent latency | Monotonic time from first fixed task submission to terminal completion/stopped execution, including tools, tests, repairs and interstage handoff. Report setup/index time, archival/cleanup and complete controller wall separately. |
| End-to-end navigation cost | Include Loci-specific index/setup time and resources in a cold-start total; show agent latency separately. Any warm-index scenario must be separately frozen with explicit amortization, not mixed into the cold pilot. Common source/dependency preparation and evaluator cost are recorded separately, identically scoped. |
| Provider computation | Full input I, cache-read K, uncached U=I−K, output O, reasoning R with inclusion semantics verified, cache-write where supported, compactions, model identity, request/retry status. Difference cumulative usage once across the fresh thread. Do not add reasoning twice if already in output. Known observed totals are not accepted as complete until reconciled with a qualified terminal boundary. |
| Tools and backend work | Native operations, MCP operations, errors, outer Code Mode calls and nested operations counted distinctly; exact output bytes and truncation flags retained. Preserve index/server startup and per-call timing. CPU/peak-memory measures need a defined process scope; unavailable observations remain unknown. Counts are effort proxies, not proof of useful work. |
| Source identity/delivery | Full target maps and content-addressed versions before/after stages; exact Loci spans and packet bytes at delivery. Native command/file outputs need their own capture and source-version association. Arbitrary shell output must not be assigned an invented source span; unresolved attribution stays unknown. Repeated source bytes are compared only within an identical file hash. |
| Total and per-correct resources | Sum every assigned attempt, including unsuccessful ones. Per-correct time = total time / correct tasks; normalized token cost = Σ(U+αK+βO), divided by correct tasks only when grades and required resources are complete. At zero correct tasks, per-correct cost/time is infinite. Publish U/K/O and frozen α/β sensitivity; no billed-dollar inference without verified prices/billing semantics. |
| Rework | Freeze a rubric for substantive correction of an earlier wrong claim/change, using stages, diffs and test failures. Report counts/time as secondary evidence. Repeated reads or extra calls alone do not establish rework. |

**Analysis.** Publish every attempt and pair before aggregate summaries. Pair by task/repetition; show per-task quality and resource differences. Quality and severe failures precede efficiency. With this small selected corpus, report descriptive results only, including discordant pairs; no significance or population claim and no retrieval-engine adoption decision. A resource winner requires complete required evidence, no worse observed completion/severe-failure outcome and a declared cost/time tradeoff. If metrics conflict, report the tradeoff. Missing telemetry invalidates the relevant resource comparison and preserves the attempt in the outcome table.

## Proposed corpus and provenance

| Candidate | Evidence provenance | Proposed use and limitation |
| --- | --- | --- |
| `anvil-creation-evidence` | [Three prompts and criteria](../../benchmarks/complete-work/design-v1/episodes.json); commit `53bf29e60cece2335aa39fe301935a07e8e8d4e4`; [638-file map](../../benchmarks/comparisons/ordinary-adoption-v1/cases.json); [independent fixture contract](../../benchmarks/complete_work/oracles/anvil_oracle.md). Export now hash-verified. | Developmental full-work pilot: explanation, advisory feature, API/page continuation and graph-state/safe-output invariants. Historically chosen for graph-context value; not an unbiased task sample. Dependency/runtime and reference-oracle checks still required before measured use. |
| `loci-direnv-exclusion` | [Three prompts and criteria](../../benchmarks/complete-work/design-v1/episodes.json); Git export `f3d9134aece5156bec1dcc302d4330522d1d96e5`; [independent path/index oracle](../../benchmarks/complete_work/oracles/loci.py); baseline/reference/regression tests pass here. | Developmental full-work pilot: exact `.direnv` policy, near-name negatives and incremental removal. Keep serving Loci separate from the editable historical target. Also selected for graph-context value. |
| `anvil_temporal_arguments`, `anvil_retrieval_limits`, `anvil_renderer_result_contract` | [TypeScript v3 corpus](../../benchmarks/corpora/typescript-context-v3/corpus.json), source archive/commit `4d5afbcb54ab9d4bbb12e39357108b3caa4f6874` documented in [v1 README](../../benchmarks/corpora/typescript-context-v1/README.md). | Optional separate answer-only diagnostics; not counted as full-work pilot tasks. Selected around type-context mechanisms, one repository. Existing provenance inspected; archive replay was not rerun in this task. |
| Independently selected ordinary tasks — **not selected yet** | No source revision, prompt or gold is claimed. Proposed selection record: eligible repositories and time window, complete candidate list, exclusion rule, fixed sampling seed, source export/hash, prompt author and independent oracle provenance. | Required before a broad value claim. Select without inspecting Loci graph shape or prior arm outcomes; include ordinary local lookup/maintenance and cross-file change, plus a task with no anticipated relationship advantage. Freeze task-specific gold before agent outputs. |

Historical fixtures are useful for developmental harness/pilot checks, not an independent confirmation set. Synthetic Python caller/callee fixtures and TypeScript mechanism fixtures remain harness controls; do not inflate the measured corpus with them. The [corpus worker note](../../.scratch/loci-r0-1/corpus-protocol.md) supplies further historical provenance.

## Minimum remaining changes and GO gate

These are proposed additions tied to specific R0 requirements, not completed capabilities:

1. **Native/Loci assignment:** extend the existing preparation/controller path with explicit N/L arms and frozen model/settings. N must omit Loci entirely; L reuses normal retrieval and receipt capture. Preserve historical on/off dispatch. No new runner framework is needed.
2. **Pair equality check:** compare normalized frozen inputs and observed effective grants/capabilities/instructions across the pair, with a narrow list of declared treatment differences. Add a deterministic mismatch control. Existing per-run access guards cannot substitute for this cross-arm check.
3. **Native evidence and terminal accounting:** extend existing wire reduction to retain native outputs, truncation and source-version associations. Establish and enforce a final usage reconciliation rule; failed requests/retries without telemetry remain unknown. Keep raw journals and all unsuccessful rows. Do not accept `arm_cost` alone as an R0 validity gate.
4. **Live host qualification:** on an environment that can apply the unchanged restrictive profile, prove read/write/source/dependency/test access, denied hidden inputs, instruction isolation and Loci target confinement. Independently qualify actual multi-turn continuation, final usage, outer/nested calls, partial failure and timeout/cleanup telemetry using a separately authorized non-campaign control. This task authorizes no such model execution.
5. **Prospective freeze:** verify the selected task dependencies and independent baseline/reference/fault controls, then freeze the new protocol, full input closure, paired schedule and scoring rubric. Publish no measured result before those gates pass.

| Gate | Current status |
| --- | --- |
| Deterministic complete-work infrastructure | PASS within the stated coverage; focused repairs verified. |
| Historical task source identity | Loci preparation verified; Anvil 638-file export recovered and verified. |
| Live OS isolation | **FAIL — reproducible exit 71.** |
| Actual native multi-turn usage and failure telemetry | **UNQUALIFIED — no model probe permitted or executed; terminal completeness gap retained.** |
| Native/Loci arm support, effective equality and native source attribution | **PROPOSED — not yet implemented/qualified.** |
| New experiment protocol, corpus and independent criteria | DRAFT; no prospective freeze. |
| First measured pilot | **NO-GO.** |

The next step that changes this decision is qualification of the same restrictive isolation profile in a host context able to enforce it. Telemetry must then pass its own gate; deterministic success does not remove either requirement. Work stops here before live comparisons.
