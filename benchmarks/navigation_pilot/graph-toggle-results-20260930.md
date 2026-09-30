# Ember navigation: production graph on versus off

## Result

**Both answered the requested behavior correctly, with essentially the same
elapsed time. Graph off reduced total tokens but increased uncached input and
required more navigation calls.** This pair does not establish that disabling
enrichment improves overall efficiency, or that Loci beats ordinary Codex.

Graph on took 143.8 seconds; off took 144.5 seconds. Off used 8.4% fewer total
tokens, 5.4% more uncached input, and 26 Loci calls versus 18. Both found and
cited the five required implementation owners. The graph supplied additional
source and static relationships; actual model reliance cannot be determined.

## Matched setup and validity

The completed run is
[loci-graph-toggle-20260930-161902](/Users/brummerv/phluxxed/tmp/loci-graph-toggle-20260930-161902/result.json).
Both arms used production `9655a287`, Ember `85969df8`, GPT-6.1 Sol / high, the
original frozen task and oracle, a fresh read-only session and a 300-second cap.
Production's internal `RetrievalRuntime(graph_enrichment=True/False)` was bound
at server startup; normal tool arguments did not select the condition.

Both passed the strict filesystem canary and tool inventory checks. Target and
serving archive hashes, instruction hashes, and actual tool descriptors matched.
Re-reducing the raw journals exactly reproduced the stored telemetry. Both root
turns completed with known usage, no capture or usage errors, no child agents,
no compactions and no source changes. Each index contained 66 source paths,
zero store paths and no pending catalog mutation. All 44 Loci calls succeeded.
Original receipts remain untouched; assessment artifacts are separate.

Stores started cold. **Off still builds and loads production's graph index for
freshness and reads.** It disables traversal and related enrichment, preserving
the shared anchor/source baseline, ownership, paging and packet schema. It is
not a comparison against an implementation without graph machinery. The new
source-context branch removes more work and is a separate experiment.

## Measurements

| Measure | Graph on | Graph off |
| --- | ---: | ---: |
| Requested behavior correctly explained | Yes | Yes |
| Required implementation owners cited | 5 / 5 | 5 / 5 |
| Turn elapsed time | 143.814 s | 144.549 s |
| Input tokens, including cached | 461,346 | 422,558 |
| Cached input tokens | 394,624 | 352,256 |
| Uncached input tokens | 66,722 | 70,302 |
| Output tokens | 4,180 | 3,914 |
| Reasoning tokens, within output | 475 | 370 |
| Total input + output tokens | 465,526 | 426,472 |
| Loci retrieve / read calls | 6 / 12 | 11 / 15 |
| Shell operations | 6 | 5 |
| Total shell + Loci operations | 24 | 31 |
| Shell operations returning nonzero | 1 | 0 |
| Loci failures | 0 | 0 |
| Returned relationship records | 60 | 0 |
| Distinct evidenced relationships | 54 | 0 |
| Traversed edges across retrieve calls | 694 | 0 |
| Eligible edges considered across calls | 1,366 | 0 |
| Captured MCP result JSON bytes | 165,251 | 138,768 |
| Captured shell output bytes | 88,252 | 64,224 |
| Median observed retrieve duration | 1.356 s | 1.094 s |
| Median observed read duration | 1.081 s | 1.043 s |
| Sum of observed Loci durations | 22.444 s | 28.995 s |

Off was 0.735 seconds slower, a 0.5% difference. Its per-call median was lower,
but its additional calls increased the summed tool duration. Durations can
include queuing and overlap; they are not isolated engine timings.

Cached input is part of input, and reasoning is part of output. The reduction in
total tokens was dominated by cached input: off used 42,368 fewer cached tokens
and 3,580 more uncached tokens. **Lower total usage does not establish lower
cost.** Provider cache warmth was uncontrolled; account pricing and plan usage
are not inferred. Edge totals include repeated traversal across requests.
Captured bytes are not unique source bytes or proven provider context delivery.

## Answer quality and grading qualification

A fresh independent reviewer read anonymized answers and the five implementation
owners without condition labels, navigation traces or metrics. Both correctly
explained approval reconciliation, blocked display, completion to ready, stale
stored-ready chat actions, the dependency guard before execution, and refusal
without graph writes or run receipts. Neither had a critical contradiction.
Both distinguished the interactive conversational Codex connection from starting
a Work execution thread. Normal blocked/ready actions were implied by their
correct rule that only stored-ready Work gets a run action.

The reviewer assigned **5.5/6 to each under a literal reading of the frozen
oracle**: both omitted the additional statement that explicitly reconciling the
stale graph would repair ship to blocked. That repair was included in the oracle
but was not requested in the investigation prompt. The earlier three-condition
review accepted the same omission and assigned 6/6. Do not interpret these
scores as a quality difference between runs: both reviewers found the requested
trace correct. We retain the stricter score and its reason. Auxiliary test claims
in the off answer were outside the blinded implementation corpus and were not
needed or verified for its correctness finding.

