from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, RootModel


JSONValue = JsonValue
_OMITTED: Any = None


class StrictOutputModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class LociErrorBody(StrictOutputModel):
    code: str
    message: str
    details: dict[str, JSONValue]


class LociErrorOutput(StrictOutputModel):
    error: LociErrorBody


class LociFileSuccess(StrictOutputModel):
    file: str
    content: str
    total_lines: int
    start_line: int
    end_line: int


class LociFileOutput(RootModel[LociFileSuccess | LociErrorOutput]):
    model_config = ConfigDict(json_schema_extra={"type": "object"})


class CoverageExclusion(StrictOutputModel):
    reason: Literal[
        "ignored",
        "policy_excluded",
        "sensitive_or_binary",
        "unsupported_file_type",
    ]
    paths: int
    samples: list[str]
    omitted_samples: int


class StoredCoverage(StrictOutputModel):
    schema_version: Literal[1]
    state: Literal["complete", "partial", "unknown"]
    scope: Literal["repository"]
    source_scope: Literal["indexed_supported_source"]
    indexed_files: int
    excluded_paths: int | None
    exclusions: list[CoverageExclusion]
    unknown_reason: str | None


class QueryCoverage(StoredCoverage):
    query_scope: Literal["indexed_symbols", "indexed_source_text"]


class GraphDiagnostic(StrictOutputModel):
    severity: Literal["info", "warning", "error"]
    code: str
    message: str
    source: str | None = _OMITTED
    details: dict[str, JSONValue]


class IndexWarning(StrictOutputModel):
    file: str
    lines: int
    reason: Literal["0 symbols extracted"]


class LociIndexSuccess(StrictOutputModel):
    path: str
    symbols_indexed: int
    graph_profiles_loaded: int
    graph_contributions_loaded: int
    graph_contributions_reused: int
    graph_node_overlays_indexed: int
    graph_edges_indexed: int
    graph_file_nodes_indexed: int
    graph_go_packages_indexed: int
    graph_rust_crates_indexed: int
    graph_imports_indexed: int
    graph_imports_resolved: int
    graph_imports_unresolved: int
    graph_symbol_references_indexed: int
    graph_symbol_references_resolved: int
    graph_symbol_references_unresolved: int
    graph_calls_indexed: int
    graph_calls_resolved: int
    graph_calls_unresolved: int
    graph_status: Literal["healthy", "degraded"]
    graph_diagnostics: list[GraphDiagnostic]
    coverage: StoredCoverage
    files_skipped: int
    languages: dict[str, int]
    warnings: list[IndexWarning] = _OMITTED


class LociIndexOutput(RootModel[LociIndexSuccess | LociErrorOutput]):
    model_config = ConfigDict(json_schema_extra={"type": "object"})


class OutlineSymbol(StrictOutputModel):
    id: str
    name: str
    kind: str
    line: int
    end_line: int
    signature: str
    summary: str
    decorators: list[str] = _OMITTED
    file_bytes: int = _OMITTED
    saved_pct: int | float = _OMITTED
    span_kind: str = _OMITTED


class OutlineFile(StrictOutputModel):
    file: str
    symbols: list[OutlineSymbol]


class LociOutlineSuccess(StrictOutputModel):
    files: list[OutlineFile]


class LociOutlineOutput(RootModel[LociOutlineSuccess | LociErrorOutput]):
    model_config = ConfigDict(json_schema_extra={"type": "object"})


class RetrievedSymbol(StrictOutputModel):
    id: str
    source: str
    byte_offset: int | None
    byte_length: int | None
    line: int | None
    end_line: int | None
    signature: str | None
    kind: str | None
    language: str | None
    decorators: list[str] = _OMITTED
    context_before: list[str] = _OMITTED
    context_after: list[str] = _OMITTED


class LociGetSuccess(StrictOutputModel):
    symbols: list[RetrievedSymbol]


