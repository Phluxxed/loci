# Explicit exploration workflow selection

This intervention belongs to W2.5.1.3
(`task_2727497172e9ceadea5ab07538da0b31`). It defines and checks a routing
instruction before any new measurement. It is not a frozen trial or a claim of
agent adoption or improved outcomes.

The completed availability trial at `624f58a` remains rejected and immutable.
Its candidate used `loci_explore` in 3/51 attempts and 0/9 maintained attempts.
Those results establish an exposure gap. They do not establish why the model
chose the other tools, or how exploration performs when used on maintained
tasks.

## Intervention

Both new conditions expose the same existing 14 retrieval tools, including
`loci_explore`, plus the same three source-free host helpers. Both use production
source `36f5e2b1662c2d6bbe2449c3189430469e8c013f`, extractor 25, with automatic
get expansion disabled. This compares availability against availability plus
explicit routing; it does not isolate a tool-schema or semantic-engine change.

A receives the original common prompt followed by the original case prompt.
B receives the exact [selection policy](selection-policy.md), one additional
newline, and that complete unchanged A prompt. The policy applies the same
task-shaped rule throughout: start typed-contract and heritage work with
`type_dependencies`; trace a call target first when the question requires it;
inspect omissions and obtain missing evidence through focused fallback reads.
The policy uses no answer gold, hidden dependency names, case-specific seed IDs
or retained model answers. Prompt hashes for all 17 cases are published in
`prompt-manifest.json`. Policy bytes are real model input and count in full.

The four call-target fixtures are `exported_arrow`, `default_identifier`,
`named_function_control` and `inline_default_control`. The other thirteen cases,
including all three maintained tasks, take the initial type-dependency branch.
This branch classification comes from the original question text and is fixed
before new provider outcomes. The agent still supplies its own query, selects
any returned IDs, inspects evidence and decides which fallback reads are needed.

The instruction is local to this evaluation. Installing it as general Loci
guidance or changing the shared runtime requires measured delivery evidence.

## Verification boundary

The preparation check must retain two actual offline Codex/MCP round trips,
one for each routing condition. They must show identical tool-schema hashes,
the exact expected prompt arriving at the host request, one real native
exploration response reaching the next request byte for byte, and complete
source/call accounting. The loopback server scripts the tool call; no provider
model chooses it. This proves prompt and tool transport, never model adoption.
Focused tests also reject prompt tampering and preserve the original prompt as
an exact suffix across all cases.

## Requirements for a subsequent measured trial

A new measurement must use a separate published freeze before provider calls.
Revalidate the current host, authentication mode and model catalog before that
freeze; the offline preparation uses the archived v2 catalog without provider access.
Retain the original 17 cases, snapshots, gold, model/reasoning controls, budgets,
three repetitions, alternating AB/BA order and serial 102-attempt schedule.
Preserve every attempt and independently replay source, relationship, usage and
cost evidence. All original numerical quality, recall, useful-call, output,
input and latency gates remain unchanged. Report the result of every gate.

Audit every effective prompt against its declared hash and both conditions
against the same B tool schema. Bind the injected policy to the measured runner
and retained provenance; a preparation-only instruction is insufficient.
Report first repository retrieval, all `loci_explore` calls and intents,
successful versus rejected deliveries, returned anchors, omissions and fallback
reads per attempt. Helpers and failed calls retain their full cost. Include
policy input in provider token totals, with cached input reported separately.

Establish maintained-task exposure only if all nine candidate attempts begin
repository retrieval with `loci_explore(intent="type_dependencies")` and receive
a source-bearing result containing the requested target anchor. Missing,
rejected or wrong-target results fail this exposure check even if a call was
issued. A later fallback may recover the answer; it does not erase the initial
miss. Report the thirteen-case branch compliance and four call-target controls
separately. This additional exposure check diagnoses whether the intervention
was exercised; it does not replace or weaken any existing delivery gate.

If exposure is missed, retain all outcomes and report that explicit routing did
not establish the intended workflow. If exposure succeeds but a delivery gate
fails, report that failure with its evidence. Neither result permits selective
retries, dropping noncompliant attempts, changing gold or thresholds, or an
automatic follow-up experiment. W2.5 acceptance remains open until its delivery
criteria are met. Required multilingual W4 remains outstanding.
