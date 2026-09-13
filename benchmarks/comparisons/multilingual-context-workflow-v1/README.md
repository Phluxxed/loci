# Multilingual workflow measurement

Manifest task: `task_ecbfc0ce724b713f2599830d21438a46`.

[Protocol](protocol.md) defines the intervention, fixed 114-attempt schedule,
budgets and independent per-language decisions. [Controls](inputs/comparison-controls.json)
contain the exact common prompt and B workflow guide. The evaluator input view
copies the original multilingual corpus/archive byte for byte; its extra controls
do not modify the corpus or become available through the task's repository tools.

A exposes exact source retrieval and explicit graph tools. B adds the implemented
`loci_explore` and a short usage guide. This measures that workflow package on
five Python tasks, four each for JavaScript, Go and Rust, one TSX control and one
Markdown navigation control. It establishes no broader language or runtime claim.

Preparation retains a current host/model catalog, actual no-provider Codex/MCP
transport evidence and actual source/relationship scorer proofs. The preparation
commit precedes a separate published `freeze.json`. Validation compares engine,
harness, scorer, inputs, prompts, configuration, environment and proof hashes
before allowing the provider runner to start.

Run from the isolated checkout with its `.venv/bin/python`. The runner requires
the explicit retained catalog and published freeze:

```sh
.venv/bin/python -m benchmarks.multilingual_context_freeze validate
.venv/bin/python -m benchmarks.multilingual_context_compare --mode run --catalog benchmarks/comparisons/multilingual-context-workflow-v1/host-preflight/model-catalog.json --output benchmarks/results/multilingual-context-workflow-v1
.venv/bin/python -m benchmarks.multilingual_context_replay benchmarks/results/multilingual-context-workflow-v1
```

The runner retains each attempt before moving to the next slot. It never
overwrites an attempt or retries correctness/provider failures. `--resume` accepts
only an unchanged, fully recorded serial prefix. An interrupted partial attempt
is retained and needs an explicit disposition; it cannot be silently rerun.

Raw artifacts contain exact model-visible MCP text, CLI events, provider token
usage, timing, source inventories and a local effective-request audit. Production
provider HTTP bodies are not captured. The selected model name is pinned; the
provider does not expose a backend snapshot identity. Token counts imply neither
API dollar prices nor ChatGPT subscription-credit costs.

Every planned slot remains in its language's denominator. Independent replay
rebuilds indexes and reconstructs source, relationship, answer and usage scores.
The report retains all pass/fail outcomes and applies the already-declared rules.
Historical TypeScript artifacts and verdicts remain unchanged. This task neither
integrates code nor promotes a shared installation.