class LociGetOutput(RootModel[LociGetSuccess | LociErrorOutput]):
    model_config = ConfigDict(json_schema_extra={"type": "object"})


class StoredSymbol(StrictOutputModel):
    id: str
    name: str
    qualified_name: str
    kind: str
    language: str
    file_path: str
    byte_offset: int
    byte_length: int
    signature: str
    docstring: str
    summary: str
    content_hash: str
    decorators: list[str]
    keywords: list[str]
    metadata: dict[str, JSONValue]
    line: int
    end_line: int


class SearchSymbol(StoredSymbol):
    score: int | float
    file_bytes: int = _OMITTED
    saved_pct: int | float = _OMITTED
    span_kind: str = _OMITTED
    match_scope: list[str] = _OMITTED


class LociSearchSuccess(StrictOutputModel):
    symbols: list[SearchSymbol]
    coverage: QueryCoverage


class LociSearchOutput(RootModel[LociSearchSuccess | LociErrorOutput]):
    model_config = ConfigDict(json_schema_extra={"type": "object"})


class GrepMatch(StrictOutputModel):
    file: str
    line: int
    match: str
    context_before: list[str]
    context_after: list[str]


class LociGrepSuccess(StrictOutputModel):
    matches: list[GrepMatch]
    coverage: QueryCoverage


class LociGrepOutput(RootModel[LociGrepSuccess | LociErrorOutput]):
    model_config = ConfigDict(json_schema_extra={"type": "object"})


class VerificationFailure(StrictOutputModel):
    id: str
    name: str
    kind: str
    file: str
    issue: str


class LociVerifySuccess(StrictOutputModel):
    repo: str
    checked: int
    passed: int
    failed: list[VerificationFailure]


class LociVerifyOutput(RootModel[LociVerifySuccess | LociErrorOutput]):
    model_config = ConfigDict(json_schema_extra={"type": "object"})


class RepositorySummary(StrictOutputModel):
    cache_key: str
    symbols: int
    path: str


class LociListSuccess(StrictOutputModel):
    repos: list[RepositorySummary]


class LociListOutput(RootModel[LociListSuccess | LociErrorOutput]):
    model_config = ConfigDict(json_schema_extra={"type": "object"})


class StoreResolution(StrictOutputModel):
    base_dir: str
    source: str
    config_path: str = _OMITTED
    namespace: str = _OMITTED
    store_id: str = _OMITTED


HealthState = Literal["healthy", "stale", "missing", "corrupt", "overlapping"]


class HealthReason(StrictOutputModel):
    state: HealthState
    code: str
    details: dict[str, JSONValue]


class ProbeUnavailableReason(StrictOutputModel):
    code: str
    details: dict[str, JSONValue]


class FreshnessProbeResult(StrictOutputModel):
    status: Literal["complete", "unavailable"]
    index_bytes: int | None
    repository_paths_scanned: int
    repository_bytes_scanned: int
    reason: ProbeUnavailableReason = _OMITTED


class StoreHealthItem(StrictOutputModel):
    cache_key: str
    repo: str
    symbols: int
    states: list[HealthState]
    reasons: list[HealthReason]
    probe: FreshnessProbeResult


class StoreHealthCounts(StrictOutputModel):
    repositories: int | None
    returned: int
    healthy: int
    stale: int
    missing: int
    corrupt: int
    overlapping: int
    incomplete: int


class Pagination(StrictOutputModel):
    offset: int
    limit: int
    next_offset: int | None


class StoreHealthBounds(StrictOutputModel):
    max_catalog_bytes: int
    max_index_bytes: int
    max_probe_paths: int
    max_probe_bytes: int


class StoreDiagnostic(StrictOutputModel):
    state: Literal["corrupt", "unavailable"]
    code: str
    details: dict[str, JSONValue]


