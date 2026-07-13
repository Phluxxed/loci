# Plan: Extensible Graph Retrieval Stage 2

**Status:** implemented and approved; Stage 3 authorized

**Date:** 2026-07-13

**Scope:** repository-local declarative graph profiles, file-based graph
contributions, freshness invalidation, and graph-health diagnostics

**Depends on:** Stage 1 commit `797e881`

**Frozen benchmark:**
`/Users/brummerv/llm-wiki/tests/fixtures/graph_shape_traversal_stage3.json`

**Frozen benchmark SHA-256:**
`c52def1bdf592ad735149d199910f74183598eccd9ccf8064335fa0cd0e84e27`

## Goal

Make the Stage 1 graph substrate safely extensible without loading executable
plugins into loci. A repository may opt into domain semantics through strict,
versioned JSON profiles and contribution documents. Loci validates those inputs,
tracks their freshness, stores only currently supported graph records, and
explains rejected or stale records through one MCP health read.

Stage 2 does not add question-shaped retrieval, multi-hop traversal, ranking,
imports, compiler integration, or benchmark scoring. Existing repositories with
no graph profile must behave exactly as they do after Stage 1.

## Authorization and Review Posture

The project owner approved Stage 1 and authorized the next stage on 2026-07-13.
They delegated implementation mechanics to the agent. This plan therefore owns
the technical gate and surfaces only product-level changes in direction.

After the technical review gate passed, the project owner authorized continued
implementation on 2026-07-13. Stage 3 may proceed.

The agent recommends this design because it is deterministic, local,
repository-portable, reversible, and adds no executable extension boundary.

## Governing Evidence

### July extensible-graph design

`docs/design/2026-07-13-extensible-graph-retrieval-design.md` requires Stage 2
to add:

- profile loading;
- contribution validation;
- incremental retention;
- stale-source invalidation;
- structured graph-health diagnostics;
- one generic profile fixture and one `llm-wiki` profile fixture;
- unchanged behaviour for repositories without profiles.

### Live Stage 1 implementation

Loci inspection confirms:

- `GraphContribution` already has a strict versioned serialization contract;
- `validate_graph_edges()` currently admits only exact `loci:contains` edges;
- `IndexStore.write()` atomically stores `index.json.graph.edges`;
- `index_repo()` recomputes exact containment after final symbol-ID remapping;
- `_index_is_stale()` currently observes only indexed source-file hashes;
- `graph_neighbors()` currently returns every stored edge because Stage 1 stores
  only exact containment;
- Markdown parsing retains a fixed frontmatter allowlist and discards
  domain-specific fields such as `knowledge_state` and `mentioned_in`.

### Live llm-wiki implementation

Loci inspection of `/Users/brummerv/llm-wiki` confirms that the current wiki
runtime:

- treats `knowledge_state` as authored frontmatter;
- creates directed `mentioned_in` edges from the named referrer to the current
  page;
- also creates body-link edges, which Stage 2 deliberately defers because loci
  does not yet expose explicit Markdown-link spans as indexed metadata;
- owns normalization, answerability, and sufficiency semantics that must not
  move into loci.

## Stage 2 Architecture Decisions

### 1. Profiles are repository-local only

Profiles are discovered from:

```text
.loci/graph/profiles/*.json
```

Files are loaded in lexical repository-relative path order. Namespaces must be
unique across the discovered set.

Stage 2 does not add an external profile registry or precedence rules. A local
profile is portable with the repository, participates directly in freshness,
and avoids hidden machine state. External registration can be added later only
if a real consumer cannot carry a repository-local profile.

### 2. Contributions are file-based only

Contribution documents are discovered from:

```text
.loci/graph/contributions/*.json
```

The Stage 1 `GraphContribution` document is the file payload. Stage 2 does not
add a mutating service or MCP call for contribution ingestion. File ingress is
restart-safe, inspectable, hashable, and naturally compatible with incremental
indexing.

### 3. Domain relationships are `declared` only

Stage 2 profile edge types may activate only the `declared` resolution tier.

- `exact` remains reserved for relationships loci proves directly.
- `import-resolved` remains reserved for a later built-in import resolver.
- `heuristic` remains serializable but is not accepted into the active Stage 2
  graph.

This prevents an authored wiki assertion from being mislabeled as parser-proven
truth and prevents heuristic records from entering retrieval before filtering
exists.

