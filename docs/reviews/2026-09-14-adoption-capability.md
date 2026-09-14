# Case-specific graph capability

W1.4.1 uses the independent Anvil source at commit
`53bf29e60cece2335aa39fe301935a07e8e8d4e4`. These are directed evaluator
checks, excluded from ordinary adoption. Requests and complete results are in
[capability-probes.json](../../benchmarks/comparisons/ordinary-adoption-v1/runtime/capability-probes.json).
Every returned explore source span matches the exact source bytes and file hash
([verification](../../benchmarks/comparisons/ordinary-adoption-v1/runtime/capability-source-check.json)).

| Case | Proven capability | Boundary or missing evidence |
| --- | --- | --- |
| Checkpoint retry/clear | Search separates the production function from its same-name test wrapper. Dependencies returns the complete checkpoint function and four type relationships (11,845 output bytes). Explicit outgoing calls returns the workspace resolver and imported mutation-lock function. | The dependencies packet is partial: four not-selected and five unresolved omissions. It does not supply the requested `recordEvent`/`updateCurrent` implementations. The call traversal also does not return those calls inside the anonymous lock callback. No exhaustive call-flow claim is supported. Exact service/store reads remain necessary. |
| Imported binding type | Type dependencies resolves `CaptureCommandResultOptions.binding` to `src/work-context/binding.ts::WorkContextBinding`, with the actual required fields and import-resolved edge. Two total type relationships, 4,372 output bytes. | The view is not selected. The barrel support source is only `export type {` at `src/work-context/index.ts:23`; it omits the rest of that multiline re-export statement. The resolved identity is correct, but the displayed barrel proof is incomplete. This packet cannot by itself establish the full view comparison. |
| Browser entrypoint | Impact returns the import-resolved incoming call from `bin/anvil.ts::main`, exact caller source with arguments and exit-code propagation, and the complete one-line import/re-export path. One relationship, 7,063 output bytes. | Partial and non-exhaustive: alternative-path and hop-limit omissions remain. It does not prove the only caller or any runtime invocation. |
| Active-task renderer | Exact get returns the entire nine-line renderer, sufficient for the ordinary question. | No relationship is required. Avoiding a graph operation is an appropriate route. |

The [checkpoint call request/result](../../benchmarks/comparisons/ordinary-adoption-v1/runtime/capability-checkpoint-calls.json)
retains its exact seed and `calls`/outgoing filters: two returned, zero omitted
neighbors. That is the result of this query, not proof that all source-level
calls have supported graph owners. The explore contract advertises authored
TypeScript types; its additional outgoing definite-call selection is described
for JavaScript. Missing checkpoint call-flow expansion therefore does not by
itself demonstrate a new engine defect.

The currently loaded compact reference behavior was already checked through the
actual host in
[primary-compact-probe.json](../../benchmarks/comparisons/ordinary-adoption-v1/runtime/primary-compact-probe.json):
one resolved record, compact detail, 832 output bytes under the default 16,384
byte limit. The previously delivered response-size fix is not new repair work.

These results establish useful available relationships and bounded omissions.
They do not establish voluntary discovery, answer benefit, efficiency or causal
reliance by the ordinary agents. Those are evaluated from the frozen task runs.
