# R1 replacement pilot: real-source inputs qualified, native execution pending

Current state: [capture and archive recovery are repaired and tested](capture-recovery-repair.md).
The original failed probes remain retained. The amended capture protocol needs
fresh top-level qualification before the 16 scored assignments. The current
command and its explicit measurement-prefix amendment are in the linked report;
the command below is historical and must not be rerun unchanged.

The replacement uses a pinned source-only snapshot of the maintained
kaggle_lab repository, rather than generated toy repositories. No replacement
scored agent run has started. An unscored native probe closed successfully but
the reader rejected a normal startup hook; the [reader repair and retained
replay](startup-hook-repair.md) correct that classification without changing
the freeze. The existing four-condition native runner, subscription
authentication, Terra6.1/max model setting, Williams order, independent stores,
native tool access, accounting and replay are retained.

The source pool contains 701 regular files and 10,062,803 bytes from commit
6909e457491f8cd2e3269dfbea4bf436fe3cf091. Files come from tracked source,
project/schema configuration and relevant guidance. Raw competition data,
predictions, notebook outputs, graph stores, credentials and untracked work
are excluded. The working source repository and its pre-existing untracked
entries were verified unchanged.

Four tasks cover an easy shared-helper location, a JavaScript HTTP mutation
contract across modules, uncertainty in Python's dynamic model loading, and
a bounded TSV reader compatibility change. Astra independently checked source
facts and task suitability. Two required rubric corrections were adopted before
freeze: explicit grading of changed-identity refusal and support checks beyond
authentic but unrelated quotations. Output types and allowed edits, including
a persistent regression test, are published in each prompt.

Three tasks use Python, where integrated semantics are unsupported. This set
primarily evaluates real source acquisition; the single JS task provides one
supported semantic opportunity. File count does not establish difficulty.
These authored engineering tasks and four paired observations cannot establish
population superiority. Efficient native navigation is a valid outcome.

## Qualification retained

- 59 reference/negative task controls matched, using the project's installed
  Python3.12.13 and synthetic temporary TSVs. No scientific workloads ran.
- The actual frozen R1 replay path accepted four reference outcomes, including
  the explicitly allowed regression test, and rejected a forbidden extra edit.
  These are offline controls, not native pilot attempts.
- The relevant harness/legacy/resume/host-observation suite passed 179 tests.
- The candidate and eager-reference implementation hashes match the prior
  qualified inputs. The original deterministic gate remains unchanged.
- The fixed metadata program ran in actual Code Mode: 619 common tool
  descriptors, 882,089 UTF-8 bytes, produced a 198-byte receipt whose SHA-256
  matched independent Python hashing. Full descriptions are fingerprinted,
  not exported; the fingerprint alone cannot reconstruct their contents.

Reproduce the 179-test harness check:

~~~sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:. \
  /Users/brummerv/phluxxed/loci/.venv/bin/python -m pytest -q -p no:cacheprovider \
  tests/test_complete_work_common_context.py tests/test_complete_work_availability.py \
  tests/test_complete_work_r1_availability.py tests/test_complete_work_r1.py \
  tests/test_complete_work_r1_resume.py tests/test_complete_work_host_observations.py
~~~

New freezes opt in with common_context=true. Each condition gets the same
supported per-invocation skills.include_instructions=false override and a
frozen capability card. This changes no global files or sandbox/profile.
All normal native tools remain available and Loci calls remain voluntary.
Probe fixtures retain the task source's exact root instructions.

Before scoring, the existing runner verifies positive native operations for
all four conditions and compares actual common rendered instructions, native
tool schemas and the common deferred-tool catalog fingerprint. It checks each
measured trace against that qualified context before its oracle runs. Typed
instruction drift fails closed; normal source text in tool outputs remains
permitted. The same readback handles resume. Old freeze artifacts and original
scores were not rewritten.

Local frozen identity:
36fe5f559905891e4079eaa6a81aeeaa8623c4e21420183683ef72ecc5803c04.
It schedules exactly 16 fresh assignments. Local freeze validation and replay
passed. Live top-level native-host qualification is still unverified; no
correctness/time/token or semantic-benefit result is claimed for this set.

## Retention and next execution

GitHub reports Loci public and kaggle_lab private. The detailed source,
prompts, oracles, review, controls and freeze are retained locally under
.scratch/r1-integrated/real-repo-pilot/ and explicitly ignored on this
experimental branch. They must not be staged into the public Loci remote.
Public changes contain harness code/tests and this sanitized report.

The current Codex session cannot supply the required normal top-level host.
Prior launchd submission failed, and no relevant host condition changed.
No nested Codex, new launcher, sandbox/profile modification or repeat
submission was attempted. From normal macOS Terminal, the existing runner
automatically performs preflight, then the 16 assignments only if it passes:

~~~sh
cd /Users/brummerv/phluxxed/loci/.worktrees/r1-integrated
PYTHONPATH=src:. /Users/brummerv/phluxxed/loci/.venv/bin/python -u \
  .scratch/r1-integrated/pilot-execute.py \
  --freeze .scratch/r1-integrated/real-repo-pilot/frozen-final/freeze.json \
  --gate .scratch/r1-integrated/qualification-gate.json \
  --amendment .scratch/r1-integrated/startup-hook-instrumentation-amendment.json \
  --output-root .scratch/r1-integrated/real-repo-pilot/execution-reader-v1
~~~

If native qualification fails, its error/evidence are retained and measurement
stops. Do not change the frozen set in response to scored performance.

Recommendation remains **hold advancement pending usable agent evidence**.
Local qualification supports attempting this bounded replacement; it supplies
no new architecture ranking or evidence that optional semantics helped.