### 4. Import extraction waits

The import plan remains deferred until the profile, health, anchor, and bounded
retrieval path is proven. Stage 2 does not add import parsing or resolution.

### 5. Existing retrieval remains exact-only

`loci_graph_neighbors` keeps its Stage 1 meaning: exact outgoing one-hop
neighbours. Stage 2 persists valid declared domain edges but does not expose them
through that exact-only operation.

This is a compatibility requirement. A later filtered-neighbour or path API may
opt into declared edges explicitly.

### 6. Invalid extension data degrades the graph, not the source index

Invalid profiles and invalid or stale contributions do not discard a valid
symbol index. Unsupported profiles and records are excluded from the active
graph, structured errors are persisted, `loci_index` reports the degraded
state, and `loci_graph_health` explains the cause. If two profiles claim the
same namespace, neither profile is active; there is no first-file-wins fallback.

This is loud failure without trapping the repository behind an unusable stale
index or making ordinary MCP code-navigation reads unavailable.

### 7. Extension inputs are bounded untrusted files

Profiles, contributions, and profile-referenced Markdown are opened through one
repository-contained reader. It resolves every parent path, rejects any path
outside the repository, opens the final component without following a symlink,
and verifies the opened descriptor is a regular file before reading.

Stage 2 limits are deliberately conservative:

- at most 32 profile files;
- at most 256 contribution files;
- at most 256 KiB per profile or contribution file;
- JSON nesting depth at most 16;
- JSON string length at most 4,096 characters;
- at most 128 node rules, edge types, or edge rules per profile;
- at most 10,000 nodes plus edges per contribution.

Strict JSON loading rejects duplicate object keys and non-finite numbers. These
limits prevent a repository-local extension file from causing unbounded CPU,
memory, or persisted-envelope growth.

## Repository Profile Contract

### Location

```text
.loci/graph/profiles/<name>.json
```

Only direct `*.json` children are discovered in Stage 2. Symlink files and
symlinked parent paths that resolve outside the repository are rejected. Every
opened file must still be a regular repository-contained file after open.

### JSON shape

```json
{
  "schema_version": 1,
  "namespace": "llm-wiki",
  "node_rules": [
    {
      "selector": {
        "language": "markdown",
        "page_root": true
      },
      "attributes": [
        {
          "name": "knowledge_state",
          "source": "frontmatter.knowledge_state",
          "value_type": "string",
          "allowed_values": [
            "current",
            "provisional",
            "historical",
            "superseded",
            "contradicted",
            "unspecified"
          ]
        }
      ]
    }
  ],
  "edge_types": [
    {
      "type": "mentioned_in",
      "directed": true,
      "allowed_resolutions": ["declared"]
    }
  ],
  "edge_rules": [
    {
      "selector": {
        "language": "markdown",
        "page_root": true
      },
      "source": "frontmatter.mentioned_in",
      "type": "mentioned_in",
      "direction": "reference_to_source",
      "resolution": "declared"
    }
  ]
}
```

### Exact typed contracts

Add `src/loci/graph/profiles.py`:

```python
PROFILE_SCHEMA_VERSION = 1
PROFILE_DIR = Path(".loci/graph/profiles")
CONTRIBUTION_DIR = Path(".loci/graph/contributions")

ProfileValueType = Literal["string", "string_list"]
ProfileEdgeDirection = Literal[
    "source_to_reference",
    "reference_to_source",
]

@dataclass(frozen=True, slots=True)
class GraphNodeSelector:
    language: str
    page_root: bool

@dataclass(frozen=True, slots=True)
class GraphNodeAttributeRule:
    name: str
    source: str
    value_type: ProfileValueType
    allowed_values: tuple[str, ...]

@dataclass(frozen=True, slots=True)
class GraphNodeRule:
    selector: GraphNodeSelector
    attributes: tuple[GraphNodeAttributeRule, ...]

@dataclass(frozen=True, slots=True)
class GraphEdgeTypePolicy:
    type: str
    directed: bool
    allowed_resolutions: tuple[ResolutionTier, ...]

@dataclass(frozen=True, slots=True)
class GraphEdgeRule:
    selector: GraphNodeSelector
    source: str
    type: str
    direction: ProfileEdgeDirection
    resolution: ResolutionTier

@dataclass(frozen=True, slots=True)
class GraphProfile:
    schema_version: int
    namespace: str
    node_rules: tuple[GraphNodeRule, ...]
    edge_types: tuple[GraphEdgeTypePolicy, ...]
    edge_rules: tuple[GraphEdgeRule, ...]

@dataclass(frozen=True, slots=True)
class LoadedGraphProfile:
    source: str
    content_hash: str
    profile: GraphProfile
```