class LociStoreHealthSuccess(StrictOutputModel):
    schema_version: Literal[1]
    status: Literal["healthy", "unhealthy", "incomplete"]
    complete: bool
    items: list[StoreHealthItem]
    counts: StoreHealthCounts
    pagination: Pagination
    bounds: StoreHealthBounds
    diagnostics: list[StoreDiagnostic]


class LociStoreHealthOutput(RootModel[LociStoreHealthSuccess | LociErrorOutput]):
    model_config = ConfigDict(json_schema_extra={"type": "object"})


class StatsRow(StrictOutputModel):
    name: str
    gets: int
    saved_bytes: int
    ratio_pct: int
    last_ts: float | None


class StatsLaneSummary(StrictOutputModel):
    outlines: int
    gets: int
    symbol_bytes: int
    file_bytes_not_loaded: int
    tokens_not_loaded: int
    savings_ratio: str
    last_get_ts: float | None


class LociStatsSuccess(StrictOutputModel):
    total_gets: int
    total_outlines: int
    symbol_bytes_retrieved: int
    file_bytes_not_loaded: int
    tokens_not_loaded: int
    savings_ratio: str
    last_get_ts: float | None
    by_file: list[StatsRow]
    by_repo: list[StatsRow]
    code: StatsLaneSummary
    docs: StatsLaneSummary
    by_file_code: list[StatsRow]
    by_repo_code: list[StatsRow]
    by_doc: list[StatsRow]
    by_repo_doc: list[StatsRow]
    store: StoreResolution


class LociStatsOutput(RootModel[LociStatsSuccess | LociErrorOutput]):
    model_config = ConfigDict(json_schema_extra={"type": "object"})


class AnalyzePeriod(StrictOutputModel):
    from_: str = Field(alias="from")
    to: str


class AnalyzeSummary(StrictOutputModel):
    total_gets: int
    total_searches: int
    total_misses: int
    miss_rate: float
    correlated_pct: float


class AnalyzeFinding(StrictOutputModel):
    type: Literal[
        "search_miss",
        "search_blind_spot",
        "search_ranking_poor",
        "kind_dead_weight",
        "poor_extraction",
        "refetch_hotspot",
    ]
    severity: Literal["high", "medium", "low"]
    data: dict[str, JSONValue]
    suggestion: str


class LociAnalyzeSuccess(StrictOutputModel):
    period: AnalyzePeriod
    summary: AnalyzeSummary
    findings: list[AnalyzeFinding]
    store: StoreResolution


class LociAnalyzeOutput(RootModel[LociAnalyzeSuccess | LociErrorOutput]):
    model_config = ConfigDict(json_schema_extra={"type": "object"})


ResolutionTier = Literal["exact", "declared", "import-resolved", "heuristic"]


class GraphNodeRef(StrictOutputModel):
    id: str
    namespace: str
    kind: str
    attributes: dict[str, JSONValue]


class GraphEvidence(StrictOutputModel):
    file: str
    line: int
    content_hash: str


class GraphEdge(StrictOutputModel):
    from_: str = Field(alias="from")
    to: str
    type: str
    directed: bool
    namespace: str
    resolution: ResolutionTier
    evidence: GraphEvidence


class GraphFilters(StrictOutputModel):
    namespaces: list[str] | None
    edge_types: list[str] | None
    resolutions: list[ResolutionTier]
    direction: Literal["outgoing", "incoming", "either"]


class GraphNeighbor(StrictOutputModel):
    node: GraphNodeRef
    edge: GraphEdge


class TraversalNeighbor(GraphNeighbor):
    traversed: Literal["forward", "reverse"]


class EvidenceSpan(StrictOutputModel):
    file: str
    start_line: int
    end_line: int
    content: str


class PathStep(StrictOutputModel):
    traversed: Literal["forward", "reverse"]
    edge: GraphEdge
    evidence_span: EvidenceSpan


class AcceptedPath(StrictOutputModel):
    nodes: list[GraphNodeRef]
    steps: list[PathStep]


