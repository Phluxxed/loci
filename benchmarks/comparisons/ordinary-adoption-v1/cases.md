# Ordinary task cases

W1.2.2 selects four tasks from one maintained TypeScript repository, Anvil,
commit `53bf29e60cece2335aa39fe301935a07e8e8d4e4`. The snapshot contains 638
tracked files and preserves its normal repository instructions. This is a local
adoption check on cross-module maintainer work, not a multilingual or model-wide
benchmark. One larger repository is sufficient for that bounded question.

[cases.json](cases.json) is evaluator-only: it contains the ordinary wording,
independently inspected answer facts, negative/uncertainty expectations,
acceptable non-graph routes, exact source-span hashes and all snapshot file
hashes. Two independent source assignments supplied the facts; the primary
checked the relevant declarations, imports, call sites and persistence source.
All 18 referenced source spans were checked against the frozen archive.

| Case | Required outcome | Relationship opportunity |
| --- | --- | --- |
| Continuity checkpoint/retry/clear | Trace the bound handler into checkpoint and persistence behavior; explain same-key retry and clearing. | Cross-module handler, service and store identities; distinguish a test wrapper with the same function name. |
| Tool-result binding identity | Identify the actual imported binding contract through its barrel and distinguish the public view. | Imported type and re-export path; similarly named declarations have materially different fields. |
| Browser CLI production entrypoint | Identify the immediate production caller and the arguments/dependencies passed through the browser branch. | Incoming static call and re-export route; test callers do not answer the production question. |
| Active-task renderer | Explain absent/present output and shown fields. | Direct-symbol control. A sufficient exact read is fully successful without graph retrieval. |

Each ordinary prompt asks for behavior and source evidence without naming Loci,
graphs, the audit, expected files, or a preferred navigation route. Named public
features/functions are legitimate user context, not an answer key. The renderer
intentionally names its small function because direct reads are sometimes the
right route. No answer format beyond a useful prose response is enforced.

The source archive is made with `git archive` of the stated commit; its SHA-256
is `e919302908ba8dfee2ee8ee055fd4a7463a37e94a71d35d2ecda7abe95463c5e`.
The initial materialization is local at
`/tmp/loci-adoption-audit-20260914/anvil-source`. W1.2.6 assigns each attempt a
separate physical copy, verified against the file hashes before and after work.
Concurrent edits in the live Anvil checkout do not enter these copies.

The task agents receive only their single ordinary prompt, source root and
normal bounded read-only assignment. They start without conversation history.
Evaluator artifacts and prior answers stay outside those roots and are neither
included nor referenced in the task assignment. The shared host's filesystem
permissions are not per-agent isolation: exclusion is enforced by the bounded
assignment and checked against the retained read/command ledger. Access to an
answer key or previous result invalidates the attempt and remains in its
scheduled denominator. Do not claim a filesystem sandbox that the host does
not provide.

Relationship opportunity is defined by source facts, independently of a tool
name. A source inspection during case selection also established the browser
call site with a partial, non-exhaustive impact packet; that was evaluator work,
not an ordinary agent outcome. W1.4.1 owns the controlled capability/budget
assessment for the complete frozen workload. Unsupported or partial graph
coverage is a valid finding, and additional exact reads are legitimate.

The schedule, repetitions and cost/quality rules are fixed separately in W1.2.6
after the passive observer has passed its preflight. Selecting these cases does
not claim any new adoption or efficiency result.
