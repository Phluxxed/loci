# R1 pilot: Terra 6.1 / max

**Completed:** all 16 assignments are retained. See [results and recommendation](RESULTS.md). The command below is the original launch receipt; do not rerun completed assignments.

Prospective replacement run requested by Vik on 27 October 2026. All 16 assignments use `gpt-6.1-terra` with `model_reasoning_effort="max"`. [Official model documentation](https://developers.openai.com/api/docs/models/gpt-6.1-terra) lists the model and max effort. Subscription availability is checked by actual external execution; this preparation launches no model.

The original freeze and 11 retained Sol assignments are preserved. This run has its own freeze, execution index and archives under this directory, and the existing runner creates fresh source copies, independent stores and sessions. Tasks, source identities, prompts, independent graders, four conditions, tool schemas, schedule, candidate, qualification gate and protection evidence are unchanged. Existing accepted instrumentation repairs are pinned directly in this new freeze; no new repair or runner code was introduced.

The current global configuration differs from the original freeze. This revision records and pins its current hash without changing the file. Therefore earlier Sol attempts and this Terra pilot have different environment identities; do not pool them or attribute differences solely to model. The runner still verifies the new hash and all other environment pins before execution. Model/effort are command-local overrides; the global defaults are not edited. Prior API trouble remains unconfirmed.

## Execute from a normal top-level macOS Terminal

The following calls the **existing** `pilot-execute.py` orchestration function with a separate result directory. No new launcher, sandbox or permission profile is used. Run once; the existing runner retains errors and stops on launch, qualification or telemetry failure. Do not retry a failed measured assignment automatically.

```sh
cd /Users/brummerv/phluxxed/loci/.worktrees/r1-integrated
PYTHONPATH=src:. /Users/brummerv/phluxxed/loci/.venv/bin/python -u - <<'PY'
import json
import runpy
from pathlib import Path

base = Path('.scratch/r1-integrated').resolve()
root = base / 'pilot-terra-max'
runner = runpy.run_path(str(base / 'pilot-execute.py'))
print(json.dumps(runner['run'](
    root / 'freeze.json', base / 'qualification-gate.json', None, root,
)), flush=True)
PY
```

For a read-only preflight, add `check_only=True` to the `run` call. For an interrupted run whose retained prefix passes the existing checks, use `resume=True`; the runner refuses silent retries of pending attempts. The freeze fails closed if pinned settings change again. It checks existing ChatGPT login before execution and removes API-key/base-URL environment overrides as before.

Results will appear in this directory's `execution-index.json` and `archived-runs/`. Every assignment emits execution and evaluation JSON lines; 16 assignments can produce more than 16 output lines. All 16 Terra results now exist. `validation.json` remains the original no-launch preparation receipt; measured results and the recommendation are in `RESULTS.md`.