class RejectedEvidence(StrictOutputModel):
    file: str
    line: int


class RejectedEdge(StrictOutputModel):
    from_: str = Field(alias="from")
    to: str
    type: str
    directed: bool
    namespace: str
    resolution: ResolutionTier
    evidence: RejectedEvidence


class RejectedStep(StrictOutputModel):
    traversed: Literal["forward", "reverse"]
    edge: RejectedEdge


class RejectedPath(StrictOutputModel):
    nodes: list[str]
    reason: Literal[
        "EVIDENCE_UNAVAILABLE",
        "EVIDENCE_BUDGET_EXCEEDED",
        "SEMANTIC_BRIDGE_MISSING",
        "HUB_SHORTCUT",
    ]
    steps: list[RejectedStep] = _OMITTED
    required_bridge_terms: list[str] = _OMITTED
    high_degree_nodes: list[str] = _OMITTED


class GraphPathBudget(StrictOutputModel):
    max_hops: int
    max_nodes: int
    max_paths: int
    path_offset: int
    evidence_bytes: int
    estimated_tokens: int
    max_evidence_bytes: int
    max_estimated_tokens: int
    hop_limit_reached: bool
    node_limit_reached: bool
    next_path_offset: int | None


class AnchorReason(StrictOutputModel):
    kind: Literal["explicit_seed", "inferred"]
    matched_terms: list[str]
    match_scope: list[str]


class Anchor(StrictOutputModel):
    node: GraphNodeRef
    matched_symbol_id: str
    name: str
    score: float | None
    reason: AnchorReason


class AnchorCounts(StrictOutputModel):
    indexed_nodes: int
    eligible_units: int
    qualified_candidates: int
    collapsed_symbols: int
    returned_anchors: int
    omitted_candidates: int


class AnchorBudget(StrictOutputModel):
    requested_max_anchors: int
    effective_max_anchors: int


class LociGraphAnchorsSuccess(StrictOutputModel):
    schema_version: Literal[1]
    repo: str
    question: str
    selection: Literal["explicit", "inferred"]
    question_terms: list[str]
    anchors: list[Anchor]
    counts: AnchorCounts
    budget: AnchorBudget
    diagnostics: list[GraphDiagnostic]


class LociGraphAnchorsOutput(
    RootModel[LociGraphAnchorsSuccess | LociErrorOutput]
):
    model_config = ConfigDict(json_schema_extra={"type": "object"})


class NeighborResult(StrictOutputModel):
    seed: GraphNodeRef
    neighbors: list[GraphNeighbor]


class LociGraphNeighborsSuccess(StrictOutputModel):
    schema_version: Literal[1]
    repo: str
    results: list[NeighborResult]
    diagnostics: list[GraphDiagnostic]


class LociGraphNeighborsOutput(
    RootModel[LociGraphNeighborsSuccess | LociErrorOutput]
):
    model_config = ConfigDict(json_schema_extra={"type": "object"})


class TraversalResult(StrictOutputModel):
    seed: GraphNodeRef
    neighbors: list[TraversalNeighbor]
    returned: int
    omitted: int


class TraversalCounts(StrictOutputModel):
    filtered_edges: int
    returned_neighbors: int
    omitted_neighbors: int


class TraversalBudget(StrictOutputModel):
    max_neighbors_per_seed: int


class LociGraphTraverseNeighborsSuccess(StrictOutputModel):
    schema_version: Literal[1]
    repo: str
    filters: GraphFilters
    results: list[TraversalResult]
    counts: TraversalCounts
    budget: TraversalBudget
    diagnostics: list[GraphDiagnostic]


class LociGraphTraverseNeighborsOutput(
    RootModel[LociGraphTraverseNeighborsSuccess | LociErrorOutput]
):
    model_config = ConfigDict(json_schema_extra={"type": "object"})


