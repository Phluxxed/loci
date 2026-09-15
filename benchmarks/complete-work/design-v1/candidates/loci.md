# Candidate: disposable `.direnv` directories across incremental indexing

## Scope

Run this three-turn Python maintenance episode against a clean worktree at
`f3d9134aece5156bec1dcc302d4330522d1d96e5`.  The target is ordinary
repository discovery/index maintenance, not retrieval selection, graph
construction, benchmark instrumentation, or MCP transport.  The evaluator
must keep the same user prompts and terminal checks in both arms.  It must not
carry an implementation patch from one arm to the other.

The episode is grounded in the current policy and scan path:

* `EXCLUDED_DIRECTORY_NAMES` does not contain `.direnv`
  ([src/loci/indexability.py](/Users/brummerv/loci/src/loci/indexability.py:14)).
  `repository_path_exclusion_root` checks every repository-relative path
  component against that set ([src/loci/indexability.py](/Users/brummerv/loci/src/loci/indexability.py:65)),
  and `source_exclusion_reason` returns `policy_excluded` when it finds one
  ([src/loci/indexability.py](/Users/brummerv/loci/src/loci/indexability.py:75)).
* Repository discovery calls that policy before it treats a candidate as a file
  or applies `.gitignore` ([src/loci/service.py](/Users/brummerv/loci/src/loci/service.py:2318)).
  It therefore never adds policy-excluded source to `indexable_files`
  ([src/loci/service.py](/Users/brummerv/loci/src/loci/service.py:2369)).
* An incremental index rebuilds `new_file_hashes` and the symbol collection
  only by iterating the current `indexable_files` ([src/loci/service.py](/Users/brummerv/loci/src/loci/service.py:274)).
  This is the reason an already indexed path moved under a newly excluded
  directory should disappear after the next incremental index.
* Existing unit coverage distinguishes maintained test/fixture source
  ([tests/test_indexability.py](/Users/brummerv/loci/tests/test_indexability.py:11)),
  disposable nested paths ([tests/test_indexability.py](/Users/brummerv/loci/tests/test_indexability.py:25)),
  non-relative path rejection ([tests/test_indexability.py](/Users/brummerv/loci/tests/test_indexability.py:56)),
  and an end-to-end nested `uv-cache` exclusion
  ([tests/test_cli.py](/Users/brummerv/loci/tests/test_cli.py:54)).

At this revision `.direnv/lib/site.py` is a supported Python file because its
directory component is absent from the policy set; it is thus scanned and can
be indexed.  Requested behavior is to treat a directory component exactly
equal to `.direnv` as disposable at any repository depth.  This must not turn
lookalikes such as `.direnv-tools` into excluded paths, nor affect normal
siblings.

## Exact user prompts

### Step 1 — orientation, read-only

> A support report says our index includes Python installed under project-local
> `.direnv` environments. Before changing anything, trace how a
> repository-relative path is excluded during indexing and say whether adding
> `.direnv` to the disposable-directory policy would also remove an
> already-indexed file after an incremental reindex. Give the relevant code and
> test locations, the current behavior, and the smallest safe change. Do not
> edit files.

Step-1 terminal acceptance:

1. The answer correctly identifies the missing policy member and the
   component-wise (not substring) check.
2. It connects policy classification to repository scanning and explains why a
   new incremental result is rebuilt without omitted paths; it does not claim
   that merely editing the set mutates an existing stored index.
3. It names a focused policy-test location and an indexing-boundary test
   location, and leaves the worktree unchanged.

### Step 2 — bounded useful change

> Implement the smallest safe fix for that support case: treat any repository
> directory named `.direnv` as disposable, so source below it is not indexed.
> Add focused coverage at the policy boundary. Keep maintained sources and the
> path-safety behavior intact.

Step-2 terminal acceptance:

1. `.direnv` is added once to the directory-name policy in
   `src/loci/indexability.py`; no retrieval, graph-selection, CLI, or unrelated
   ignore behavior is changed.
