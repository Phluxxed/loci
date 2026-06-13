# loci: relationship / graph layer — Design

**Goal:** Give loci a relationship layer (symbol→symbol edges) and an orientation layer (hub ranking + subsystem clustering) on top of its existing per-file symbol index — *without* inheriting the trust-destroying failure mode that sank the graphify trial.

**Architecture:** Extend the existing `index.json` schema with an `edges` list and add a graph-analysis read path. Edge extraction hooks into the existing tree-sitter walk in `parser/extractor.py`; cross-file resolution and graph queries live in `storage/index_store.py`; new read-only subcommands surface the results. Phased so the trustworthy, cheap edges ship first and the dangerous cross-file call edges come last, gated behind an explicit confidence tier.

**Tech Stack:** Python (existing). Edge extraction = tree-sitter (existing, no new parser). Graph analysis (centrality, communities) = `networkx` — **a new dependency** (loci currently has none beyond `tree-sitter-language-pack`); flagged for decision, not assumed. Community *naming* is an optional LLM tier, off by default.

---

## Provenance — why this doc exists

This design is the constructive output of the **graphify accuracy trial** (2026-06-10, written up in `~/improvements/graphify-accuracy-trial-2026-06-10.md`). graphify (PyPI `graphifyy`) was trialled as a "scout" to feed loci and **rejected** for that role. But the trial doubled as free R&D: it proved which graph-shaped features are *valuable* and handed us an exact spec of the *trap* to avoid.

Two findings from that trial drive every decision below:

1. **The valuable part.** graphify's community detection (Probe E — coherent subsystems) and centrality on *real* hubs (Probe F — `Store`/`AnalyticsClient` ranked correctly) are a genuine orientation aid that loci does not currently provide. Worth having.
2. **The fatal part.** graphify resolved cross-file `calls` edges by **bare symbol name with no scope/file/package boundary**, and stamped the guess `EXTRACTED, confidence 1.0` — its highest-trust label. A backend `presets()` calling its own local closure `daysAgo` got linked to a same-named *frontend* function in a different file/package/tier. That phantom edge became the graph's **#1 betweenness bridge** and corrupted global pathfinding. **A graph that stamps a fabrication as ground-truth is worse than no graph**, because the consumer can't tell which edge is the lie.

The design rule that falls out of finding 2 is the spine of this whole proposal: **loci must be structurally incapable of asserting an unresolved guess as fact.**

## Current state (audit, 2026-06-10)

loci today is a pure per-file symbol extractor. Confirmed by source audit:

