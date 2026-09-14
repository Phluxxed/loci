# W1.8.3 post-change ordinary audit: execution preflight

Preparation only, 14 September 2026.  This is an execution recipe, not a
runtime freeze and not evidence that any reserved row has run.

## Frozen reserved work

Authoritative source: `benchmarks/comparisons/ordinary-adoption-v1/post-change-template.json`.
Read each `rows[]` entry verbatim at launch and verify its `prompt_sha256`; do
not reconstruct prompts from this table.  Every row has
`conditional_on_selected_correction: true`, task source commit
`53bf29e60cece2335aa39fe301935a07e8e8d4e4`, and source archive SHA-256
`e919302908ba8dfee2ee8ee055fd4a7463a37e94a71d35d2ecda7abe95463c5e`.

| row | case | repeat | role / model / effort | source root | task name | prompt SHA-256 |
| --- | --- | ---: | --- | --- | --- | --- |
| 15 | continuity_checkpoint_retry_and_clear | 1 | delegate / gpt-5.6-terra / high | `/tmp/anvil-source-tasks-20260914/t15` | `inspection_15` | `92af3dba39cb1ec95e81b6b27d1e3195dfac092a0733d2bff9c28b54d2849c43` |
| 16 | tool_result_capture_binding_type_identity | 1 | delegate / gpt-5.6-terra / high | `/tmp/anvil-source-tasks-20260914/t16` | `inspection_16` | `f450f8b6bc880225393ee86fb53de81527124f09fed6c42ebec8cbf0ebf3e9be` |
| 17 | browser_cli_immediate_production_entrypoint | 1 | delegate / gpt-5.6-terra / high | `/tmp/anvil-source-tasks-20260914/t17` | `inspection_17` | `2b119d58c5fce1666281716d4e485f34dd4f6b3b92fd6617da5add2090f4e6bf` |
| 18 | continuity_render_active_task | 1 | delegate / gpt-5.6-terra / high | `/tmp/anvil-source-tasks-20260914/t18` | `inspection_18` | `4b83f127f7f045b3baf5811fdc4e2a7d143f224a6310e418c6522d559fcc2dcd` |
| 19 | continuity_render_active_task | 2 | delegate / gpt-5.6-terra / high | `/tmp/anvil-source-tasks-20260914/t19` | `inspection_19` | `da4315b82d86d418278962ce6e805e9d58d65dd87e16e5da1df43005033c1fb3` |
| 20 | browser_cli_immediate_production_entrypoint | 2 | delegate / gpt-5.6-terra / high | `/tmp/anvil-source-tasks-20260914/t20` | `inspection_20` | `dd72b6a5e6d3c1fa05cbc44ec95273144cdc2ec69aa25b5683c262b2aa1437a8` |
| 21 | tool_result_capture_binding_type_identity | 2 | delegate / gpt-5.6-terra / high | `/tmp/anvil-source-tasks-20260914/t21` | `inspection_21` | `06af7bd05614e8aaf86c20495a059571d1fb53efec6a5f52ea7d633575cda96b` |
| 22 | continuity_checkpoint_retry_and_clear | 2 | delegate / gpt-5.6-terra / high | `/tmp/anvil-source-tasks-20260914/t22` | `inspection_22` | `104e066afc3f5ceb81ae91169decab295f19d628661e537d3943532ae1745fe7` |
| 23 | tool_result_capture_binding_type_identity | 1 | primary / gpt-6-astra / ultra | `/tmp/anvil-source-tasks-20260914/t23` | — | `43a346012515e32b4a508b78afb352caa409cdfb8a683785ac50ed9a7288ff6c` |
| 24 | browser_cli_immediate_production_entrypoint | 1 | primary / gpt-6-astra / ultra | `/tmp/anvil-source-tasks-20260914/t24` | — | `3f4e8bfdeed7e353ba4bacbc6531a905efa0873e8076ead3b20cfaf0156ab7fd` |

The common prompt wrapper and each full case prompt are frozen in that JSON.
Rows 15–22 are fresh native delegates with `fork_turns: "none"`; run in
adjacent pairs (15–16, 17–18, 19–20, 21–22), at most two concurrent.  Run 23
then 24 serially in the actual primary host only after the delegate block.
Those two reserved checks must not be substituted with the current Loci-repo
W1.6.3 functional-acceptance calls.

## Required pre-launch freeze

`post-change-template.json` is `reserved_not_runtime_frozen` and says the
selected Loci engine, installed instruction, and catalog identities must be
frozen separately.  `freeze.json` confirms
`post_change_runtime_frozen: false`; its status and input hashes cover only the
retained 14-row baseline.  Before row 15, create a separate immutable freeze
that records, at minimum:

1. the selected correction and delivered engine revision/tree;
2. normal operation/catalog identity (the public surface is only
   `loci_retrieve` and `loci_read`), including the installed Loci skill and
   referenced guidance hashes;
