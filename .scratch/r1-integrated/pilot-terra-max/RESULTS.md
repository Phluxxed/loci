# R1 native comparison: availability unverified; recommendation withdrawn

The 16 Terra runs completed and their accounting and frozen grades remain retained. **They do not establish a valid Loci condition comparison:** no measured native-host check established that the assigned tools were discoverable and callable. The architecture recommendation previously derived from this comparison is withdrawn. Lack of tool use does not prove tool absence, particularly with deferred discovery.

See the [validity correction](../availability-repair/validity-correction.json) and [availability repair](../availability-repair/README.md). The old scores are descriptive records only. Source/proof deterministic qualification remains separate and is not invalidated by this missing native-host gate.

---

## Prior report retained for history; comparative conclusions superseded

# R1 native pilot completed: Terra 6.1 / max

**Recommendation: revise; hold advancement.** The integrated implementation remains deterministically qualified, but this pilot provides no evidence that its optional semantics or focused proof improved agent work. None of the 16 agents discovered or invoked a Loci operation in recorded actions. Official completion scores differ, but the failed scores reflect nested answer representation or test-file allowlists rather than a demonstrated failure to acquire necessary source information. No candidate, evaluator, prompt, score or measured attempt was changed after execution.

This is the bounded exploratory pilot, not evidence of superiority or a rejection of semantic analysis. The requested execution and evidence review are complete; no additional run or production integration is proposed as part of this task.

## Frozen execution and integrity

- Four independently constructed JS engineering problems × native, path-only, integrated and production eager reference; all 16 scheduled assignments retained. Fixed balanced order, original task snapshots/prompts/oracles/tool configurations and independent source copies/stores.
- Actual model contexts: `gpt-6.1-terra`, effort `max`, 16 distinct fresh native threads. Existing ChatGPT login and original native execution path; no API keys, global changes, additional sandboxes, permission profiles, launcher or harness. Preparation and offline analysis did not launch pilot models.
- Terra freeze `339b51aba273ae36fb56f0aac13ad6db9b33b128a476b9071149fd5e336fc91d`. All measurements closed, all native qualifications passed and all reported usage is known. Native error lists and exec stderr are empty; 14 failed shell attempts are retained separately. No current evidence of provider/API failures within these 16 traces; invisible retries remain unknown.
- [Independent archive replay](analysis/independent-replay/summary.json): 16/16 source/config/trace/receipt bindings validate, and all replayed official outcomes agree. Existing `r1.replay` reads archived content-addressed bytes through copied manifests with only observer remapped; no live workspace/source history is used. Every remap and invocation is retained.
- [Blinded review](analysis/manual-review.json): all 16 opaque case packets reviewed without condition labels, usage or traces. Frozen oracles were rerun and independent behavior checked. The [key](analysis/blinding-key.json) was applied by the primary only after review completed; no replacement score was created.
- The [model revision](revision.json) preserved the earlier Sol freeze and attempts separately. Global config had independently drifted before the Terra freeze; current config was pinned read-only. Do not pool Sol and Terra or attribute differences solely to model.

## Task-level results

Each cell is **official result · elapsed seconds · total provider-reported tokens**. “Fail” is the unchanged frozen oracle plus file allowlist outcome. Elapsed is CLI subprocess launch-to-exit, including startup and task execution; it excludes offline grading/replay. Complete wall time through original grading was not recorded and remains unknown.

| Task | Native | Path-only | Integrated | Eager |
|---|---:|---:|---:|---:|
| receipt-location | Fail · 46.56s · 128,819 | Fail · 37.87s · 100,388 | Fail · 43.17s · 149,904 | Fail · 33.58s · 101,190 |
| inventory-contract | Fail · 34.77s · 123,806 | Pass · 51.94s · 127,634 | Pass · 51.66s · 153,049 | Fail · 43.74s · 127,530 |
| dispatch-ambiguity | Pass · 39.51s · 123,407 | Pass · 40.12s · 125,312 | Pass · 44.25s · 124,478 | Pass · 39.79s · 152,374 |
| zero-quantity | Fail · 72.26s · 188,506 | Fail · 63.01s · 187,526 | Pass · 74.20s · 160,270 | Pass · 47.68s · 151,732 |

