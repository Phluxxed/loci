# Deterministic retrieval implementation worklog

Task authority is the existing Manifest. This file records delegated evidence
and primary decisions; it does not introduce additional completion gates.

## W1.7.2.1 — contract evidence, 14 September 2026

- `contract_graph_evidence`: Sol / high / fork none. Read-only ownership:
  existing graph edge record and source-proof assembly feasibility, including
  imports, references and calls across supported languages. Contribution:
  prevent the default policy promising evidence the resolver cannot deliver.
  Acceptance: source-backed minimal implementation seam, supported relationship
  matrix, concrete proof/ambiguity/budget gaps; no source edits or trials.
- `contract_acceptance`: Terra / high / fork none. Read-only ownership:
  existing frozen audit inputs and observer contracts. Contribution: specify
  honest numerical value gates and the smallest observer adapter needed before
  reserved post-change execution. Acceptance: preserve all historical rows,
  prompts, accounting semantics and ten reserved rows; separate mechanism,
  delivery and ordinary value. No model trials or mutations.

Primary owns the request/response, traversal/ranking policy, migration,
contract artifact and Manifest state. Both workers must complete their
assignment directly without spawning agents.

`contract_acceptance` returned source-backed findings against frozen protocol,
accounting, results and the existing observer. Primary adopted the 8/8 strict
correctness, exact-delivery and separate primary gates, with the proposed 25%
per-case cost ceiling as an explicit tradeoff rather than an efficiency claim.
The observer seam is versioned; historical rows/helpers remain unchanged.
Result is recorded in contract.md's Ordinary value acceptance section.

Reuse `contract_acceptance` (Terra/high; retained context fits the frozen audit)
for a read-only contradiction review of contract.md: identify unresolved rules,
hidden model-selected policy, unsupported claims and acceptance weakening.
Scope now includes the written interface contract, not source implementation.
Acceptance is an actionable list of material gaps or a qualified pass. No edits.

`contract_graph_evidence` returned a supported language matrix and import
endpoint proof decision. Primary adopted separate indexed ownership, unchanged
native file/package/module/crate endpoints, unique parsed full declaration
hydration and explicit proof omission on unsupported source. The normal packer
must not force zero-width endpoints into symbol-only exploration bundles.
Source owners: exploration.py `_records`/`_Source`, graph/imports.py
`ImportRecord`/`materialize_import_edges`, graph/state.py, graph/anchors.py,
graph/traversal.py, parser/symbols.py, graph/go_modules.py,
graph/_rust_resolution.py, graph/swift_modules.py and graph/builtins.py.
Result is incorporated in contract.md Structural traversal/File and package
context. The existing parser/resolver guarantees are unchanged.

The contract review identified five material gaps: model-visible proof gates,
exact-file query representation, source-reference provenance, typed response
shapes and target-degree definition. Primary resolved them explicitly in
contract.md and added contract.schema.json. The operation/byte accounting flags
remain reported flags, as the frozen protocol requires. The same reviewer is
checking these specific corrections to close the outstanding review; no new
review scope or model trials were added.

Final review closed those five gaps, conditional on correcting character-count
limits to UTF-8 byte validation. Primary removed the accidental shared string
maxLength values, recorded x-maxUtf8Bytes for query and retained runtime byte
limits. Draft 2020-12 schema validation passes. Disposition: adopted, corrected,
contract frozen. This is design acceptance, not product test evidence.

## Implementation assignments after contract freeze

- Reuse `contract_graph_evidence` as the engine implementer, Sol/high, original
  fork none. Retained source/proof context is directly relevant. Owned scope:
  new normal graph selection/source assembly/packing modules and focused engine
  tests only. Primary supplies retrieval_io.py helpers and service/MCP adapters.
  Contribution: W1.7.2.2 executes the frozen policy. Acceptance: current fixture
  source proves incoming/outgoing relationships, native import endpoints,
  bounded repeatability and truthful partial results through the normal engine.
- `catalog_integrity`: Terra/high/fork none. Owned scope:
  storage/repository_catalog.py, narrowly necessary IndexStore call-site changes
  and focused catalog concurrency tests. Contribution: W1.7.4 makes parallel
  ordinary retrieval usable. Acceptance: live owner waits/busy without crash
  repair, owner-only release, abandoned marker behavior and both roots retained.
  No live catalog repair. Do not edit retrieval/service/MCP or Manifest files.

Primary owns retrieval_io.py, service.py, mcp_server.py, output schemas,
integration, installed surfaces, Manifest and final judgment. Workers complete
directly without spawning agents. No benchmark/model trials until runtime freeze.
