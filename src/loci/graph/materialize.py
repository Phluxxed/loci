from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, cast

from loci.graph.builtins import extract_markdown_contains_edges
from loci.graph.contracts import (
    GRAPH_STATE_SCHEMA_VERSION,
    GraphContractError,
    GraphContribution,
    GraphEdge,
    GraphEvidence,
    GraphNodeRef,
    JSONValue,
)
from loci.graph.imports import (
    materialize_import_edges,
    resolve_imports,
)
from loci.graph.go_modules import GoPackageIndex
from loci.graph.javascript_modules import JavaScriptResolutionIndex
from loci.graph.profiles import (
    GraphNodeAttributeRule,
    GraphProfile,
    LoadedGraphProfile,
    MAX_EXTENSION_BYTES,
    discover_graph_contribution_candidates,
    discover_graph_profile_candidates,
    parse_extension_json,
    read_contained_file,
    validate_contained_file,
)
from loci.graph.state import (
    GraphDiagnostic,
    GraphIndexState,
    LoadedGraphContribution,
)
from loci.parser.imports import RawImport
from loci.parser.symbols import Symbol


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
) -> GraphExtensionLoad:
    """Load bounded repository graph extensions without failing source indexing."""
    input_hashes: dict[str, str] = {}
    load_diagnostics: list[GraphDiagnostic] = []
    loaded_profiles: list[LoadedGraphProfile] = []
    loaded_contributions: list[LoadedGraphContribution] = []
    contributions_reused = 0

    try:
        profile_paths = discover_graph_profile_candidates(repo_path)
    except GraphContractError as exc:
        profile_paths = ()
        load_diagnostics.append(_contract_diagnostic(
            "INVALID_GRAPH_PROFILE",
            exc,
            fallback_source=".loci/graph/profiles",
        ))
    for path in profile_paths:
        source = _candidate_source(repo_path, path)
        try:
            data, source = read_contained_file(
                repo_path,
                path,
                record="profile",
                max_bytes=MAX_EXTENSION_BYTES,
            )
            content_hash = hashlib.sha256(data).hexdigest()
            input_hashes[source] = content_hash
            payload = parse_extension_json(
                data,
                relative=source,
                record="profile",
            )
            profile = GraphProfile.from_dict(_mapping_payload(payload, "profile"))
        except GraphContractError as exc:
            load_diagnostics.append(_contract_diagnostic(
                "INVALID_GRAPH_PROFILE",
                exc,
                fallback_source=source,
            ))
            continue
        loaded_profiles.append(LoadedGraphProfile(
            source=source,
            content_hash=content_hash,
            profile=profile,
        ))

    duplicate_namespaces = {
        namespace
        for namespace in {item.profile.namespace for item in loaded_profiles}
        if sum(item.profile.namespace == namespace for item in loaded_profiles) > 1
    }
    if duplicate_namespaces:
        for item in loaded_profiles:
            if item.profile.namespace in duplicate_namespaces:
                load_diagnostics.append(_diagnostic(
                    "GRAPH_PROFILE_NAMESPACE_DUPLICATE",
                    "Multiple graph profiles register the same namespace",
                    source=item.source,
                    namespace=item.profile.namespace,
                ))
        loaded_profiles = [
            item
            for item in loaded_profiles
            if item.profile.namespace not in duplicate_namespaces
        ]

    previous_contributions = {
        item.source: item
        for item in (previous_graph.contributions if previous_graph else ())
    }
    previous_parse_diagnostics = {
        item.source: item
        for item in (previous_graph.diagnostics if previous_graph else ())
        if item.code == "INVALID_GRAPH_CONTRIBUTION" and item.source is not None
    }
    try:
        contribution_paths = discover_graph_contribution_candidates(repo_path)
    except GraphContractError as exc:
        contribution_paths = ()
        load_diagnostics.append(_contract_diagnostic(
            "INVALID_GRAPH_CONTRIBUTION",
            exc,
            fallback_source=".loci/graph/contributions",
        ))
    for path in contribution_paths:
        source = _candidate_source(repo_path, path)
        try:
            data, source = read_contained_file(
                repo_path,
                path,
                record="contribution",
                max_bytes=MAX_EXTENSION_BYTES,
            )
        except GraphContractError as exc:
            load_diagnostics.append(_contract_diagnostic(
                "INVALID_GRAPH_CONTRIBUTION",
                exc,
                fallback_source=source,
            ))
            continue
        content_hash = hashlib.sha256(data).hexdigest()
        input_hashes[source] = content_hash
        previous = previous_contributions.get(source)
        if previous is not None and previous.content_hash == content_hash:
            loaded_contributions.append(previous)
            contributions_reused += 1
            if previous.contribution is None and source in previous_parse_diagnostics:
                load_diagnostics.append(previous_parse_diagnostics[source])
            continue
        try:
            payload = parse_extension_json(
                data,
                relative=source,
                record="contribution",
            )
            contribution = GraphContribution.from_dict(
                _mapping_payload(payload, "contribution")
            )
        except GraphContractError as exc:
            loaded_contributions.append(LoadedGraphContribution(
                source=source,
                content_hash=content_hash,
                contribution=None,
            ))
            load_diagnostics.append(_contract_diagnostic(
                "INVALID_GRAPH_CONTRIBUTION",
                exc,
                fallback_source=source,
            ))
            continue
        loaded_contributions.append(LoadedGraphContribution(
            source=source,
            content_hash=content_hash,
            contribution=contribution,
        ))

    return GraphExtensionLoad(
        profiles=tuple(sorted(
            loaded_profiles,
            key=lambda item: (item.profile.namespace, item.source),
        )),
        contributions=tuple(sorted(
            loaded_contributions,
            key=lambda item: item.source,
        )),
        input_hashes=dict(sorted(input_hashes.items())),
        diagnostics=tuple(sorted(load_diagnostics, key=_diagnostic_sort_key)),
        contributions_reused=contributions_reused,
    )


