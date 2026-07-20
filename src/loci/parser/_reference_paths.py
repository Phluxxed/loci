from __future__ import annotations

from typing import Any

from loci.parser._reference_exports import _node_text
from loci.parser.reference_models import MAX_REFERENCE_PATH_SEGMENTS


def _python_path(
    node: Any | None,
    source: bytes,
    remaining: int = MAX_REFERENCE_PATH_SEGMENTS,
) -> tuple[str, ...] | None:
    if node is None:
        return None
    if remaining <= 0:
        raise ValueError("reference path exceeds the segment limit")
    if node.type == "identifier":
        return (_node_text(node, source),)
    if node.type != "attribute":
        return None
    value = node.child_by_field_name("object")
    attribute = node.child_by_field_name("attribute")
    prefix = _python_path(value, source, remaining - 1)
    if prefix is None or attribute is None or attribute.type != "identifier":
        return None
    return (*prefix, _node_text(attribute, source))


def _javascript_path(
    node: Any | None,
    source: bytes,
    remaining: int = MAX_REFERENCE_PATH_SEGMENTS,
) -> tuple[str, ...] | None:
    if node is None:
        return None
    if remaining <= 0:
        raise ValueError("reference path exceeds the segment limit")
    if node.type in {"identifier", "type_identifier"}:
        return (_node_text(node, source),)
    fields = {
        "member_expression": ("object", "property"),
        "nested_type_identifier": ("module", "name"),
    }
    field_names = fields.get(node.type)
    if field_names is None:
        return None
    value = node.child_by_field_name(field_names[0])
    member = node.child_by_field_name(field_names[1])
    prefix = _javascript_path(value, source, remaining - 1)
    if prefix is None or member is None:
        return None
    if member.type not in {"identifier", "type_identifier", "property_identifier"}:
        return None
    return (*prefix, _node_text(member, source))


def _go_path(
    node: Any | None,
    source: bytes,
    remaining: int = MAX_REFERENCE_PATH_SEGMENTS,
) -> tuple[str, ...] | None:
    if node is None:
        return None
    if remaining <= 0:
        raise ValueError("reference path exceeds the segment limit")
    if node.type == "selector_expression":
        value = node.child_by_field_name("operand")
        member = node.child_by_field_name("field")
        if value is None or member is None:
            return None
        if value.type in {"identifier", "package_identifier"}:
            prefix = (_node_text(value, source),)
        else:
            prefix = _go_path(value, source, remaining - 1)
        return (*prefix, _node_text(member, source)) if prefix is not None else None
    if node.type == "qualified_type":
        package = node.child_by_field_name("package")
        name = node.child_by_field_name("name")
        if package is None or name is None:
            return None
        return (_node_text(package, source), _node_text(name, source))
    return None


def _rust_path(
    node: Any | None,
    source: bytes,
    remaining: int = MAX_REFERENCE_PATH_SEGMENTS,
) -> tuple[str, ...] | None:
    if node is None:
        return None
    if remaining <= 0:
        raise ValueError("reference path exceeds the segment limit")
    if node.type in {"identifier", "type_identifier"}:
        return (_node_text(node, source),)
    if node.type not in {"scoped_identifier", "scoped_type_identifier"}:
        return None
    value = node.child_by_field_name("path")
    name = node.child_by_field_name("name")
    prefix = _rust_path(value, source, remaining - 1)
    if prefix is None and value is not None and value.type in {"crate", "self", "super"}:
        prefix = (_node_text(value, source),)
    if prefix is None or name is None:
        return None
    return (*prefix, _node_text(name, source))
