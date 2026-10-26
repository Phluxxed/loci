"""Conservative source-only guards for JavaScript value binding proofs."""
from __future__ import annotations

from typing import Any


def mutated_roots(root: Any, source: bytes) -> frozenset[str]:
    """Refuse a target name written anywhere in the same file.

    This deliberately makes no execution-order or alias-analysis claim.
    """
    def walk(node):
        yield node
        for child in node.named_children:
            yield from walk(child)

    result = set()
    for node in walk(root):
        if node.type in {"assignment_expression", "augmented_assignment_expression"}:
            target = node.child_by_field_name("left")
        elif node.type == "update_expression":
            target = node.child_by_field_name("argument")
        elif node.type == "unary_expression" and any(child.type == "delete" for child in node.children):
            target = node.child_by_field_name("argument")
        else:
            continue
        if target is None:
            continue
        while target.type in {"member_expression", "subscript_expression"}:
            target = target.child_by_field_name("object")
            if target is None:
                break
        if target is not None:
            result.update(source[child.start_byte:child.end_byte].decode("utf-8")
                          for child in walk(target)
                          if child.type in {"identifier", "shorthand_property_identifier_pattern"})
    return frozenset(result)
