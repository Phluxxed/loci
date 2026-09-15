# Loci episode oracle receipt

The evaluator is `benchmarks.complete_work.oracles.loci` (schema 1) for
`loci-direnv-exclusion`.  It requires an isolated Git export of
`f3d9134aece5156bec1dcc302d4330522d1d96e5`, prepends that export's `src` to
the evaluator child process `PYTHONPATH`, and gives every behavioral fixture a
fresh `LOCI_BASE_DIR` below the supplied work directory.  Its dependency pin is
recorded in `benchmarks/complete_work/oracles/loci_environment.json`:
tree-sitter-language-pack 1.15.8, pathspec 1.1.1, mcp 2.0.0, PyYAML 6.0.3 and
pytest 9.0.2.

`baseline-receipt.json` is an untouched `/tmp/loci-episode-baseline.*` export.
It failed as expected: `nested_exclusion`, `incremental_terminal_state` and
`regression_deliverable` were false; the target-source import and dependency
pin checks passed.

`reference-patch-receipt.json` is a separate `/tmp/loci-episode-patched.*`
export carrying only the disposable-policy entry and the requested focused
policy/incremental regression tests.  It passed all checks: exact nested Python
and TypeScript exclusion, `.direnv-tools` and maintained-source controls,
path-safety `ValueError`s, existing `.gitignore` and `uv-cache` behavior, real
post-move index state/search, required regression artifacts and focused target
tests.

The evaluator's self-tests ran with:

```sh
.venv/bin/python3 -m pytest -q tests/test_complete_work_loci.py
```

and passed: `5 passed in 70.98s`.  They also prove controlled broad-name,
path-safety and stale-hash variants fail their corresponding oracle checks.

The receipt explicitly leaves orientation prose and the final human summary to
semantic/manual review.  Its regression-source inspection only verifies that
the requested policy and indexing tests exist and run; independently-created
fixtures determine terminal behavior.
