# Exploration argument and observation repairs

W2.5.1.3.2 (`task_9c2dc19a6ac4044f44a327567cee2f8e`) and
W2.5.1.3.3 (`task_1d5fef5ce1d2a71474d6af6f75fd122b`) are repaired in the
isolated exploration branch. This report records repair acceptance, not a new
provider comparison or delivery qualification.

## Argument boundary

The retained routing-v1 call failed before the adapter because the host sent
explicit `null` for both byte limits while the MCP argument model required
integers. See the immutable
[retained initial failure and recovery](https://github.com/Phluxxed/loci/blob/633ca52c528b51741f6e8e0fc0aa18c7ee21af81/benchmarks/results/typescript-context-routing-v1/anvil_temporal_arguments-r1-B/events.json).

Both the product MCP entry point in this branch and the separately versioned
comparison tool now advertise nullable integer byte limits. Omission and `null`
resolve to the existing defaults: 16,384 output bytes and 8,192 source bytes.
Explicit zero evidence remains zero. Bool, string and float coercions are
rejected. The product entry point retains its existing structured `INVALID_INPUT`
response for an out-of-range integer.

| Surface | Output range | Evidence range |
| --- | ---: | ---: |
| Product MCP entry point | 2,048–262,144 | 0–65,536 |
| Comparison MCP tool | 2,048–32,768 | 0–16,384 |

These are the existing limits. The new comparison normalizer changes only
omitted/null byte defaults before calling the frozen strict normalizer. The
ledger records effective integers; retained host events keep their raw arguments.
Both routing conditions expose the same fourteen repository tools.

## Failed-call observation

The new routing-v2 observer accepts `item.completed` with either `completed` or
`failed` tool status, and retains support for `item.failed` with failed status.
A recognized nonempty native error supplies a known failed delivery: zero source
bytes, full error payload bytes, and false initial maintained-source exposure.
Missing/malformed error evidence and corrupted lifecycle records remain unknown.

The first call remains authoritative. A failed `type_dependencies` call still
records the selected route; later successful recovery can establish eventual
anchor receipt but cannot turn initial exposure into a pass. Every failed and
recovery call remains charged. Existing snapshot hashes, exact source spans,
anchor proof, and clipped-versus-complete distinctions remain enforced.

Raw adapter traces retain `typescript-context-explore-v1`; observation output is
versioned as `typescript-context-routing-v2`. The frozen routing-v1 observer,
inputs, numerical scorer, reports and verdicts were not rewritten or rescored.

## Offline acceptance

[Transport result](byte-limit-transport.json) and its
[pre-run declaration](byte-limit-transport-evidence/declaration.json) retain
source hashes, the fixed case matrix, actual Codex requests, native events,
next-request payloads, adapter traces, accounting and routing observations.
The endpoint is scripted loopback Responses: **11 modes passed, zero provider
calls**. This establishes transport behavior, not model adoption.

| Modes | Result |
| --- | --- |
| Omitted limits; both limits null; maximum valid limits | Requested anchor source delivered and verified against the snapshot |
| Explicit 8,192/512 limits | Output and source stayed within the supplied budgets |
| Null output limit with zero evidence | Default output limit retained; zero source delivered |
| Minimum 2,048 output limit | Bounded output and source delivered; omissions retained |
| Output above cap or below minimum; evidence above cap or negative; coercible string | Five native failures, fully accounted, zero source, known false initial exposure |

The product budget check measures its complete MCP result envelope. Evaluator
metadata is added separately by the existing adapter and is included in measured
payload costs. Every native payload was verified against what reached the next
Codex request.

Focused checks passed: product MCP boundary (12 tests), existing exploration
MCP compatibility (5 tests), new comparison tool contract (24 tests), and new
and frozen observer suites (36 tests): **77 tests in total**. The observer checks
cover failed-first recovery costs, both failed lifecycle forms, the native
`item.error` representation, malformed/missing evidence, unchanged raw arguments,
and exact source-proof failures. Targeted Pyright checks reported no errors.

Reproduce the offline proof with a new output path:

```sh
.venv/bin/python -m benchmarks.typescript_context_routing_v2_transport \
  --catalog benchmarks/comparisons/typescript-context-explore-v2/model-catalog.json \
  --output /tmp/loci-routing-v2-byte-limit-transport.json
```

## Qualification boundary

W2.5.1.3.4 (`task_ea390eab34f135070671da42c06f097d`) remains the next task:
declare follow-on qualification against the repaired effective schema before
collecting provider outcomes. The prior numerical keep and inconclusive strict
qualification remain historical results. This repair proof does not establish
the maintained-task nine-attempt exposure requirement, does not close parent
delivery acceptance, and does not promote the shared runtime. Multilingual W4
also remains outstanding.