Answers: [graph on](graph-on-answer.md), [graph off](graph-off-answer.md).

## Observed routes

| Condition | Route |
| --- | --- |
| Graph on | File discovery → broad retrieve → proposals → source search → graph/status/execution/chat retrieves → continuations → tests and line-numbered source checks |
| Graph off | File discovery → broad retrieve → proposals/mutations/status/context/runs/chat retrieves → continuations → graph/execution retrieves → more continuations → tests and line-numbered source checks |

On queried fewer files explicitly and needed three fewer continuations. Off
first visited mutations, context and runs before graph and execution. On also
used an early shell search that named the relevant files and functions, so fewer
Loci calls cannot be assigned solely to graph guidance. Both used direct source
reads to establish the behavior. The one on-arm shell failure was an initial
file-pattern search with no matches; later inventory succeeded. Neither arm ran
Ember or its tests.

The [ordered navigation](/Users/brummerv/phluxxed/tmp/loci-graph-toggle-20260930-161902/assessment/navigation.md)
retains every command and MCP call with completion offsets and delivered files.
The [machine comparison](graph-toggle-completed-run.json) retains exact values
and raw journal hashes. Full results and source spans remain in the per-arm
assessment traces outside the repository.

## What the graph actually contributed

A separate navigation audit found one concrete use of graph-selected context:
the execution-file retrieval selected the related `RunStore` in `runs.py` and
returned a source reference; the agent subsequently read that exact reference.
It did not cite `runs.py` in its final answer. This is evidence that the agent
followed an enrichment result, without establishing an answer-quality benefit.

The 54 distinct relationships comprised 31 imports, 14 references, four type
uses and five calls. They included useful module links: proposals and status
importing graph, chat importing proposals/status/execution, and refusal tests
importing execution/chat. The five call records concerned benchmark acceptance
setup, proposals' CLI entrypoint and status timestamp helpers. None represented
the central approval-to-reconciliation, transition-to-reconciliation, or
run-to-claim-to-dependency-guard chain. Both agents established those behaviors
from actual source. Absence from delivered packets does not prove absence from
the full index.

On received MCP source content from 21 distinct files versus 14 for off; counting
shell source content as well gave 25 versus 18. These include excerpts and search
matches, exclude file listings, and do not mean every file was fully read or
attended to. Both traces contain complete continuations for the five central
owners. All retrieves were partial: on reported graph budgets and unresolved
or unsupported relationships; off reported previews and broad-query ambiguity.
The records' `proof: complete` describes each supported static relation, not
complete dependency coverage.

All delivered records are retained in
[graph-on relationships](/Users/brummerv/phluxxed/tmp/loci-graph-toggle-20260930-161902/assessment/graph_on-relationships.json).

## Relation to the earlier vanilla observation

| Observation | Elapsed | Total tokens | Uncached input | Requested trace correct |
| --- | ---: | ---: | ---: | --- |
| Earlier vanilla | 149.1 s | 199,889 | 51,251 | Yes |
| Earlier production graph on | 238.4 s | 534,767 | 83,973 | Yes |
| Earlier new source context | 209.5 s | 391,489 | 69,385 | Yes |
| Latest production graph on | 143.8 s | 465,526 | 66,722 | Yes |
| Latest production graph off | 144.5 s | 426,472 | 70,302 | Yes |

The earlier rows are **historical references, not fresh arms in this pair**.
The latest graph-on run was 39.7% faster than its earlier observation despite
using the same production version and task. This makes the original timing
ranking weak evidence of a stable speed advantage. Vanilla still used fewer
total and uncached input tokens than either latest Loci run, but one observation
per condition cannot establish a general efficiency advantage. The full
[earlier comparison](results-20260930.md) is preserved.

## Judgment

The graph is unnecessary for answering this particular task correctly. Its
delivery coincided with fewer queries and lower uncached input, while off
produced smaller outputs and lower total tokens. This is mixed evidence of
utility, not a demonstrated overall win for either setting.

These observations do not yet show that Loci earns its place over ordinary
Codex for the smallest useful context goal. They also do not justify attributing
all production overhead to traversal: both toggle arms retain graph indexing,
loading and freshness, and both perform substantial source paging. Keeping the
source-context work isolated while judging its source selection and reading
ergonomics remains a reasonable direction. No further product change or model
campaign is part of this completed pair.

There was one task and one episode per condition, fixed on-then-off order,
uncontrolled provider caching and unconstrained navigation choices. Ember has
93 tracked files and substantial cross-module behavior; larger repositories and
other task types remain untested. Delivered relationships do not reveal model
reliance or prove that missing relationships are absent from the complete graph.
