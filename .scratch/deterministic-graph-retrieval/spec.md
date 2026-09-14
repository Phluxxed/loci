# Deterministic graph retrieval: delivery direction

Status: selected direction; public contract and implementation remain unfinished

Date: 14 September 2026. Task authority: the existing Manifest Objective,
“Make Loci relationship retrieval effective in ordinary agent work”. This is
supporting design evidence, not a second task tracker.

## Required outcome

Normal Loci context retrieval must run a deterministic graph selection and
traversal policy. An agent supplies its query, repository and any known source
identity; it does not choose whether graph traversal happens, an exploration
intent, relation families, direction or hop strategy. Vik explicitly selected
this direction after reviewing the ordinary-use audit. Prompting the agent to
make better routing choices is insufficient.

The enforceable guarantee is inside Loci. Loci cannot force an external host to
invoke it instead of a shell. Installed host delivery and actual ordinary use
therefore remain separate acceptance requirements, and skipped Loci use must
remain visible in the outcome report.

## Recommended shape to make concrete in W1.7.2.1

Expose one normal context-retrieval operation. Keep maintenance and low-level
graph diagnostics in an operator-selected compatibility/diagnostic surface,
outside the normal agent workflow. Exact source hydration remains narrowly
available for inspecting or editing already-located source; it must not become
another search-and-navigation route that bypasses normal context retrieval.
The operation names, exact input fields and compatibility migration are not
frozen by this direction document. Traversal limits and selection policy belong
to maintained host configuration, rather than optional model-selected knobs.

The normal operation owns this sequence:

1. Refresh the named repository and resolve bounded starting candidates from
   explicit identities or stable source/symbol matching. Ambiguous candidates
   remain distinguishable; never fabricate a unique identity from a name.
2. Select eligible stored relationships using code-owned rules based on node
   kind, relation semantics and resolution. Include bounded incoming and outgoing
   context where supported. Query terms may deterministically rank candidates;
   they must not silently classify a natural-language intent that switches
   traversal on or off. No model call is needed to select the traversal policy.
3. Traverse and rank with fixed family priorities, stable tie-breaks, cycle
   handling and bounded work. Determine how imports and file/package/crate
   anchors connect to declaration context. Explicitly resolve family allocation
   and deeper continuation before coding; simply concatenating today's explore
   modes is not the contract.
4. Assemble anchors, related source and exact relationship proof together.
   Enforce complete-result and source budgets and report unsupported,
   ambiguous, stale, unavailable and clipped evidence. A legitimate zero-edge
   result is not an exhaustive absence claim.
5. Report the policy identity, traversal outcome, delivered relationships and
   omissions sufficiently for deterministic verification and existing audit
   accounting. Do not count internal traversal as extra public tool calls.

For the same source snapshot, request and policy configuration, semantic
selection and ordering must be repeatable. Transport identifiers and timing
are outside that repeatability claim. No repository-specific names, audit case
IDs, required-answer spans or golden answers may influence runtime policy.

## Existing implementation to reuse

`src/loci/service.py::explore` already loads fresh graph context and delegates
to `explore_context`. `src/loci/exploration.py` supplies bounded selection,
proof/source assembly and omissions. Existing graph storage/resolution and
generic traversal supply proven relationships. The new normal operation should
reuse these mechanisms behind a smaller interface.

The current `loci_explore` still requires an intent at the MCP surface. `locate`
has no relationships; `dependencies` is type-oriented for TypeScript, Python,
Go and Rust, with additional JavaScript dependency support; `impact` follows
known static dependents. These are not a complete deterministic normal-retrieval
policy. Supported stored calls, references, imports and types need an explicit
composition contract. Unsupported dispatch remains unsupported; this effort
does not assume a new resolver or complete runtime call-flow reconstruction.
In particular, current exploration filters call/reference dependencies by
language and does not pack import records as ordinary exploration proof. Reuse
stored edges while implementing the missing selection and proof assembly;
do not describe this as only changing tool descriptions. Independent source
review identified `src/loci/graph/anchors.py` as the existing stable anchor
ranking owner and the traversal/record helpers in `src/loci/exploration.py` as
the composition seam. Exact weights and allocation still require the first
contract task.

