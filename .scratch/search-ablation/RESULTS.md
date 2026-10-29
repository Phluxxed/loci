# Search and source-delivery ablation

Historical mechanical replay. The corrected task-discovery and model-token findings are in [AGENT-RESULTS.md](AGENT-RESULTS.md); the measurements below do not answer that end-to-end question.

Completed 2026-10-28 on `experiment/search-ablation`, based on R1 commit `84d5179a42c5ee12d76031dd440c0ce8941d0e83`.

**The main measured cost is repository inventory refresh during already-located source acquisition.** A direct reader delivered the same required source in one call per case. Adding the actual repository refresh back to that otherwise identical reader restored most of R1's elapsed cost. The experiment supports simplifying that read path. It does not establish whole-agent task improvement or settle source ranking and graph usefulness.

The search comparison was mixed. tgrep did not improve the five recorded, scoped ripgrep searches on this 701-file snapshot. It accelerated two adapted repository-wide literal probes by about 40 ms each; one of those returned no matches. There is no basis here to replace ripgrep globally or expand the evaluation to obtain a preferred result.

## Source delivery

Each cell is the median of seven interleaved measurements after one warmup. All three modes delivered exactly the same required source bytes. Times are in-process service acquisition, including canonical response accounting, and exclude model inference, MCP transport, oracle preparation and receipt writes.

| Observed source requirement | R1 | Direct reader + full refresh | Direct reader | R1 / direct calls |
| --- | ---: | ---: | ---: | ---: |
| Viewer, lines 1–440 | 758.5 ms | 611.3 ms | 67.6 ms | 4 / 1 |
| JS service file | 620.9 ms | 620.6 ms | 65.5 ms | 2 / 1 |
| JS domain file | 687.6 ms | 644.1 ms | 69.0 ms | 3 / 1 |
| JS storage file | 626.6 ms | 634.5 ms | 69.2 ms | 2 / 1 |

The two direct modes use identical pages, addressing, output and requested-file checks. Their only difference is the actual existing `IntegratedSource.index_repo` refresh plus refreshed inventory validation before the read. Each selected span fits one direct page. This control isolates the inventory work under those conditions.

R1 versus the refreshed direct reader remains a combined comparison of previews, navigation, response framing, page limits and repeated eligibility checks. The service/storage elapsed differences are small or reversed; do not claim paging alone explains the large speed difference. What is deterministic is the reduction from 11 to 4 service calls across the four source requirements. This does not translate directly into model turns, which can contain batched calls.

The direct reader retains current eligibility, protected regular-file reads, the existing 2 MiB admission limit, UTF-8 boundaries, pinned content hashes, explicit errors and bounded output. It does not compute a repository-wide snapshot. Its page budget is 2,000 lines / 50 KiB; it is an experimental Python reader, not the actual Pi implementation. For larger requirements the refreshed control would refresh per direct page, whereas R1 refreshes on initial retrieval; these results do not cover that case.

The viewer span contains 18,781 bytes of a 456-line, 19,642-byte file. R1 delivered 861 extra unique bytes and 74 duplicate preview bytes. The other cases also repeated 49–75 preview bytes. These are recorded acquisition spans, not claims that every selected line is necessary or sufficient to answer the original tasks.

## Search backend

Both tools enumerated exactly the same 701 files / 10,062,803 bytes. Original rg patterns, scopes, case sensitivity and exclusions were preserved. Full matching-line results were compared; the recorded schema command's `head -80` output cap was not applied to either replay backend. Seven interleaved measurements followed one warmup. Timings include subprocess execution and output capture; tgrep's diagnostic `--stats` is included. Parsing and evidence writes are excluded.

| Case | rg | tgrep indexed condition | tgrep current scan | Indexed condition actually used |
| --- | ---: | ---: | ---: | --- |
| Recorded viewer search | 12.2 ms | 18.7 ms | 19.2 ms | Server/index |
| Recorded JS symbol search | 12.0 ms | 13.3 ms | 17.8 ms | Server/index |
| Recorded schema search | 7.7 ms | 9.7 ms | 10.0 ms | File scan |
| Recorded template search | 11.2 ms | 12.4 ms | 10.0 ms | File scan |
| Recorded results-reader search | 11.9 ms | 16.6 ms | 19.6 ms | Server/index |
| Adapted whole-repository symbol A | 54.6 ms | 14.1 ms | 112.3 ms | Server/index; zero matches |
| Adapted whole-repository symbol B | 52.8 ms | 13.7 ms | 111.0 ms | Server/index; 16 matching lines |