Every type implements strict `to_dict()` and `from_dict()` methods. Unknown or
missing keys fail with `INVALID_GRAPH_PROFILE`.

### Profile validation

Profiles must satisfy all of these rules:

- `schema_version == 1`;
- namespace, attribute, and type names use lowercase ASCII
  `[a-z][a-z0-9_-]{0,63}`; values are never case-folded or Unicode-normalized;
- namespace `loci` is reserved for built-ins and cannot be registered;
- namespaces are unique across files;
- selectors are exactly Markdown page-root selectors in Stage 2;
- `source` is exactly `frontmatter.<field>` with a safe field identifier;
- attribute names and source fields are unique within their applicable rule;
- `allowed_values`, when present, contain unique nonempty strings;
- edge types are unique;
- every edge rule references a registered edge type;
- every edge rule uses `resolution="declared"`;
- rule direction agrees with the edge type's directed policy;
- duplicate rules fail rather than creating ambiguous precedence.

The strict JSON reader rejects duplicate keys, non-finite numbers, excessive
depth, excessive strings, and files or collections above the Stage 2 limits.

## Contribution Contract and Validation

### Location

```text
.loci/graph/contributions/<name>.json
```

### Ingress

Each file is parsed through `GraphContribution.from_dict()`. The wrapper stored
in the graph envelope records:

```python
@dataclass(frozen=True, slots=True)
class LoadedGraphContribution:
    source: str
    content_hash: str
    contribution: GraphContribution | None
```

`contribution=None` is retained only when parsing failed. The persisted record
contains only source path, content hash, and the structured parse diagnostic;
raw malformed bytes and excerpts are not copied into the index.

### Validation rules

- The contribution namespace must match one loaded profile.
- Every node ID must exist in the current symbol registry.
- Node attributes must be declared by a profile node rule, match its value type,
  and satisfy any allowed-values set.
- Every edge type must be registered by the namespace profile.
- Every edge uses an allowed resolution; Stage 2 therefore accepts only
  `declared` domain edges.
- Edge direction must match the registered edge policy.
- Both endpoints must exist in the current symbol registry.
- Evidence file paths are normalized repository-relative paths, pass the same
  opened-descriptor containment checks as profile inputs, and may not escape the
  repository through a symlinked component.
- Evidence must name a currently indexed source file.
- Evidence `content_hash` must equal that source file's current raw SHA-256.
- Evidence line must be within the current source file.

Invalid records are excluded from active `graph.nodes` or `graph.edges` and
produce diagnostics. The contribution document and its own source hash remain
inspectable in `graph.contributions`.

### Overlay conflict rule

Node attributes are merged deterministically by `(namespace, node_id,
attribute)`, with profile-derived values considered first. Repeating the same
value is deduplicated. A differing value produces
`GRAPH_NODE_ATTRIBUTE_CONFLICT`; the later conflicting value is excluded.

No implicit override or file-order precedence is allowed.

## Declarative Materialization

`src/loci/graph/profiles.py` exposes the selected parser fields:

```python
def required_frontmatter_fields(
    profiles: Sequence[LoadedGraphProfile],
) -> frozenset[str]: ...
```

`src/loci/graph/materialize.py` separates incremental extension loading from
materialization so reused contributions are still revalidated:

```python
@dataclass(frozen=True, slots=True)
class GraphExtensionLoad:
    profiles: tuple[LoadedGraphProfile, ...]
    contributions: tuple[LoadedGraphContribution, ...]
    input_hashes: dict[str, str]
    diagnostics: tuple[GraphDiagnostic, ...]
    contributions_reused: int

def load_graph_extensions(
    repo_path: Path,
    *,
    previous_graph: GraphIndexState | None = None,
) -> GraphExtensionLoad: ...

def materialize_graph(
    repo_path: Path,
    symbols: Sequence[Symbol],
    file_hashes: Mapping[str, str],
    profiles: Sequence[LoadedGraphProfile],
    contributions: Sequence[LoadedGraphContribution],
    *,
    input_hashes: Mapping[str, str] | None = None,
    diagnostics: Sequence[GraphDiagnostic] = (),
) -> GraphIndexState: ...
```

