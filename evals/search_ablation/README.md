# Local search and agent-discovery ablation

The corrected end-to-end study is specified in [agent-study.md](../../.scratch/search-ablation/agent-study.md), with findings in [AGENT-RESULTS.md](../../.scratch/search-ablation/AGENT-RESULTS.md) and per-assignment measurements in [agent-summary.json](../../.scratch/search-ablation/agent-summary.json). It starts agents from engineering questions and measures source-backed answer quality and cumulative provider token usage. The original mechanical replay below remains separate historical evidence.

`agent_provider.py` runs fresh Pi processes through Promptfoo, with native search/read tools in all three conditions: native only, normal Loci retrieval, and the same retrieval with graph expansion disabled. `pi_extension.ts` and `agent_loci.py` bind the existing service to a private trial repository/store. Both Loci conditions expose identical tool schemas. The disabled-expansion condition still indexes source, selects anchors and returns anchor ownership metadata; it is not a graph-free implementation.

The fixed study has three real-source investigation tasks, two repetitions and 18 assignments. Each starts with an unchanged source copy and empty index store. Instructions, model/effort, limits and balanced run order are fixed. Raw prompts, source, traces, answers, reviews and replay configurations remain ignored under `private/agent-v1`, `private/agent-cases` and `private/agent-review`. Nothing here configures the production server or global Pi/Codex settings.

The adapter counts each authoritative Pi assistant response once, plus reported compaction usage. Logical input includes uncached and cached input; output already includes reasoning. Missing/unreconciled counters and unknown failed-attempt consumption fail accounting qualification. Tool schemas, voluntary non-use, repeated conversation context and ordinary native fallback remain part of the measured integration.

`agent_cases.py` checks private factual expectations and authentic source quotations. Independent blinded source review supplies semantic judgments, bound to exact answer bytes. These are model judgments, not human acceptance. Promptfoo replays saved answers for grading without rerunning targets. The protocol records the original strict rubric and a disclosed correction where it required details absent from the task prompt.

Focused verification is in `tests/test_search_ablation_agent_provider.py` and `tests/test_search_ablation_agent_loci.py`; actual Pi tool/usage qualification and calibrated source review are retained privately. Fixture tests alone are not agent-success evidence.

## Original mechanical replay

This is the experiment on `experiment/search-ablation`, not a replacement for the production Loci server. See the [results](../../.scratch/search-ablation/RESULTS.md) and [frozen protocol](../../.scratch/search-ablation/spec.md).

`backend.py` wraps real ripgrep/tgrep CLIs and owns only its local subprocesses. `delivery.py` calls the existing R1 source implementation and the two controlled direct readers. `provider.py` runs each paired case through Promptfoo with one warmup and seven sequential, interleaved rounds. No model or remote grader is configured.

The actual source snapshot, query provenance, source requirements, binary, indexes and raw output are private and ignored under `.scratch/search-ablation/private/`. They are available on this machine, not distributed in Git. The suite checks byte/content equality and delivery completeness; it does not grade completion of the original engineering tasks.

## Recorded run

From this worktree:

```sh
npm --prefix /Users/brummerv/phluxxed/promptfoo run promptfoo -- validate config -c "$PWD/evals/search_ablation/promptfooconfig.yaml"
npm --prefix /Users/brummerv/phluxxed/promptfoo run promptfoo -- eval -c "$PWD/evals/search_ablation/promptfooconfig.yaml" --no-cache --no-share -j 1 -o "$PWD/.scratch/search-ablation/private/promptfoo-measured-v1.json"
```

The recorded `measured-v1` case files are protected against accidental overwriting. Do not rerun that command with the same label to replace results.

## Independent repeat on this machine

Keep the frozen files unchanged and verify the owning implementation matches the experiment's base:

```sh
git diff --exit-code 84d5179a42c5ee12d76031dd440c0ce8941d0e83 -- src
```

Create a separate invocation config from the retained export. The original YAML and frozen protocol stay unchanged:

```sh
python3 - <<'PY'
from datetime import datetime, timezone
from pathlib import Path
import json
root = Path.cwd()
private = root / '.scratch/search-ablation/private'
config = json.loads((private / 'promptfoo-measured-v1.json').read_text())['config']
label = 'replay-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
config['providers'][0]['id'] = 'file://' + str(root / 'evals/search_ablation/provider.py')
config['providers'][0]['config']['run_id'] = label
target = private / (label + '-config.json')
target.write_text(json.dumps(config, indent=2) + '\n')
print(target)
PY
```

Pass that printed config path to the same shared Promptfoo `eval` command and choose a new output filename. Run with concurrency one. The prepared pinned binary and immutable source index are reused; services are started/stopped per search case. A new corpus, changed query set or changed code requires a separately recorded protocol/freeze, not overwriting this evidence.

The source-delivery methods run inside Python with the project's existing environment, so timings exclude MCP/host transport. Direct and `direct_full_refresh` differ only by the actual repository inventory refresh; R1 versus the control still combines several presentation/serving differences. Read the limitations before attributing an effect.

Focused checks are in `tests/test_search_ablation_backend.py` and `tests/test_search_ablation_delivery.py`. The latter includes a synthetic multipage control proving that refresh actually occurs while direct packets remain identical. Synthetic fixture checks and assertion calibration do not substitute for the retained real-source results.
