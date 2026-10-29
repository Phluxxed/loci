# Discovery and model-token study

Completed 2026-10-29 on `experiment/search-ablation`.

This study did not demonstrate a token saving from making Loci available. Across the same assigned tasks, full Loci used **at least 12.4% more reported tokens** than native tools; disabling graph expansion used **17.0% more**. All 18 answers supplied the requested facts and substantive source support in blinded review, but exact citation compliance differed. This is a small exploratory result, not evidence that graph retrieval is generally ineffective.

## What we did

Agents started with three engineering questions: locate a shared helper and explain its behavior, trace a mutation through routing and persistence, and establish what a reusable template leaves unconfigured. They discovered source themselves. Prompts supplied no answer-file lists or selected source spans.

Each task ran twice in each of three conditions: native Pi search/read tools; those same tools plus normal Loci retrieval; and the same Loci integration with relationship/ownership expansion disabled. The last condition still indexes source, selects anchors and returns anchor ownership metadata. It does not remove graph construction or indexing.

The 18 assignments used fresh sessions, identical copies of a historical 701-file repository snapshot, empty independent Loci stores, balanced condition order, Pi 0.87.1, and `openai-codex/gpt-6-sol` with requested effort `high`. The experiment used the existing subscription login through Promptfoo 0.125.1. Source and target implementation were frozen throughout measurement. Normal native tools remained available; Loci use was voluntary.

## Tokens and answer quality

Totals sum provider-reported input and output across every model request, including repeated conversation context. Cached input is included once. Reasoning is already included in output and is not added again. These are token measurements, not subscription-cost estimates.

| Condition | Total reported tokens | Change from native | Requested facts and substantive support | Full prompt compliance, including exact citations | Runs using Loci |
|---|---:|---:|---:|---:|---:|
| Native tools | 211,308 | — | 6/6 | 1/6 | — |
| Native + full Loci | **at least 237,561** | **at least +12.4%** | 6/6 | 4/6 | 1/6 |
| Native + Loci without expansion | 247,167 | +17.0% | 6/6 | 3/6 | 2/6 |

One full-Loci assignment recovered from two provider-overload errors. The failed attempts reported zero usage, which cannot establish zero consumption. Its successful responses are counted, but the all-in total is a lower bound. The other 17 assignments have reconciled accounting. Excluding that assignment and its matched native counterpart leaves five matched pairs with **9.3% more** tokens in the full-Loci condition.

The native condition was cheaper, but did not satisfy the exact quotation/line-range contract as often. Citation failures were overlong quotations or quotations absent from the stated lines. They are preserved as failures, even where the underlying engineering facts were correct. Only one pair per native comparison met the entire prompt contract on both sides: full Loci used 42.2% more tokens and expansion-disabled Loci 55.6% more on that pair. One pair cannot establish a reliable quality-matched effect.

## What the traces explain

Loci was actually available in every assigned Loci session: measured tool catalogs matched the conditions, and separate live operational checks executed both retrieve and read successfully. Non-use here is not inferred tool absence.

Agents called Loci in only **three of twelve eligible assignments**. Each of those retrievals exposed useful source locations, and each was followed by ordinary file reads. None used `loci_read` during measurement. The graph-enriched query delivered two static relationships, alongside previews, ambiguity and omission metadata; the two expansion-disabled queries delivered no relationships. The agents still inspected implementation files and collected line citations with native tools.

The observed integration therefore seldom replaced native discovery, and using it did not eliminate follow-up reading. That is an explanation supported by these traces, not proof that a particular graph algorithm caused the token difference. Most episodes never exercised the graph toggle, and only one measured retrieval used enrichment. The experiment does **not** establish graph removal, indexing removal, or a different grep backend as the remedy.

## Grading correction and limits

An independent Astra reviewer received randomly labeled answers, the actual questions and pristine source evidence, without condition labels, usage, tool traces or the mapping to runs. This was internal model review, not human acceptance.

After seven blinded reviews, before inspecting condition token totals, the primary identified overreach in its authored rubric: some clauses demanded extra implementation detail absent from the question. The reviewer independently agreed and appended a separate assessment against the actual prompt. Original judgments remain intact. This is an explicitly **post-hoc evaluator correction**, not a preregistered result.

Original strict full-rubric scores were native 1/6, full Loci 3/6, and expansion-disabled Loci 3/6. Correcting the optional-detail overreach changed full prompt compliance to the table above; false facts, missing requested evidence, malformed quotations and incorrect line ranges still fail. Both grading methods were calibrated on the same nine blinded controls: three supported answers pass; six incorrect or unsupported answers fail. Saved-answer Promptfoo replays reproduce original scores of 7 passes/11 failures and corrected scores of 8 passes/10 failures, with no grader errors or new target inference.

Other limits remain material: three convenience tasks on one historical snapshot, two repetitions, two Python tasks and one JavaScript task, persistent provider cache effects, and a strict JSON/quotation contract that adds work. Target working-directory paths contained condition labels, so the target agents were not blinded to condition. Identical Loci tool schemas do not remove that possible expectation effect. The effort setting was requested and recorded; backend-effective effort was not independently observed.

## Verification and retained evidence

Seven focused checks pass for production retrieval/read binding, expansion control, persistent source references, errors, token accounting and grading boundaries. Three live Promptfoo operational probes pass. All 18 source copies remained unchanged; inspected tool traces show source search/read only, with no observed access outside their source boundary. The boundary is instructions plus observation, not a newly installed filesystem sandbox.

The frozen adapter is retained separately from the final grading/replay additions. Initial qualification failures and the calibration adapter's whitespace error are preserved in the [protocol](agent-study.md). The original mechanical experiment remains historical evidence in [RESULTS.md](RESULTS.md); it did not measure task discovery or model-token savings.

[agent-summary.json](agent-summary.json) contains public per-assignment measurements, both quality scores, paired subsets, accounting qualifications and evidence hashes. Private source, prompts, oracles, answers and traces remain ignored locally under `private/agent-v1`, `private/agent-cases`, `private/agent-review` and `private/pi-qualification`. The adapter and verification code are described in [the evaluation README](../../evals/search_ablation/README.md).

The bounded investigation is complete. It supports no token-saving claim for this integration on these tasks, and leaves graph-policy efficacy unresolved. All changes remain on the experimental branch; no product implementation change or additional experiment follows from this result.