Materialization order is fixed:

1. exact loci built-ins;
2. profile-derived node attributes;
3. profile-derived declared edges;
4. valid contribution node attributes;
5. valid contribution declared edges;
6. deterministic deduplication and sorting;
7. diagnostics sorted by severity, code, source, and stable details digest.

Profile edge references are repository-relative Markdown file paths. A
reference resolves only when that file has exactly one indexed page-root node.
Zero roots produce `GRAPH_REFERENCE_UNRESOLVED`; multiple roots produce
`GRAPH_REFERENCE_AMBIGUOUS`. Bare symbol names, titles, and fuzzy matching are
forbidden.

For a rule on page `source.md`:

- `source_to_reference` emits `source.md page root -> referenced page root`;
- `reference_to_source` emits `referenced page root -> source.md page root`.

Profile-derived edge evidence points to the declaring frontmatter field:

```json
{
  "file": "concepts/current-page.md",
  "line": 7,
  "content_hash": "raw-sha256-of-current-page"
}
```

## Markdown Parser Extension

Preserve the existing public call:

```python
parse_file(path)
```

Add a keyword-only opt-in:

```python
def parse_file(
    path: Path,
    *,
    markdown_frontmatter_fields: Collection[str] = (),
) -> list[Symbol]: ...
```

`parse_markdown()` and `_parse_frontmatter()` receive the same keyword-only
field set. Built-in fields remain unchanged. Profile-selected fields are
retained only when their values are strings or lists of strings. A requested
field with a number, object, mixed list, duplicate YAML key, alias, or merge is
not treated as absent: its raw value is not persisted, but page-root metadata
records a field name, line, and rejection reason under `frontmatter_invalid` so
materialization emits a loud diagnostic.

Page-root Markdown metadata gains:

```json
{
  "frontmatter": {
    "knowledge_state": "current",
    "mentioned_in": ["concepts/overview.md"]
  },
  "frontmatter_lines": {
    "knowledge_state": 6,
    "mentioned_in": 7
  },
  "frontmatter_invalid": [
    {
      "field": "mentioned_in",
      "line": 7,
      "reason": "expected string or string list"
    }
  ]
}
```

No complete arbitrary frontmatter mapping is persisted. This keeps profile
access explicit and avoids indexing unknown nested data or secrets.

Because parser output can now depend on profiles, increment
`EXTRACTOR_VERSION` from `3` to `4` and `INDEX_SCHEMA_VERSION` from `4` to `5`.

## Persisted Graph Envelope

Add `src/loci/graph/state.py`:

```python
GraphDiagnosticSeverity = Literal["info", "warning", "error"]

@dataclass(frozen=True, slots=True)
class GraphDiagnostic:
    severity: GraphDiagnosticSeverity
    code: str
    message: str
    source: str | None
    details: Mapping[str, JSONValue]

@dataclass(frozen=True, slots=True)
class GraphIndexState:
    schema_version: int
    profiles: tuple[LoadedGraphProfile, ...]
    nodes: tuple[GraphNodeRef, ...]
    edges: tuple[GraphEdge, ...]
    contributions: tuple[LoadedGraphContribution, ...]
    input_hashes: Mapping[str, str]
    diagnostics: tuple[GraphDiagnostic, ...]
```

The persisted envelope becomes:

```json
{
  "graph": {
    "schema_version": 1,
    "profiles": [],
    "nodes": [],
    "edges": [],
    "contributions": [],
    "input_hashes": {},
    "diagnostics": []
  }
}
```

The graph schema stays at version 1 because these are additive fields reserved
by Stage 1's envelope. The containing index schema increments to version 5.

Change storage APIs to:

```python
def IndexStore.write(
    self,
    repo_path: Path,
    symbols: list[Symbol],
    file_hashes: dict[str, str],
    *,
    graph_state: GraphIndexState | None = None,
) -> None: ...

def IndexStore.get_graph_state(self, repo_path: Path) -> GraphIndexState: ...

def IndexStore.get_graph_edges(self, repo_path: Path) -> list[GraphEdge]: ...
```

`graph_state=None` writes an empty valid graph state. `get_graph_edges()` remains
as a compatibility convenience over `get_graph_state().edges`.

