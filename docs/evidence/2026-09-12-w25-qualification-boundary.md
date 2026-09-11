# W2.5 continuation — qualify the delivered exploration workflow

The 12 September continuation follows Vik's explicit instruction to resume W2.5
after adding required multilingual scope and reviewing North Star alignment.
Canonical work remains in Objective `obj_0110c8712b21bdd2c12532f189d84a74` at the
original Loci repository; implementation remains in the isolated worktree.

## Existing result and remaining question

The published [three-arm experiment](../../benchmarks/results/typescript-context-three-arm-v1/README.md)
finished all 153 attempts and independently replayed them. Its A/B/C full passes
are 51/47/49, with 9/5/7 maintained passes. All frozen candidate verdicts reject.
C saves 60% of eligible median calls but increases maintained output by 94.57%.
Its corpus, source pins, tools, scores, raw attempts and verdicts stay unchanged.

That experiment exposed automatic get expansion. It did not expose
`loci_explore`, its intent selection or compact result packer. Its seven
budget-rejected operations were broad outlines and greps, not failed exploration
calls. These results do not demonstrate a delivery defect in the new workflow.

The [W2.4 acceptance](2026-09-11-w24.md) already retained all 14 required Anvil
type definitions, reduced related definitions from 30 to 15, checked exact
source/proof and output limits, and exercised actual MCP host calls. This is
deterministic delivery evidence, not a matched agent-efficiency result.

One public-contract clarification is justified: the tool description now names
TypeScript/TSX as the current type-dependency language boundary. Runtime behavior
is unchanged. Python, plain JavaScript, Go and Rust delivery remain planned W4
work; generic navigation and output machinery do not establish semantic parity.

## New qualification boundary

A separately versioned comparison will test the delivered workflow:

- Control A: the existing exact-retrieval and graph tools, without automatic
  type expansion or the new exploration tool.
- Candidate B: the same tools plus the actual `loci_explore` implementation.
- Both use the same pinned current production source and freshly built index.
  This isolates workflow availability; it is not a new three-arm semantic ablation.
- All 17 original frozen cases and task prompts, three repetitions per condition,
  serial execution, the requested model/reasoning, and numerical budget/acceptance
  gates remain unchanged: 102 newly declared attempts, with no correctness retries.
- The new harness must observe the returned source and embedded relationship
  proof, including `uses_type` and heritage. Generic dependency proof remains
  distinct from more precise relationship subtypes that the implementation does
  not claim. Old scores are not retroactively changed.
- Freeze and publish the new tools, accounting, scorer coverage, schedule and
  source binding after focused offline/host transport verification and before
  measured agent calls. Retain failed attempts and independently replay results.

The old frozen result stays rejected. First-milestone acceptance remains open
until the actual workflow satisfies the declared quality, context, useful-work
and cost gates. New language work, source integration and shared-runtime promotion
are not part of this comparison.

## Manifest boundaries

- W2.5.1.1 (`task_76e3c3e37e002e0497fdbcd7a4c617a4`): resolve the completed
  experiment and the remaining qualification boundary.
- W2.5.1.2 (`task_abc93235c56d46207f7ef4bdd412b1fb`): freeze and verify actual
  exploration measurement.
- W2.5.1.3 (`task_2727497172e9ceadea5ab07538da0b31`): execute and qualify the
  matched workflow comparison.

The original W2.5.1 acceptance criteria remain required; its additional criterion
requires the actual delivered workflow to be measured. The milestone review
follows accepted qualification, with required multilingual W4 still outstanding.