class GraphPathCounts(StrictOutputModel):
    filtered_edges: int
    examined_nodes: int
    examined_paths: int
    returned_paths: int
    rejected_paths: int
    omitted_rejected_paths: int
    omitted_nodes: int
    omitted_paths: int


class LociGraphPathsSuccess(StrictOutputModel):
    schema_version: Literal[1]
    repo: str
    support_kind: Literal["edge_sequence"]
    sources: list[GraphNodeRef]
    targets: list[GraphNodeRef]
    filters: GraphFilters
    paths: list[AcceptedPath]
    rejected_paths: list[RejectedPath]
    counts: GraphPathCounts
    budget: GraphPathBudget
    diagnostics: list[GraphDiagnostic]


class LociGraphPathsOutput(RootModel[LociGraphPathsSuccess | LociErrorOutput]):
    model_config = ConfigDict(json_schema_extra={"type": "object"})


class SemanticBridge(StrictOutputModel):
    required: bool
    required_terms: list[str]
    matched_terms: list[str]


class RetrievalScoreComponents(StrictOutputModel):
    anchor: float
    endpoint: float
    evidence: float
    hop: float
    direct: float
    hub_penalty: float


class RetrievedPath(AcceptedPath):
    support_kind: Literal["direct_authored_edge", "semantic_bridge"]
    semantic_bridge: SemanticBridge
    retrieval_score: float
    score_components: RetrievalScoreComponents


class RetrievalRouting(StrictOutputModel):
    kind: Literal["relationship", "suppressed"]
    reason: Literal[
        "relationship_intent",
        "no_candidate_endpoint",
        "attribute_or_measurement_question",
        "non_relationship_question",
    ]


class RetrievalCounts(GraphPathCounts):
    duplicate_paths: int


class LociGraphRetrieveSuccess(StrictOutputModel):
    schema_version: Literal[1]
    repo: str
    question: str
    selection: Literal["explicit", "inferred"]
    question_terms: list[str]
    anchors: list[Anchor]
    routing: RetrievalRouting
    filters: GraphFilters
    hub_threshold: int
    paths: list[RetrievedPath]
    rejected_paths: list[RejectedPath]
    counts: RetrievalCounts
    budget: GraphPathBudget
    diagnostics: list[GraphDiagnostic]


class LociGraphRetrieveOutput(
    RootModel[LociGraphRetrieveSuccess | LociErrorOutput]
):
    model_config = ConfigDict(json_schema_extra={"type": "object"})


class GraphProfileEdgeType(StrictOutputModel):
    type: str
    directed: Literal[True]
    allowed_resolutions: list[Literal["declared"]]


class GraphProfile(StrictOutputModel):
    namespace: str
    source: str
    content_hash: str
    node_attributes: list[str]
    edge_types: list[GraphProfileEdgeType]


class GraphHealthCounts(StrictOutputModel):
    profiles: int
    node_overlays: int
    edges: int
    contributions: int
    diagnostics: int
    graph_file_nodes_indexed: int
    graph_go_packages_indexed: int
    graph_rust_crates_indexed: int
    graph_imports_indexed: int
    graph_imports_resolved: int
    graph_imports_unresolved: int
    graph_symbol_references_indexed: int
    graph_symbol_references_resolved: int
    graph_symbol_references_unresolved: int
    graph_calls_indexed: int
    graph_calls_resolved: int
    graph_calls_unresolved: int


class LociGraphHealthSuccess(StrictOutputModel):
    schema_version: Literal[1]
    repo: str
    status: Literal["healthy", "degraded"]
    profiles: list[GraphProfile]
    counts: GraphHealthCounts
    diagnostics: list[GraphDiagnostic]


class LociGraphHealthOutput(RootModel[LociGraphHealthSuccess | LociErrorOutput]):
    model_config = ConfigDict(json_schema_extra={"type": "object"})