def materialize_graph(
    repo_path: Path,
    symbols: Sequence[Symbol],
    file_hashes: Mapping[str, str],
    profiles: Sequence[LoadedGraphProfile],
    contributions: Sequence[LoadedGraphContribution],
    *,
    raw_imports: Sequence[RawImport] = (),
    go_packages: GoPackageIndex | None = None,
    javascript_modules: JavaScriptResolutionIndex | None = None,
    input_hashes: Mapping[str, str] | None = None,
    diagnostics: Sequence[GraphDiagnostic] = (),
) -> GraphIndexState:
    """Compile validated profile and contribution data into persisted graph state."""
    indexed_nodes = {symbol.id: symbol for symbol in symbols}
    page_roots = _page_roots(symbols)
    active_profiles = tuple(sorted(
        profiles,
        key=lambda item: (item.profile.namespace, item.source),
    ))
    active_contributions = tuple(sorted(contributions, key=lambda item: item.source))

    file_nodes = {
        symbol.file_path: symbol
        for symbol in symbols
        if symbol.kind == "file"
    }
    import_records = tuple(sorted(
        resolve_imports(
            raw_imports,
            file_nodes=file_nodes,
            go_packages=go_packages,
            javascript_modules=javascript_modules,
        ),
        key=lambda record: (
            record.raw.source_file,
            record.raw.line,
            record.raw.specifier,
            record.raw.imported_name or "",
            record.target_file or "",
            record.target_package or "",
        ),
    ))
    active_edges = list(extract_markdown_contains_edges(symbols))
    active_edges.extend(materialize_import_edges(
        import_records,
        file_nodes=file_nodes,
        go_packages=go_packages,
    ))
    overlay_values: dict[tuple[str, str], dict[str, JSONValue]] = {}
    overlay_kinds: dict[tuple[str, str], str] = {}
    materialization_diagnostics = list(diagnostics)
    graph_path_errors: dict[str, str | None] = {}
    evidence_source_lines: dict[str, int | str] = {}

    for loaded_profile in active_profiles:
        profile = loaded_profile.profile
        for symbol in symbols:
            if not _is_page_root(symbol):
                continue
            for node_rule in profile.node_rules:
                if not _matches_page_root_selector(symbol):
                    continue
                for attribute_rule in node_rule.attributes:
                    field = _source_field(attribute_rule.source)
                    invalid = _frontmatter_invalid(symbol, field)
                    if invalid is not None:
                        materialization_diagnostics.append(_diagnostic(
                            "GRAPH_NODE_ATTRIBUTE_INVALID",
                            "Profile-selected frontmatter attribute is invalid",
                            source=symbol.file_path,
                            namespace=profile.namespace,
                            node_id=symbol.id,
                            field=field,
                            line=invalid.get("line"),
                            reason=invalid.get("reason"),
                        ))
                        continue
                    value = _frontmatter_value(symbol, field)
                    if value is None:
                        continue
                    if not _valid_attribute_value(attribute_rule, value):
                        materialization_diagnostics.append(_diagnostic(
                            "GRAPH_NODE_ATTRIBUTE_INVALID",
                            "Profile-derived node attribute violates its policy",
                            source=symbol.file_path,
                            namespace=profile.namespace,
                            node_id=symbol.id,
                            attribute=attribute_rule.name,
                        ))
                        continue
                    source_error = _graph_path_error(
                        repo_path,
                        symbol.file_path,
                        graph_path_errors,
                        record="profile node source",
                    )
                    if source_error is not None:
                        materialization_diagnostics.append(_diagnostic(
                            "GRAPH_NODE_ATTRIBUTE_INVALID",
                            "Profile node source cannot be read safely",
                            source=symbol.file_path,
                            namespace=profile.namespace,
                            node_id=symbol.id,
                            reason=source_error,
                        ))
                        continue
                    _merge_overlay(
                        overlay_values,
                        overlay_kinds,
                        materialization_diagnostics,
                        profile.namespace,
                        symbol,
                        attribute_rule.name,
                        cast(JSONValue, value),
                        source=symbol.file_path,
                    )

        for edge_rule in profile.edge_rules:
            for source_symbol in symbols:
                if not _matches_page_root_selector(source_symbol):
                    continue
                field = _source_field(edge_rule.source)
                invalid = _frontmatter_invalid(source_symbol, field)
                if invalid is not None:
                    materialization_diagnostics.append(_diagnostic(
                        "GRAPH_REFERENCE_UNRESOLVED",
                        "Profile-selected frontmatter reference is invalid",
                        source=source_symbol.file_path,
                        namespace=profile.namespace,
                        node_id=source_symbol.id,
                        field=field,
                        line=invalid.get("line"),
                        reason=invalid.get("reason"),
                    ))
                    continue
                references = _reference_values(_frontmatter_value(source_symbol, field))
                if references is None:
                    materialization_diagnostics.append(_diagnostic(
                        "GRAPH_REFERENCE_UNRESOLVED",
                        "Profile reference must be a path or list of paths",
                        source=source_symbol.file_path,
                        namespace=profile.namespace,
                        node_id=source_symbol.id,
                        field=field,
                    ))
                    continue
                if not references:
                    continue
                evidence_hash = file_hashes.get(source_symbol.file_path)
                if evidence_hash is None:
                    materialization_diagnostics.append(_diagnostic(
                        "GRAPH_EVIDENCE_SOURCE_NOT_FOUND",
                        "Profile edge evidence source is not indexed",
                        source=source_symbol.file_path,
                        namespace=profile.namespace,
                        node_id=source_symbol.id,
                    ))
                    continue
                evidence_line = _frontmatter_line(source_symbol, field)
                for reference in references:
                    normalized_reference = _relative_path(reference)
                    if normalized_reference is None:
                        materialization_diagnostics.append(_diagnostic(
                            "GRAPH_REFERENCE_UNRESOLVED",
                            "Profile reference is not a canonical repository-relative path",
                            source=source_symbol.file_path,
                            namespace=profile.namespace,
                            node_id=source_symbol.id,
                            reference=reference,
                        ))
                        continue
                    targets = page_roots.get(normalized_reference, ())
                    if not targets:
                        materialization_diagnostics.append(_diagnostic(
                            "GRAPH_REFERENCE_UNRESOLVED",
                            "Profile reference has no indexed page root",
                            source=source_symbol.file_path,
                            namespace=profile.namespace,
                            node_id=source_symbol.id,
                            reference=normalized_reference,
                        ))
                        continue
                    if len(targets) != 1:
                        materialization_diagnostics.append(_diagnostic(
                            "GRAPH_REFERENCE_AMBIGUOUS",
                            "Profile reference has multiple indexed page roots",
                            source=source_symbol.file_path,
                            namespace=profile.namespace,
                            node_id=source_symbol.id,
                            reference=normalized_reference,
                            matching_ids=[target.id for target in targets],
                        ))
                        continue
                    reference_error = _graph_path_error(
                        repo_path,
                        normalized_reference,
                        graph_path_errors,
                        record="profile reference",
                    )
                    if reference_error is not None:
                        materialization_diagnostics.append(_diagnostic(
                            "GRAPH_REFERENCE_UNRESOLVED",
                            "Profile reference cannot be read safely",
                            source=source_symbol.file_path,
                            namespace=profile.namespace,
                            node_id=source_symbol.id,
                            reference=normalized_reference,
                            reason=reference_error,
                        ))
                        continue
                    source_error = _graph_path_error(
                        repo_path,
                        source_symbol.file_path,
                        graph_path_errors,
                        record="profile edge source",
                    )
                    if source_error is not None:
                        materialization_diagnostics.append(_diagnostic(
                            "GRAPH_REFERENCE_UNRESOLVED",
                            "Profile edge source cannot be read safely",
                            source=source_symbol.file_path,
                            namespace=profile.namespace,
                            node_id=source_symbol.id,
                            reason=source_error,
                        ))
                        continue
                    target = targets[0]
                    if edge_rule.direction == "source_to_reference":
                        from_id, to_id = source_symbol.id, target.id
                    else:
                        from_id, to_id = target.id, source_symbol.id
                    if from_id == to_id:
                        materialization_diagnostics.append(_diagnostic(
                            "INVALID_GRAPH_EDGE",
                            "Profile reference would create a self edge",
                            source=source_symbol.file_path,
                            namespace=profile.namespace,
                            node_id=source_symbol.id,
                            reference=normalized_reference,
                        ))
                        continue
                    active_edges.append(GraphEdge(
                        from_id=from_id,
                        to_id=to_id,
                        type=edge_rule.type,
                        directed=True,
                        namespace=profile.namespace,
                        resolution="declared",
                        evidence=GraphEvidence(
                            file=source_symbol.file_path,
                            line=evidence_line,
                            content_hash=evidence_hash,
                        ),
                    ))

    profiles_by_namespace = {
        loaded.profile.namespace: loaded.profile for loaded in active_profiles
    }
    for loaded_contribution in active_contributions:
        contribution = loaded_contribution.contribution
        if contribution is None:
            if not any(
                item.code == "INVALID_GRAPH_CONTRIBUTION"
                and item.source == loaded_contribution.source
                for item in materialization_diagnostics
            ):
                materialization_diagnostics.append(_diagnostic(
                    "INVALID_GRAPH_CONTRIBUTION",
                    "Graph contribution could not be parsed",
                    source=loaded_contribution.source,
                ))
            continue
        profile = profiles_by_namespace.get(contribution.namespace)
        if profile is None:
            materialization_diagnostics.append(_diagnostic(
                "GRAPH_PROFILE_NOT_FOUND",
                "Contribution namespace has no active graph profile",
                source=loaded_contribution.source,
                namespace=contribution.namespace,
            ))
            continue

        for node in contribution.nodes:
            symbol = indexed_nodes.get(node.id)
            if symbol is None:
                materialization_diagnostics.append(_diagnostic(
                    "GRAPH_ENDPOINT_NOT_FOUND",
                    "Contribution node is not present in the current symbol index",
                    source=loaded_contribution.source,
                    namespace=contribution.namespace,
                    node_id=node.id,
                ))
                continue
            if node.kind != symbol.kind:
                materialization_diagnostics.append(_diagnostic(
                    "GRAPH_NODE_ATTRIBUTE_INVALID",
                    "Contribution node kind does not match the indexed symbol",
                    source=loaded_contribution.source,
                    namespace=contribution.namespace,
                    node_id=node.id,
                    expected_kind=symbol.kind,
                    actual_kind=node.kind,
                ))
                continue
            node_source_error = _graph_path_error(
                repo_path,
                symbol.file_path,
                graph_path_errors,
                record="contribution node source",
            )
            if node_source_error is not None:
                materialization_diagnostics.append(_diagnostic(
                    "GRAPH_ENDPOINT_NOT_FOUND",
                    "Contribution node source cannot be read safely",
                    source=loaded_contribution.source,
                    namespace=contribution.namespace,
                    node_id=node.id,
                    reason=node_source_error,
                ))
                continue
            attribute_policies = _attribute_policies(profile, symbol)
            invalid_attributes = [
                name
                for name, value in node.attributes.items()
                if name not in attribute_policies
                or not _valid_attribute_value(attribute_policies[name], value)
            ]
            if invalid_attributes:
                materialization_diagnostics.append(_diagnostic(
                    "GRAPH_NODE_ATTRIBUTE_INVALID",
                    "Contribution node has undeclared or invalid attributes",
                    source=loaded_contribution.source,
                    namespace=contribution.namespace,
                    node_id=node.id,
                    attributes=sorted(invalid_attributes),
                ))
                continue
            for name, value in sorted(node.attributes.items()):
                _merge_overlay(
                    overlay_values,
                    overlay_kinds,
                    materialization_diagnostics,
                    contribution.namespace,
                    symbol,
                    name,
                    value,
                    source=loaded_contribution.source,
                )

        edge_policies = {policy.type: policy for policy in profile.edge_types}
        for edge_index, edge in enumerate(contribution.edges):
            policy = edge_policies.get(edge.type)
            if policy is None:
                materialization_diagnostics.append(_diagnostic(
                    "GRAPH_EDGE_TYPE_UNSUPPORTED",
                    "Contribution edge type is not registered by the profile",
                    source=loaded_contribution.source,
                    namespace=contribution.namespace,
                    edge_index=edge_index,
                    type=edge.type,
                ))
                continue
            if edge.resolution not in policy.allowed_resolutions:
                materialization_diagnostics.append(_diagnostic(
                    "GRAPH_RESOLUTION_UNSUPPORTED",
                    "Contribution edge resolution is not allowed by the profile",
                    source=loaded_contribution.source,
                    namespace=contribution.namespace,
                    edge_index=edge_index,
                    resolution=edge.resolution,
                ))
                continue
            if edge.directed != policy.directed:
                materialization_diagnostics.append(_diagnostic(
                    "INVALID_GRAPH_EDGE",
                    "Contribution edge direction does not match the profile policy",
                    source=loaded_contribution.source,
                    namespace=contribution.namespace,
                    edge_index=edge_index,
                ))
                continue
            missing_ids = [
                node_id
                for node_id in (edge.from_id, edge.to_id)
                if node_id not in indexed_nodes
            ]
            if missing_ids:
                materialization_diagnostics.append(_diagnostic(
                    "GRAPH_ENDPOINT_NOT_FOUND",
                    "Contribution edge endpoint is not present in the current index",
                    source=loaded_contribution.source,
                    namespace=contribution.namespace,
                    edge_index=edge_index,
                    missing_ids=missing_ids,
                ))
                continue
            evidence_error = _validate_contribution_evidence(
                repo_path,
                file_hashes,
                edge.evidence,
                evidence_source_lines,
                source=loaded_contribution.source,
                namespace=contribution.namespace,
                edge_index=edge_index,
            )
            if evidence_error is not None:
                materialization_diagnostics.append(evidence_error)
                continue
            unsafe_endpoints = [
                node_id
                for node_id in (edge.from_id, edge.to_id)
                if _graph_path_error(
                    repo_path,
                    indexed_nodes[node_id].file_path,
                    graph_path_errors,
                    record="contribution endpoint source",
                ) is not None
            ]
            if unsafe_endpoints:
                materialization_diagnostics.append(_diagnostic(
                    "GRAPH_ENDPOINT_NOT_FOUND",
                    "Contribution edge endpoint source cannot be read safely",
                    source=loaded_contribution.source,
                    namespace=contribution.namespace,
                    edge_index=edge_index,
                    unsafe_ids=unsafe_endpoints,
                ))
                continue
            active_edges.append(edge)

    nodes = tuple(
        GraphNodeRef(
            id=node_id,
            namespace=namespace,
            kind=overlay_kinds[(namespace, node_id)],
            attributes=dict(sorted(attributes.items())),
        )
        for (namespace, node_id), attributes in sorted(overlay_values.items())
        if attributes
    )
    edges = tuple(_deduplicate_edges(active_edges))
    resolved_input_hashes = dict(input_hashes or {})
    for profile in active_profiles:
        resolved_input_hashes.setdefault(profile.source, profile.content_hash)
    for contribution in active_contributions:
        resolved_input_hashes.setdefault(contribution.source, contribution.content_hash)
    sorted_diagnostics = tuple(sorted(
        materialization_diagnostics,
        key=_diagnostic_sort_key,
    ))
    return GraphIndexState(
        schema_version=GRAPH_STATE_SCHEMA_VERSION,
        profiles=active_profiles,
        nodes=nodes,
        edges=edges,
        imports=import_records,
        contributions=active_contributions,
        input_hashes=dict(sorted(resolved_input_hashes.items())),
        diagnostics=sorted_diagnostics,
    )


