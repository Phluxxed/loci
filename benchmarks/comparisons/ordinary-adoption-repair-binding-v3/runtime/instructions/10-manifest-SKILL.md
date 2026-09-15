---
name: manifest
description: Plan and track accepted project work in Manifest from the conversation, shaping its Planning graph and carrying the same Tasks through Implementation.
---

# Manifest

Use the existing conversation and project evidence to put accepted project work
into one repository-owned Objective graph. When Vik accepts a project direction
or asks to plan or carry out project work, create or resume its Manifest
Objective without requiring him to name the skill. Questions and exploratory
reviews retain their requested scope; tentative ideas remain uncommitted until
Vik accepts the work or asks to plan it.

Invocation creates or shapes Planning. Implementation begins only on Vik's
explicit direction for this Objective, either in conversation or through the
frontend's Start Implementation control. Existing explicit authorization carries
forward for the same Objective until Vik withdraws it; a stored Implementation
phase by itself is not evidence of that authorization. Creating, viewing or
finishing decomposition leaves Planning in place. Once work is active, follow
its graph throughout the accepted assignment and preserve its identity on resume.

## Establish the Objective

1. Recover the intended project, outcome, decisions, constraints, accepted scope,
   and unresolved questions from the conversation and relevant project evidence.
   Prefer current user direction and live files over remembered state. Ask only
   for missing information that changes the target or consequential work meaning;
   do not make Vik repeat context or complete an intake form.
2. Resolve the Git worktree of the thing being built. This is the target repository,
   even when Anvil itself is installed elsewhere. Reuse a known Objective identity
   from the current assignment or Continuity. Otherwise inspect the target's
   `.manifest/objectives/` files for an existing matching Objective. Reuse a clear
   match; resolve genuinely ambiguous targets before writing. A request for a new,
   distinct Objective may create another file in the same repository.
   Preserve an accepted completed Objective when Vik later requests a separate
   enhancement. Required work omitted from the same assignment belongs in its
   existing Objective, with completed evidence retained.
3. Discover the registered `anvil_manifest_create`, `anvil_manifest_orient`,
   `anvil_manifest_inquire`, and `anvil_manifest_change` tools and use their live
   schemas. Targeted calls carry the absolute repository root and Objective ID.
   If the tools or target Git repository are unavailable, report that concrete
   blocker; keep the gathered context ready without inventing a substitute store.
4. For existing Work, orient and inquire before changing it. For new Work, create
   the Objective in Planning and retain its returned ID. A failed or invalid load
   remains visible for repair; never silently replace it with a new Objective.

This step is done when the intended repository and Objective are unambiguous and
the current graph is loaded, or the new Planning Objective has been created.

## Shape the Planning graph

Decompose the work required to deliver the Objective through semantic changes.
Carry its actual structure into ordered Workstreams and recursive Tasks, keeping
every agreed requirement and its meaningful parentage. For each Task, establish
what it should achieve, the approach, dependencies, relevant findings and how
it will be verified. Record that planning in its outcome, details, relationships
and completion criteria, to the depth the work needs.

These are the same Tasks that will execute in Implementation. Planning prepares
their delivery; it does not normally create a set of completed planning Tasks
that must later be replaced by a delivery plan. A review or proposal can itself
be a Task when that artifact is part of the requested outcome.

Keep tentative ideas and open decisions explicitly identified in relevant Work
details. Add proposed decomposition as Planning material without claiming Vik
has accepted it. Do not invent certainty, evidence, dependencies, or completion.
A leaf identifies work at its current execution depth; it does not prove the
plan exhaustive or the work delivered. When a Task's planning and required
decomposition are complete, record `decompositionComplete: true`. That makes it
white in Planning. Required descendant decomposition determines parent Planning
state; a parent marker cannot stand in for planning its children.

Actual delivery completion is separate: criterion-associated implementation
evidence earns the tick in Implementation and rolls up through required
descendants. A fully planned, unimplemented Task has completed decomposition
and no delivery completion. Changing phase or surface preserves both facts.

Objective completion requires Vik's explicit acceptance. Include a required
final Task for that acceptance and leave its delivery completion empty until
Vik states that the Objective is complete or accepts the entire delivered
outcome. Preserve his actual statement as its criterion evidence. This keeps
the derived Objective rollup open while work is ready for review. Ordinary
Task completion and authorized execution remain agent-owned; this rule adds
no per-Task or per-experiment approval gate.

Use structure for grouping and sibling order for plan order. Dependencies join
executable leaf Tasks only within the same Workstream subtree and mean that the
prerequisite must be complete. An outside condition belongs in an External
Blocker. A separate delivery-stage plan is not a replacement for the work graph.

After the semantic changes, read back the Objective and compare its full recursive
structure with the requested outcome, corrections, and unresolved findings.
Represent required follow-through as concrete work with outcomes and completion
criteria in this graph. Identify the actual delivery surface for each required
finding: product code, tool contract, or installed operating instructions as
applicable. Workflow corrections need their instruction changes represented
alongside the cases that verify them. Keep optional recommendations identified
as optional. Check each proposed Task's outcome and criteria against the current
contract; preserve an unresolved meaning as an open decision rather than filling
it with an invented rule.
A completed review satisfies a review-only assignment. When the assignment also
requires improvements, its findings must lead to the warranted delivery and
verification work before the graph represents that assignment. Preserve the
finished review evidence. Summarize the supported graph and consequential open
decisions; shaping may remain incomplete without a separate readiness record.