Graph validation completes before the atomic index replacement. Symbols,
profiles, overlays, edges, contribution records, hashes, and diagnostics are
serialized into one temporary `index.json` and become visible through one
rename; no reader can observe mixed graph generations.

## Freshness and Incremental Retention

### Input hashes

`GraphIndexState.input_hashes` contains the raw SHA-256 of every discovered
profile and contribution file, keyed by repository-relative path.

`_index_is_stale()` compares both:

- ordinary indexed `file_hashes`;
- graph profile/contribution `input_hashes`.

Adding, changing, or deleting a profile or contribution therefore triggers the
same MCP freshness boundary as changing source code or Markdown.

### Incremental algorithm

At the beginning of `index_repo()`:

1. discover and strictly load profiles;
2. derive the union of required frontmatter fields;
3. discover current contribution paths and hashes;
4. load the previous graph state when index versions are current.

For each contribution:

- unchanged source path/hash: reuse the prior parsed contribution document;
- changed or new source: parse the current document;
- deleted source: remove its active records;
- all reused or reparsed records: revalidate namespace, attribute rules, edge
  types, resolutions, direction, endpoints, and evidence against the current
  profile policy, symbol registry, and source hashes.

Revalidation is mandatory even for a reused contribution because its evidence
source may have changed independently.

Profile-derived records are deterministically rebuilt from the complete symbol
set. Unchanged source files retain their existing symbols, so their serialized
profile records remain byte-for-byte stable.

`index_repo()` adds these result fields without changing existing fields:

```json
{
  "graph_profiles_loaded": 1,
  "graph_contributions_loaded": 2,
  "graph_contributions_reused": 1,
  "graph_node_overlays_indexed": 5,
  "graph_edges_indexed": 12,
  "graph_status": "healthy",
  "graph_diagnostics": []
}
```

## Graph Health Service and MCP API

### Service

Add to `src/loci/service.py`:

```python
def graph_health(
    repo: str | Path,
    *,
    ensure_fresh: bool = False,
) -> dict[str, Any]: ...
```

Exact success shape:

```json
{
  "schema_version": 1,
  "repo": "/absolute/repository/path",
  "status": "healthy",
  "profiles": [
    {
      "namespace": "llm-wiki",
      "source": ".loci/graph/profiles/llm-wiki.json",
      "content_hash": "sha256",
      "node_attributes": ["knowledge_state"],
      "edge_types": [
        {
          "type": "mentioned_in",
          "directed": true,
          "allowed_resolutions": ["declared"]
        }
      ]
    }
  ],
  "counts": {
    "profiles": 1,
    "node_overlays": 2,
    "edges": 4,
    "contributions": 1,
    "diagnostics": 0
  },
  "diagnostics": []
}
```

`status` is `degraded` when any persisted diagnostic has severity `error` or
`warning`; otherwise it is `healthy`.

A repository with no profile succeeds with empty profile, overlay,
contribution, and diagnostic collections. Built-in exact containment edges are
still included in the edge count.

### MCP

Add one thin handler to `src/loci/mcp_server.py`:

```python
@mcp.tool()
def loci_graph_health(repo: str) -> CallToolResult:
    """Inspect loaded graph profiles, active record counts, and diagnostics."""
    return _handle_loci_error(
        lambda: graph_health(repo, ensure_fresh=True)
    )
```

No CLI command is added. README and both repository Loci skill surfaces list the
new MCP tool.

### Existing neighbours compatibility

Change `graph_neighbors()` to select only active edges satisfying all Stage 1
conditions: `namespace == "loci"`, `type == "contains"`, `directed is True`,
and `resolution == "exact"`. Add an explicit regression test proving that a
valid declared profile edge, or any extension-owned exact edge, does not appear
in the Stage 1 exact-neighbour response.

## Structured Diagnostic Codes

Stage 2 introduces these stable codes:

