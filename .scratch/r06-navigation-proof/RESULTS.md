# Loci R0.6: navigation and semantic proof

2026-10-26. **Keep path-aware source navigation and optional targeted semantic
proof separate.** All seven source spans credited to R0.5 can be acquired through
observable paths without semantic bindings. Native semantic resolution adds a
different capability: independently supported declaration relationships and
configuration evidence. Its availability, delivery and task value must remain
separate measures. This assessment does not adopt either prototype or authorize
production integration, Loci V2, or an agent/model campaign.

The experiment reused the existing R0.5 worktree on
`experiment/r06-navigation-proof`, the R0 harness and frozen corpora. Control is
R0.5 `5fc52cb`; candidate code is `d94471e`. Both main checkouts, R0.3/R0.4
references, historical results and strict semantic scorers are preserved.
The [protocol](protocol.md), [gate](gate.json), [summary](summary.json),
[replay](replay.json) and [preservation check](preservation-after.json) retain
the provenance. All six comparisons completed, with 960 independently replayed
first/repeat case executions. Requests and limits were fixed before scoring;
no scored miss changed the policy.

The four targeted cases ran first: the two Anvil questions, optional Rust
reexport/module case and Rust uncertainty case. Useful recovery, sound proof
and observed navigation trade-offs passed the predeclared broader gate. The
unchanged candidates then ran all 36 frozen cases, in two fresh repetitions
with immediate repeat queries and alternating arm order. The eager architecture
was not rerun: its existing R0.5 results remain historical context, not a new
matched measurement.

The full results distinguish the evidence layers:

| Condition | Necessary source spans | Native authored links available | Complete packet / strict session links |
| --- | ---: | ---: | ---: |
| Frozen lexical source acquisition | 180/187 | 0 | 0 / 0 |
| Path-aware source acquisition | 185/187 | 0 | 0 / 0 |
| R0.5 demand semantics | 187/187 | 59 | 39 / 39 |
| Demand + focused proof, 8/16 KiB | 187/187 | 59 | 48 / 48 |
| Demand + focused proof, 32/64 KiB | 187/187 | 59 | 56 / 56 |

There are 84 authored positive links overall. **Python and Go account for the
25 unsupported links**, separately from the 59 JS/TS/Rust links addressed here.
No Python/Go semantic support was added. The TypeScript scorer retains its
historical generic dependency fallback; these totals do not establish every
precise type-use subtype. All arms acquired entry source in 36/36 cases. Source
and path each covered every required span in 34/36 cases; all demand conditions
did so in 36/36. First/repeat capabilities and the independently repeated focused
condition agree. Agent task answers were never observed or scored.

**Source recovery required path discovery, not semantic binding.** The pure
[path scheduler](../../src/loci/path_navigation.py) inspects only delivered
source and the common filename/hash/size inventory. It follows relative import
and reexport syntax, Rust module paths and paths in delivered Cargo controls,
then uses lexical fallback. It performs no filesystem reads itself and imports
no graph, parser or semantic store. Existing GraphFreeSource supplies protected,
hash-bound source reads. Candidate paths, comments, inactive cfg and alternative
extensions are never asserted to be resolved bindings.

On Anvil, the five recovered spans are `input`, `omission`, `stop`, `reporting`
and `diagnostic`. On Rust, the recovered spans are `module` and `reexport` in
`core/src/lib.rs`. These are all seven motivating R0.5 additions. The same
five-call scheduler loses `thing` in `core/src/api.rs` and `cargo` in the Rust
uncertainty case: Cargo/path-control acquisition consumes one case's final slot,
while module-source alternatives consume the other's slots. Thus seven-span
recovery yields a net gain of five spans, **not source-equivalence to demand**.
These are scheduling/budget trade-offs, not evidence that either missing source
requires semantic resolution. The exact gains, losses and request provenance
are in [full-source-path](results/full-source-path/result.json) and summary.json.

The minimal helper deliberately does not implement package aliases, macro
expansion, `#[path]`, inline-module binding or custom Cargo targets. It is an
ablation of observable source paths, not a second module resolver. No new graph
framework or eager graph reconstruction was built.

