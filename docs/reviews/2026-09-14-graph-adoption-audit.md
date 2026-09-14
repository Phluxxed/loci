# Graph adoption: observed routing and measurement gap

14 September 2026. This investigation asks whether agents actually consume
Loci's relationship capabilities during ordinary navigation. Availability,
invocation, delivered relationships, answer use, and improved outcomes are
different observations.

## Fresh-context observation

A Terra/high native subagent received no conversation history and this task:

> Investigate Anvil read-only. A user prompt sometimes arrives with little
> useful remembered context. Find the implementation path from a host
> receiving the prompt to the final context injected into it. Explain where
> evidence is selected, what makes it belong to the requested workspace, and
> what happens when it is stale, missing, or over budget. Identify the main
> entry point and its immediate consumers/dependencies so a maintainer knows
> where to investigate first.

The full assignment also required concise source references, normal repository
instructions, no edits, no broad tests, no delegation, and the existing denied
path boundaries. It did not mention graph usage, the adoption investigation,
or a preferred retrieval tool. The target was
`/Users/brummerv/phluxxed/anvil_redux`.

Before its first completed answer, the agent made **13 shell command calls,
zero Loci calls, and zero tool-discovery calls**. It read the installed Loci
skill and its setup reference, then used `rg`, `sed`, and line-numbered reads.
The first and last tool calls were 04:12:38 and 04:13:53 UTC. The resulting
answer traced the requested modules; this investigation did not independently
grade its completeness or compare its quality/cost to a graph-assisted answer.

A diagnostic follow-up, after completion, asked it to inspect `ALL_TOOLS`
without repeating the task. That returned all **21 Loci tools**, including
`loci_explore` and the graph tools. The agent reported that it had inferred
unavailability from the directly listed tools without checking deferred
discovery. This establishes a discovery/routing failure in this run; it does
not establish an unavailable server or a broken graph engine. The tools were
observed in the same agent on follow-up, not independently probed before its
initial task.

Local evidence: Codex session
`01a09e1d-d62a-7e40-8243-d7a5add917a2`, in
`/Users/brummerv/.codex/sessions/2026/09/14/rollout-2026-09-14T14-12-30-01a09e1d-d62a-7e40-8243-d7a5add917a2.jsonl`.
Initial calls are at lines 15 through 101; post-task discovery and its result
are at lines 121 and 123. The follow-up is excluded from initial-task counts.

## Historical evidence and limits

A diagnostic scan inspected 208 locally retained Codex rollout files modified
since 11 September, filtering tool events to 11 September 00:00:00 through
14 September 04:08:26 UTC, before this investigation. It deduplicated call IDs
and counted literal Loci invocation sites in Code Mode. No JSON parse failed.
This is a count of observed invocation sites, not a complete executed-call
ledger: loops, dynamic dispatch, shell/CLI routes, and unretained histories
prevent treating it as a production adoption rate.

- 3,683 ordinary retrieval sites: file 1,197; outline 852; get 984; search 406;
  grep 244.
- 29 explore sites: 15 `locate`, seven `impact`, five `dependencies`, and two
  parameterized sites from runtime activation.
- 11 gets explicitly enabled type context; all were in subagent histories.
- Primary histories contained 965 ordinary retrieval sites. Their three
  literal explore sites and four additional dynamic-dispatch cells belonged
  to W5.5 runtime activation, rather than ordinary navigation.

There is nevertheless real relationship delivery outside Loci's own tests.
An Anvil source investigation on 14 September at 01:25:37 UTC made three
`dependencies` requests about Manifest service, derivation, and persistence.
Their retained responses contain seven, six, and two relationships, respectively,
with explicit partial status and omissions. A separate 02:47:32 impact request
about Anvil's Manifest frontend link returned four relationships. Thus usage
is not zero across the team; delivery does not prove that those relationships
changed an answer or improved efficiency.

Those examples are in sessions `01a09d82-8731-73b2-8c07-58b872b7feac` at
tool-call line 167 and `01a09dcd-7cf6-75b2-980f-885d52abbd65` at line 101.
Workspace labels in the scan are session working directories, not necessarily
the repository targeted by a tool call.

## Why current product stats cannot answer the question

`IndexStore.log_retrieval` records repository, symbol, timestamp, kind/language,
and bytes, without tool/intent, parent request, client/session, or run purpose
([implementation](../../src/loci/storage/index_store.py#L520)).
`get_session_stats` aggregates get and outline events; it has no graph/explore
counter ([implementation](../../src/loci/storage/index_store.py#L543)).
Graph and explore services compute responses without a corresponding usage
event ([graph routes](../../src/loci/service.py#L944),
[explore](../../src/loci/service.py#L1181)). Type-context supporting source can
be recorded as ordinary gets, losing its relationship origin
([implementation](../../src/loci/type_context.py#L330)).

The installed Codex skill resolves to this checkout's guide. Its main route
foregrounds outline/search followed by get; relationship retrieval is an
additional choice ([guide](../../skills/loci/SKILL.md#L39)). The bootstrap
example is narrower still ([README](../../README.md#L886)). Existing instructions
already require deferred-tool discovery; this run skipped it. Adding another
instruction alone is not an established fix.

Counting only names beginning `loci_graph_` is insufficient:
`explore` with dependency/type-dependency/impact intents and
`get(include_type_context=true)` can consume relationships. Conversely,
`explore(intent="locate")`, graph-health counters, and background graph
indexing do not establish relationship consumption.

## Disposition

There is a demonstrated discovery failure, a plausible default-routing
weakness, and a confirmed measurement gap. One fresh run establishes a concrete
failure mode, not its frequency or a model-wide comparison. The private Claude
repository and its runtime were not inspected.

Useful next work is to capture operation, explore intent/type-context flag,
outcome, delivered relationship count, and host/session/run purpose; then
repeat bounded ordinary tasks with known tool visibility and compare answer
quality and retrieval cost. Graph invocation counts alone are not the success
criterion. No runtime, skill, telemetry, or graph-engine change was made in this
investigation. No existing completed Objective was reopened; no next Manifest
task had been assigned for these candidate follow-ups at the diagnostic handoff.

## Manifest follow-through

Vik subsequently endorsed starting Manifest and reiterated that it carries both
Planning and Implementation. Objective `obj_47c29425d32907d2bde961f1fd313970`
now owns the continued audit, evidence-backed decisions, selected implementation,
and actual-host outcome verification in `/Users/brummerv/loci`. The initial
diagnostic is complete with criterion-associated evidence. At Vik's request,
the original eight Tasks have been recursively decomposed into 32 Task nodes:
seven parent branches and 25 executable leaves, of which only the initial
diagnostic is complete. The Objective remains in Planning.

The decomposition separates prior-evidence reconciliation, case truth,
observation contracts, host/role conditions, observer preflight and the schedule
freeze. Discovery and usefulness share one execution schedule. Findings lead to
concrete proposals and selected measurement, discovery, guidance and installed
delivery work, followed by source review, actual-host checks, ordinary-task
comparison and outcome acceptance. Permanent product telemetry and any new
graph-engine repair remain decisions; the graph does not prescribe them.

The next Planning leaf is `task_303dc49a495c13bc068b1fdb71431b10`, reconciling
prior evidence with the adoption question. No new research or implementation
leaf was marked complete merely by decomposition. Readback verified parentage,
sibling order, dependency membership and preservation of the initial completion;
independent bounded review found no material omission. The canonical Manifest
owns current work and status. Completing the audit alone will not complete this
Objective.