| Code | Meaning |
| --- | --- |
| `INVALID_GRAPH_PROFILE` | Profile JSON or typed profile contract is invalid |
| `GRAPH_PROFILE_NAMESPACE_DUPLICATE` | Two profiles register one namespace |
| `INVALID_GRAPH_CONTRIBUTION` | Contribution JSON cannot be parsed as the versioned contract |
| `GRAPH_PROFILE_NOT_FOUND` | Contribution namespace has no loaded profile |
| `GRAPH_EDGE_TYPE_UNSUPPORTED` | Domain edge type is not registered |
| `GRAPH_RESOLUTION_UNSUPPORTED` | Domain edge tier is not allowed |
| `GRAPH_ENDPOINT_NOT_FOUND` | Node or edge endpoint is absent from the current index |
| `GRAPH_EVIDENCE_SOURCE_NOT_FOUND` | Evidence source is not a current indexed file |
| `GRAPH_EVIDENCE_STALE` | Evidence hash does not match current source bytes |
| `GRAPH_EVIDENCE_LINE_INVALID` | Evidence line is outside the current source |
| `GRAPH_REFERENCE_UNRESOLVED` | Declarative file reference has no indexed page root |
| `GRAPH_REFERENCE_AMBIGUOUS` | Declarative file reference has more than one page root |
| `GRAPH_NODE_ATTRIBUTE_INVALID` | Attribute is undeclared or has an invalid value |
| `GRAPH_NODE_ATTRIBUTE_CONFLICT` | Two sources assert different values for one overlay field |

Profile, contribution, and materialization errors are persisted as degraded
`GraphDiagnostic` records so ordinary source navigation remains available.
Service and MCP boundary failures still use the existing `LociError` envelope.

## Exact Files

### New production files

- `src/loci/graph/profiles.py`
- `src/loci/graph/state.py`
- `src/loci/graph/materialize.py`

### Modified production files

- `src/loci/parser/extractor.py`
- `src/loci/graph/contracts.py`
- `src/loci/storage/index_store.py`
- `src/loci/service.py`
- `src/loci/mcp_server.py`

### New tests and fixtures

- `tests/graph/test_profiles.py`
- `tests/graph/test_state.py`
- `tests/graph/test_materialize.py`
- `tests/fixtures/graph_profiles/generic.json`
- `tests/fixtures/graph_profiles/llm-wiki.json`
- `tests/fixtures/graph_contributions/example-valid.json`
- `tests/fixtures/graph_contributions/llm-wiki-valid.json`

### Modified tests

- `tests/parser/test_markdown.py`
- `tests/storage/test_index_store.py`
- `tests/test_service.py`
- `tests/test_mcp_server.py`

### Documentation

- `README.md`
- `skills/loci/SKILL.md`
- `.claude/skills/loci/SKILL.md`
- this plan

The frozen benchmark is read for its checksum only and is never modified.

## Implementation Tasks

### Task 1: Freeze profile contracts and discovery

**Files:**

- `src/loci/graph/profiles.py`
- `tests/graph/test_profiles.py`
- `tests/fixtures/graph_profiles/generic.json`
- `tests/fixtures/graph_profiles/llm-wiki.json`

**Acceptance criteria:**

- Profiles round-trip deterministically.
- Unknown keys, versions, tiers, selectors, fields, directions, or duplicate
  registrations fail with exact structured codes.
- Discovery is lexical, repository-contained, JSON-only, and symlink-safe.
- Required frontmatter fields are derived deterministically.

**Verification:**

```bash
.venv/bin/python -m pytest tests/graph/test_profiles.py -q
```

### Task 2: Add opt-in frontmatter retention

**Files:**

- `src/loci/parser/extractor.py`
- `tests/parser/test_markdown.py`

**Acceptance criteria:**

- Existing `parse_file(path)` output is unchanged.
- Profile-selected string and string-list fields appear on page-root metadata.
- Exact one-based frontmatter field lines are retained.
- Nested mappings and unrequested fields are not retained.

**Verification:**

```bash
.venv/bin/python -m pytest tests/parser/test_markdown.py -q
```

### Task 3: Freeze graph state persistence

**Files:**

- `src/loci/graph/state.py`
- `src/loci/storage/index_store.py`
- `tests/graph/test_state.py`
- `tests/storage/test_index_store.py`

**Acceptance criteria:**

- Empty and populated graph states round-trip deterministically.
- State parsing rejects malformed profiles, nodes, edges, contributions, hashes,
  and diagnostics.
- Storage validates before replacing the existing index.
- Schema version 4 indexes rebuild to version 5.

**Verification:**

```bash
.venv/bin/python -m pytest \
  tests/graph/test_state.py \
  tests/storage/test_index_store.py -q
```

### Checkpoint A: Contracts and storage

- Profile and state tests pass.
- Existing contract, parser, and storage tests pass.
- `git diff --check` is clean.

### Task 4: Materialize profiles and validate contributions

**Files:**

