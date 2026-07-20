from __future__ import annotations

from typing import Any, TypeAlias

from loci.parser._binding_context import (
    LexicalBinding,
    SyntaxContext,
    nearest_executable_owner,
)
from loci.parser._reference_exports import _node_text, _walk_nodes
from loci.parser.call_models import (
    MAX_CALL_BINDING_CANDIDATES,
    MAX_CALL_PATH_SEGMENTS,
    MAX_CALL_SITES_PER_FILE,
    CallBindingState,
    CallCalleeForm,
    LocalCallableBinding,
    RawCallSite,
)


_SUPPORTED_LANGUAGES = {"python", "javascript", "typescript", "go", "rust"}
_CALL_NODE_TYPES = {
    "python": {"call"},
    "javascript": {"call_expression"},
    "typescript": {"call_expression"},
    "go": {"call_expression"},
    "rust": {"call_expression"},
}

StaticPath: TypeAlias = tuple[str, ...]


def extract_call_sites(
    root_node: Any,
    source: bytes,
    *,
    source_file: str,
    language: str,
    source_hash: str,
    context: SyntaxContext,
) -> tuple[RawCallSite, ...]:
    """Extract bounded call observations from an existing parse and context."""
    if language not in _SUPPORTED_LANGUAGES:
        raise ValueError(f"unsupported call extraction language: {language}")
    if not isinstance(context, SyntaxContext):
        raise ValueError("context must be a SyntaxContext")

    observations: list[RawCallSite] = []
    for node in _walk_nodes(root_node):
        if node.type not in _CALL_NODE_TYPES[language]:
            continue
        callee = node.child_by_field_name("function")
        if callee is None or callee.start_byte >= callee.end_byte:
            continue
        if language in {"javascript", "typescript"} and any(
            child.type == "optional_chain" for child in node.named_children
        ):
            callee_form, callee_path = "dynamic", ()
        else:
            callee_form, callee_path = _classify_callee(callee, source, language)
        local_candidates, local_binding_state = _local_call_binding(
            callee,
            callee_path,
            callee_form,
            source,
            context,
        )
        observations.append(
            RawCallSite(
                source_file=source_file,
                language=language,
                line=node.start_point.row + 1,
                column=node.start_point.column + 1,
                start_byte=node.start_byte,
                end_byte=node.end_byte,
                callee_start_byte=callee.start_byte,
                callee_end_byte=callee.end_byte,
                callee_text=_node_text(callee, source),
                callee_path=callee_path,
                callee_form=callee_form,
                local_candidates=local_candidates,
                local_binding_state=local_binding_state,
                owner=nearest_executable_owner(context, node),
                source_hash=source_hash,
            )
        )
        if len(observations) > MAX_CALL_SITES_PER_FILE:
            raise ValueError("calls exceeds the per-file limit")

    return tuple(
        sorted(
            observations,
            key=lambda call: (
                call.source_file,
                call.start_byte,
                call.end_byte,
                call.callee_start_byte,
                call.callee_end_byte,
            ),
        )
    )


def _classify_callee(
    node: Any,
    source: bytes,
    language: str,
) -> tuple[CallCalleeForm, StaticPath]:
    if node.type == "identifier":
        return "identifier", (_node_text(node, source),)
    path: StaticPath | None
    if language == "python":
        path = _python_path(node, source)
    elif language in {"javascript", "typescript"}:
        path = _javascript_path(node, source)
    elif language == "go":
        path = _go_path(node, source)
    else:
        path = _rust_path(node, source)
    if path is not None and len(path) > 1:
        return "static_path", path
    return "dynamic", ()


def _python_path(
    node: Any,
    source: bytes,
    remaining: int = MAX_CALL_PATH_SEGMENTS,
) -> StaticPath | None:
    if remaining <= 0:
        raise ValueError("call path exceeds the segment limit")
    if node.type == "identifier":
        return (_node_text(node, source),)
    if node.type != "attribute":
        return None
    value = node.child_by_field_name("object")
    attribute = node.child_by_field_name("attribute")
    if value is None or attribute is None or attribute.type != "identifier":
        return None
    prefix = _python_path(value, source, remaining - 1)
    if prefix is None:
        return None
    return (*prefix, _node_text(attribute, source))


