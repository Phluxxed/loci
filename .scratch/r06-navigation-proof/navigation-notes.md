# R0.6 graph-free path navigation candidate

Worker assignment: `navigation`, Sol/high/none; directly implemented without
further delegation. Owned only the new path navigator, focused tests, benchmark
import entry point, and this note. Primary owns scored measurement and git.

## Frozen interface and scheduling

`benchmarks.architecture_navigation.choose_next_query(inventory, packets, asked)`
returns `{query, reason, observed_in, work}`. Its `next_acquisition_query` wrapper
returns only the query. Both import the same self-contained implementation from
`loci.path_navigation`, so scoring replay can reproduce exactly the actual
query sequence. The caller must time selection and archive its receipt.

The scheduler receives common inventory metadata and already delivered source
packets. It performs no filesystem reads and imports no graph, parser, store,
service, corpus, or evaluator. It preserves the R0.4 incomplete observed-file
expansion priority, then tries ordered source path candidates, then uses the
frozen R0.4 lexical path/control/identifier rules. Source fragments are joined
only when their byte intervals overlap or touch; separated fragments cannot
invent an import statement.

Candidate paths come from relative JS/TS imports, exports, dynamic imports and
`require`; Rust external `mod` declarations and `crate/self/super` paths;
ancestor Cargo control paths present in inventory; and explicit local
dependency `path` values in **delivered** Cargo TOML. TOML uses the standard
library, with the existing `tomli` dependency only on Python 3.10. Cargo local
paths suggest inventory-listed conventional `src/lib.rs`, `src/main.rs`, and
`Cargo.toml` entries. Workspace dependency paths become available only after
the workspace control has actually been delivered. No unrequested control or
target source is opened by the navigator.

Every emitted path must belong to the supplied inventory. Containment rejects
absolute paths, escaping parents, backslashes and NULs. Existing
`GraphFreeSource` remains completely unchanged and performs actual acquisition,
including fresh inventory/hash scans, eligibility checks, symlink protection,
hash-bound references, bounded continuation, and packet byte accounting.
The primary harness retains five acquisition calls, sixteen continuations,
128 KiB source and 256 KiB response soft admission caps. The navigator adds no
source acquisition operation or separate budget.

## Accounting

The selection receipt records inventory paths available, source spans received,
source bytes received (including repeated delivered bytes), source bytes
presented to path scanning, source bytes presented to each lexical fallback
pass, admitted candidate paths generated, and filesystem source bytes read
(always zero). Path-scan bytes are counted after contiguous interval merging;
fallback intentionally uses original spans to preserve its original policy.
These are exact pass-input byte counters, not regex instruction counts or CPU
estimates. Selection CPU/wall time must be measured by the harness; packet and
continuation accounting remains the existing source service's responsibility.

## Focused verification before scoring

```
PYTHONPATH=src /Users/brummerv/phluxxed/loci/.venv/bin/python -m pytest -q tests/test_path_navigation.py
```

Result: **12 passed in 0.19s**. Novel fixtures cover JS import/reexport and
ambiguous extension alternatives; Rust inactive module alternatives; delivered
Cargo workspace control acquisition; root-relative local dependency candidates;
malformed TOML; path escapes; contiguous versus gapped source pages; incomplete
file priority; lexical fallback; deterministic query/work replay; absence of
semantic/evaluator imports in a fresh process; and unchanged GraphFreeSource
hash-staleness and symlink exclusion protections. A test initially expected
an absent exact path search to return no sources, but GraphFreeSource correctly
falls back to lexical matches; the assertion was corrected to require exclusion
of the symlink target. No service behavior changed.

The navigator and tests were frozen before scored R0.6 runs. This worker ran no
corpus scoring and made no policy changes based on missing target contexts.
Historical source import headers and manifests were inspected to identify
applicable syntax families; no fixture paths, case IDs, authored context, symbol
names, missing spans, or evaluator results enter the implementation.

## Qualification and limits

These are lexical acquisition **candidates**, not unique module resolution or
semantic proof. Multiple extensions, module layouts, cfg branches and local
dependency targets remain alternatives. Optional/workspace/target dependency
presence does not establish activation. Regex matching may see comments or
inactive source. Bare JS package aliases, tsconfig path maps, external package
resolution, Rust macros, `#[path]`, inline module scope and custom Cargo target
paths are not resolved. Full Rust name binding is intentionally absent. Missing
targets or slot/budget exhaustion establish no negative semantic conclusion.

Source availability, relationship proof, and task correctness remain distinct.
Seven-span recovery is a measured hypothesis, not an implementation acceptance
criterion; supported misses can complete the assessment. There is no production
integration, live model evaluation, new dependency, persistent relationship
state, or new framework.