class RecordCounts(StrictOutputModel):
    total: int
    resolved: int
    unresolved: int
    returned: int


class RustImportContext(StrictOutputModel):
    kind: Literal["use", "module", "extern_crate"]
    lexical_module_path: list[str]
    visibility: str
    module_level: bool
    configuration: Literal["unconditional", "conditional", "unsupported"]
    path_override: str | None
    lexical_module_visibilities: list[str]
    lexical_module_configurations: list[
        Literal["unconditional", "conditional", "unsupported"]
    ]
    inline: bool


class RawImport(StrictOutputModel):
    source_file: str
    language: str
    line: int
    text: str
    specifier: str
    imported_name: str | None
    type_only: bool
    is_reexport: bool
    source_hash: str
    rust: RustImportContext | None


ImportUnresolvedReason = Literal[
    "external",
    "not_indexed",
    "ambiguous",
    "unsupported_language",
    "invalid_specifier",
    "inaccessible",
    "unsupported_configuration",
]

ImportResolutionBasis = Literal[
    "relative_path",
    "compiler_paths",
    "compiler_base_url",
    "compiler_root_dirs",
    "package_imports",
    "package_self_reference",
    "workspace_exports",
    "workspace_legacy_entry",
    "rust_module_declaration",
    "rust_module_path",
    "cargo_path_dependency",
    "cargo_workspace_dependency",
    "cargo_package_library",
]


class ImportItem(StrictOutputModel):
    raw: RawImport
    source_file: str
    source_id: str
    target_file: str | None
    target_package: str | None
    target_crate: str | None
    target_kind: Literal["file", "package", "crate"] | None
    target_id: str | None
    specifier: str
    imported_name: str | None
    language: str
    line: int
    text: str
    type_only: bool
    is_reexport: bool
    status: Literal["resolved", "unresolved"]
    resolution: Literal["import-resolved"] | None
    unresolved_reason: ImportUnresolvedReason | None
    resolution_basis: ImportResolutionBasis | None
    resolution_control_files: list[str]
    resolution_configuration: Literal["unconditional", "declared_possible"] | None


class LociGraphImportsSuccess(StrictOutputModel):
    schema_version: Literal[1]
    repo: str
    file: str | None
    status: Literal["all", "resolved", "unresolved"]
    items: list[ImportItem]
    counts: RecordCounts
    pagination: Pagination


class LociGraphImportsOutput(
    RootModel[LociGraphImportsSuccess | LociErrorOutput]
):
    model_config = ConfigDict(json_schema_extra={"type": "object"})


class ImportBinding(StrictOutputModel):
    local_name: str | None
    imported_name: str | None
    exported_name: str | None
    kind: Literal["symbol", "namespace", "module", "glob", "side_effect", "blank"]
    type_only: bool
    module_level: bool
    declaration_start_byte: int
    scope_start_byte: int
    scope_end_byte: int
    import_line: int
    import_text: str
    import_specifier: str


class ExecutableOwner(StrictOutputModel):
    kind: Literal["file", "callable", "unindexed"]
    definition_start_byte: int | None
    definition_end_byte: int | None
    body_start_byte: int | None
    body_end_byte: int | None


class RawSymbolReference(StrictOutputModel):
    source_file: str
    language: str
    line: int
    column: int
    start_byte: int
    end_byte: int
    text: str
    path: list[str]
    candidate_bindings: list[ImportBinding]
    binding_state: Literal[
        "definite", "deferred", "shadowed", "ambiguous", "unsupported"
    ]
    source_hash: str
    owner: ExecutableOwner


class ReferenceSupport(StrictOutputModel):
    kind: Literal["import_binding", "local_export", "reexport", "definition"]
    file: str
    line: int
    content_hash: str
    endpoint_id: str


ReferenceUnresolvedReason = Literal[
    "import_unresolved",
    "binding_shadowed",
    "ambiguous_binding",
    "ambiguous_source",
    "target_not_indexed",
    "target_inaccessible",
    "ambiguous_target",
    "unsupported_reference",
    "configuration_divergent",
]