def _javascript_path(
    node: Any,
    source: bytes,
    remaining: int = MAX_CALL_PATH_SEGMENTS,
) -> StaticPath | None:
    if remaining <= 0:
        raise ValueError("call path exceeds the segment limit")
    if node.type in {"identifier", "this"}:
        return (_node_text(node, source),)
    if node.type != "member_expression" or _contains_type(node, "optional_chain"):
        return None
    value = node.child_by_field_name("object")
    property_node = node.child_by_field_name("property")
    if value is None or property_node is None or property_node.type not in {
        "identifier",
        "property_identifier",
        "private_property_identifier",
    }:
        return None
    prefix = _javascript_path(value, source, remaining - 1)
    if prefix is None:
        return None
    return (*prefix, _node_text(property_node, source))


def _go_path(
    node: Any,
    source: bytes,
    remaining: int = MAX_CALL_PATH_SEGMENTS,
) -> StaticPath | None:
    if remaining <= 0:
        raise ValueError("call path exceeds the segment limit")
    if node.type == "identifier":
        return (_node_text(node, source),)
    if node.type != "selector_expression":
        return None
    value = node.child_by_field_name("operand")
    field = node.child_by_field_name("field")
    if value is None or field is None or field.type != "field_identifier":
        return None
    prefix = _go_path(value, source, remaining - 1)
    if prefix is None:
        return None
    return (*prefix, _node_text(field, source))


def _rust_path(
    node: Any,
    source: bytes,
    remaining: int = MAX_CALL_PATH_SEGMENTS,
) -> StaticPath | None:
    if remaining <= 0:
        raise ValueError("call path exceeds the segment limit")
    if node.type in {"identifier", "crate", "self", "super"}:
        return (_node_text(node, source),)
    if node.type != "scoped_identifier":
        return None
    prefix_node = node.child_by_field_name("path")
    name = node.child_by_field_name("name")
    if prefix_node is None or name is None or name.type != "identifier":
        return None
    prefix = _rust_path(prefix_node, source, remaining - 1)
    if prefix is None:
        return None
    return (*prefix, _node_text(name, source))


def _contains_type(node: Any, node_type: str) -> bool:
    return any(child.type == node_type for child in _walk_nodes(node))


def _local_call_binding(
    callee: Any,
    path: StaticPath,
    form: CallCalleeForm,
    source: bytes,
    context: SyntaxContext,
) -> tuple[tuple[LocalCallableBinding, ...], CallBindingState]:
    if form == "dynamic":
        return (), "unsupported"
    if form == "static_path":
        return (), "absent"

    name = path[0]
    visible = [
        binding
        for binding in context.local_bindings
        if binding.name == name
        and binding.scope_start_byte <= callee.start_byte
        and callee.end_byte <= binding.scope_end_byte
        and binding.active_start_byte <= callee.start_byte
    ]
    if not visible:
        return (), "absent"
    nearest_span = min(
        binding.scope_end_byte - binding.scope_start_byte for binding in visible
    )
    nearest = [
        binding
        for binding in visible
        if binding.scope_end_byte - binding.scope_start_byte == nearest_span
    ]
    if any(
        binding.kind != "callable" or binding.callable_kind is None
        for binding in nearest
    ):
        return (), "shadowed"

    candidates_by_identity: dict[tuple[Any, ...], LocalCallableBinding] = {}
    for binding in nearest:
        candidate = _callable_candidate(binding, source)
        key = (
            candidate.name,
            candidate.callable_kind,
            candidate.definition_start_byte,
            candidate.definition_end_byte,
            candidate.scope_start_byte,
            candidate.scope_end_byte,
        )
        candidates_by_identity[key] = candidate
    candidates = tuple(
        sorted(
            candidates_by_identity.values(),
            key=lambda candidate: (
                candidate.definition_start_byte,
                candidate.definition_end_byte,
                candidate.callable_kind,
                candidate.scope_start_byte,
                candidate.scope_end_byte,
            ),
        )
    )
    if len(candidates) > MAX_CALL_BINDING_CANDIDATES:
        raise ValueError("local call candidates exceeds the candidate limit")
    if len(candidates) == 1:
        return candidates, "definite"
    return candidates, "ambiguous"


def _callable_candidate(
    binding: LexicalBinding,
    source: bytes,
) -> LocalCallableBinding:
    assert binding.callable_kind is not None
    return LocalCallableBinding(
        name=binding.name,
        callable_kind=binding.callable_kind,
        definition_start_byte=binding.declaration_start_byte,
        definition_end_byte=binding.declaration_end_byte,
        definition_line=source.count(b"\n", 0, binding.declaration_start_byte) + 1,
        scope_start_byte=binding.scope_start_byte,
        scope_end_byte=binding.scope_end_byte,
    )