def _page_roots(symbols: Sequence[Symbol]) -> dict[str, tuple[Symbol, ...]]:
    roots: dict[str, list[Symbol]] = {}
    for symbol in symbols:
        if _is_page_root(symbol):
            roots.setdefault(symbol.file_path, []).append(symbol)
    return {
        path: tuple(sorted(items, key=lambda item: item.id))
        for path, items in roots.items()
    }


def _is_page_root(symbol: Symbol) -> bool:
    if symbol.language != "markdown":
        return False
    markdown = symbol.metadata.get("markdown")
    return isinstance(markdown, Mapping) and markdown.get("page_root") is True


def _matches_page_root_selector(symbol: Symbol) -> bool:
    return _is_page_root(symbol)


def _source_field(source: str) -> str:
    return source.removeprefix("frontmatter.")


def _frontmatter_value(symbol: Symbol, field: str) -> Any:
    frontmatter = symbol.metadata.get("frontmatter")
    if not isinstance(frontmatter, Mapping):
        return None
    return frontmatter.get(field)


def _frontmatter_line(symbol: Symbol, field: str) -> int:
    lines = symbol.metadata.get("frontmatter_lines")
    if isinstance(lines, Mapping):
        line = lines.get(field)
        if isinstance(line, int) and not isinstance(line, bool) and line > 0:
            return line
    return max(symbol.line, 1)