2. A policy test proves both `is_excluded_repository_path` and
   `is_indexable_source_path` classify a nested path such as
   `tools/.direnv/lib/site.py` as excluded/non-indexable.
3. The focused test also proves a maintained source remains indexable and that
   the existing absolute/`..` rejection stays a `ValueError`.  A lookalike such
   as `tools/.direnv-tools/site.py` remains indexable, proving exact-name rather
   than prefix/substr matching.
4. Existing `.gitignore` behavior and `uv-cache` exclusion still pass; a
   solution that only filters a top-level `.direnv`, only filters Python files,
   or silently broadens the policy fails.

### Step 3 — follow-up extension using prior understanding

> Follow-up: add a regression at the indexing boundary for an already-indexed
> repository that moves a Python source file under a `.direnv` subtree before
> an incremental reindex. Its symbol must disappear from the index while a
> normal sibling source stays searchable. Keep the new policy confined to the
> exact directory name.

Step-3 terminal acceptance:

1. The regression first indexes two distinct Python symbols in a temporary
   repository. It then moves one source to a nested `.direnv` directory,
   performs `index_repo(..., incremental=True)` (or the equivalent CLI
   incremental invocation), and proves the moved symbol is absent while the
   unchanged sibling is still present.
2. The test uses a fresh `LOCI_BASE_DIR`/temporary store and asserts the result
   after the incremental invocation, rather than checking only the pure policy
   function or relying on test order.
3. A nested location is used (for example
   `tools/.direnv/lib/site.py`) so the component-wise path policy is exercised.
   A `.direnv-tools` negative case remains indexable either in this test or the
   focused policy test from step 2.
4. The implementation must not preserve stale symbols or hashes for the moved
   file. It must not delete unrelated sibling symbols, alter `.gitignore`
   semantics, or suppress all dot-directories.

## Relevant verification commands

The episode author does not execute these commands.  The benchmark evaluator
may run them in its isolated worktree after the appropriate step:

```sh
.venv/bin/python -m pytest -q tests/test_indexability.py
.venv/bin/python -m pytest -q tests/test_cli.py -k 'gitignore or uv_cache or direnv'
.venv/bin/python -m pytest -q tests/test_service.py -k 'direnv or incremental'
```

For step 3, the evaluator should also inspect the actual temporary-store search
result required by the new test.  Existing deletion/reindex coverage provides a
nearby precedent for testing that stale indexed items vanish after a scan
changes ([tests/test_service.py](/Users/brummerv/loci/tests/test_service.py:1451)).

## Why retained context can help

Step 1 establishes the otherwise non-obvious relationship between the
component-level policy, `_scan_repository_files`, and incremental replacement
of file hashes/symbols.  Step 2 applies the local policy correction and records
the exact-name negative case.  In step 3, retaining that understanding avoids
re-discovering where scanning happens and avoids a plausible but incomplete
follow-up that tests only `is_indexable_source_path` or assumes incremental
indexing retains old records.

The graph-context arm may use its normal source-retrieval facility while the
comparison arm uses its ordinary allowed navigation.  Neither arm receives a
graph-use hint in the prompts.  Completion is scored by the step-specific
terminal checks above, then by the verification results and the count of
navigation/tool calls and repair turns required to reach them.

## Setup limits and evidence record

The live checkout contains unrelated skill and scratch dirt, so evaluation must
start from an isolated checkout of the stated commit and preserve that dirt.
No service, dependency installation, provider trial, product change, or test
execution was performed while authoring this candidate.

Normal Loci packets were saved during authoring under
`loci.normal.tools`, `loci.normal.retrieve.contract`,
`loci.normal.read.contract`, `loci.retrieve.cli-config.1`,
`loci.retrieve.case.2`, `loci.retrieve.case.3`,
`loci.retrieve.case.4`, `loci.read.indexability.1`, and
`loci.retrieve.test-indexability`.  They reported partial, non-exhaustive
static coverage, including the import relationship from `service.py` to
`indexability.py` and the test-to-policy calls.  Direct source reads supplied
the line-level behavior cited above; no conclusion relies on an omitted edge.
