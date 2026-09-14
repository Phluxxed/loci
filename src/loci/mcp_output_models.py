from __future__ import annotations

from pathlib import PurePosixPath
from typing import Annotated, Any, Literal, get_args

from pydantic import BaseModel, ConfigDict, Field, JsonValue, RootModel, model_validator
from loci.parser.type_models import valid_type_import_path


JSONValue = JsonValue
_OMITTED: Any = None


def _require_relative_path(value: str, field: str) -> None:
    path = PurePosixPath(value)
    if (
        not value
        or "\\" in value
        or path.is_absolute()
        or ".." in path.parts
        or path.as_posix() != value
    ):
        raise ValueError(f"{field} must be a normalized relative path")


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
    graph_swift_modules_indexed: int
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
    graph_type_relations_indexed: int | None = _OMITTED
    graph_type_relations_resolved: int | None = _OMITTED
    graph_type_relations_unresolved: int | None = _OMITTED
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
    search_id: str | None


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
    explicit_search_selections: int
    ranked_search_selections: int
    not_surfaced_search_selections: int


class AnalyzeFinding(StrictOutputModel):
    type: Literal[
        "search_miss",
        "search_blind_spot",
        "search_ranking_poor",
        "kind_dead_weight",
        "poor_extraction",
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


class TypeDeclarationOwner(StrictOutputModel):
    kind: Literal[
        "function", "method", "class", "interface", "type", "constant", "struct", "enum", "trait", "impl", "unindexed"
    ]
    start_byte: int = Field(ge=0)
    end_byte: int = Field(ge=1)

    @model_validator(mode="after")
    def _ordered_span(self) -> TypeDeclarationOwner:
        if self.start_byte >= self.end_byte:
            raise ValueError("owner span must be non-empty and ordered")
        return self


class LocalTypeBinding(StrictOutputModel):
    name: str = Field(min_length=1)
    kind: Literal[
        "class", "interface", "type", "enum", "struct", "trait", "function", "constant",
        "type_parameter", "parameter", "namespace", "unindexed",
    ]
    namespace: Literal["type", "value", "both"]
    declaration_start_byte: int = Field(ge=0)
    declaration_end_byte: int = Field(ge=1)
    scope_start_byte: int = Field(ge=0)
    scope_end_byte: int = Field(ge=1)

    @model_validator(mode="after")
    def _valid_spans_and_namespace(self) -> LocalTypeBinding:
        if self.declaration_start_byte >= self.declaration_end_byte:
            raise ValueError("declaration span must be non-empty and ordered")
        if self.scope_start_byte >= self.scope_end_byte:
            raise ValueError("scope span must be non-empty and ordered")
        if not (
            self.scope_start_byte <= self.declaration_start_byte
            and self.declaration_end_byte <= self.scope_end_byte
        ):
            raise ValueError("declaration span must be contained by the binding scope")
        namespaces = {
            "interface": {"type"},
            "struct": {"type"}, "trait": {"type"},
            "type": {"type"},
            "type_parameter": {"type"},
            "function": {"value"},
            "constant": {"value"},
            "parameter": {"value"},
            "class": {"both"},
            "enum": {"both"},
            "namespace": {"both"},
            "unindexed": {"type", "value", "both"},
        }
        if self.namespace not in namespaces[self.kind]:
            raise ValueError(
                f"{self.kind} bindings cannot use the {self.namespace} namespace"
            )
        return self


class RawTypeObservation(StrictOutputModel):
    source_file: str = Field(min_length=1)
    language: Literal["typescript", "python", "javascript", "go", "rust"]
    line: int = Field(ge=1)
    column: int = Field(ge=1)
    start_byte: int = Field(ge=0)
    end_byte: int = Field(ge=1)
    text: str = Field(min_length=1)
    path: list[str] = Field(max_length=16)
    relation: Literal["uses_type", "extends", "implements", "embeds", "supertrait", "impl_trait", "impl_self_type"]
    context: Literal[
        "annotation", "return", "property", "alias", "type_argument",
        "constraint", "type_query", "heritage", "struct_embedding", "interface_embedding",
        "supertrait", "impl_trait", "impl_self_type",
    ]
    lookup_space: Literal["type", "value"]
    owner: TypeDeclarationOwner
    local_bindings: list[LocalTypeBinding] = Field(max_length=16)
    import_bindings: list[ImportBinding] = Field(max_length=16)
    binding_state: Literal[
        "local", "imported", "package", "deferred", "shadowed", "ambiguous", "unbound", "unsupported"
    ]
    candidates_complete: bool
    candidates_truncated: int = Field(ge=0)
    unsupported_reason: str | None = Field(max_length=256)
    source_hash: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def _valid_observation(self) -> RawTypeObservation:
        _require_relative_path(self.source_file, "source_file")
        if self.language == "javascript" and (
            self.relation != "extends" or self.context != "heritage" or self.lookup_space != "value"
        ):
            raise ValueError("JavaScript observations require authored value-space class heritage")
        if self.relation == "embeds" and (self.language != "go" or self.context not in {"struct_embedding", "interface_embedding"}):
            raise ValueError("embedding requires an authored Go embedding context")
        if self.context in {"struct_embedding", "interface_embedding"} and self.relation != "embeds":
            raise ValueError("embedding context requires an embeds relation")
        if self.language == "go" and (self.relation not in {"uses_type", "embeds"} or self.lookup_space != "type"):
            raise ValueError("Go observations require authored types or embedding")
        rust_relations = {"supertrait", "impl_trait", "impl_self_type"}
        if self.relation in rust_relations and (self.language != "rust" or self.context != self.relation):
            raise ValueError("Rust relation requires its authored Rust context")
        if self.context in rust_relations and self.relation != self.context:
            raise ValueError("Rust context requires its matching relation")
        if self.language == "rust" and (self.relation not in {"uses_type", *rust_relations} or self.lookup_space != "type"):
            raise ValueError("Rust observations require authored type relations")
        if self.relation == "supertrait" and self.owner.kind not in {"trait", "unindexed"}:
            raise ValueError("supertrait requires a trait owner")
        if self.relation in {"impl_trait", "impl_self_type"} and self.owner.kind not in {"impl", "unindexed"}:
            raise ValueError("implementation links require a separate impl owner")
        if self.binding_state == "package" and (self.language != "go" or len(self.path) != 1 or self.local_bindings or self.import_bindings):
            raise ValueError("package lookup requires a bare Go name without lexical bindings")
        if self.binding_state == "deferred" and (self.language != "go" or len(self.path) != 2 or self.local_bindings or not self.import_bindings or any(b.kind != "namespace" or b.local_name is not None for b in self.import_bindings)):
            raise ValueError("deferred Go lookup requires implicit package imports")
        if self.start_byte >= self.end_byte:
            raise ValueError("observation span must be non-empty and ordered")
        if len(self.text.encode("utf-8")) != self.end_byte - self.start_byte:
            raise ValueError("text UTF-8 byte length must match the observation span")
        if not (
            self.owner.start_byte <= self.start_byte
            and self.end_byte <= self.owner.end_byte
        ):
            raise ValueError("observation span must be contained by its owner")
        if len(self.local_bindings) + len(self.import_bindings) > 16:
            raise ValueError("observation exceeds the type binding limit")
        if any(not segment for segment in self.path):
            raise ValueError("path segments must be non-empty")
        if self.candidates_complete and self.candidates_truncated:
            raise ValueError("complete candidates cannot report truncation")
        if self.binding_state == "unsupported":
            if not self.unsupported_reason:
                raise ValueError("unsupported observations require a reason")
        else:
            if not self.path:
                raise ValueError("supported observations require a non-empty path")
            if self.unsupported_reason is not None:
                raise ValueError(
                    "unsupported_reason is only valid for unsupported observations"
                )
            if self.binding_state == "local" and not self.local_bindings:
                raise ValueError("local observations require a local binding")
            if self.binding_state == "imported" and not self.import_bindings:
                raise ValueError("imported observations require an import binding")
            if self.binding_state == "ambiguous" and (
                len(self.local_bindings) + len(self.import_bindings) < 2
            ):
                raise ValueError("ambiguous observations require multiple candidates")
            if self.binding_state == "unbound" and (
                self.local_bindings or self.import_bindings
            ):
                raise ValueError("unbound observations cannot carry bindings")
        for binding in self.local_bindings:
            if not (
                binding.scope_start_byte <= self.start_byte
                and self.end_byte <= binding.scope_end_byte
            ):
                raise ValueError("local binding scope must contain the observation")
            if self.binding_state != "unsupported" and binding.name != self.path[0]:
                raise ValueError("local binding name must match the path root")
            if binding.namespace != "both" and self.lookup_space != binding.namespace:
                raise ValueError("local binding namespace does not contain lookup space")
        for binding in self.import_bindings:
            if not (
                binding.scope_start_byte <= self.start_byte
                and self.end_byte <= binding.scope_end_byte
            ):
                raise ValueError("import binding scope must contain the observation")
            if (
                self.binding_state != "unsupported"
                and binding.local_name is not None
                and binding.local_name != self.path[0]
            ):
                raise ValueError("import binding local name must match the path root")
        return self


class TypeSupport(StrictOutputModel):
    kind: Literal[
        "type_site", "owner", "definition", "import_binding", "local_export", "reexport", "package_clause", "module_declaration"
    ]
    file: str = Field(min_length=1)
    line: int = Field(ge=1)
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    endpoint_id: str | None

    @model_validator(mode="after")
    def _valid_support(self) -> TypeSupport:
        _require_relative_path(self.file, "file")
        if self.endpoint_id is not None and not self.endpoint_id:
            raise ValueError("endpoint_id must be non-empty when present")
        return self


class TypeControl(StrictOutputModel):
    file: str = Field(min_length=1)
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def _valid_control(self) -> TypeControl:
        _require_relative_path(self.file, "file")
        return self


class ReferenceSupport(StrictOutputModel):
    kind: Literal["import_binding", "local_export", "reexport", "definition"]
    file: str
    line: int
    content_hash: str
    endpoint_id: str


class TypeContextReferenceSpan(StrictOutputModel):
    file: str
    start_byte: int
    end_byte: int


class TypeContextReference(StrictOutputModel):
    owner_id: str
    target_id: str
    reference: TypeContextReferenceSpan
    edge: GraphEdge
    support: list[TypeSupport | ReferenceSupport]


class TypeContextEvidence(StrictOutputModel):
    file: str
    start_line: int
    end_line: int
    byte_offset: int
    content: str
    content_hash: str


class TypeContext(StrictOutputModel):
    scope: Literal["existing_imported_type_references", "declared_type_relations"]
    status: Literal["complete", "partial", "unavailable"]
    symbols: list[RetrievedSymbol]
    references: list[TypeContextReference]
    evidence: list[TypeContextEvidence]
    limits: dict[str, int]
    omissions: dict[str, int]


class LociGetSuccess(StrictOutputModel):
    symbols: list[RetrievedSymbol]
    type_context: TypeContext = _OMITTED


class LociGetOutput(RootModel[LociGetSuccess | LociErrorOutput]):
    model_config = ConfigDict(json_schema_extra={"type": "object"})


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
    graph_swift_modules_indexed: int
    graph_rust_crates_indexed: int
    graph_imports_indexed: int
    graph_imports_resolved: int
    graph_imports_unresolved: int
    graph_symbol_references_indexed: int
    graph_symbol_references_resolved: int
    graph_symbol_references_unresolved: int
    graph_symbol_references_resolved_by_basis: dict[str, int]
    graph_calls_indexed: int
    graph_calls_resolved: int
    graph_calls_unresolved: int
    graph_calls_resolved_by_basis: dict[str, int]
    graph_type_relations_indexed: int | None = _OMITTED
    graph_type_relations_resolved: int | None = _OMITTED
    graph_type_relations_unresolved: int | None = _OMITTED
    graph_type_relations_resolved_by_basis: dict[str, int] | None = _OMITTED
    graph_type_relations_unresolved_by_reason: dict[str, int] | None = _OMITTED


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


class GraphRecordPageBudget(StrictOutputModel):
    max_output_bytes: int = Field(ge=2048, le=262144)
    output_bytes: int = Field(ge=0)
    byte_limit_reached: bool

    @model_validator(mode="after")
    def _within_requested_limit(self) -> GraphRecordPageBudget:
        if self.output_bytes > self.max_output_bytes:
            raise ValueError("output_bytes cannot exceed max_output_bytes")
        return self


GraphRecordLanguage = Literal[
    "typescript", "python", "javascript", "go", "rust", "swift"
]


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
    target_module: str | None
    target_kind: Literal["file", "package", "crate", "module"] | None
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


TypeRelationUnresolvedReason = Literal[
    "unsupported_syntax", "unsupported_owner", "ambiguous_owner", "type_parameter",
    "binding_not_found", "binding_ambiguous", "binding_unindexed", "target_not_indexed",
    "ambiguous_target", "unsupported_target", "unsupported_reference", "import_unresolved",
    "binding_limit", "self_heritage", "type_only_value", "binding_shadowed", "unsupported_configuration", "target_inaccessible",
]

_REFERENCE_UNRESOLVED_REASON_VALUES = frozenset(
    get_args(ReferenceUnresolvedReason)
)
_TYPE_RELATION_UNRESOLVED_REASON_VALUES = frozenset(
    get_args(TypeRelationUnresolvedReason)
)


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


class TypeRelationItem(StrictOutputModel):
    raw: RawTypeObservation
    source_id: str | None
    source_kind: str | None
    target_id: str | None
    target_file: str | None
    target_kind: str | None
    status: Literal["resolved", "unresolved"]
    unresolved_reason: TypeRelationUnresolvedReason | None
    resolution_basis: Literal[
        "lexical_binding", "package_binding", "direct_binding", "qualified_member", "reexport_chain"
    ] | None
    support: list[TypeSupport] = Field(max_length=256)
    resolution_controls: list[TypeControl] = Field(max_length=256)
    candidate_universe: Literal["lexical_scope", "package_scope", "import_surface", "unavailable"]
    candidate_scope_file: str | None
    candidate_ids: list[str] = Field(max_length=16)
    candidates_complete: bool
    candidates_truncated: int = Field(ge=0)
    resolution_configuration: Literal["unconditional", "declared_possible"] | None
    source_file: str = Field(min_length=1)
    resolution: Literal["exact", "import-resolved"] | None

    @model_validator(mode="after")
    def _valid_relation(self) -> TypeRelationItem:
        _require_relative_path(self.source_file, "source_file")
        if self.source_file != self.raw.source_file:
            raise ValueError("source_file must match the raw observation")
        if self.source_id is None:
            if self.source_kind is not None:
                raise ValueError("source_kind requires source_id")
        elif not self.source_kind:
            raise ValueError("source_id requires source_kind")
        if self.target_file is not None:
            _require_relative_path(self.target_file, "target_file")
        if self.candidate_scope_file is not None:
            _require_relative_path(self.candidate_scope_file, "candidate_scope_file")
        for value, field in (
            (self.source_id, "source_id"),
            (self.source_kind, "source_kind"),
            (self.target_id, "target_id"),
            (self.target_kind, "target_kind"),
        ):
            if value is not None and not value:
                raise ValueError(f"{field} must be non-empty when present")
        target_values = (self.target_id, self.target_file, self.target_kind)
        if any(value is None for value in target_values) and any(
            value is not None for value in target_values
        ):
            raise ValueError("target endpoint fields must be complete")
        if self.candidates_complete and self.candidates_truncated:
            raise ValueError("complete candidates cannot report truncation")
        if self.candidate_universe == "unavailable":
            if self.candidate_scope_file is not None or self.candidates_complete:
                raise ValueError("unavailable candidates cannot have scope or completeness")
        elif self.candidate_scope_file is None:
            raise ValueError("available candidates require a scope file")
        if len(set(self.candidate_ids)) != len(self.candidate_ids):
            raise ValueError("candidate_ids must be unique")
        if any(not candidate_id for candidate_id in self.candidate_ids):
            raise ValueError("candidate_ids must be non-empty")
        if len({control.file for control in self.resolution_controls}) != len(
            self.resolution_controls
        ):
            raise ValueError("resolution control files must be unique")

        support_kinds = {support.kind for support in self.support}
        if "type_site" not in support_kinds:
            raise ValueError("type relation support must include the type site")
        if self.resolution_configuration not in {None, "unconditional", "declared_possible"}:
            raise ValueError("resolution_configuration is not supported")
        if self.raw.language == "rust" and self.status == "resolved":
            if self.resolution_configuration is None:
                raise ValueError("Rust relations require declared configuration proof")
        elif self.resolution_configuration is not None:
            raise ValueError("configuration is only carried by resolved Rust relations")
        if self.status == "resolved":
            if self.source_id is None or self.target_id is None:
                raise ValueError("resolved relations require source and target endpoints")
            if self.unresolved_reason is not None or self.resolution_basis is None:
                raise ValueError("resolved relations require only a resolution basis")
            if self.resolution is None:
                raise ValueError("resolved relations require a public resolution")
            if not self.candidates_complete or self.candidates_truncated:
                raise ValueError("resolved relations require complete candidates")
            if self.candidate_ids != [self.target_id]:
                raise ValueError("resolved relations require one target candidate")
            if not self.raw.candidates_complete or self.raw.candidates_truncated:
                raise ValueError("resolved relations require complete raw candidates")
            if self.resolution_basis == "lexical_binding":
                if not (
                    self.candidate_universe == "lexical_scope"
                    and self.raw.binding_state == "local"
                    and len(self.raw.local_bindings) == 1
                    and len(self.raw.path) == 1
                ):
                    raise ValueError("lexical resolutions require local evidence")
            elif self.resolution_basis == "package_binding":
                if self.raw.language != "go" or self.raw.binding_state != "package" or self.candidate_universe != "package_scope" or "package_clause" not in support_kinds:
                    raise ValueError("package resolutions require Go package evidence")
            else:
                if self.candidate_universe != "import_surface":
                    raise ValueError("import resolutions require an import surface")
                if self.raw.language == "go" and self.raw.binding_state == "deferred":
                    if self.resolution_basis != "qualified_member" or "package_clause" not in support_kinds:
                        raise ValueError("deferred package lookup requires qualified package evidence")
                elif self.raw.binding_state != "imported" or len(self.raw.import_bindings) != 1:
                    raise ValueError("import resolutions require imported binding evidence")
                if not all(valid_type_import_path(self.raw.language, self.raw.path, binding) for binding in self.raw.import_bindings):
                    raise ValueError("resolved import paths must match their binding kind")
            if not {"owner", "definition"} <= support_kinds:
                raise ValueError("resolved relations require owner and definition support")
        else:
            if any(value is not None for value in target_values):
                raise ValueError("unresolved relations cannot carry a target endpoint")
            if self.unresolved_reason is None or self.resolution_basis is not None:
                raise ValueError("unresolved relations require only an unresolved reason")
            if self.resolution is not None:
                raise ValueError("unresolved relations cannot carry a public resolution")
        return self


class CompactGraphRecordItem(StrictOutputModel):
    source_id: str | None
    source_file: str = Field(min_length=1)
    target_id: str | None
    target_file: str | None
    language: GraphRecordLanguage
    line: int = Field(ge=1)
    column: int = Field(ge=1)
    start_byte: int = Field(ge=0)
    end_byte: int = Field(ge=1)
    text: str = Field(min_length=1)
    status: Literal["resolved", "unresolved"]
    resolution: Literal["exact", "import-resolved"] | None
    unresolved_reason: str | None
    resolution_configuration: Literal["unconditional", "declared_possible"] | None

    @model_validator(mode="after")
    def _valid_compact_outcome(self) -> CompactGraphRecordItem:
        _require_relative_path(self.source_file, "source_file")
        if self.target_file is not None:
            _require_relative_path(self.target_file, "target_file")
        if self.start_byte >= self.end_byte:
            raise ValueError("compact record span must be non-empty and ordered")
        for value, field in (
            (self.source_id, "source_id"),
            (self.target_id, "target_id"),
        ):
            if value is not None and not value:
                raise ValueError(f"{field} must be non-empty when present")
        has_target = self.target_id is not None or self.target_file is not None
        if (self.target_id is None) != (self.target_file is None):
            raise ValueError("target endpoint requires both id and file")
        if self.status == "resolved":
            if self.source_id is None or not has_target:
                raise ValueError("resolved compact records require source and target endpoints")
            if self.resolution is None or self.unresolved_reason is not None:
                raise ValueError("resolved compact records require a resolution only")
        else:
            if has_target or self.resolution is not None:
                raise ValueError("unresolved compact records cannot carry a target or resolution")
            if self.unresolved_reason is None:
                raise ValueError("unresolved compact records require an unresolved reason")
            if self.resolution_configuration is not None:
                raise ValueError("unresolved compact records cannot carry resolution configuration")
        return self


class CompactReferenceItem(CompactGraphRecordItem):
    relation: Literal[
        "references", "references_type", "uses_type", "extends", "implements",
        "embeds", "supertrait", "impl_trait", "impl_self_type",
    ]
    context: Literal[
        "annotation", "return", "property", "alias", "type_argument",
        "constraint", "type_query", "heritage", "struct_embedding", "interface_embedding",
        "supertrait", "impl_trait", "impl_self_type",
    ] | None
    unresolved_reason: ReferenceUnresolvedReason | TypeRelationUnresolvedReason | None
    import_unresolved_reason: ImportUnresolvedReason | None

    @model_validator(mode="after")
    def _valid_compact_reference(self) -> CompactReferenceItem:
        if len(self.text.encode("utf-8")) != self.end_byte - self.start_byte:
            raise ValueError("compact reference text must match its UTF-8 span")
        symbol_relation = self.relation in {"references", "references_type"}
        if symbol_relation:
            if self.context is not None:
                raise ValueError("symbol compact references cannot carry a type context")
            if (
                self.unresolved_reason is not None
                and self.unresolved_reason not in _REFERENCE_UNRESOLVED_REASON_VALUES
            ):
                raise ValueError("symbol compact references require a symbol unresolved reason")
            if self.status == "resolved":
                if self.resolution != "import-resolved":
                    raise ValueError("resolved symbol compact references require import resolution")
                if self.import_unresolved_reason is not None:
                    raise ValueError("resolved symbol compact references cannot carry import failure")
            elif (
                self.import_unresolved_reason is not None
                and self.unresolved_reason != "import_unresolved"
            ):
                raise ValueError("import failure requires an import_unresolved reference")
            return self

        if self.context is None:
            raise ValueError("type compact relations require their authored context")
        if self.import_unresolved_reason is not None:
            raise ValueError("type compact relations cannot carry import failure")
        if (
            self.unresolved_reason is not None
            and self.unresolved_reason not in _TYPE_RELATION_UNRESOLVED_REASON_VALUES
        ):
            raise ValueError("type compact relations require a type unresolved reason")
        return self


class LociGraphReferencesSuccess(StrictOutputModel):
    schema_version: Literal[1]
    repo: str
    file: str | None
    status: Literal["all", "resolved", "unresolved"]
    family: Literal["symbol", "type"] | None = _OMITTED
    detail: Literal["compact", "full"] | None = _OMITTED
    budget: GraphRecordPageBudget | None = _OMITTED
    items: list[ReferenceItem | TypeRelationItem | CompactReferenceItem]
    counts: RecordCounts
    pagination: Pagination

    @model_validator(mode="after")
    def _family_matches_items(self) -> LociGraphReferencesSuccess:
        if (self.detail is None) != (self.budget is None):
            raise ValueError("detail and budget must be supplied together")
        compact = self.detail == "compact"
        if self.detail == "full" or self.detail is None:
            if any(isinstance(item, CompactReferenceItem) for item in self.items):
                raise ValueError("full reference pages require rich reference items")
        elif any(not isinstance(item, CompactReferenceItem) for item in self.items):
            raise ValueError("compact reference pages require compact reference items")

        if self.family == "type":
            if compact:
                if any(
                    item.relation in {"references", "references_type"}
                    for item in self.items
                    if isinstance(item, CompactReferenceItem)
                ):
                    raise ValueError("type reference pages require type relation items")
            elif any(not isinstance(item, TypeRelationItem) for item in self.items):
                raise ValueError("type reference pages require type relation items")
        elif compact:
            if any(
                item.relation not in {"references", "references_type"}
                for item in self.items
                if isinstance(item, CompactReferenceItem)
            ):
                raise ValueError("symbol reference pages require symbol reference items")
        elif any(not isinstance(item, ReferenceItem) for item in self.items):
            raise ValueError("symbol reference pages require symbol reference items")
        return self


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


class MemberCallableBinding(StrictOutputModel):
    name: str
    callable_kind: Literal["function", "method"]
    owner_type_name: str
    owner_declaration_start_byte: int
    owner_declaration_end_byte: int
    owner_body_start_byte: int
    owner_body_end_byte: int
    definition_start_byte: int
    definition_end_byte: int
    definition_line: int


class RawCallSite(StrictOutputModel):
    source_file: str
    language: Literal[
        "python", "javascript", "typescript", "go", "rust", "swift"
    ]
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
    member_candidates: list[MemberCallableBinding]
    member_binding_state: Literal[
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
    "member_binding_ambiguous",
    "member_target_not_indexed",
    "callee_not_proven",
    "reference_unresolved",
    "target_not_callable",
    "imported_member_ambiguous",
    "type_member_ambiguous",
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
    resolution_basis: (
        Literal[
            "local_callable",
            "member_callable",
            "imported_reference",
            "imported_member",
            "type_member",
        ]
        | None
    )
    support: list[CallSupport]
    resolution_control_files: list[str]
    resolution_configuration: Literal["unconditional", "declared_possible"] | None


class CompactCallItem(CompactGraphRecordItem):
    relation: Literal["calls"]
    callee_start_byte: int = Field(ge=0)
    callee_end_byte: int = Field(ge=1)
    unresolved_reason: CallUnresolvedReason | None
    reference_unresolved_reason: ReferenceUnresolvedReason | None

    @model_validator(mode="after")
    def _valid_compact_call(self) -> CompactCallItem:
        if self.callee_start_byte >= self.callee_end_byte:
            raise ValueError("compact call callee span must be non-empty and ordered")
        if not (
            self.start_byte <= self.callee_start_byte
            and self.callee_end_byte <= self.end_byte
        ):
            raise ValueError("compact call callee span must be contained by call span")
        if len(self.text.encode("utf-8")) != self.callee_end_byte - self.callee_start_byte:
            raise ValueError("compact call text must match its callee UTF-8 span")
        if self.status == "resolved":
            if self.reference_unresolved_reason is not None:
                raise ValueError("resolved compact calls cannot carry a reference failure")
        elif (
            self.reference_unresolved_reason is None
        ) != (self.unresolved_reason != "reference_unresolved"):
            raise ValueError("reference failure is valid only for reference_unresolved calls")
        return self


class LociGraphCallsSuccess(StrictOutputModel):
    schema_version: Literal[1]
    repo: str
    file: str | None
    status: Literal["all", "resolved", "unresolved"]
    detail: Literal["compact", "full"] | None = _OMITTED
    budget: GraphRecordPageBudget | None = _OMITTED
    items: list[CallItem | CompactCallItem]
    counts: RecordCounts
    pagination: Pagination

    @model_validator(mode="after")
    def _detail_matches_items(self) -> LociGraphCallsSuccess:
        if (self.detail is None) != (self.budget is None):
            raise ValueError("detail and budget must be supplied together")
        if self.detail == "compact":
            if any(not isinstance(item, CompactCallItem) for item in self.items):
                raise ValueError("compact call pages require compact call items")
        elif any(not isinstance(item, CallItem) for item in self.items):
            raise ValueError("full call pages require rich call items")
        return self


class LociGraphCallsOutput(RootModel[LociGraphCallsSuccess | LociErrorOutput]):
    model_config = ConfigDict(json_schema_extra={"type": "object"})


ExplorationIntent = Literal["locate", "type_dependencies", "dependencies", "impact"]
ExplorationStatus = Literal["ok", "partial", "empty"]
ExplorationSelection = Literal["explicit", "inferred"]


class ExplorationScope(StrictOutputModel):
    source: Literal["indexed_supported_source"]
    coverage: Literal["complete", "partial", "unknown"]
    relationships: Literal["none", "authored_types", "authored_dependencies", "known_static_dependents"]
    exhaustive: Literal[False]


class ExplorationItem(StrictOutputModel):
    id: str
    name: str
    kind: str
    file: str
    role: Literal["anchor", "dependency", "dependent"]
    depth: int = Field(ge=0)
    source_id: int = Field(ge=1)
    complete: bool
    why: str
    path: list[int]


class ExplorationRelationship(StrictOutputModel):
    id: int = Field(ge=1)
    edge: GraphEdge
    traversed: Literal["forward", "reverse"]
    source_ids: list[int] = Field(min_length=1)

    resolution_configuration: Literal["unconditional", "declared_possible"] | None = _OMITTED


class ExplorationSource(StrictOutputModel):
    id: int = Field(ge=1)
    file: str
    start_byte: int = Field(ge=0)
    end_byte: int = Field(ge=1)
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    content: str

    @model_validator(mode="after")
    def _valid_utf8_span(self) -> ExplorationSource:
        if self.end_byte <= self.start_byte:
            raise ValueError("source byte span must be non-empty and ordered")
        if self.end_line < self.start_line:
            raise ValueError("source line span must be ordered")
        if not self.content:
            raise ValueError("source content must be non-empty")
        if len(self.content.encode("utf-8")) != self.end_byte - self.start_byte:
            raise ValueError("source content does not match its UTF-8 span")
        return self


ExplorationOmissionReason = Literal[
    "no_anchor",
    "anchor_limit",
    "unsupported_anchor",
    "unsupported_language",
    "unresolved_relation",
    "not_selected",
    "alternative_path",
    "cycle",
    "hop_limit",
    "node_limit",
    "neighbor_limit",
    "item_limit",
    "evidence_budget",
    "output_budget",
    "source_clipped",
    "source_unavailable",
    "ancestor_unavailable",
]


class ExplorationOmission(StrictOutputModel):
    reason: ExplorationOmissionReason
    count: int = Field(ge=1)


class ExplorationLimits(StrictOutputModel):
    max_hops: int = Field(ge=0, le=4)
    max_nodes: Literal[64]
    max_items: Literal[12]
    max_neighbors: Literal[32]
    max_output_bytes: int = Field(ge=2048, le=262144)
    max_evidence_bytes: int = Field(ge=0, le=65536)


class ExplorationUsage(StrictOutputModel):
    nodes_examined: int = Field(ge=0)
    evidence_bytes: int = Field(ge=0)
    output_bytes: int = Field(ge=0)
    estimated_tokens: int = Field(ge=0)
    token_estimate_method: Literal["utf8_bytes_div_4"]
    output_encoding: Literal["mcp_result_json_utf8"]


class LociExploreSuccess(StrictOutputModel):
    schema_version: Literal[1]
    intent: ExplorationIntent
    status: ExplorationStatus
    selection: ExplorationSelection
    scope: ExplorationScope
    items: list[ExplorationItem]
    relationships: list[ExplorationRelationship]
    sources: list[ExplorationSource]
    omissions: list[ExplorationOmission]
    limits: ExplorationLimits
    usage: ExplorationUsage


class LociExploreOutput(RootModel[LociExploreSuccess | LociErrorOutput]):
    model_config = ConfigDict(json_schema_extra={"type": "object"})


# Normal retrieval is intentionally separate from the legacy exploration shapes.
# The matching JSON Schema is .scratch/deterministic-graph-retrieval/contract.schema.json.


class NormalExtent(StrictOutputModel):
    file: str = Field(min_length=1)
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    start_byte: int = Field(ge=0)
    end_byte: int = Field(ge=0)

    @model_validator(mode="after")
    def _ordered_extent(self) -> NormalExtent:
        _require_relative_path(self.file, "file")
        if self.end_byte < self.start_byte:
            raise ValueError("source extent must be ordered")
        return self


class NormalSource(StrictOutputModel):
    id: int = Field(ge=1)
    file: str = Field(min_length=1)
    start_byte: int = Field(ge=0)
    end_byte: int = Field(ge=0)
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    content: str
    source_ref: str = Field(min_length=1)

    @model_validator(mode="after")
    def _ordered_source(self) -> NormalSource:
        _require_relative_path(self.file, "file")
        if self.end_byte < self.start_byte:
            raise ValueError("source byte span must be ordered")
        if self.end_line < self.start_line:
            raise ValueError("source line span must be ordered")
        try:
            content_bytes = len(self.content.encode("utf-8"))
        except UnicodeEncodeError as exc:
            raise ValueError("source content must be valid UTF-8") from exc
        if content_bytes != self.end_byte - self.start_byte:
            raise ValueError("source content must match its UTF-8 byte span")
        return self


class NormalEvidence(StrictOutputModel):
    file: str = Field(min_length=1)
    line: int = Field(ge=1)
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def _relative_file(self) -> NormalEvidence:
        _require_relative_path(self.file, "evidence.file")
        return self


class NormalEdge(StrictOutputModel):
    from_: str = Field(alias="from", min_length=1)
    to: str = Field(min_length=1)
    type: str = Field(min_length=1)
    directed: Literal[True]
    namespace: Literal["loci"]
    resolution: Literal["exact", "declared", "import-resolved"]
    evidence: NormalEvidence


class NormalRelationship(StrictOutputModel):
    id: int = Field(ge=1)
    edge: NormalEdge
    traversed: Literal["forward", "reverse"]
    source_ids: list[Annotated[int, Field(ge=1)]] = Field(min_length=1)
    proof: Literal["complete"]
    resolution_configuration: Literal["unconditional", "declared_possible"] | None

    @model_validator(mode="after")
    def _unique_source_ids(self) -> NormalRelationship:
        if len(set(self.source_ids)) != len(self.source_ids):
            raise ValueError("relationship source_ids must be unique")
        return self


class NormalNode(StrictOutputModel):
    id: str = Field(min_length=1)
    name: str
    kind: str = Field(min_length=1)
    file: str | None

    @model_validator(mode="after")
    def _relative_file(self) -> NormalNode:
        if self.file is not None:
            _require_relative_path(self.file, "node.file")
        return self


class NormalAnchor(StrictOutputModel):
    node_id: str = Field(min_length=1)
    score: float
    matched_terms: list[str]
    match_scope: list[str]


class NormalItem(StrictOutputModel):
    node_id: str = Field(min_length=1)
    role: Literal["anchor", "related"]
    depth: int = Field(ge=0)
    why: str = Field(min_length=1)
    source_ids: list[Annotated[int, Field(ge=1)]] = Field(min_length=1)
    complete: bool
    extent: NormalExtent
    source_ref: str = Field(min_length=1)

    @model_validator(mode="after")
    def _unique_source_ids(self) -> NormalItem:
        if len(set(self.source_ids)) != len(self.source_ids):
            raise ValueError("item source_ids must be unique")
        return self


class NormalOwnership(StrictOutputModel):
    owner_id: str = Field(min_length=1)
    member_id: str = Field(min_length=1)
    basis: Literal["indexed_file", "go_package", "rust_crate", "swift_module"]


class NormalOmission(StrictOutputModel):
    reason: Literal[
        "no_anchor",
        "anchor_limit",
        "ambiguous_anchor",
        "lookup_limit",
        "node_limit",
        "neighbor_limit",
        "item_limit",
        "hop_limit",
        "cycle",
        "alternative_path",
        "ownership_limit",
        "unsupported_semantics",
        "unresolved_relation",
        "ambiguous_relation",
        "external_relation",
        "inaccessible_relation",
        "source_unavailable",
        "source_stale",
        "source_preview",
        "proof_unavailable",
        "evidence_budget",
        "output_budget",
    ]
    count: int = Field(ge=1)


class NormalLimits(StrictOutputModel):
    max_hops: Literal[2]
    max_nodes: Literal[64]
    max_neighbors: Literal[32]
    max_items: Literal[12]
    max_anchors: Literal[3]
    max_explicit_anchors: Literal[5]
    max_owner_members: Literal[3]
    max_evidence_bytes: Literal[8192]
    max_output_bytes: Literal[16384]
    max_anchor_source_bytes: Literal[1024]
    max_related_source_bytes: Literal[768]
    max_lookup_bytes: Literal[33554432]
    max_lookup_files: Literal[4096]
    max_literal_matches: Literal[256]


class NormalUsage(StrictOutputModel):
    nodes_examined: int = Field(ge=0)
    eligible_edges_considered: int = Field(ge=0)
    edges_traversed: int = Field(ge=0)
    relationships_delivered: int = Field(ge=0)
    lookup_bytes: int = Field(ge=0)
    lookup_files: int = Field(ge=0)
    evidence_bytes: int = Field(ge=0)
    output_bytes: int = Field(ge=0)
    estimated_tokens: int = Field(ge=0)
    token_estimate_method: Literal["utf8_bytes_div_4"]
    output_encoding: Literal["mcp_result_json_utf8"]


class NormalSelection(StrictOutputModel):
    mode: Literal["explicit", "inferred", "file", "literal"]
    candidate_count: int = Field(ge=0)
    omitted_candidates: int = Field(ge=0)


class NormalScope(StrictOutputModel):
    source: Literal["indexed_supported_source"]
    coverage: Literal["complete", "partial", "unknown"]
    matching: Literal["explicit_ids", "exact_file", "symbol_metadata", "source_literal"]
    relationships: Literal["known_static_relationships"]
    exhaustive: Literal[False]


class LociRetrieveSuccess(StrictOutputModel):
    schema_version: Literal[1]
    policy: Literal["normal-graph-v1"]
    snapshot: str = Field(pattern=r"^[0-9a-f]{64}$")
    status: Literal["ok", "partial", "empty"]
    selection: NormalSelection
    scope: NormalScope
    anchors: list[NormalAnchor]
    nodes: list[NormalNode]
    items: list[NormalItem]
    ownership: list[NormalOwnership]
    relationships: list[NormalRelationship]
    sources: list[NormalSource]
    omissions: list[NormalOmission]
    limits: NormalLimits
    usage: NormalUsage

    @model_validator(mode="after")
    def _validate_links_and_budgets(self) -> LociRetrieveSuccess:
        node_ids = [node.id for node in self.nodes]
        source_ids = [source.id for source in self.sources]
        relationship_ids = [relationship.id for relationship in self.relationships]
        if len(set(node_ids)) != len(node_ids):
            raise ValueError("nodes must have unique IDs")
        if len(set(source_ids)) != len(source_ids):
            raise ValueError("sources must have unique IDs")
        if len(set(relationship_ids)) != len(relationship_ids):
            raise ValueError("relationships must have unique IDs")
        known_nodes = set(node_ids)
        known_sources = {source.id: source for source in self.sources}
        if any(anchor.node_id not in known_nodes for anchor in self.anchors):
            raise ValueError("anchors must name returned nodes")
        for item in self.items:
            if item.node_id not in known_nodes:
                raise ValueError("items must name returned nodes")
            if any(source_id not in known_sources for source_id in item.source_ids):
                raise ValueError("items must name returned sources")
        for ownership in self.ownership:
            if ownership.owner_id not in known_nodes or ownership.member_id not in known_nodes:
                raise ValueError("ownership endpoints must be returned nodes")
        for relationship in self.relationships:
            if relationship.edge.from_ not in known_nodes or relationship.edge.to not in known_nodes:
                raise ValueError("relationship endpoints must be returned nodes")
            proof_sources = [known_sources[source_id] for source_id in relationship.source_ids if source_id in known_sources]
            if len(proof_sources) != len(relationship.source_ids):
                raise ValueError("relationships must name returned proof sources")
            if not any(
                source.file == relationship.edge.evidence.file
                and source.content_hash == relationship.edge.evidence.content_hash
                and source.start_line <= relationship.edge.evidence.line <= source.end_line
                for source in proof_sources
            ):
                raise ValueError("relationship proof must contain matching edge evidence")
        if self.usage.relationships_delivered != len(self.relationships):
            raise ValueError("relationships_delivered must equal returned relationships")
        if self.usage.evidence_bytes > self.limits.max_evidence_bytes:
            raise ValueError("evidence bytes exceed the normal retrieval budget")
        if self.usage.output_bytes > self.limits.max_output_bytes:
            raise ValueError("output bytes exceed the normal retrieval budget")
        return self


class LociRetrieveOutput(RootModel[LociRetrieveSuccess | LociErrorOutput]):
    model_config = ConfigDict(json_schema_extra={"type": "object"})


class NormalReadUsage(StrictOutputModel):
    evidence_bytes: int = Field(ge=0)
    output_bytes: int = Field(ge=0)
    output_encoding: Literal["mcp_result_json_utf8"]


class LociReadSuccess(StrictOutputModel):
    schema_version: Literal[1]
    status: Literal["ok"]
    source: NormalSource
    complete: bool
    next_source_ref: Annotated[str, Field(min_length=1)] | None
    usage: NormalReadUsage

    @model_validator(mode="after")
    def _bounded_page(self) -> LociReadSuccess:
        page_bytes = len(self.source.content.encode("utf-8"))
        if page_bytes > 8192:
            raise ValueError("read source exceeds the 8192-byte page limit")
        if self.complete != (self.next_source_ref is None):
            raise ValueError("complete reads must have no next source reference")
        if self.usage.evidence_bytes != page_bytes:
            raise ValueError("read evidence bytes must equal the returned page bytes")
        if self.usage.output_bytes > 16384:
            raise ValueError("read output bytes exceed the complete result budget")
        return self


class LociReadOutput(RootModel[LociReadSuccess | LociErrorOutput]):
    model_config = ConfigDict(json_schema_extra={"type": "object"})