class ReferenceItem(StrictOutputModel):
    raw: RawSymbolReference
    binding: ImportBinding | None
    source_file: str
    source_id: str
    source_kind: str
    import_source_id: str
    import_target_id: str | None
    target_file: str | None
    target_id: str | None
    target_kind: str | None
    status: Literal["resolved", "unresolved"]
    resolution: Literal["import-resolved"] | None
    unresolved_reason: ReferenceUnresolvedReason | None
    import_unresolved_reason: ImportUnresolvedReason | None
    resolution_basis: Literal[
        "direct_binding", "qualified_member", "reexport_chain"
    ] | None
    support: list[ReferenceSupport]
    resolution_control_files: list[str]
    resolution_configuration: Literal["unconditional", "declared_possible"] | None


class LociGraphReferencesSuccess(StrictOutputModel):
    schema_version: Literal[1]
    repo: str
    file: str | None
    status: Literal["all", "resolved", "unresolved"]
    items: list[ReferenceItem]
    counts: RecordCounts
    pagination: Pagination


class LociGraphReferencesOutput(
    RootModel[LociGraphReferencesSuccess | LociErrorOutput]
):
    model_config = ConfigDict(json_schema_extra={"type": "object"})


class LocalCallableBinding(StrictOutputModel):
    name: str
    callable_kind: Literal["function", "method"]
    definition_start_byte: int
    definition_end_byte: int
    definition_line: int
    scope_start_byte: int
    scope_end_byte: int


class RawCallSite(StrictOutputModel):
    source_file: str
    language: Literal["python", "javascript", "typescript", "go", "rust"]
    line: int
    column: int
    start_byte: int
    end_byte: int
    callee_start_byte: int
    callee_end_byte: int
    callee_text: str
    callee_path: list[str]
    callee_form: Literal["identifier", "static_path", "dynamic"]
    local_candidates: list[LocalCallableBinding]
    local_binding_state: Literal[
        "definite", "shadowed", "ambiguous", "absent", "unsupported"
    ]
    owner: ExecutableOwner
    source_hash: str


class CallSupport(StrictOutputModel):
    kind: Literal[
        "call_site", "caller_definition", "local_definition", "symbol_reference"
    ]
    file: str
    line: int
    content_hash: str
    endpoint_id: str


CallUnresolvedReason = Literal[
    "unsupported_callee",
    "caller_not_indexed",
    "caller_ambiguous",
    "local_binding_shadowed",
    "local_binding_ambiguous",
    "local_target_not_indexed",
    "callee_not_proven",
    "reference_unresolved",
    "target_not_callable",
    "conflicting_resolution",
]


class CallItem(StrictOutputModel):
    raw: RawCallSite
    caller_id: str | None
    caller_kind: Literal["file", "function", "method"] | None
    target_file: str | None
    target_id: str | None
    target_kind: str | None
    status: Literal["resolved", "unresolved"]
    resolution: Literal["exact", "import-resolved"] | None
    unresolved_reason: CallUnresolvedReason | None
    reference_unresolved_reason: ReferenceUnresolvedReason | None
    resolution_basis: Literal["local_callable", "imported_reference"] | None
    support: list[CallSupport]
    resolution_control_files: list[str]
    resolution_configuration: Literal["unconditional", "declared_possible"] | None


class LociGraphCallsSuccess(StrictOutputModel):
    schema_version: Literal[1]
    repo: str
    file: str | None
    status: Literal["all", "resolved", "unresolved"]
    items: list[CallItem]
    counts: RecordCounts
    pagination: Pagination


class LociGraphCallsOutput(RootModel[LociGraphCallsSuccess | LociErrorOutput]):
    model_config = ConfigDict(json_schema_extra={"type": "object"})