def _frontmatter_invalid(symbol: Symbol, field: str) -> Mapping[str, Any] | None:
    values = symbol.metadata.get("frontmatter_invalid")
    if not isinstance(values, list):
        return None
    for value in values:
        if isinstance(value, Mapping) and value.get("field") == field:
            return value
    return None


def _valid_attribute_value(rule: GraphNodeAttributeRule, value: Any) -> bool:
    if rule.value_type == "string":
        values = (value,) if isinstance(value, str) and value else ()
    elif isinstance(value, list) and value and all(
        isinstance(item, str) and item for item in value
    ):
        values = tuple(value)
    else:
        values = ()
    if not values:
        return False
    return not rule.allowed_values or all(
        item in rule.allowed_values for item in values
    )


def _attribute_policies(
    profile: GraphProfile,
    symbol: Symbol,
) -> dict[str, GraphNodeAttributeRule]:
    if not _matches_page_root_selector(symbol):
        return {}
    return {
        attribute.name: attribute
        for rule in profile.node_rules
        for attribute in rule.attributes
    }


def _merge_overlay(
    values: dict[tuple[str, str], dict[str, JSONValue]],
    kinds: dict[tuple[str, str], str],
    diagnostics: list[GraphDiagnostic],
    namespace: str,
    symbol: Symbol,
    attribute: str,
    value: JSONValue,
    *,
    source: str,
) -> None:
    key = (namespace, symbol.id)
    attributes = values.setdefault(key, {})
    kinds[key] = symbol.kind
    existing = attributes.get(attribute)
    if attribute in attributes and existing != value:
        diagnostics.append(_diagnostic(
            "GRAPH_NODE_ATTRIBUTE_CONFLICT",
            "Graph node attribute conflicts with an earlier value",
            source=source,
            namespace=namespace,
            node_id=symbol.id,
            attribute=attribute,
            retained=existing,
            excluded=value,
        ))
        return
    attributes[attribute] = value


