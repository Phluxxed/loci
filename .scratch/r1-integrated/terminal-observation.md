# Retain failed task attempts without qualifying missing observations

The ninth native attempt ended without investigating its task or writing an
answer. The agent copied a SHA constant incorrectly, causing the mandatory
capture checksum to fail, and stopped as instructed. Its native trace and usage
are complete, but no successful capture receipt exists. This is an incorrect
task outcome and an unqualified condition observation; it must not be repaired
into a success, repeated or replaced.

The existing frozen task oracle now runs after exact assignment/prompt, native
qualification, known usage and source-integrity checks even if the catalog or
rendered-context observation is unqualified. Task correctness and comparison
qualification are recorded separately. Unqualified observations remain excluded
from controlled condition comparisons; their actual task outcome, elapsed time,
usage and errors remain retained. Input/gate integrity failures and incomplete
native/accounting/source evidence still stop execution.

The existing runner accepts such a fully retained terminal attempt, validates
its archive and independent replay, and proceeds to the next scheduled assignment.
It does not change the task, scorer, model, capture program, prompts, conditions,
stores, order or native permissions. The [explicit amendment](terminal-observation-amendment.json)
records this distinction. It changes observation handling, not frozen grading.

214 focused checks passed. The full-run integration reproduces a ninth-attempt
checksum failure and no answer, retains its false oracle result and unqualified
comparison, and finishes all16 without another delivery of that session. A
separate ordinary wrong answer with valid treatment remains a qualified incorrect
outcome. Controlled-comparison eligibility is not selected from the answer score.

Actual archived ninth-run readback independently confirmed incorrectness,
known usage and matching frozen oracle replay. Its original index and evidence
were unchanged during review. [Machine evidence](terminal-observation-checks.json).

The already-waiting normal-Terminal runner receives the changed, hash-bound
amendment through its existing repair-request channel. No manual restart,
additional launcher, model retry or global configuration change is needed.
The interrupted task remains a measurement-induced failure in the final report;
the protocol's mandatory copy-and-execute step is a limitation of this pilot.
