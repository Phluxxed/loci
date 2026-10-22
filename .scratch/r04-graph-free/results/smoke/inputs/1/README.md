# Multilingual context inputs v1

These are W4.1's source/context targets for the existing Python, JavaScript, Go
and Rust delivery tasks. They are authored before those implementations. They
do not report implementation passes, agent outcomes or a final measurement freeze.
See the [capability and delivery contract](../../../docs/design/2026-09-12-multilingual-context-cases.md).

`corpus.json` contains task prompts, independent answer facts, required exact
source spans and semantic relationship expectations. `corpus.sha256` pins those
bytes. Each snapshot's inventory pins every file plus `fixtures.tar.gz`; the
archive contains only source and repository control files, never evaluator gold.

Expected relationships describe language meaning. They are not assumed to be
existing graph enum values. An implementation must map them to a documented,
source-proven graph relationship without changing their direction or certainty.
Negative expectations forbid exact target claims even when source contains a
plausible same-name declaration.

Verify data integrity with the existing loader:

```sh
.venv/bin/python -m benchmarks.typescript_context_corpus --root benchmarks/corpora/multilingual-context-v1
```

Despite its historical module name, this loader verifies generic corpus/source
hashes and exact JSON facts. It does not establish that the TypeScript-specific
adapter or relationship scorer already supports the new languages. W4.7 verifies
those mappings against actual output before provider measurement.

Use `load_corpus` and `materialize_snapshot` from that same module to create a
fresh absent/empty source directory. A future task agent receives that directory
and only its ordinary `prompt`. Keep `corpus.json`, expected source/relationships,
case IDs, group labels and saved results outside the task agent's reach.

All new cases share the corpus's byte, traversal and whole-task budgets. Fixtures
are small repository-work questions: their origin is explicitly synthetic. The
Loci Python output-contract case uses a complete maintained source module pinned
at the starting commit. It is a real regression-input task, with a stated
single-module limit; none of these inputs establishes general code-edit success.

The corpus contains **19 cases, 16 snapshots and 60 source/control files**.

| Language | Cases |
| --- | --- |
| Python | `python_alias_annotation`, `python_base_and_literal_forward`, `python_known_call_impact`, `python_unproven_contracts` |
| JavaScript | `javascript_value_dependencies`, `javascript_direct_class_base`, `javascript_known_call_impact`, `javascript_unproven_dependencies` |
| Go | `go_alias_generic_contract`, `go_explicit_embedding`, `go_known_api_impact`, `go_unproven_package_uses` |
| Rust | `rust_authored_trait_contract`, `rust_contained_optional_reexport`, `rust_known_call_impact`, `rust_unproven_contracts` |
| Additional controls/work | `tsx_props_control`, `markdown_section_control`, `python_loci_bundle_contract` |

[The source-only input check](input-check.json) verifies the archive inventory,
all span hashes, positive relationship endpoints, answer shape, retained
TypeScript identity and source-byte fit. The largest required source set is
2,033 bytes. It also records 58 matching declaration expectations and four
missing ones at the starting commit: Python `Alias`, Go `AliasID`, Rust `UserId`
and TSX `Badge`. Alias extraction belongs to the corresponding language tasks;
the demonstrated TSX grammar/anchor gap belongs to W4.6. Expected alias symbol
metadata describes the required implementation target, not current support.

Go context uses complete type specifications without the enclosing shared
`type` keyword, matching existing symbol source boundaries while retaining the
alias `=`. Rust impl context keeps each complete impl declaration as a separate
source owner, with no assumed generated symbol ID. Ordered pairs in prompts
retain their stated order; only unordered answer arrays are sorted.

The existing TypeScript v3 corpus is retained by exact corpus hash and all
seventeen case IDs. A new TSX props case and Markdown section case provide
additional controls. Published TypeScript outcomes remain unchanged. W4.7 will
choose and pin its matched schedule before outcomes; the retained identity list
does not authorize another run of a completed historical batch.

For each language implementation, also check source/target removal or change,
applicable resolver-control changes, repeated names, cycles and reduced/zero
evidence budgets. A source or control mutation requires fresh identities and
proof. A bounded unresolved or omitted response must not become an exact edge,
complete source receipt or proof of repository-wide absence.