Owners to inspect and edit as required: `src/loci/exploration.py`,
`src/loci/service.py`, `src/loci/mcp_server.py`, `src/loci/mcp_output_models.py`,
the graph traversal modules, canonical `skills/loci/` and maintained installer/
launcher surfaces. Preserve unrelated working-tree changes and the sole
canonical Manifest.

## Delivery sequence in the existing tasks

- **W1.7.2.1 — Freeze the deterministic retrieval contract.** Resolve the normal
  request/response, candidate ambiguity, eligible relation families, priority,
  budgets, continuation, exact hydration and default/diagnostic migration.
  Define concrete expected packets on independent fixtures and acceptance
  thresholds before product implementation. Contract choices remain unfinished.
- **W1.7.2.2 — Implement deterministic context assembly.** Wire the chosen
  structural policy into the existing graph/source machinery, including honest
  no-edge and partial results, with no intent or opt-in dependency.
- **W1.7.2.3 — Deliver the normal MCP interface.** Register the graph-backed
  normal operation and narrow hydration; isolate compatibility/diagnostics so
  an agent does not choose among alternative retrieval implementations.
- **W1.7.2.4 — Verify deterministic retrieval end to end.** Test the normal
  public operation through service/MCP, including renamed symbols, decoys,
  ambiguous matches, cycles, high fan-out, stale data, budgets and unresolved
  semantics. Graph helper tests alone cannot pass this task.
- **W1.7.1 / W1.7.3 — Deliver and activate the installed workflow.** Align the
  owned registration, tool descriptions and instructions with the implemented
  default. Verify the actual primary and delegate surface after any required
  restart. Do not substitute a standalone client for a stale actual host.
- **W1.6 / W1.8 — Account for delivery and establish practical value.** Reuse
  and, where needed, version the existing observer/readout, review the change,
  verify actual hosts, run the reserved ordinary post-change block and publish
  its complete outcome. A new telemetry platform or dashboard is not selected.

The two demonstrated catalog/source-proof defects remain supporting delivery
work, with their own bounded acceptance from the audit proposals. They are not
the main retrieval redesign. No further graph capability expansion is assumed.

## Acceptance and stopping boundary

The first gate is deterministic: ordinary retrieval executes the specified
policy without model-selected flags, delivers expected source-backed
relationships for supported fixtures, and preserves uncertainty, freshness and
budgets. Validate retained exact-source access and intentional compatibility.

The second gate is actual-host delivery: the default registered operation,
installed guidance and runtime identities agree, and a normal retrieval call
through the real host returns the required evidence. A directed graph diagnostic
or tool-catalog listing alone is insufficient.

The third gate is ordinary-task value. Preserve the eight original ordinary
outcomes, four visibility diagnostics and two known-answer primary checks.
The existing ten reserved post-change rows remain unrun. Freeze the new engine,
catalog, installed guidance, observer adapter and accounting before execution;
keep fixed prompts, task sources and rubrics. Use a separate version if their
semantics must change. No graph reminder, replacement attempt or baseline
rescore may manufacture a pass. Do not launch extra model trials by default.

Report source-backed correctness, relevant relationship delivery, total calls,
input/output cost and latency together. Define numerical value gates before
the post block, without weakening historical criteria. More traversals alone
cannot pass. A negative or inconclusive experiment is a valid investigation
result; it does not establish successful product adoption. Fix only demonstrated
remaining failures or make an explicit scope decision, rather than rerunning
until a favourable result appears.

## Evidence

- `docs/reviews/2026-09-14-ordinary-graph-adoption-results.md`
- `docs/reviews/2026-09-14-adoption-correction-proposals.md` (earlier routing
  deferral is superseded by Vik's selected direction above)
- `skills/loci/SKILL.md`
- `skills/loci/references/graph-navigation.md`
- `benchmarks/comparisons/ordinary-adoption-v1/post-change-template.json`

This document records the way forward. It does not mark the new contract,
implementation, installed activation or post-change acceptance complete.