The official outcomes must be read with these diagnostic qualifications:

- **receipt-location:** all four found the billing owner, correct outbound route and example key. The frozen oracle requires bare-symbol strings in `call_chain`; agents supplied path-qualified strings or `{file, symbol}` objects. The visible prompt specifies ordered symbols and exact top-level keys, but gives no nested JSON element schema and also requests paths and symbols. The oracle stops at equality before its runtime checks; the blinded review separately verified behavior.
- **inventory-contract:** all four identified the right files and values. Native/eager supplied `{path, symbol}` entries where the frozen oracle requires file strings. Path-only/integrated used file strings and passed. The diagnostic distinction concerns representation, not missed dependency/type-contract information.
- **dispatch-ambiguity:** all four passed, correctly retained runtime-dependent dispatch and excluded the legacy handler. Review found no unsupported unconditional target or missed required source fact.
- **zero-quantity:** all four source changes passed the frozen behavioral oracle, including zero, invalid input and unchanged CLI behavior. Native/path-only additionally added `test/api-quantity.test.js`, outside the frozen two-file allowlist. That exact allowlist was not in the agent-visible prompt, which requests a relevant check. Those two official failures remain failures; they do not establish incorrect API behavior.

## Usage and effort

Totals below include all four attempted assignments, including failures. They are descriptive effort totals, not efficiency rankings across unequal outcomes. Cached input is a subset of input; reasoning is a subset of output. Do not add either subset to total tokens. Usage is observed provider reporting, not complete billing or invisible retry accounting.

| Condition | Official completion | Elapsed sum (s) | Input | Cached input | Uncached input | Output | Reasoning subset | Total tokens | Outer calls | Shell calls | Edits | Failed shell |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| native | 1/4 | 193.10 | 550,053 | 486,656 | 63,397 | 14,485 | 9,430 | 564,538 | 18 | 28 | 5 | 5 |
| path-only | 2/4 | 192.94 | 526,573 | 484,736 | 41,837 | 14,287 | 8,036 | 540,860 | 17 | 31 | 1 | 4 |
| integrated | 3/4 | 213.28 | 572,030 | 509,440 | 62,590 | 15,671 | 9,413 | 587,701 | 19 | 31 | 3 | 2 |
| eager | 2/4 | 164.80 | 520,607 | 470,144 | 50,463 | 12,219 | 6,816 | 532,826 | 17 | 41 | 1 | 3 |

Across the retained attempts: 764.12 seconds of summed launch-to-exit time, 2,225,925 reported tokens (1,950,976 cached input, 218,287 uncached input and 56,662 output), 71 outer Code Mode calls and 131 shell operations. Parallel nested operations are counted separately; their durations are not added to elapsed. No aggregate quality score or cost-per-success ratio is introduced.

For comparable official successes, native was fastest and lowest-token on dispatch (39.51s, 123,407 tokens). Path-only and integrated had nearly equal inventory time (51.94s vs 51.66s), with fewer tokens for path-only (127,634 vs 153,049). Eager used less time and fewer tokens than integrated on zero-quantity (47.68s/151,732 vs 74.20s/160,270). These single task/condition observations cannot be attributed to Loci: it was never called.

| Condition | Observed tool-response text bytes | Command-output text bytes | Agent MCP calls | Optional semantic requests | Focused proof requests |
|---|---:|---:|---:|---:|---:|
| native | 10,617 | 7,566 | 0 | 0 | 0 |
| path-only | 15,215 | 10,223 | 0 | 0 | 0 |
| integrated | 10,653 | 7,169 | 0 | 0 | 0 |
| eager | 13,835 | 8,096 | 0 | 0 | 0 |

