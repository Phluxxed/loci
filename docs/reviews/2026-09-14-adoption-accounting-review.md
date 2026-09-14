# Ordinary adoption accounting and access review

Date: 14 September 2026  
Scope: frozen ordinary delegated runs `run-01` through `run-08`. This review
checks retained native accounting, run association, provider conditions and
recorded access. It does not grade answer facts or infer causal benefit.

## Conclusion

All eight attempts are usable as attempted ordinary-run records. Each selected
interval has a `task_complete` boundary, a final answer and cumulative provider
usage. All observed sessions match the scheduled OpenAI provider,
`gpt-5.6-terra` model and high effort, with no observer condition deviation.
For every run, the retained interval hash matches both capture metadata and the
observer artifact; its terminal IDs are unique and their set exactly matches
the separately normalized MCP and shell records. The detailed evidence is in
the [published access ledger](../../benchmarks/comparisons/ordinary-adoption-v1/runtime/ordinary-access-ledger.json).

The manual access review found no out-of-scope access among the 31 MCP calls and
69 shell commands actually retained. Every MCP `repo` argument names that
run's scheduled source copy. Every shell command is a read-only composition of
`pwd`, `rg`, `find`, `sed`, `nl`, `head` or `sort`, limited to the task copy,
installed Loci skill/reference files, and, in `run-04`, the permitted parent
`AGENTS.md`. Two searches exited 2 (`run-03` line 31 and `run-06` line 45), but
their full commands still contain no mutation. No retained shell command invokes
the Loci CLI, runs tests, starts a service, or reads a gold answer, another task
copy, unrelated repository source, or another session. This conclusion is deliberately
limited to retained terminal operations; terminal-only native logging cannot
prove that an upstream host operation was never omitted.

## Qualification boundary

The frozen observer's `complete_for_graph_use_claim` remains true only for
`run-01` and false for the other seven. Nine explicit read-only shell chains
were conservatively labelled `unknown` by the generic shell classifier: eight
as `shell_opaque_or_other`, largely because they include `pwd`, and one
`run-05` command as `shell_loci_cli` because its `rg --files` path contains the
word `loci`. Manual inspection qualifies those nine recorded commands as
read-only and in scope, but does not rewrite the frozen observer field. The
manual ledger can establish that the recorded commands contain no CLI graph
invocation; it does not turn a raw observer zero into a broad claim about
unrecorded activity. The distinction follows the frozen
[accounting contract](../../benchmarks/comparisons/ordinary-adoption-v1/accounting.md)
and is explicit per command in the ledger.

Four runs (`run-02`, `run-03`, `run-04`, `run-06`) have an actual native MCP
count of zero. That count is narrower than a statement that no retrieval
happened: all four used retained shell reads. `run-03` announced that Loci MCP
tools were unavailable, but its retained activity contains no MCP invocation or
discovery attempt supporting that announcement. Its recorded developer input
also lacks an `ALL_TOOLS` listing or the primary's explicit discovery hook,
although it does include the Loci skill catalog entry. The same recorded-input
shape applies to all eight runs, and tool declarations or system inputs not
present in the receipt remain unknown. See the local run receipt summarized in
the ledger and the frozen [condition definition](../../benchmarks/comparisons/ordinary-adoption-v1/conditions.md).

`run-08` reached and invoked the discovered `loci_search` and `loci_grep` tools,
so it is not a zero-call run. Both calls failed with
`REPOSITORY_CATALOG_REPAIR_REQUIRED`, reporting a pending interrupted catalog
mutation, and returned no source. Its paired `run-07` retained nine successful
Loci calls. The concurrent observations establish the two outcomes; they do not
establish that `run-07` caused `run-08`'s failure.

## Recorded retrieval

The eight attempts contain 31 MCP invocations: 29 completed without an
application error and the two `run-08` calls failed. No run used an explicit
`loci_graph_*` query.

- `run-01` used 15 exact-retrieval calls and one relationship-oriented
  `loci_explore`. The explore result contained four semantic relationships.
- `run-05` used four exact-retrieval calls and returned no semantic
  relationships.
- `run-07` used seven exact-retrieval calls plus two opt-in type-context gets;
  the retained packets contain 12 semantic relationships.
- `run-08` attempted two exact-retrieval calls, both application errors.
- The other four runs recorded no MCP calls.

These are invocation and delivery facts. Whether a delivered relationship
supported a correct answer belongs to the separate answer review.

## Cost evidence

Native-result bytes below use the observer's canonical compact JSON
serialization and are not wire sizes. Provider usage is the final cumulative
turn snapshot for each run and is not a sum of intermediate snapshots. Summed
tool duration can overlap under concurrency.

| Run | MCP (failed) | Shell | Outer | Native JSON B | Model output B | Shell output B | Source B | Elapsed ms | Tool ms | Provider tokens (out/reasoning) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 01 | 16 (0) | 4 | 16 | 1,480,664 | 146,581 | 28,830 | 42,648 | 153,556 | 45,844 | 799,426 (3,310/995) |
| 02 | 0 (0) | 10 | 5 | 0 | 130,248 | 470,875 | 0 | 52,759 | 2 | 224,534 (1,988/519) |
| 03 | 0 (0) | 4 | 4 | 0 | 83,770 | 108,120 | 0 | 50,052 | 0 | 211,944 (1,804/504) |
| 04 | 0 (0) | 8 | 4 | 0 | 58,875 | 58,683 | 0 | 48,150 | 2 | 156,344 (1,395/364) |
| 05 | 4 (0) | 3 | 7 | 7,413 | 62,365 | 21,580 | 374 | 63,178 | 15,212 | 278,902 (1,086/279) |
| 06 | 0 (0) | 14 | 6 | 0 | 116,509 | 168,640 | 0 | 71,004 | 101 | 282,938 (2,806/1,116) |
| 07 | 9 (0) | 4 | 6 | 56,111 | 115,495 | 56,549 | 12,721 | 94,447 | 37,670 | 278,011 (1,961/636) |
| 08 | 2 (2) | 22 | 10 | 988 | 243,780 | 1,237,889 | 0 | 104,950 | 34 | 611,528 (4,001/953) |
| **Total** | **31 (2)** | **69** | **58** | **1,545,176** | **957,623** | **2,151,166** | **55,743** | **638,096** | **98,865** | **2,843,627 (18,351/5,366)** |

The total provider input count is 2,825,276, including 2,483,456 cached input
tokens; the provider reports zero cache-write input tokens. Totals describe all
attempted runs and are not a matched-case efficiency result.

## Task association and retained limits

For every run, case, condition, repetition, role, purpose, prompt hash, source
root, requested model/effort, task source identity and agent task name match the
corresponding row in the frozen [schedule](../../benchmarks/comparisons/ordinary-adoption-v1/schedule.json).
Observed agent paths are `/root/inspection_01` through
`/root/inspection_08`, matching the scheduled task names. The primary
coordinator reports that spawn arguments used the exact scheduled prompts.
Native delegated assignment payload text is encrypted, so this review cannot
independently recompute the prompt hash from plaintext in the retained interval.

Whole native files remain local. The ledger republishes bounded terminal
arguments, IDs, source lines, interval hashes, accounting and receipt summaries;
it preserves each whole-file hash without copying the whole rollout. Recorded
developer receipts cover only retained developer-message text. They do not
establish what unrecorded tool declarations or system inputs contained.