**The 20 supported but undelivered R0.5 links are delivery losses.** The
[edge-level audit](delivery-audit.json) joins each missing authored relationship
to native edges, reconstructs the original directional two-hop frontier, and
joins exact packing failures. Both retained repetitions produce the same split:

| Original delivery failure | Links | Recovered at 8/16 KiB | Recovered at 32/64 KiB |
| --- | ---: | ---: | ---: |
| Selection/frontier exclusion | 11 | 7 | 8 |
| Packet capacity | 9 | 3 | 9 |
| Solely closure/support failure among these 20 | 0 | 0 | 0 |
| Total recovered from the original 20 | 20 | 10 | 17 |

Native presence does not erase general closure limitations. Anvil still has
incomplete reexport/closure observations and unresolved records. Those can block
other claims; they do not explain these 20 specific losses. Resolved records,
eligible traversal, selected candidates and delivered proof remain distinct.

The [focused wrapper](../../src/loci/focused_proof.py) retains the exact already
computed native slice and source/control bytes. A focused request accepts only
a previously delivered node ID, selects incident edges and packs proof before
source previews. It does not discover another slice or rerun semantic
resolution. Fresh inventory validation occurs before and after each request;
support-declaration parsing and serialization remain charged. The consumer
heuristic requests at most four IDs in encounter order, anchors before other
nodes, after the existing five base acquisition slots. Neither evaluator gold,
audit-only identities nor missing scores are available to that policy.

The original complete caller, target, import/reexport/module and configuration
support remains mandatory. Every emitted relationship has complete linked
packet proof; there is no paging or promotion of an incomplete packet claim by
session scoring. Focused limits are 8 KiB unique evidence / 16 KiB envelope, or
32/64 KiB in the wider diagnostic. Both retain the case's soft 128 KiB source /
256 KiB response admission limits; real overshoot is retained and charged.

The narrow condition recovers ten original losses but loses one previously
delivered Anvil caller link as explicit uncertainty competes for the initial
packet. Its net change is therefore 39→48, not +10 without qualification. The
wider condition restores that link and recovers 17/20 original losses, yielding
56/59 supported links. [delivery-outcomes.json](delivery-outcomes.json) retains
each transition.

The remaining three are Rust implementation-site relationships:
`format_impl→format`, `format_impl→receipt` and `render_impl→receipt` in
`rust_authored_trait_contract`. The four focused requests were `build`,
`Envelope`, `Render` and `UserId`. Later discovered `Format` and implementation
site IDs were not requested. Those focused calls recorded **zero budget
rejections**. This is a bounded identity-selection result, not a resolver
failure or evidence that no focused policy could deliver the links. No extra
request was added after observing the misses.

Capacity is often **envelope competition rather than intrinsically oversized
proof**. In the first full narrow repetition, 135 packing rejection receipts
include 113 envelope-only and 22 evidence-plus-envelope failures. Of these,
107 fit the same narrow limits when packed alone with their full support and
uncertainty metadata. For example, Anvil's `compilerRetrievalLimits` type
dependency had 4,127 unique source bytes but a 20,927-byte attempted envelope;
alone it needed 3,257 / 13,576 bytes. A Rust `Envelope→UserId` proof needed only
147 / 6,507 bytes alone but failed in a 16,434-byte accumulated envelope. Some
other Anvil callers genuinely exceed both narrow limits. These diagnostics
cover attempted native edges, including surplus edges and repeat attempts;
135 is not a count of distinct authored failures. The packer reserves 512 bytes
inside the envelope cap for final metadata. Raising both caps tests combined
capacity; it does not independently identify their marginal effects.

**Consumer uncertainty is visible and separately scoped.** The old
`rust_unproven_contracts` packet had complete coverage and no omissions despite
one external import, four unresolved references and two unresolved type-parameter
observations in its native audit. The cause was representation: packing visited
materialized resolved edges and never mapped the unresolved records to consumer
omissions. Rust closure for that case was complete. The
[retained audit](uncertainty-audit.md) preserves the original negative finding.

