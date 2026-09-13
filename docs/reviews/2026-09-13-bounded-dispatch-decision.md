# W3.1 — bounded dispatch decision

Decision: **defer a dispatch extension; no build now**.

Task: `task_d2ccb47aa4e580e84a8b9e8741aa28bb` in canonical Objective
`obj_0110c8712b21bdd2c12532f189d84a74` at `/Users/brummerv/loci`.
This completes the optional capability decision. It does not establish that
dispatch would never be useful.

## Evidence and attribution

Reviewed the saved 13 September handoff, current Manifest criteria and retained
W4.7 evidence at isolated source commit
`86bca31305defdeabd2b5d1fef247a64ddc4eec5`. All links below pin that source;
the decision introduces no changes to its code, corpus or outcomes.

The [19-case corpus](https://github.com/Phluxxed/loci/blob/86bca31305defdeabd2b5d1fef247a64ddc4eec5/benchmarks/corpora/multilingual-context-v1/corpus.json)
asks for authored contracts, known direct calls and explicit uncertainty.
Its dispatch-adjacent questions do not ask for a positive runtime candidate set.

| Retained question | Evidence and consequence for W3.1 |
| --- | --- |
| `python_base_and_literal_forward` | Requests the authored base and forward annotation; gold explicitly says no computed MRO. Base/forward proof is delivered. No override target or method-resolution task is demonstrated. |
| `javascript_direct_class_base` | Requests `Worker -> Base`, source and `proves_runtime_dispatch=false`. Direct base and known-call proof already exist. Authored heritage alone is not receiver/override evidence. |
| `go_explicit_embedding` | Requests struct/interface embeddings and `promoted_call_proven=false` for `e.Stamp()`. Packets deliver all four required relationships. Incorrect promoted-target certainty does not demonstrate that a new positive target edge is required. |
| `rust_authored_trait_contract` | Requests alias/bound/authored struct-constructor spelling, supertrait and explicit impl sites; `dynamic_call_target_proven=false`. `return_constructor=Envelope` names the authored construction, not a requested constructor call edge or dispatch target. B supplies 9/11, 3/11 and 5/11 required relationships: omitted existing authored proof, not a missing runtime relation. |
| Python/JavaScript/Go/Rust known-call impact cases | Request definite direct callers, not all runtime impact. JavaScript's alternate `make -> add` path and Go/Rust selected call/type omissions concern relationships already available to the engine. |
| Unproven-dependency cases and TSX control | Demand no guessed computed, shadowed, ambiguous, external, macro or JSX call targets. These test the uncertainty boundary, not positive dispatch discovery. |
| Constructor, callback and override analysis | No retained case requests executable constructor resolution, callback target propagation or override candidate enumeration. There is no maintained dispatch workload, benefit estimate or first-language comparison in this evidence. |

The [W4.7 review](https://github.com/Phluxxed/loci/blob/86bca31305defdeabd2b5d1fef247a64ddc4eec5/docs/reviews/2026-09-13-multilingual-workflow-measurement.md)
and [defect analysis](https://github.com/Phluxxed/loci/blob/86bca31305defdeabd2b5d1fef247a64ddc4eec5/docs/reviews/2026-09-13-multilingual-measurement-defects.md)
retain all 114 outcomes. Sixty-three have incomplete graph accounting; exact
Go/Cargo control reads are asymmetric; several answer shapes are underspecified;
available alternate paths and task-agent selection choices limit delivery.
Actual false certainty and wrong facts remain errors. No rescoring is implied.
These findings do not support programming-language efficiency claims or an
exhaustive absence-of-defects claim.

## Current semantic boundary

The [JavaScript](https://github.com/Phluxxed/loci/blob/86bca31305defdeabd2b5d1fef247a64ddc4eec5/docs/reviews/2026-09-12-javascript-context.md),
[Go](https://github.com/Phluxxed/loci/blob/86bca31305defdeabd2b5d1fef247a64ddc4eec5/docs/reviews/2026-09-12-go-context.md)
and [Rust](https://github.com/Phluxxed/loci/blob/86bca31305defdeabd2b5d1fef247a64ddc4eec5/docs/reviews/2026-09-13-rust-context.md)
contracts preserve language-specific authored relationships. They do not infer
runtime dispatch, implicit satisfaction or active Rust configuration.
Source inspection of
[`_resolve_call`](https://github.com/Phluxxed/loci/blob/86bca31305defdeabd2b5d1fef247a64ddc4eec5/src/loci/graph/calls.py#L731)
confirms unsupported/dynamic calls remain unresolved and exact targets require
accepted binding/reference evidence. The existing
[callback-field negative](https://github.com/Phluxxed/loci/blob/86bca31305defdeabd2b5d1fef247a64ddc4eec5/tests/graph/test_calls.py#L1310)
keeps `self.callback()` unresolved without a matching method. That is evidence
of a deliberate capability limit, not measured demand to extend it.

## Rationale and reopening condition

The strongest measured counterpoint is `go_explicit_embedding-r1-A` and
`-r2-A`: both assert `promoted_call_proven=true` despite the prompt's boundary.
All three B answers say false with all four authored relationships delivered.
This could motivate clearer unresolved reasoning, but the existing semantics
already support the correct distinction; it does not establish a need for
positive dispatch edges. See the retained
[Go audit](https://github.com/Phluxxed/loci/blob/86bca31305defdeabd2b5d1fef247a64ddc4eec5/benchmarks/results/multilingual-context-workflow-v1/independent-reviews/go.md).

The strongest broader argument for building is that constructor, callback and receiver
questions could matter in real change-impact work; the deliberately bounded
corpus cannot measure that value. However, adding candidate machinery now has no
demonstrated task benefit, no supported first-language choice and no evidence
that it would repair the retained failures. It would add selection and proof
cost while existing relationship delivery remains incomplete. Defer is therefore
the supported current product decision.

Revisit when a concrete repository task needs a constructor, override, callback
or interface target and current source/relationship retrieval leaves a semantic
gap that matters to the answer or edit. Preserve the task and source evidence,
show why an existing-edge delivery repair is insufficient, and identify a
bounded language-specific proof rule. A new benchmark campaign is not required
merely to reopen the discussion.

Only if a build is subsequently justified, specify the first language,
receiver/target evidence, candidate universe and completeness/truncation,
exact-versus-possible query behavior and negative-case acceptance. Agree its
separate implementation scope before building. No detailed dispatch design or
implementation subtree is selected by this defer.

## Closure and next work

W3.1's retained-evidence and decision criteria are satisfied; its build-only
criterion is inapplicable because the decision is defer. Acceptance is this
bounded evidence review plus Manifest criterion/reference readback and scoped
diff checks. No provider run, new test campaign, corpus edit, historical rescore,
integration or installed-runtime promotion is part of this decision.

W5.1 retains exact Go/Cargo control access; W5.2 retains bounded selection
assessment/repair (including valid no-change outcomes); W5.3 retains deterministic
evaluator/tool/answer-contract repair. None is reclassified as dispatch work.

Next in the agreed workstream order: **W3.2 — bounded flow decision**,
`task_57921953d7db2edec160865ce62bcfeb`. W3.2 is not started by this record.
