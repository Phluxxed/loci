# Complete-work comparison implementation

This is the implementation for **W1.8.4.4.10.2.2**. The fixed question, prompts,
eight-row schedule and decision rule remain in
[design-v1](../complete-work/design-v1/protocol.md). This directory does not
contain a campaign freeze or measured outcomes.

The controller gives one fresh native Terra/high thread three fixed turns. A
benchmark-only MCP server fixes graph enrichment on or off for that thread.
Both arms expose the same `loci_retrieve` and `loci_read` descriptors and share
normal anchor selection, source packing, paging and freshness. The off arm
omits graph traversal and related enrichment. Normal Loci has no new public
switch. Failed tools, retries and non-use stay in their assigned episode.

## Prepare one scheduled target

Run from the serving checkout using its prepared interpreter. Every destination
must be new and outside the serving repository:

```sh
.venv/bin/python -m benchmarks.complete_work.prepare \
  --run-id episode-v1-b2-off \
  --destination /tmp/complete-work-b2-off \
  --serving-root /Users/brummerv/loci \
  --install-deps --prepare
```

Use `episode-v1-b1-on` to prepare the first Anvil episode. Each scheduled row
gets its own destination, dependency environment, index and source-reference
state. Omitting `--install-deps` makes an inspection-only preparation that the
controller refuses to execute. Source exports retain identity maps; exclusions
of benchmark/history material are explicit. Anvil uses the verified retained
638-file export and original npm lockfile. Loci uses the pinned `f3d9134` export
and the [environment asset](oracles/loci_environment.json). The serving source
is outside every writable task copy.

The resulting `observer/run.json` binds all paths. Prepared source, dependency
provenance, control config and instructions are observer inputs; receipts,
source history, evaluation and other episodes remain outside the trial's
allowed filesystem. Ambient hooks, memories, plugins, apps, web search and
child delegation are disabled equally. This is a declared difference from the
usual interactive host. Trial instructions and effective host configuration
must be matched and frozen, including applicable instruction sources exposed
by the native thread response. Path shapes and actual provider cache hits must
also be retained; no cold-cache claim is made.

## Preflight and freeze — W1.8.4.4.10.2.3

```sh
.venv/bin/python -m benchmarks.complete_work.controller preflight \
  --config /tmp/complete-work-b2-off/observer/run.json
```

Preflight initializes the installed App Server, checks advertised Terra/high,
creates a fresh thread without a model turn, verifies the permission profile
and two-tool MCP inventory, and tests read/write boundaries using evaluator-owned
canaries. It writes to `output-preflight`, leaving the measured output unused.
A second attempt needs a distinct preparation or a separately recorded diagnostic
output; it must not overwrite a prior receipt.

**Current host limitation:** the installed CLI advertises Terra/high, but its
native sandbox command probe returned exit 71, `sandbox_apply: Operation not
permitted`, both ordinarily and in an approved tool retry. This was an OS
sandbox failure, not an approval-review rejection. Do not weaken the profile or
launch measured turns while this boundary is unverified. The recorded probe is
under `.scratch/deterministic-graph-retrieval/episode-runtime-capability/`.

The freeze task must establish a host that can enforce those permissions, verify
Node/Python test execution within them and confirm hidden source/instructions
cannot enter trial context. It must also validate actual native multi-turn
usage, partial failure capture, outer-call visibility and timeout behavior on a
separate non-campaign control. Scripted tests do not establish provider telemetry
availability. Missing request/retry telemetry remains unknown or a completion
lower bound, never a fabricated zero.

Before any measured outcome, publish a JSON freeze with `schema_version: 1`,
`kind: "complete-work-campaign-freeze"`, and `files` mapping input paths to SHA-256
hashes. Include all eight run configs, design inputs, implementation/oracle
files, serving source/resources, active user config identity, actual instruction
sources, dependency identities and preparation receipts. The controller checks
its required input closure and every listed file against an independently
supplied freeze hash. The next task owns freeze creation and publication.

## Execute and evaluate — only after freeze

```sh
.venv/bin/python -m benchmarks.complete_work.controller run \
  --config /tmp/complete-work-b2-off/observer/run.json \
  --freeze /absolute/path/campaign-freeze.json \
  --freeze-sha256 FROZEN_SHA256

.venv/bin/python -m benchmarks.complete_work.evaluate \
  --config /tmp/complete-work-b2-off/observer/run.json
```

Run the eight rows in the declared order, one at a time. A campaign lock prevents
concurrent measured execution; exclusive output creation prevents reuse of a
consumed run. The controller never chooses follow-up prompts based on quality.
Timeout, abort, protocol violation or capture failure ends the episode and
retains later stages as `not_reached`.

The wire journal precedes accounting reduction. Cumulative usage is differenced
once across the fresh thread, with per-stage and downstream totals. Unique raw
response completions are an observed request lower bound; they may omit failed
upstream attempts. Native tool items and outer calls are distinct counts.
Latency ends at terminal completion or stopped execution. Between-stage handoff
is included; final archival/teardown and complete controller wall time are
reported separately, including timeout overruns.

Each MCP result retains its full packet and the content-addressed source version
it cites. The delivery join checks native items against these receipts, retaining
ambiguous/unmatched evidence as unknown. Repeated source spans count only against
the same complete file hash. Changed-source reads are separate. Graph proof
counts describe delivered evidence, not internal model reliance.

The evaluator restores stage source from those retained bytes before running the
independent behavioral oracle. It also writes stage diffs. Oracle results never
feed back into the trial. Correctness, material final claims, severe failures
and rework still require the predeclared arm-blinded Sol review. A passing oracle
alone does not set `correct: true` or accept the Objective.

`accounting.arm_cost` requires the exact expected run-ID set, includes all
unsuccessful outcomes in resource totals, and returns unproven for missing
telemetry/rows. Zero successes have infinite per-correct cost/time. The later
analysis task applies the frozen quality/Pareto rule and price sensitivity; no
historical gate is changed by this implementation.

## Local acceptance

```sh
.venv/bin/python -m pytest -q tests/test_complete_work_*.py \
  tests/test_retrieval.py tests/test_normal_source_refs.py tests/test_normal_mcp.py
```

The oracle controls reject unchanged and deliberately faulty implementations
and accept disposable reference patches; their receipts preserve runtime and
manual-review limits. Scripted App Server tests cover continuation, deadline
and failure retention; actual local MCP tests cover both arms and source edits.
No test here is a measured campaign episode.

> **TL;DR:** The runnable harness measures whole work and keeps failures and uncertainty. Native preflight and a published freeze must pass before the eight measured episodes.