Show Vik the live Objective using the MCP result's `frontend`. When its status is
`available`, return its verified `url` directly. The primary handles this routine
step. The qualified URL identifies both repository and Objective; one frontend
can serve targets from different repositories.

When `frontend.status` is `unavailable`, retain the successful graph result and
its identity. If a running frontend's custom origin is known, supply it as
`frontendOrigin` to `anvil_manifest_orient`. Otherwise use the normal launcher
when needed: `manifest --repository <root> --objective-id <id>`, or
`node /Users/brummerv/phluxxed/anvil_redux/bin/manifest.ts` with the same flags.
Keep it running and reorient using the concrete origin it prints. Use the
requested port when supplied; preserve occupied listeners. An unavailable view
is a viewing limitation, not a reason to repeat creation or a graph change.

During MCP upgrade, if the loaded schema lacks `frontend`, construct
`/objectives/<id>?repository=<encoded-root>` against the known frontend origin
with URL/URLSearchParams. Check the corresponding qualified `/api/objectives/<id>`
in memory with a bounded HTTP request, requiring its returned `target` to match
both identities before presenting the link as verified. Link lookup needs no
temporary files or shell cleanup. A fresh MCP session enables the new contract.

Before reporting decomposition complete, read back the planned Tasks and verify
that their decomposition facts match the planning actually finished, while
delivery completion remains unchanged. Persist a missing decomposition fact
through the semantic tool; prose saying that planning is finished does not
record it. If the tool cannot persist it, report the concrete limitation.

The Planning invocation is complete when the graph contains the supported work,
its recorded decomposition state is accurate, Vik can inspect it, and remaining
decisions are clear. Continue shaping when requested. Phase changes use
`change.phaseChange: { to, userDirection }`; quote or faithfully identify Vik's
actual explicit instruction for this Objective in `userDirection`. Ordinary
`update.set` edits leave phase alone. Completed planning, an agent-authored next
step and authorization for another Objective do not supply that instruction.

If Vik says the Objective is Planning-only or its stored phase is wrong, stop
execution and semantically return that same graph to `planning`, preserving its
Tasks, decomposition and delivery evidence. Read back the saved phase before
reporting correction. The frontend's Return to Planning control performs the
same correction. A Planning presentation URL changes only the view and cannot
repair an Implementation-phase graph. If the loaded MCP schema predates
`phaseChange`, use the current frontend phase control for the authorized
correction or report that the MCP session needs refreshing; do not claim a
presentation change fixed stored phase.

## Execute the agreed graph

When implementation is authorized, orient against the current graph and execute
those same Tasks using their recorded planning and new relevant information.
Supply the agreed executable Task's ID as the session's `currentTaskId` when
calling tools that project Current. Before following derived Next or Available
Work, check whether Vik's requested assignment still has an unmet requirement.
Select work that addresses that requirement. A whole-Objective assignment
continues across its Tasks; a finished bounded correction can return with the
wider Objective open and its existing authorization preserved. Where the graph
leaves consequential alternatives, agree the choice with Vik. Phase and Task
facts determine available execution; they do not expand the user's assignment.

Before making newly discovered work a required Task, dependency, or delivery
criterion, identify the existing requirement it is necessary to satisfy and
record that connection in the relevant Task's details. Preserve other findings
as clearly identified follow-ups in relevant Work details. Recording a finding
alone does not authorize its execution or make it required for completion.

Record genuine plan changes, blockers, and evidence through
`anvil_manifest_change`. Keep accepted Work visible: revise or decompose it as
agreed, and use Discontinued with a reason when Vik drops it. Re-read the graph
after a change to confirm the intended result. If discoveries leave required
planning unfinished, update the plan and its decomposition state honestly.
Use repository checks appropriate to the delivered change, then record actual
completion with evidence for every delivery criterion. Completed planning alone
is never that evidence.

Before claiming a Task, Workstream, or Objective complete, compare the whole
relevant recursive subtree with Vik's accepted outcome, unresolved findings,
dependencies, blockers, criteria, and evidence. Complete executable leaves;
Manifest derives parent and Workstream progress. Add missing work necessary for
Vik's accepted outcome before assessing closure, using the requirement connection
above. Apply the global Verification Boundary before selecting further work;
other unfinished Tasks do not prevent reporting a completed bounded assignment.

The primary session is the sole graph writer. Subagents may implement bounded
assignments and report results, but completion and plan changes return to the
primary.

The Objective JSON is the sole durable Manifest graph. Git owns diffs, history,
restoration, and commits; include its changes with the relevant implementation
or plan commit when committing is authorized. Brain and handoff notes explain
the work but do not replace graph facts. Use the semantic tools rather than
directly editing Objective JSON or keeping a parallel execution checklist.

## Resume and hand off

Carry the repository root, Objective ID, optional Current Task ID, Vik's active
requested outcome, its directly relevant completion condition, and this skill's
path through ordinary Continuity or the handoff. Distinguish remaining work for
that assignment from follow-ups. Agent-authored next steps retain this boundary.
On resumption, reopen the existing Objective through orientation and inquiry. Read
the graph's actual phase, Work, and evidence, and recover Vik's explicit
Implementation direction before executing. Current Planning-only direction
overrides an older authorization and requires the phase correction above. If
authorization cannot be established, continue Planning work and resolve that
uncertainty before execution. Reuse the same Objective. A user-requested pause
stops execution and preserves this return point.

When the task is to change Manifest itself, also follow its repository's delivery
authority documents. This skill governs using Manifest and does not replace the
Delivery Invariant or authorize a new Manifest architecture.