All warmup and measured results matched exactly by path, line and matching text. Natural-language and exact-path Loci requests were retained in the case provenance but excluded from grep comparisons because they have different meanings. The two adapted symbol probes are separate from the five recorded rg queries.

The predeclared materiality threshold was at least 10 ms and 20% median saving per query. No recorded rg case met it; both adapted probes did. These are local mechanism measurements, not population estimates or agent answer-quality scores.

The reference executable was ripgrep 15.2.0 (`e89fff89ac`). Pinned tgrep 1.2.5 came from Microsoft's arm64 macOS release, with its published asset digest verified. Its source revision is `0ef484c5b3bf9390520cfd3b97c8950a628f45f8`. The forced index rebuild took 145.3 ms with already-warm filesystem caches, and the index occupied 12,820,964 bytes. Per-case server readiness took 51.8–112.7 ms and is recorded separately from warm queries. Download/extraction and cold OS-cache behavior were not measured. RSS was unavailable under the sandbox.

In a separate synthetic edit probe, rg and `--no-index` immediately agreed on new content. The indexed server still returned the old match and omitted the new one at the last of 100 observations, 7.315 seconds after the edit. This is a bounded observation, not an estimate of eventual update time or a diagnosed watcher defect. It excludes indexed search as an immediate-current-source equivalent in that probe. Hidden-file, no-match and nonselective queries agreed; invalid regex was an explicit error in all modes.

## Verification and preservation

- Promptfoo 0.125.1: 11 cases passed, 0 failed, 0 errors; 231 measured trials plus 33 warmups. No LLM/provider API calls were made. Promptfoo's 11 local provider invocations are not model requests.
- Assertion calibration accepted two known-good summaries and rejected all four deliberately wrong summaries: mismatched result digest, missing source byte, missing trial and an error presented as a successful match.
- Fourteen focused implementation checks passed across the backend and delivery workers, including stale changes, containment, exact UTF-8 coverage and actual refresh invocation with identical direct packets.
- The original private snapshot and its experiment copy remained byte-identical. All seven measured servers were stopped by their owning context managers. No product `src/` file was changed.
- Both production/master heads remained unchanged. Global Loci skill and Pi settings hashes remained unchanged. The global Codex config hash changed during the experiment; this work made no edits there, and the change was not reverted or attributed. The deterministic run used frozen local code/cases and no agent configuration.
- Product Graph was read after the new instructions arrived. At revision `95c94f4ff1bcd846583e407b0101ceb55b7ae90b`, no Loci product, source registration or matching outcome existed. No outcome was invented or modified.

The [sanitized summary](summary.json) records per-case metrics, versions, freeze identity and evidence hashes. Raw source, commands, output, private cases, calibration and measured receipts remain ignored under `private/`. [Replay instructions](../../evals/search_ablation/README.md) describe the local prerequisites and exact target.

## Disposition

Keep the simpler known-source reader as the next implementation candidate: narrow validation to the requested source where the contract permits, and deliver adequate bounded source directly. Preserve the broader repository validation where relationships or repository-wide claims actually require it. Keep tgrep optional for broader repeated searches; these scoped cases do not support replacing rg by default.

No whole-agent campaign or product change was needed to answer this mechanical stage's question. Selection quality, voluntary use, graph benefit and task-level savings remain unmeasured; they are not declared successes or failures. A later deployment decision would need the relevant agent comparison. Production was not merged or deployed.

Worker results were adopted with qualifications. `/root/ablation_cases` supplied the private case/provenance files; the primary corrected the final path-list schema and stale notes before freeze. `/root/ablation_backend` supplied the pinned backend, focused tests and negative freshness probe. `/root/ablation_delivery` supplied the source comparison and, on reuse within its retained scope, the full-refresh control. The primary owns the frozen protocol, Promptfoo integration, final measurements and interpretation.
