# Bounded ordinary-adoption protocol

This document becomes the W1.2.6 pre-outcome freeze only when `freeze.json`
records the case, source, prompt, observer, review and runtime identities plus a
passing deterministic preflight. Until then it is prepared protocol text; no
scheduled task outcome may be used to tune it.

## Workload and schedule

Use the four cases in [cases.json](cases.json), the native host conditions in
[conditions.md](conditions.md), and [accounting.md](accounting.md).

- Eight ordinary baseline attempts: two fresh Terra/high attempts per case.
- Four visibility diagnostics: one fresh Terra/high attempt per case, after all
  baseline attempts finish. Only the visibility sentence differs.
- Two primary baseline checks: binding identity and browser entrypoint. Rowan
  verifies known-answer source/proof delivery in the actual primary host.
- Eight post-change ordinary attempts and two primary post-change checks, only
  for the correction selected through W1.5 and actually delivered. If no such
  correction is selected, discontinue these rows with decision evidence; do not
  invent a before/after benefit or mark an unrun attempt successful.

This is at most 20 delegated task attempts and four primary functional checks.
Evaluator fixture/capability calls and the
separate surface probe are excluded from that count and labeled explicitly.
No third diagnostic condition, additional model/language matrix or selective
retry is added from an interesting outcome.

`schedule.json` freezes only the first 14 rows: 12 delegates and two primary
checks. `post-change-template.json` reserves the later ten rows and their fixed
case/prompt/order/rubric; it is not an executable runtime freeze. After W1.5
selects a correction, W1.8.3 must bind its exact Loci engine, installed
instruction and catalog identities in a separate pre-run freeze. The task
source remains the same Anvil commit; it is distinct from the Loci engine
source being corrected. Unselected post-change rows are discontinued with the
decision, and never appear as attempted baseline rows.

Case order within the first ordinary repeat is checkpoint, binding, browser,
renderer; the second reverses that order. Run at most two delegates concurrently
in adjacent pairs. The visibility block uses the first-repeat order. The
post-change block repeats the same eight-row order and pairing. Primary checks
run serially after their delegated block. Retain each attempt's actual start/end
time and concurrent partner. Costs describe this bounded host/load condition,
not isolated-server or population latency. The coordinator issues no additional
Loci source queries while a scored pair runs.

Each attempt uses a new native agent with `fork_turns=none`, selected model and
effort recorded explicitly, and a new physical copy of the same source archive.
Presented paths use neutral names under `/tmp/anvil-source-tasks-20260914/`;
condition, audit and graph labels never appear in those paths or agent names.
Do not reuse an earlier agent as a fresh replicate. Follow-ups cannot alter the
first task outcome. Later probes are separate turns and purposes.

## Task assignment

The following common assignment wraps the case's exact ordinary prompt. The
source-root substitution and case prompt are the only case-specific fields.
The assignment contains no expected file, answer or graph/tool hint.

```text
Investigate the repository at {repo} read-only.

{ordinary_prompt}

Follow the normal repository instructions. Keep this a focused source
investigation: do not edit files, run tests, or launch services. Use only this
repository and installed operating instructions for evidence; do not inspect
other repositories, earlier agent sessions or unrelated task artifacts. Give
a concise answer with relevant source paths and lines, and state any material
uncertainty. Complete this assignment directly. Do not spawn other agents.
```

The visibility condition inserts its one sentence from `conditions.md` after
the ordinary prompt. It does not name Loci, a graph operation or an answer.
The post-change ordinary condition uses the unchanged ordinary assignment.

The real shared filesystem does not provide per-agent enforcement. Check the
native access ledger for cross-run/gold/session reads. An instruction breach is
a retained invalid attempt, not an excuse to rerun until a clean answer appears.
Normal skill references and root/project guidance are permitted.

## Budgets, failures and stopping

Allow five minutes of elapsed wall time per delegated attempt. At the cap,
interrupt the agent and retain the partial native interval; no evidence-seeking
continuation is a scored completion. A provider/tool timeout, missing terminal
record, malformed output, cancelled task or unsupported operation stays in its
declared row. Do not retry that row. Untouched scheduled rows may continue when
the host is healthy; a condition/source drift pauses the affected block pending
an explicit updated freeze and leaves original rows intact.

Use normal advertised per-tool budgets without forcing graph calls or larger
packets. Flag attempts exceeding 60 terminal MCP/shell operations or 400,000
model-visible tool-output UTF-8 bytes as over-budget after capture; counts and
costs remain reported. These are accounting limits, not hidden answer-quality
criteria. The coordinator does not infer operation totals from code-site text.

There are no selective retries and no stopping for a favorable or unfavorable
answer. Stop a completed block at its scheduled row count. A negative or
inconclusive audit result is valid. Necessary audit/tool bugs discovered during
preflight are repaired before freeze; a post-freeze observer bug preserves raw
evidence and requires a versioned correction applied uniformly to affected rows.
Do not rewrite old benchmark scores.

## Scoring and comparisons

Freeze all required semantic facts and forbidden unsupported inferences before
the attempt. A reviewer uses the independent source rubric and exact answer
quotes to mark each fact correct, incorrect, missing or uncertain. A fully
sufficient answer has all required facts correct and no material unsupported
claim. Source-grounded uncertainty is valid where the rubric permits it. Wrong
or missing facts are reported separately from capture and budget failures.
Additional correct supported detail and non-graph routes remain valid.

Report discovery, recorded invocations, native relationship delivery,
model-visible proof and observable final-answer support separately. The terminal
ledger is complete relative to the retained host stream, not a guarantee against
an upstream host logging defect. Graph invocation with no useful proof is not
success. An exact non-graph answer may be fully successful.

Per case/condition, show every attempt's answer and accounting status, followed
by medians for calls, model-visible bytes, elapsed time and provider usage where
complete. With two repetitions, publish individual values and range as well as
the median; do not estimate population confidence, p95 or statistical significance.
Show incomplete/failed rows beside any complete-pair cost summary. Separate shell,
MCP, outer-round-trip and byte measures; do not conflate or double-count them.

For the local correction decision, prioritize a demonstrated owned failure and
its repaired real-host behavior. Post-change acceptance requires the selected
failure scenario to pass, every case to have sufficient source-supported answers
under the frozen rubric, and no material correctness regression. Report any
cost increase; do not claim efficiency unless the comparable complete rows
actually support it. Increased graph-call share alone cannot qualify a change.
If all baseline cases are already correct, a visibility correction may still
repair a demonstrated discovery failure, but answer-quality benefit remains
unproven. An inconclusive post-change outcome is recorded as such rather than
triggering more attempts.

The scoped evidence supports a local instruction/runtime/capture decision for
this repository and host. It cannot establish universal graph usefulness,
unprimed primary adoption, a Terra-versus-Astra ranking, or Claude behavior in
the inaccessible work environment.

Primary rows are explicit functional checks inside the ongoing primary turn,
not fresh completed task turns. Retain their native item/output IDs, verified
source/proof assertions and any limitations in a check artifact. Do not label
the entire audit turn as a per-case primary cost sample or invent a native final
message boundary. They establish usable primary-host retrieval and proof
delivery, while per-case provider cost and unprimed selection remain unknown.
The delegated adoption denominator is separate from these four checks.