- **Symbols** (`parser/symbols.py:6`): `id`, `name`, `qualified_name`, `kind`, `language`, `file_path`, byte range, `signature`, `docstring`, `content_hash`, `line`/`end_line`. `qualified_name` encodes **single-file** parent scope only (`MyClass.method`).
- **No edges.** No `calls`, `imports`, `references`, `callers`, or any relationship field. No edge table in `index.json`.
- **No cross-file resolution.** Symbols are indexed per file; there is no mechanism to resolve an import or a call to a symbol in another file (`parser/extractor.py` only reads `call_expression` to grab a decorator's name, not to record calls).
- **No graph analysis.** The `analyze` command (`storage/index_store.py:588`) computes *behavioural* analytics from the session log (refetch hotspots, search misses) — not structural graph metrics.
- **Storage:** single `index.json` per repo at `~/.codeindex/<cache_key>/index.json` (JSON, not SQLite) + a `sources/` mirror for byte-range reads.
- **Output:** all commands emit JSON; no command currently carries a confidence field.

**Correction worth recording:** loci was the trial's "oracle," but *not* because it has a resolver — it doesn't. It was accurate because `get` returns the real source body (exposing the local `daysAgo` closure) and `outline` gives distinct per-file symbol IDs (so the two `presets()` were visibly different). The resolution was done by a human/agent *reading loci's accurate output*. loci has the accurate **node substrate** to build a correct graph on; it does **not** get the resolver for free. Building that resolver is precisely the component graphify botched.

## Design principles (non-negotiable)

1. **Never assert an unresolved edge as fact.** Every edge carries a `resolution` tier: `exact` (in-scope binding) | `import-resolved` (followed an import to a definite target) | `heuristic` (name-matched, ambiguous). No bare-name fallback is ever labelled `exact`. If a target can't be resolved in-scope or via import, loci emits **no edge** or a `heuristic`-tagged one — the caller decides whether to trust it. This is the structural fix for graphify's `EXTRACTED 1.0` lie.
2. **Direction is information.** Dependency edges are directed from day one. graphify built undirected and rendered `imports_from` backwards (Probe C); loci does not repeat this.
3. **Cheap and deterministic first.** Edge *extraction* and graph *math* are local and free (graphify's AST edges cost 0 tokens). Only community *naming* needs an LLM, and it's opt-in.
4. **Phase by trust, not by ease.** Ship the edge classes graphify got *right* first; defer the class it got *fatally wrong* to last, behind the tier from principle 1.

---

## Phased plan

### Phase 1 — intra-file edges (cheap, zero fabrication risk, high value)

Edges resolvable entirely within a single file:
- `contains` (parent→child; loci half-derives this already via `qualified_name`).
- `calls` where the callee is a sibling/local binding **in the same file**.
- local references.

These are exactly the edges Probe A showed graphify got **right** (intra-file call edges were trustworthy). The guardrail: **if a call's target has no in-scope binding in this file, emit nothing in Phase 1** — do not fall through to a repo-wide match. A local closure like `daysAgo` is either noded or its call edge is suppressed. This phase alone enables per-file / per-symbol neighbourhood views with zero fabrication risk, and proves the resolution-discipline pattern before anything harder is attempted.

**Schema:** add to `index.json`:
```json
"edges": [
  {"from": "<symbol_id>", "to": "<symbol_id>", "type": "calls|contains|references", "resolution": "exact"}
]
```

### Phase 2 — import edges, directed (medium)

Parse `import` statements, resolve them to source files, emit **directed** `imports` edges (`A imports B`, never the reverse). Resolution tier `import-resolved`. This is the dependency-orientation backbone and is where graphify's direction bug (Probe C) is explicitly *not* reproduced. Existence + direction of imports is high-value on its own, independent of call edges.

### Phase 3 — cross-file call edges (medium-high — the graveyard)

The class that killed graphify. Permitted **only** when the callee resolves through an import to a definite target (tier `import-resolved`). Genuinely ambiguous matches are either suppressed or emitted as tier `heuristic` and **never** `exact`. No bare-name repo-wide fallback, ever. Because every edge carries its tier in the JSON, a consumer (agent or human) can filter to `exact`/`import-resolved` only and get a graph with no guesses in it — the property graphify could not offer.

### Phase 4 — orientation layer (cheap once edges exist)

With an edge table present, run `networkx` over it:
- **Centrality / hubs:** degree + betweenness → "what are the spine symbols of this repo" (the Probe F view that ranked `Store`/`AnalyticsClient` correctly). Compute over `exact`/`import-resolved` edges only, so a stray `heuristic` edge can never become a phantom betweenness bridge.
- **Communities:** modularity clustering → "what subsystems exist" (the coherent Probe E view).

Compute is free and local. **Auto-naming** communities ("Frontend Dashboard Components") is the only part needing an LLM — matching graphify's cost split (its 132k-token spend was *all* semantic naming; AST edges were free). Ship the unnamed numeric clusters first; naming is an opt-in flag.

**Surfacing:** new read-only subcommands (names TBD), e.g. `loci graph` / `loci hubs` / `loci communities`, plus optionally extending `get`/`outline` output with a `related_symbols` field. All additive, no breaking changes to existing JSON.

---

## Cost / risk notes

- **networkx dependency.** New to loci. Decision needed before Phase 4. Phases 1–3 need no new deps (tree-sitter + stdlib).
- **Single-JSON storage.** `index.json` is a flat file. An edge list is fine at this repo's scale (~9k symbols), but on a large monorepo the edge list could bloat the file and slow load. This may force a storage rethink (SQLite, or a separate `edges.json`) at Phase 3 — flagged now so it isn't a surprise later. Not blocking for Phases 1–2.
- **Resolution correctness is the whole game.** The value of every phase is contingent on principle 1 holding. A loci that fabricates edges has the same defect that made graphify net-negative. The phasing exists so the risky resolution work is isolated, last, and tier-gated.

## Recommended next step

Spec **Phase 1** concretely as a paired implementation plan (`2026-06-10-graph-layer.md`), TDD throughout, to prove the resolution-discipline pattern on the zero-risk edge classes before committing to Phases 2–4. Phases 3 and 4 each warrant a go/no-go check against results from the prior phase rather than being committed up front.