3. the installed launcher/adapter identity and adapter version
   `ordinary-adoption-normal-v2` plus `ordinary-adoption-native-v2`, with the observer/reviewer source and test
   hashes;
4. the matching host/catalog preflight for delegate and primary, selected
   Anvil source-copy identities, exact scheduled prompt hashes, and the
   frozen rubric; and
5. a passing deterministic adapter/review preflight plus a retained actual-host
   normal retrieve/read proof for the selected installation.

The previous baseline provenance is evidence of the fields to retain, not a
license to reuse its identities: `runtime/runtime-provenance.json` records the
old engine tree, catalog, launcher, installed skill/guidance files, host, and
runtime.  Recompute them after the correction.

## Execution, capture, and readout

There is no checked-in post-change campaign runner.  Launch delegates through
the native subagent path above, preserving the verbatim schedule prompt and
fresh-agent/no-history condition.  Cap each delegate at 300 wall seconds;
preserve an interrupted raw interval and never retry or replace its row.  The
schedule also freezes a 60 terminal-MCP/shell-operation flag and a 400000
model-visible-output-byte flag.  These are reported accounting flags, not
answer-score exclusions.

For each attempt, retain its native rollout JSONL and select exactly its first
task interval.  `benchmarks.ordinary_adoption_observed.observe_rollout` needs
at least this JSON metadata:

```json
{
  "run_id": "run-15",
  "purpose": "post_change",
  "thread_id": "<actual native thread id>",
  "turn_id": "<actual native turn id>",
  "target_repo": "/tmp/anvil-source-tasks-20260914/t15"
}
```

Add the schedule identity fields (`case_id`, `condition`, `repetition`,
`role`, requested model/effort, source root/canonical root, source hashes,
prompt hash, and agent task name); add `expected_interval_sha256` only after
hashing the selected raw interval.  The observer validates the matching native
`session_meta`, `task_started`, and `turn_context`, then captures terminal MCP
and shell items and correlates emitted outer Code Mode output.  Feed that same
rollout and metadata to
`benchmarks.ordinary_adoption_normal.observe_normal_rollout`; it calls the base
observer then recognizes only `loci_retrieve` and `loci_read`.  A relationship
can enter the review registry only when its normal-operation proof validates
and its model delivery is `full_exact`.

The existing CLI executes only the base observer:
` .venv/bin/python benchmarks/ordinary_adoption_observed.py ROLLOUT METADATA.json --output observed.json`.
Serialize the normal-adapter function result separately; it has no command-line
entry point.  The two `host-acceptance/primary-*.json` files are exact selected
result packets for current W1.6.3 functional acceptance.  They do not provide
native event IDs, outer output blocks, a selected rollout interval, or a
completed task boundary, so they cannot be converted into rows 23/24 or passed
to the observer as fabricated capture.

## Acceptance accounting

The ordinary denominator is eight delegated post-change rows (15–22); the two
reserved primary checks are outside it.  Required gates from the normal
retrieval contract are:

* 8/8 ordinary rows keep source/prompt/rubric/capture/model/effort and are
  within the five-minute cap; every answer satisfies the frozen required facts
  with no material unsupported claim.
* At least 4/8 ordinary rows have normal-retrieval, source-backed semantic
  relationship delivery with retained `full_exact` model output; at least 3/4
  binding/browser rows and at least one of each case.  At least 2/8 final
  answers need reviewer-validated relationship-support annotations linked to
  complete-proof, `full_exact` normal context.
* Both reserved primary checks return their expected relationship with complete
  proof, retained actual-host `full_exact` model output, and verified proof IDs.
* For each case pair, post-change medians of visible bytes, provider input
  tokens, and elapsed time are each no more than 1.25× the corresponding
  baseline ordinary-pair median.  Missing capture fails the gate; all failures
  remain in accounting.  Publish individual values, ranges, calls and provider
  usage, not only medians.

Do not add trials, reminders, substitutions, selective retries, rescoring, or
criteria changes.  A failed or inconclusive result is retained and completes
the planned comparison.

## Current blockers / required inputs

1. The selected correction is delivered at 90068fa. Its separate post-change
   engine/runtime/catalog/installed-guidance/adapter freeze remains required;
   the two reviewed accounting corrections are incorporated before that freeze.
2. Fresh Anvil copies t15–t24 are now prepared and verified against all 638
   frozen file hashes; runtime/source-copies.json in the new comparison retains
   their canonical-root identities. They remain unrun.
3. Fresh native delegate/primary session IDs, turn IDs, raw rollout paths, and
   selected-interval hashes do not exist until rows run.  Do not derive them
   from host-acceptance packets or prior baseline sessions.
4. The frozen post-change rubric and baseline per-case unrounded cost values
   must be linked into the new freeze/readout before gate evaluation.
