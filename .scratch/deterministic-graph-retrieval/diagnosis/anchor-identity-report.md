# Named-identity anchor repair diagnosis

The retained request was reproduced verbatim against the intact 638-file
`/tmp/anvil-source-tasks-20260914/t16` source:

`captureCommandResult work context binding accepted type imported public contract`

Before the repair, inferred selection returned `WorkContextBinding`,
`WorkContextBindingView`, and the work-context planning document. The query's
case-bearing `captureCommandResult` token was treated like every other term, so
the exact code declaration lost to candidates accumulating four broad terms.

`anchors.py` now detects case-sensitive camel/Pascal or underscore-shaped query
words and gives an exact non-Markdown declaration-name match a corpus-derived
score bonus above the maximum regular score. The bound follows the existing
four-contribution, weight-8, phrase-16, and 1.25 coverage maxima. Duplicate exact
names remain separate candidates and use the existing score/file/ID tie order.
Ordinary lowercase natural-language and Markdown selection keep their existing
path. This is intentionally limited to ASCII case-bearing or underscore-shaped
identifiers; it does not claim arbitrary plain or Unicode name recognition.

The anchor correction alone selected the function but did not deliver the
required binding proof: a body-call bundle consumed the remaining output budget
before the function's signature type. The final scheduler repair uses existing
static edges only. It finds non-native declaration targets connected to at least
two selected anchors through supported type-family edges, orders them by the
selected anchor-index tuple and target ID, and stages each bridge's incident type
proof consecutively before ordinary queues. Calls to the same target are not
promoted. Existing explicit-anchor direct-edge priority, proof validation,
family queues, and all node/neighbor/hop/item/evidence/output limits remain.

The repaired full normal packet anchors `captureCommandResult`,
`WorkContextBinding`, and `WorkContextBindingView`. Its first two relationships
are the exact `captureCommandResult -> CaptureCommandResultOptions` type use and
the complete import-resolved `CaptureCommandResultOptions -> WorkContextBinding`
type use. The response is partial and non-exhaustive, with 77 output-budget and
other reported omissions. It delivers 3 relationships, 3,099 evidence bytes,
and a 16,251-byte native envelope under the unchanged 8,192/16,384-byte limits.

Verification: the targeted anchor, retrieval, and normal-MCP suites passed 49
tests. The `runBrowserCli` control remained 14,417 bytes with its forward call
and reverse caller/reference proof. The `renderActiveTask` control remained
16,117 bytes with forward/reverse calls, type proof, and imports. All 638 source
files matched the frozen manifest after replay. No provider trial ran and no
frozen campaign or source file was modified.

The complete canonical after-envelope is retained as
`anchor-identity-after-envelope.json`; its source records allow independent
validation of every proof source ID. Replay it from the repository root with:

`.venv/bin/python .scratch/deterministic-graph-retrieval/diagnosis/anchor-identity-replay.py`

The exact targeted test command was:

`.venv/bin/pytest -q tests/graph/test_anchors.py tests/test_retrieval.py tests/test_normal_mcp.py`

The original before-envelope remains frozen in
`benchmarks/comparisons/ordinary-adoption-repair-binding-v1/runs/binding-repair-01/observation.json`
under MCP item `exec-87201109-c4e7-4bcc-a7ec-14ed83f3f9fb`. The compact
machine-readable comparison and checks are in `anchor-identity-replay.json`.
