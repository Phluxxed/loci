# R1 integrated implementation and agent pilot

Outcome: integrated source/path navigation, optional native semantics and focused proof, deterministic qualification, prospectively frozen four-condition native Codex pilot, recommendation, commit and push. No production/global configuration changes, no API billing, no Python/Go semantic implementation.

Base: experiment/r06-navigation-proof at 1fed52dc. Primary owns src integration and MCP interface.

## Delegations before launch

- qualification: combined end-to-end acceptance and existing R0 harness extension, exclusive tests/test_r1_integrated.py and benchmarks/architecture_integrated.py plus .scratch/r1-integrated/qualification*; configured default model, high effort, fork none. Acceptance: validate source-only no semantic loading, path workflow, semantics/proof, invalidation, uncertainty, independent source/proof replay and end-to-end costs. Await interface coordination before writing imports. Return results and limitations. Independent from pilot orchestration.
- pilot: inspect and minimally extend R0.1 orchestration, exclusive benchmarks/complete_work/r1.py, tests/test_complete_work_r1.py and .scratch/r1-integrated/pilot*; configured default model, high effort, fork none. Acceptance: native subscription execution through existing host, four independent tasks and conditions with freeze/evaluators/order/accounting, no scored execution until primary qualification gate. Report actual host feasibility. No global settings/sandbox changes. Return code and evidence paths.

Tree checked: only primary active, three worker slots available. Both assignments contribute required independent deliverables; no overlap with primary source scope.

## Integration decision

Primary implemented `IntegratedSource` and separate `loci.integrated_mcp` experimental entrypoint. Four tools (retrieve/read/semantic/proof); path-only exposes first two. Retrieval adds bounded source-path candidates, without automatic reads/resolution. Existing read wire format preserved exactly. Source reanchor accepts one delivered identity, file granularity.

Full-corpus qualification uncovered a compatibility failure when navigation was initially added to read packets: unchanged strict read schema rejected it. Primary removed the read override instead of changing production schema or relaxing scorers. Initial failed full run and the temporary now-obsolete regression failure remain retained; no pilot freeze or scored run preceded this correction.

Native pilot worker found inherited SessionStart Loci hook would discover Git ancestor if task copies lived inside this worktree. Independent run workspaces will use /private/tmp outside Git ancestors; unchanged hook exits there. Global settings/hooks/sandbox remain unchanged. Generic ambient Loci guidance is shared and will be disclosed.

## Bounded native-launch escalation (before launch)

- identity: native_launch_decision; contribution: determine whether already-frozen pilot can execute through existing native Codex without changing its sandbox/config, after nested shell helper failure before any thread.
- scope: read-only recommendation from frozen command, stderr and R0.1 contracts; no launch, edits, sandbox investigation or broader framework.
- acceptance: distinguish standard parent tool escalation from changing native Codex protections; recommend a bounded allowed next step or supported blocker.
- model: explicit gpt-6-astra; effort high; fork none.
- tree checked: primary plus pilot/qualification workers active, one free slot; preserve both workers.

## Returned assignments and primary dispositions

- qualification: adopted tests/test_r1_integrated.py, benchmarks/architecture_integrated.py, qualification.md and gate/replay artifacts. They use unchanged strict scorers and actual combined costs. Preserve material negative coverage (180/187 vs185/187;24/84 links) and initial failure. Final gate passed288 replayed executions.
- pilot: adopted benchmarks/complete_work/r1.py, nine tests, frozen tasks/oracles/catalogs/schedule and retained startup attempt. Native comparison remains unexecuted because no model session could start. Primary retained a second prospectively amended parent-launch attempt; same failure, no further retry.
- native_launch_decision (gpt-6-astra, high, none): adopted bounded recommendation to try one standard auto-reviewed parent escalation while leaving native child argv/protections frozen; preserve/relocate prior attempt first and stop on failure. Recommendation in native_launch_decision message; no worker files. The attempt was approved for launch but failed identically before any thread. No unsupported claim that effective child protections were verified.

All54 relevant tests pass. Final288-case independent replay passed after removing session-created ephemeral source exports/stores. Primary reviewed task source/prompts/oracles before final freeze, archived pre-score corrections and both native startup failures, and retained null unknown metrics. Final recommendation: revise/hold advancement; no production adoption or measured superiority claim.