Tool-response bytes sum text parts in retained native tool output records. Command-output bytes sum completed command item output. These overlap and mix source, metadata and checks, so neither is exact source-only acquisition or total context. Native source-only byte counts, acquisition-only time, unique delivered context and exhaustive repeat-read attribution remain unknown. Exact commands and outputs are retained; [metrics.json](analysis/metrics.json), [metrics.csv](analysis/metrics.csv), [tool-attribution.json](analysis/tool-attribution.json) and [command-index.json](analysis/command-index.json) make the definitions and evidence inspectable.

## Acquisition, discovery and uncertainty

All observed outer calls were Code Mode `exec`; their bodies used native shell/edit operations. There were no recorded `ALL_TOOLS`/tool-search requests, direct MCP calls, local Loci imports, semantic requests or focused proof requests. Thus observed Loci source/proof delivery was zero. Empty eager startup traces are not assumed: four eager startup files explicitly show store binding and stdio entry (~635–731ms); they do not establish graph construction. Deferred runtime MCP catalogs were never queried by agents. The pilot establishes no agent use; it cannot distinguish rational avoidance on tiny sources from discoverability problems or verify actual per-turn deferred-tool availability.

Acquisition was through lexical shell search and full tiny-file reads, followed by executable checks. The blinded source review identified no necessary source fact missed and no unsupported relationship claim in the answers. All four agents handled the dynamic dispatch uncertainty explicitly. No Loci relationship was emitted or promoted to proven in this pilot because no proof was requested; relationship integrity and cache invalidation remain covered by the separate deterministic evidence.

Repeated effort is visible without inventing a complete classification: inventory path-only reread the same five active files with line numbers after initially reading them; receipt agents searched source and then read the same files fully. That overlap can aid orientation, so it is not all labeled waste. Additional Git-status attempts failed in intentionally non-Git exports, and missing AGENTS/test-file searches often exited 1. All 14 failed shell attempts recovered and every session closed normally. No measured API recovery or semantic-cache cost exists in these trajectories.

## Recommendation and limits

**Revise; do not advance the integrated architecture to production on this evidence.** Keep the experimental implementation and its qualified capabilities. Its earlier combined deterministic evidence remains material: 288 replayed executions, zero integrity failures/forbidden proven claims, with source coverage 180/187 integrated versus 185/187 source-only and higher measured integrated acquisition cost. The native pilot resolves the launch blocker but supplies no benefit evidence for optional analysis or proof, and its official correctness contrast is dominated by representation/allowlist policy.

Any future pilot should prospectively clarify agent-visible nested schemas and permissible test changes and establish whether optional tools can be discovered, while retaining native tools and voluntary use. Those are follow-up recommendations, not changes made to this scored experiment. No additional execution, evaluator tuning, speculative routing or production integration was performed.

Python/Go semantics remain unsupported. The pilot uses four small constructed JS problems, not maintained-repository coverage or a statistical superiority test. TS/Rust semantics, mutation invalidation and consumer native uncertainty were qualified deterministically but not exercised by these agents. Complete provider billing, invisible retries, exact native source acquisition costs and runtime tool discoverability remain unestablished. No launch blocker remains for the completed run; remaining gaps limit interpretation.

## Retained evidence

- [Frozen experiment](freeze.json), [revision and environment lineage](revision.json), [original no-launch preflight](validation.json), [execution index](execution-index.json), and all 16 `archived-runs/` source copies, raw native rollouts, execution output/stderr, native accounting, graded receipts, replay receipts and content-addressed source blobs.
- [Original deterministic gate](../qualification-gate.json), [implementation usage](../../../docs/r1-integrated.md), [combined architectural report](../RESULTS.md).
- [Independent replay summary](analysis/independent-replay/summary.json), per-run replay invocations/config remaps and frozen-oracle output; [blinded packets](analysis/blinded/cases.json), [review](analysis/manual-review.json), [unblinding key](analysis/blinding-key.json).
- [Per-task machine comparison](analysis/comparison.json), reproducible retained-evidence [summarizer](analysis/summarize.py), metrics/CSV, native tool attribution, command index, publication inventory and review.
