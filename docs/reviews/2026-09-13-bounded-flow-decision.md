# W3.2 — bounded value-flow decision

Decision: **defer value-flow retrieval; no build now**.

Task `task_57921953d7db2edec160865ce62bcfeb`, canonical Objective
`obj_0110c8712b21bdd2c12532f189d84a74` at `/Users/brummerv/loci`.
This decision was assessed independently of the W3.1 dispatch defer.

Value-flow retrieval would trace how an input or intermediate value reaches a
use, argument, field or return. Knowing which declaration an imported name refers
to, or which function a definite call targets, does not by itself establish that
value movement. The retained tasks do not demonstrate a consequential gap that
requires adding those semantics.

## Retained evidence

Reviewed the current Manifest criteria, all 19 frozen prompts/gold and the
flow-adjacent retained outcomes at isolated source
`86bca31305defdeabd2b5d1fef247a64ddc4eec5`. An independent bounded audit checked
the case/attempt attributions. No new provider measurement or rescore was run.

The [frozen corpus](https://github.com/Phluxxed/loci/blob/86bca31305defdeabd2b5d1fef247a64ddc4eec5/benchmarks/corpora/multilingual-context-v1/corpus.json)
and its `fixtures.tar.gz` preserve the source. Direct archive reads verified
file and selected-span SHA-256 against the corpus for `run`, `add`, `make`,
`Badge`, `build` and `_validate_bundle`; their actual bodies support these distinctions:

| Retained task | Question, source and outcome | W3.2 attribution |
| --- | --- | --- |
| `javascript_value_dependencies` | Asks direct helper origins, authored `add_expression` and default export binding. `run` returns `make() + add(1)`; `add` is `(value) => value + 1`; `make` returns `add(0)`. All six attempts have 7/7 required source. B delivers 2/3 required relationships, omitting the available `make -> add` alternate path. | Declaration origin and direct calls already supply the requested structure; reading the helper body supplies the expression. The omitted call is existing-edge selection work in W5.2, not absent value flow. |
| `tsx_props_control` | `Badge(props: Props)` returns `<span>{props.label}</span>`. All six answers correctly name `label`, all have full source, and B delivers 1/1 type relationship. | Direct source inspection answers the field question. Origin spelling/granularity failures do not require tracking prop values through a program. |
| `python_loci_bundle_contract` | `_validate_bundle` checks that a root bundle has role `anchor` and raises `bundle requires a definition source` for missing source. All six answers are exact with 4/4 source; B relationship delivery is 2/4, 2/4 and 0/4. | Local branch inspection answers these questions. No demonstrated need for a new value-propagation graph; omitted authored relationships remain a separate limitation. |
| `rust_authored_trait_contract` | `build(id, body)` contains `Envelope { id, body }`. The prompt asks the authored constructor name and type/trait facts; answers identify Envelope but several differ from exact gold encoding. | Construction syntax is visible in source. The task does not ask to trace an argument into a field or propagate the returned value to callers. |
| Remaining catalog | Type aliases, import/re-export origins, known callers and uncertainty controls; `javascript_unproven_dependencies` also asks about returned identifiers under uncertain bindings. | None requests assignment-to-use, argument-to-parameter or return-to-caller propagation. Binding uncertainty is not evidence of a missing positive flow relationship. |

Attempt evidence lives under
[`benchmarks/results/multilingual-context-workflow-v1`](https://github.com/Phluxxed/loci/tree/86bca31305defdeabd2b5d1fef247a64ddc4eec5/benchmarks/results/multilingual-context-workflow-v1),
with directories `<case>-r<1..3>-<A|B>`. In particular,
`javascript_value_dependencies-r3-B/result.json` reports `add_expression: "add(1)"`
despite full source. This is the strongest observed counterpoint: a task agent
confused the call-site expression with the helper implementation. Three other
attempts (`r1-A`, `r1-B`, `r3-A`) answer exactly using the existing source/tool
surface. The error does not demonstrate an absent flow relationship or prove
that adding flow would fix it. Clearer source-use guidance might help, but no
such repair is established by this decision.

The existing
[`exploration.py`](https://github.com/Phluxxed/loci/blob/86bca31305defdeabd2b5d1fef247a64ddc4eec5/src/loci/exploration.py#L25)
selects authored type/heritage, reference and definite-call relationships for
its supported intents. These relationships preserve their original meaning;
they must not be advertised as value propagation. The
[W4.7 review](https://github.com/Phluxxed/loci/blob/86bca31305defdeabd2b5d1fef247a64ddc4eec5/docs/reviews/2026-09-13-multilingual-workflow-measurement.md)
retains incomplete accounting, control-access asymmetry and answer-format limits.
Keep all 114 outcomes and their existing dispositions.

## Rationale, limits and reopening condition

Tracing values could help explain a long function or investigate change impact.
The current 19-case corpus is too narrow to establish that benefit, choose a
first language or measure saved retrieval against indexing, selection and proof
cost. This is insufficient evidence for a build, not evidence that value flow
is unimportant. Correct answers from source also do not prove that explicit
flow could never improve efficiency.

Reopen for a concrete task asking where a value came from or where it goes,
with exact source showing why current declaration/call/type retrieval leaves a
consequential gap. Distinguish missing source/available relationships from new
semantic work. If building is justified, separately agree the first language,
intra/interprocedural scope, exact evidence spans, unsupported cases, hop and
evidence costs, and acceptance boundary. No detailed implementation design is
selected now; no dispatch build or whole-program analysis is a prerequisite
for reconsidering a bounded flow slice.

## Closure

The retained-task review and defer/rationale criteria are satisfied. The
build-only criterion is inapplicable. Acceptance is the scoped source/outcome
audit, source/span hash checks, Manifest criterion/reference readback and scoped
diff verification. W5 retains delivery/selection/evaluator work. No code change,
new experiment, frozen-input edit, rescore, integration or runtime promotion
follows this decision.

Next in workstream order: **W3.3 — storage-cost decision**,
`task_f97e457ebc125c47ba7076bf7b05f286`; it is not started by this record.