The experimental wrapper includes native family/reason counts, up to eight
location examples, an omitted-example count and configuration-possibility count
before proof packing. It exposes ambiguity, inaccessible targets, external
imports, configuration divergence and other unresolved observations without
turning them into edges. `declared_possible` still does not establish active
features. The summary is explicitly non-exhaustive and scoped to the computed
slice; Python/Go's unsupported capability remains separate.

The independent [consumer audit](consumer-checks.json) matched all 1,456 new
semantic/focused responses to their own native projections. Counts, examples,
omissions and configuration matched. All 72 Rust uncertainty observations
expose the external import, four unresolved references, two generic type uses,
and configuration-possible count two. Thirty-six responses retain `status=empty`
because no source/proof item was delivered; they still have partial coverage,
non-exhaustive scope and explicit uncertainty/omissions. Empty selection must
not be read as proof that no relationships exist. This experiment demonstrates
availability of uncertainty information, not that an agent notices or interprets
it correctly.

The cost comparisons below are **matched pairs**, means of two fresh full
workloads. Each workload indexes 31 snapshots and acquires 36 first-use plus
36 immediate-repeat case sequences. CPU includes children. KiB is binary;
MB/KB elsewhere are decimal. Operation times include selection, source reads,
continuations, semantic requests and focused proof calls as applicable.

| Matched condition | First elapsed / CPU, s | Repeat elapsed / CPU, s | All worker elapsed / CPU, s | Peak worker RSS, MB |
| --- | ---: | ---: | ---: | ---: |
| A: lexical | 6.097 / 3.682 | 6.111 / 3.682 | 13.249 / 8.070 | 39.44 |
| A: path-aware | 6.413 / 3.916 | 6.404 / 3.909 | 13.861 / 8.526 | 40.81 |
| B: R0.5 demand | 8.809 / 5.705 | 7.145 / 4.389 | 17.382 / 11.128 | 96.56 |
| B: focused 8/16 | 13.971 / 8.747 | 12.262 / 7.393 | 27.854 / 17.351 | 112.73 |
| C: focused 8/16, independent repeat condition | 18.375 / 11.511 | 16.372 / 9.920 | 36.787 / 22.934 | 113.77 |
| C: focused 32/64 | 18.083 / 11.310 | 16.282 / 9.845 | 36.378 / 22.634 | 115.21 |

Path navigation adds 0.316 s first-use and 0.293 s repeat elapsed per 36-case
suite, with 0.233/0.228 s CPU. The actual path-selection phase is about 0.015 s;
most extra cost follows its different source choices. It adds 79,342 output
bytes and about 1.37 MB RSS in its matched pair.

Adding focused proof and honest uncertainty to demand costs 5.162 s first-use
and 5.117 s repeat elapsed, 3.042/3.005 s CPU, and about 16.17 MB peak RSS in B.
Its 70 focused calls directly account for 4.746/4.697 s first/repeat elapsed and
2.821/2.798 s CPU. R0.5's 36 semantic operations themselves cost 3.616 s first
and 2.020 s repeat; cached resolution still revalidates inventory. Focused
delivery also remains nonzero on repeats because it repacks and revalidates.

The wider matched condition C delivers eight more links and 288,707 more bytes
per sequence suite, with about 1.44 MB more peak RSS and similar operation time.
It issues 69 rather than 70 focused requests because larger responses reach
the shared case admission bound sooner. Fewer requests and fewer failed packing
attempts can offset serialization work; this does not establish that larger
packets are free. C's narrow reference is materially slower than B's identical
narrow reference despite equal capabilities, so cross-pair time subtraction is
not a defensible causal estimate. Two repetitions, warmed filesystem state and
host variation support descriptive costs only.

| Condition | Source bytes / unique, first suite | Delivered bytes incl. inventory, first suite | Runtime store, KB | Arm evidence archive, MB |
| --- | ---: | ---: | ---: | ---: |
| A lexical | 336,926 / 247,720 | 943,077 | 36.271 | 6.560 |
| A path | 399,790 / 310,635 | 1,022,419 | 36.271 | 7.999 |
| B demand | 300,157 / 218,214 | 1,058,129 | 36.364 | 12.167 |
| B focused 8/16 | 327,162 / 209,695 | 1,768,689 | 36.364 | 19.640 |
| C focused 8/16 | 327,162 / 209,695 | 1,764,935 | 36.302 | 19.622 |
| C focused 32/64 | 416,208 / 219,218 | 2,053,642 | 36.302 | 20.284 |

