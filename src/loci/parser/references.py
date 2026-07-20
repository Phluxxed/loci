from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, AbstractSet, Any, Sequence

from loci.parser._binding_context import (
    LexicalBinding,
    SyntaxContext,
    collect_syntax_context,
    node_key,
    python_scope,
)
from loci.parser._reference_exports import (
    _extract_local_exports,
    _node_text,
)
from loci.parser._reference_paths import (
    _go_path,
    _javascript_path,
    _python_path,
    _rust_path,
)
from loci.parser.reference_models import (
    MAX_REFERENCE_RESOLUTION_CANDIDATES,
    MAX_SYMBOL_REFERENCES_PER_FILE,
    BindingState,
    ImportBinding,
    RawSymbolReference,
    ReferenceExtractionBatch,
)

if TYPE_CHECKING:
    from loci.parser.imports import RawImport


@dataclass(frozen=True, slots=True)
class _PathObservation:
    node: Any
    path: tuple[str, ...]
    supported: bool = True


def extract_reference_batch(
    root_node: Any,
    source: bytes,
    *,
    source_file: str,
    language: str,
    source_hash: str,
    imports: Sequence[RawImport],
    context: SyntaxContext | None = None,
) -> ReferenceExtractionBatch:
    """Extract local exports and import-rooted references from an existing tree."""
    if language not in {"python", "javascript", "typescript", "go", "rust"}:
        raise ValueError(f"unsupported reference language: {language}")

    if context is None:
        context = collect_syntax_context(root_node, source, language)
    elif not isinstance(context, SyntaxContext):
        raise ValueError("context must be a SyntaxContext")
    exports = _extract_local_exports(
        root_node,
        source,
        source_file=source_file,
        language=language,
        source_hash=source_hash,
        imports=imports,
    )
    bindings_by_name: dict[str, list[ImportBinding]] = {}
    go_deferred: list[ImportBinding] = []
    for raw_import in imports:
        for binding in raw_import.bindings:
            if binding.local_name is not None:
                bindings_by_name.setdefault(binding.local_name, []).append(binding)
            elif language == "go" and binding.kind == "namespace":
                go_deferred.append(binding)
    local_bindings_by_name: dict[str, list[LexicalBinding]] = {}
    for binding in context.local_bindings:
        local_bindings_by_name.setdefault(binding.name, []).append(binding)
    references: list[RawSymbolReference] = []
    for observation in _iter_path_observations(
        root_node,
        source,
        language,
        context.excluded_subtrees,
    ):
        reference = _match_observation(
            observation,
            source,
            source_file=source_file,
            language=language,
            source_hash=source_hash,
            named_bindings=bindings_by_name.get(observation.path[0], ()),
            deferred_bindings=go_deferred,
            local_bindings=local_bindings_by_name.get(observation.path[0], ()),
            unsupported_import_starts=context.unsupported_import_starts,
        )
        if reference is None:
            continue
        if len(references) >= MAX_SYMBOL_REFERENCES_PER_FILE:
            raise ValueError("references exceeds the per-file limit")
        references.append(reference)

    return ReferenceExtractionBatch(
        exports=tuple(exports),
        references=tuple(references),
    )


def _match_observation(
    observation: _PathObservation,
    source: bytes,
    *,
    source_file: str,
    language: str,
    source_hash: str,
    named_bindings: Sequence[ImportBinding],
    deferred_bindings: Sequence[ImportBinding],
    local_bindings: Sequence[LexicalBinding],
    unsupported_import_starts: AbstractSet[int],
) -> RawSymbolReference | None:
    node = observation.node
    root_name = observation.path[0]
    all_named = [
        binding
        for binding in named_bindings
        if binding.kind not in {"blank", "glob", "side_effect"}
        and _binding_contains(binding, node)
    ]
    visible_named = [
        binding
        for binding in all_named
        if language != "python"
        or (
            binding.declaration_start_byte < node.start_byte
            and _python_import_scope_is_visible(binding, node)
        )
    ]
    candidates = _nearest_import_candidates(visible_named, language)

    if candidates:
        if len(candidates) > MAX_REFERENCE_RESOLUTION_CANDIDATES:
            raise ValueError("candidate bindings exceeds the candidate limit")
        state: BindingState
        if not observation.supported or any(
            candidate.declaration_start_byte in unsupported_import_starts
            for candidate in candidates
        ):
            state = "unsupported"
        elif len(candidates) > 1:
            state = "ambiguous"
        elif _binding_is_shadowed(
            candidates[0],
            node,
            language=language,
            local_bindings=local_bindings,
            all_named_imports=all_named,
        ):
            state = "shadowed"
        else:
            state = "definite"
        return _raw_reference(
            observation,
            source,
            source_file=source_file,
            language=language,
            source_hash=source_hash,
            candidates=tuple(candidates),
            state=state,
        )

    if language != "go" or not observation.supported or len(observation.path) < 2:
        return None

    deferred = [
        binding
        for binding in deferred_bindings
        if _binding_contains(binding, node)
    ]
    if not deferred or _unbound_go_root_is_shadowed(
        node,
        local_bindings,
    ):
        return None
    if len(deferred) > MAX_REFERENCE_RESOLUTION_CANDIDATES:
        raise ValueError("candidate bindings exceeds the candidate limit")
    return _raw_reference(
        observation,
        source,
        source_file=source_file,
        language=language,
        source_hash=source_hash,
        candidates=tuple(deferred),
        state="deferred",
    )


