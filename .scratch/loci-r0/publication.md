# R0 assessment publication scope

This commit publishes the R0 architectural assessment, its experiment/evidence records, the disposable runners and three existing supporting review documents. It does not integrate the experimental architecture changes or the pre-existing R0.1 benchmark implementation. R0.1 qualification reports describe that locally retained implementation and evidence; their implementation/raw qualification links may refer to files outside this assessment commit. The serving baseline is f41b3eaa4c7871c68972de5f760572a6bcbe1760.

Experiment worktrees are intentionally ignored. Final direct corpus runners, selection driver/diff, validation driver and parse driver are retained here. Recreate disposable worktrees from the serving baseline before running experiments; never point their stores at a production catalog. Absolute local paths in raw evidence identify the observed execution environment.

The existing queued pagination-policy commit f41b3ea precedes this assessment on master. Publication uses Phluxxed <tempest13@gmail.com>.

Whitespace verification excludes selection-diff.patch (unified-diff context prefixes) and the two generated cProfile text outputs (their terminal blank lines), preserving raw evidence bytes. The retained selection patch separately passes git apply --check against the serving source. All other staged files pass git diff --cached --check.
