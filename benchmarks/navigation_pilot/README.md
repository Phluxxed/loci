# Three-condition navigation pilot

## Current result

**Blocked before model generation. No comparison results yet.**

Codex CLI `0.159.2` initialized successfully and advertised
`gpt-6.1-sol` with high reasoning. Its strict filesystem command canary failed
with exit code **71** and:

```text
sandbox-exec: sandbox_apply: Operation not permitted
```

The ordinary launch and an approved escalated launch failed identically.
Neither started a model turn. This is a local runtime failure, not evidence
about any of the three navigation conditions. Time, token use, and correctness
for those conditions are **unavailable**, not zero.

See [host-blocker.json](host-blocker.json),
[ordinary receipt](preflight-ordinary.json), and
[escalated receipt](preflight-escalated.json). Raw probe paths and hashes are
retained in the blocker receipt.

The finished adapter was also run with `--preflight-only`. All three conditions
reproduced exit 71; its [receipt](host-preflight/result.json) and per-condition
wire journals are retained under `host-preflight/`. No `turn/start` was sent.
Archive/setup took 9.3 seconds and total preflight took 12.4 seconds; these are
setup measurements, not agent task timings. Compile and three focused runner
checks passed. Live tool inventories, model-turn telemetry, and answers remain
unverified because preflight stopped before thread creation.

## Frozen comparison

| Condition | Navigation available | Loci commit |
| --- | --- | --- |
| Vanilla Codex | Ordinary local Codex tools; no MCP navigation tools | None |
| Production Loci | Same tools plus normal `loci_retrieve` / `loci_read` | `9655a287` |
| Source context Loci | Same tools plus normal `loci_retrieve` / `loci_read` | `180a886c` |

All receive Ember commit `85969df8`, the same question and instructions,
`gpt-6.1-sol` / high reasoning (verified from this session's turn metadata),
and a five-minute turn limit. Sessions are fresh;
ambient apps, hooks, memories, host skills, project instruction discovery,
other MCP servers, web search, and delegation are disabled equally.
The two Loci servers retain their respective product tool descriptions. Each
Loci arm also receives its pinned `skills/loci/SKILL.md` as operating guidance;
vanilla receives no Loci guidance. This instruction overhead counts toward token
usage. Skill reference documents and serving source are not exposed.
Loci use is optional; failure to use an available tool is an observable result.

The task asks the agent to trace proposal approval, dependency reconciliation,
status and chat context, and refusal of stale-ready Work. It crosses five
implementation owners. The prompt contains no file locations or helper names.
The [frozen case](case.json) contains six source-backed scoring facts and the
required source list. It is observer material and must not be visible to trial
agents. Its SHA-256 was recorded before any trial output:

```text
a22c11fb0561051c8975163254101b3d9480f0a4f9c3d34f5acd5c0a6ef939de
```

Each condition receives a separate Git archive, rather than a Git worktree:
Loci canonicalizes worktrees to their main repository's cache identity.
Each Loci arm gets its own store and an exact-target repository guard. Serving
source, the oracle, and other arms' captures stay outside trial access.
Indexes start cold; their first-call cost belongs to the observed trial.
Startup and preflight time are recorded separately from model-turn elapsed time.
Production installation, original repositories, and user configuration are
never modified by the runner.

## Run from a terminal

The runner includes a strict preflight before any model turn. An ordinary
terminal launch may avoid this session's runtime restriction; it still must
pass that check. It stops rather than changing permissions if the check fails.

From the isolated branch:

```sh
cd /Users/brummerv/phluxxed/loci-scalpel
/Users/brummerv/loci/.venv/bin/python -m benchmarks.navigation_pilot.run --output "$HOME/phluxxed/tmp/loci-navigation-pilot-20260930"
```

Outputs live under `~/phluxxed/tmp`, outside the repositories and outside system
temporary storage. The runner creates missing parent directories. Omitting
`--output` uses a fresh timestamped directory under that same persistent base.
Existing output directories are never overwritten.

The earlier temporary probe directories have been copied and verified byte for
byte under `~/phluxxed/tmp`; [host-blocker.json](host-blocker.json) records their
persistent locations. Historical paths embedded in raw captures remain intact.

Use a fresh output directory. For a check with no model generation, add
`--preflight-only` and use a separate output directory. Actual runs use the
existing Codex account and consume its normal usage allowance.

## What to compare

| Metric | Interpretation |
| --- | --- |
| Correctness / 6 | Frozen facts, with source support and critical contradictions recorded |
| Required source found / 5 | Needed source excerpts observed in tool results; citations checked against the five owners |
| Ordered navigation | Commands and MCP requests, their results, follow-up reads, and returned relationships |
| Turn elapsed time | Wall time from turn submission to completion or timeout |
| Input / cached / uncached tokens | Provider-reported cumulative usage, with uncached input derived once |
| Output / reasoning tokens | Provider-reported fields; reasoning is not added again to total usage |
| Tool calls / failed calls | Completed observed shell and MCP operations, counted once by item identity |
| Tool output bytes | Captured native output volume; not a claim about unique source bytes, provider delivery, or model attention |
| Tool durations | Observed completed item durations, where supplied |
| Compactions | Observed context-compaction events |

Raw wire journals, stderr, answers, navigation records, and summary receipts
remain in the output directory. Score answers against the frozen oracle before
interpreting condition differences. The runner captures evidence; it does not
automatically grade source reasoning or declare a winner.

## Limits

This is **one task, one run per condition**. Ember has 93 tracked files and
complex cross-module behavior, but it is not a huge repository. Results can
expose useful differences and failure modes; they cannot establish a general
speed or quality advantage. Model randomness, run order, and uncontrollable
provider caching remain possible confounders.

Visible tool events show navigation, not hidden reasoning. Returned graph edges
are evidence delivered, not proof the agent used them. Shell output does not
always establish an exact unique source footprint. Missing telemetry remains
unknown; interrupted usage can be incomplete. No dollar-cost estimate is made
without verified pricing for the account.