def _reference_values(value: Any) -> tuple[str, ...] | None:
    if value is None:
        return ()
    if isinstance(value, str) and value:
        return (value,)
    if isinstance(value, list) and all(isinstance(item, str) and item for item in value):
        return tuple(value)
    return None


def _relative_path(value: str) -> str | None:
    if not value or "\\" in value:
        return None
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or path.as_posix() != value:
        return None
    return value


def _graph_path_error(
    repo_path: Path,
    relative_path: str,
    errors: dict[str, str | None],
    *,
    record: str,
) -> str | None:
    if relative_path not in errors:
        try:
            validate_contained_file(
                repo_path,
                Path(relative_path),
                record=record,
            )
        except GraphContractError as exc:
            errors[relative_path] = exc.message
        else:
            errors[relative_path] = None
    return errors[relative_path]


def _validate_contribution_evidence(
    repo_path: Path,
    file_hashes: Mapping[str, str],
    evidence: GraphEvidence,
    source_lines: dict[str, int | str],
    *,
    source: str,
    namespace: str,
    edge_index: int,
) -> GraphDiagnostic | None:
    current_hash = file_hashes.get(evidence.file)
    if current_hash is None:
        return _diagnostic(
            "GRAPH_EVIDENCE_SOURCE_NOT_FOUND",
            "Contribution evidence source is not a current indexed file",
            source=source,
            namespace=namespace,
            edge_index=edge_index,
            evidence_file=evidence.file,
        )
    if current_hash != evidence.content_hash:
        return _diagnostic(
            "GRAPH_EVIDENCE_STALE",
            "Contribution evidence hash does not match the current source",
            source=source,
            namespace=namespace,
            edge_index=edge_index,
            evidence_file=evidence.file,
            expected_hash=current_hash,
            actual_hash=evidence.content_hash,
        )
    if evidence.file not in source_lines:
        try:
            data, _ = read_contained_file(
                repo_path,
                Path(evidence.file),
                record="evidence source",
            )
        except GraphContractError as exc:
            source_lines[evidence.file] = exc.message
        else:
            source_lines[evidence.file] = len(data.splitlines())
    line_count = source_lines[evidence.file]
    if isinstance(line_count, str):
        return _diagnostic(
            "GRAPH_EVIDENCE_SOURCE_NOT_FOUND",
            "Contribution evidence source cannot be read safely",
            source=source,
            namespace=namespace,
            edge_index=edge_index,
            evidence_file=evidence.file,
            reason=line_count,
        )
    if evidence.line > line_count:
        return _diagnostic(
            "GRAPH_EVIDENCE_LINE_INVALID",
            "Contribution evidence line is outside the current source",
            source=source,
            namespace=namespace,
            edge_index=edge_index,
            evidence_file=evidence.file,
            line=evidence.line,
            line_count=line_count,
        )
    return None


