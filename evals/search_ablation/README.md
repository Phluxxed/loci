# Local search and source-delivery ablation

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