- `src/loci/graph/materialize.py`
- `src/loci/graph/contracts.py`
- `tests/graph/test_materialize.py`
- `tests/fixtures/graph_contributions/llm-wiki-valid.json`

**Acceptance criteria:**

- Generic profile attributes and forward declared edges materialize.
- llm-wiki `knowledge_state` overlays and reverse `mentioned_in` edges
  materialize with exact source evidence.
- Valid contributions enter active overlays and edges.
- Invalid endpoints, policies, attributes, hashes, lines, and references produce
  deterministic diagnostics and no active invalid record.
- Node conflicts are explicit and deterministic.

**Verification:**

```bash
.venv/bin/python -m pytest tests/graph/test_materialize.py -q
```

### Task 5: Integrate freshness and incremental retention

**Files:**

- `src/loci/service.py`
- `src/loci/storage/index_store.py`
- `tests/test_service.py`

**Acceptance criteria:**

- No-profile repositories preserve Stage 1 output and behaviour.
- Profile/contribution add, edit, and delete events trigger refresh.
- Unchanged contribution documents are reused.
- Reused documents are revalidated against current evidence sources.
- Changed or deleted evidence invalidates affected records and produces health
  diagnostics.
- Declared edges never leak into exact-only `graph_neighbors()`.

**Verification:**

```bash
.venv/bin/python -m pytest tests/test_service.py -q
```

### Task 6: Expose graph health through MCP

**Files:**

- `src/loci/service.py`
- `src/loci/mcp_server.py`
- `tests/test_mcp_server.py`
- `README.md`
- `skills/loci/SKILL.md`
- `.claude/skills/loci/SKILL.md`

**Acceptance criteria:**

- `loci_graph_health(repo)` matches the exact success schema.
- Missing and stale repositories use the existing structured error envelope.
- A fresh stdio process reads persisted profiles and diagnostics.
- Existing MCP result shapes remain unchanged.
- All three documentation surfaces list the new tool accurately.

**Verification:**

```bash
.venv/bin/python -m pytest tests/test_mcp_server.py -q
```

### Checkpoint B: Complete Stage 2 slice

- Focused graph, parser, storage, service, and MCP tests pass.
- Complete test suite passes.
- Package build and source compilation pass.
- Fresh-process dogfood indexing works with no profile.
- Generic-profile service tests report healthy and then degraded after evidence
  drift, including reused-document revalidation.
- The llm-wiki profile and contribution fixtures materialize healthy
  `knowledge_state` and reverse `mentioned_in` records.
- A fresh stdio process reads persisted profile and diagnostic state.
- Frozen benchmark checksum is unchanged.
- Complete diff contains no Stage 3 or later retrieval work.

### Final verification evidence

- Complete suite: `302 passed in 29.73s`.
- Source compilation: passed.
- Package build: `dist/loci-0.1.0.tar.gz` and
  `dist/loci-0.1.0-py3-none-any.whl` built successfully.
- Fresh self-index: 780 symbols, 422 exact containment edges, healthy graph.
- Self-index verification: 780 checked, 780 passed, 0 failed.
- Frozen benchmark SHA-256:
  `c52def1bdf592ad735149d199910f74183598eccd9ccf8064335fa0cd0e84e27`.
- `git diff --check`: clean.

## Test Matrix

### Profile contracts

- valid generic profile round-trip;
- valid llm-wiki profile round-trip;
- unsupported schema;
- unknown key;
- duplicate namespace;
- duplicate edge type;
- undeclared edge-rule type;
- forbidden exact/import-resolved/heuristic domain tier;
- unsafe source field;
- reserved or non-canonical namespace;
- duplicate JSON key or non-finite number;
- size, depth, and collection bounds;
- unsafe discovery path, symlinked parent, or non-regular file.

### Parser

- default allowlist unchanged;
- opt-in string field;
- opt-in list field;
- correct field line;
- nested mapping excluded;
- unrequested field excluded;
- requested invalid value emits metadata without retaining the raw value;
- duplicate YAML key, alias, and merge emit rejection metadata.

### Materialization

- generic forward edge;
- llm-wiki reverse `mentioned_in` edge;
- `knowledge_state` overlay;
- unresolved reference diagnostic;
- ambiguous page-root reference diagnostic;
- invalid allowed value diagnostic;
- valid contribution;
- unknown namespace/type/tier;
- missing endpoint;
- stale evidence hash;
- missing evidence source;
- out-of-range line;
- attribute conflict;
- deterministic ordering and deduplication.