def _deduplicate_edges(edges: Sequence[GraphEdge]) -> list[GraphEdge]:
    by_record = {
        json.dumps(edge.to_dict(), sort_keys=True, separators=(",", ":")): edge
        for edge in edges
    }
    return [by_record[key] for key in sorted(by_record)]


def _diagnostic(
    code: str,
    message: str,
    *,
    source: str | None,
    **details: Any,
) -> GraphDiagnostic:
    return GraphDiagnostic(
        severity="error",
        code=code,
        message=message,
        source=source,
        details=cast(dict[str, JSONValue], details),
    )


def _contract_diagnostic(
    code: str,
    error: GraphContractError,
    *,
    fallback_source: str,
) -> GraphDiagnostic:
    details = dict(error.details)
    source_value = details.pop("source", fallback_source)
    source = source_value if isinstance(source_value, str) else fallback_source
    return _diagnostic(
        code,
        error.message,
        source=source,
        contract_code=error.code,
        **details,
    )


def _candidate_source(repo_path: Path, path: Path) -> str:
    try:
        return path.absolute().relative_to(repo_path.resolve()).as_posix()
    except ValueError:
        return str(path)


def _mapping_payload(value: Any, record: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise GraphContractError(
            f"INVALID_GRAPH_{record.upper()}",
            f"Graph {record} must be an object",
            {"record": record},
        )
    return value


def _diagnostic_sort_key(diagnostic: GraphDiagnostic) -> tuple[str, str, str, str]:
    details = json.dumps(
        diagnostic.details,
        sort_keys=True,
        separators=(",", ":"),
    )
    return (
        diagnostic.severity,
        diagnostic.code,
        diagnostic.source or "",
        hashlib.sha256(details.encode("utf-8")).hexdigest(),
    )