Repeats deliver the same bytes again and must be charged again. Source totals
include repeated/overlapping spans; unique bytes are unioned per case and then
summed. Archive bytes include both repetitions' arm-specific runtime evidence;
shared inputs/evaluator overhead is separate. The full pair directories occupy
16.083, 33.389 and 41.493 MB for A/B/C. Absolute path/reference length changes
explain small cross-pair byte differences. All external cache directories report
zero bytes. Runtime stores remain file inventories, not semantic stores.

That does not mean zero semantic memory. Demand's serialized cache proxy peaks
at about 3.579 MB. Focused delivery additionally retains up to 1.908 MB raw
source/control bytes and native objects with an approximately 3.563 MB index
serialization proxy. These proxies are not heap-size measurements and should
not replace RSS. Source indexing and ordinary reads import no graph/parser
modules; all conditions have zero semantic modules loaded before questions.
There is no persistent semantic graph or proof store.

Initial index elapsed/CPU is 0.686/0.446 versus 0.691/0.443 s in A,
0.728/0.460 versus 0.715/0.460 s in B, and 0.974/0.618 versus 0.967/0.612 s in C.
Setup elapsed/CPU is about 2.42–2.50/2.11–2.17 s per arm in A/B and
3.33–3.43/2.71–2.78 s in C. Independent observer validation is separate from
product work: 2.23→2.18 s elapsed in A, 2.95→5.28 s in B, and 7.48→11.25 s in C
(CPU 1.57→1.52, 2.16→3.69 and 4.88→7.37 s). Nested native timings overlap their
operations and are never added twice. RSS is process lifetime high water,
not a separately sampled phase peak or concurrent aggregate.

**Validation and limits.** All complete claims pass the unchanged strict
semantic checks, with zero claim-integrity violations and zero forbidden-proven
relationships. Structural delivered claims are zero; no structural success is
inferred from vacuous validation. TypeScript does not expose a distinct
forbidden-delivered counter, and summary.json preserves that absence as null.
Source-only zero claims are also vacuous, not proof of semantic correctness.
The five historical eager packet-proof failures remain untouched; no eager
failure was relabelled by this experiment.

Forty-nine distinct focused/harness tests passed across the development batches
(overlapping batches are recorded in [validation.json](validation.json)). They
cover native-slice reuse, stale/cross-root refusal, undisclosed identities,
query provenance, source corruption, large complete caller budgets, path
alternatives, source protection and consumer uncertainty. Independent replay
verified all 960 executions after source exports/stores were removed. The
optional macOS `time -l` wrapper exited 1 after each full replay because the
existing sandbox denied `sysctl kern.clockrate`; each verification itself
completed and printed its verified receipt. The limitation is retained in
replay.json/logs. No permission or sandbox configuration was changed.

Preservation verified both main checkouts and R0.3/R0.4, 3,730 historical file
hashes, 15 unchanged strict observer/source-scoring functions, and candidate
code equality with `d94471e`. Only the explicitly experimental packer seam and
new-operation observer validators changed; the R0.5 branch reference remains
at its original commit. Harness dirty metadata in the full runs concerns the
documented gate/work artifacts, not different candidate/evaluator code.

The corpus remains small and selected: 32 cases have sub-KiB snapshots and often
require most of the fixture. No result establishes broad repository-scale
performance, exhaustive reverse impact, runtime dispatch, active feature
configuration, or agent task correctness. The separate arms also do not measure
a combined path-first-plus-proof consumer workflow. Their costs must not be
summed into an unobserved end-to-end outcome.

The architectural decision supported by this evidence is to retain a cheap
source-acquisition capability and a separately requested, bounded semantic-proof
capability with explicit uncertainty. Source coverage alone does not justify
semantic resolution; native records alone do not establish delivery; delivered
proof alone does not establish task correctness. The remaining selection losses
and unmeasured consumer behavior qualify the decision without requiring a V2
implementation. This investigation stops at that assessment.