### Storage and freshness

- empty Stage 2 graph envelope;
- populated state round-trip;
- atomic validation failure;
- schema v4 rebuild;
- profile add/change/delete refresh;
- contribution add/change/delete refresh;
- unchanged contribution reuse;
- independent evidence drift invalidates reused contribution;
- profile-policy changes revalidate reused contribution;
- no-profile incremental behaviour unchanged.

### Service and MCP

- healthy no-profile response;
- healthy generic profile response;
- healthy llm-wiki fixture response;
- degraded stale contribution response;
- exact neighbors exclude declared edges;
- structured missing-repository error;
- fresh-process persistence proof;
- exact MCP tool list update.

## Baseline and Final Verification

Before implementation:

```bash
.venv/bin/python -m pytest tests/ -q
shasum -a 256 \
  /Users/brummerv/llm-wiki/tests/fixtures/graph_shape_traversal_stage3.json
git diff --check
```

After implementation:

```bash
.venv/bin/python -m pytest tests/graph -q
.venv/bin/python -m pytest tests/parser/test_markdown.py -q
.venv/bin/python -m pytest \
  tests/storage/test_index_store.py \
  tests/test_service.py \
  tests/test_mcp_server.py -q
.venv/bin/python -m pytest tests/ -q
.venv/bin/python -m compileall -q src
uv build
loci index /Users/brummerv/loci --incremental
loci verify /Users/brummerv/loci
git diff --check
shasum -a 256 \
  /Users/brummerv/llm-wiki/tests/fixtures/graph_shape_traversal_stage3.json
```

## Stage 2 Review Gate

The agent must review these observable claims before declaring Stage 2 done:

- a repository with no profile is unchanged;
- one generic profile loads and materializes without loci-core modification;
- the llm-wiki fixture profile projects `knowledge_state` and creates the
  correctly directed `mentioned_in` edge;
- a valid file contribution survives a fresh process;
- an unchanged contribution is reused during incremental indexing;
- changed and deleted evidence invalidates active contribution records;
- stale and invalid records remain visible as structured diagnostics;
- declared domain edges do not appear in the exact-only Stage 1 neighbours API;
- all extension paths are repository-contained and non-executable;
- all extension inputs obey strict JSON and resource bounds;
- the frozen benchmark checksum is unchanged;
- no Stage 3 anchor selection, Stage 4 traversal, Stage 5 compiler integration,
  or Stage 6 import extraction entered the diff.

Stage 3 remains blocked until this evidence passes and the agent recommends the
Stage 2 implementation for approval. Product-owner review is required only if
implementation evidence forces a change to the high-level direction above.

## Risks and Mitigations

| Risk | Impact | Mitigation |
| --- | --- | --- |
| Profiles become an executable plugin system by accident | High | JSON-only strict contracts; no imports, commands, callbacks, or entry points |
| Domain metadata leaks arbitrary frontmatter into the index | High | Explicit profile field allowlist; scalar/string-list values only |
| Stale contributions remain queryable | High | Revalidate evidence hashes on every materialization, including reused documents |
| Declared assertions are mistaken for exact facts | High | Stage 2 domain tier fixed to `declared`; exact neighbours explicitly filter them out |
| Profile precedence creates hidden behavior | Medium | Repository-local only; every duplicate claimant is excluded with a diagnostic |
| Bad contribution prevents code navigation | Medium | Preserve the valid symbol index and persist degraded diagnostics |
| JSON envelope grows without bound | Medium | Stage 2 fixtures are small; measure before any storage-engine change |
| llm-wiki semantics leak into loci | High | Fixture profile is data; no llm-wiki imports, normalization, answerability, or sufficiency logic |

## Explicitly Deferred

- external or machine-global profile registration;
- service-call or MCP contribution mutation;
- executable profile adapters or Python entry points;
- arbitrary YAML/JSONPath expressions;
- nested or secret frontmatter retention;
- Markdown body-link extraction;
- profile ranking hints and state filters;
- neighbour trust/type filter parameters;
- multi-hop paths, cycles, budgets, continuation, and ranking;
- question-shaped anchors;
- llm-wiki compiler integration or provider removal;
- import extraction or resolution;
- benchmark execution or threshold changes;
- graph database or graph-analysis dependency.