def _raw_reference(
    observation: _PathObservation,
    source: bytes,
    *,
    source_file: str,
    language: str,
    source_hash: str,
    candidates: tuple[ImportBinding, ...],
    state: BindingState,
) -> RawSymbolReference:
    node = observation.node
    return RawSymbolReference(
        source_file=source_file,
        language=language,
        line=node.start_point[0] + 1,
        column=node.start_point[1] + 1,
        start_byte=node.start_byte,
        end_byte=node.end_byte,
        text=_node_text(node, source),
        path=observation.path,
        candidate_bindings=candidates,
        binding_state=state,
        source_hash=source_hash,
    )


def _binding_contains(binding: ImportBinding, node: Any) -> bool:
    return (
        binding.scope_start_byte <= node.start_byte
        and node.end_byte <= binding.scope_end_byte
    )


def _nearest_import_candidates(
    bindings: list[ImportBinding],
    language: str,
) -> list[ImportBinding]:
    if not bindings:
        return []
    smallest_scope = min(
        binding.scope_end_byte - binding.scope_start_byte
        for binding in bindings
    )
    nearest = [
        binding
        for binding in bindings
        if binding.scope_end_byte - binding.scope_start_byte == smallest_scope
    ]
    if language == "python" and nearest:
        latest_declaration = max(
            binding.declaration_start_byte for binding in nearest
        )
        nearest = [
            binding
            for binding in nearest
            if binding.declaration_start_byte == latest_declaration
        ]
    return nearest


def _binding_is_shadowed(
    binding: ImportBinding,
    node: Any,
    *,
    language: str,
    local_bindings: Sequence[LexicalBinding],
    all_named_imports: list[ImportBinding],
) -> bool:
    matching_locals = [
        local
        for local in local_bindings
        if local.scope_start_byte <= node.start_byte
        and node.end_byte <= local.scope_end_byte
    ]
    if language == "python":
        for other in all_named_imports:
            if (
                _scope_span(other.scope_start_byte, other.scope_end_byte)
                < _scope_span(binding.scope_start_byte, binding.scope_end_byte)
            ):
                return True
        for local in matching_locals:
            same_scope = (
                local.scope_start_byte == binding.scope_start_byte
                and local.scope_end_byte == binding.scope_end_byte
            )
            if not same_scope:
                if local.scope_type in {
                    "function_definition",
                    "lambda",
                    "definition_body",
                }:
                    return True
                nearest_scope = python_scope(node)
                if (
                    nearest_scope.start_byte != local.scope_start_byte
                    or nearest_scope.end_byte != local.scope_end_byte
                ):
                    continue
                if local.active_start_byte <= node.start_byte:
                    return True
                continue
            if (
                local.active_start_byte <= node.start_byte
                and local.declaration_start_byte > binding.declaration_start_byte
            ):
                return True
        return False
    if language == "javascript" or language == "typescript":
        return bool(matching_locals)
    return any(local.active_start_byte <= node.start_byte for local in matching_locals)


def _unbound_go_root_is_shadowed(
    node: Any,
    local_bindings: Sequence[LexicalBinding],
) -> bool:
    return any(
        local.scope_start_byte <= node.start_byte
        and node.end_byte <= local.scope_end_byte
        and local.active_start_byte <= node.start_byte
        for local in local_bindings
    )


def _scope_span(start: int, end: int) -> int:
    return end - start


def _python_import_scope_is_visible(binding: ImportBinding, node: Any) -> bool:
    ancestor = node
    while ancestor is not None:
        if (
            ancestor.start_byte == binding.scope_start_byte
            and ancestor.end_byte == binding.scope_end_byte
        ):
            if ancestor.type != "class_definition":
                return True
            nearest_scope = python_scope(node)
            return (
                nearest_scope.start_byte == ancestor.start_byte
                and nearest_scope.end_byte == ancestor.end_byte
            )
        ancestor = ancestor.parent
    return False


def _iter_path_observations(
    root: Any,
    source: bytes,
    language: str,
    excluded_subtrees: AbstractSet[tuple[int, int, str]],
):
    def visit(node: Any):
        if node_key(node) in excluded_subtrees:
            return
        observation = _path_observation(node, source, language)
        if observation is not None:
            yield observation
            return
        for child in node.named_children:
            yield from visit(child)

    yield from visit(root)


def _path_observation(
    node: Any,
    source: bytes,
    language: str,
) -> _PathObservation | None:
    if language == "python":
        path = _python_path(node, source)
        if path is not None:
            return _PathObservation(node=node, path=path)
        if node.type == "subscript":
            value = node.child_by_field_name("value")
            root = _python_path(value, source) if value is not None else None
            if root is not None:
                return _PathObservation(node=node, path=(root[0],), supported=False)
        return None
    if language in {"javascript", "typescript"}:
        path = _javascript_path(node, source)
        if path is not None:
            return _PathObservation(node=node, path=path)
        if node.type == "subscript_expression":
            value = node.child_by_field_name("object")
            root = _javascript_path(value, source) if value is not None else None
            if root is not None:
                return _PathObservation(node=node, path=(root[0],), supported=False)
        return None
    if language == "go":
        path = _go_path(node, source)
        return _PathObservation(node=node, path=path) if path is not None else None
    if node.type == "macro_invocation":
        macro = node.child_by_field_name("macro")
        path = _rust_path(macro, source)
        if path is not None:
            return _PathObservation(node=node, path=path, supported=False)
    path = _rust_path(node, source)
    return _PathObservation(node=node, path=path) if path is not None else None
