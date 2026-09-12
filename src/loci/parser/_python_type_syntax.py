"""Small syntax helpers shared by Python declarations and type observations."""
from __future__ import annotations

from typing import Any, Iterator


def walk(node: Any) -> Iterator[Any]:
    yield node
    for child in node.named_children:
        yield from walk(child)


def text(node: Any, source: bytes) -> str:
    return source[node.start_byte:node.end_byte].decode("utf-8")


def name_path(node: Any, source: bytes) -> tuple[str, ...]:
    if node.type == "type" and len(node.named_children) == 1:
        return name_path(node.named_children[0], source)
    if node.type == "identifier":
        return (text(node, source),)
    if node.type == "attribute":
        head = node.child_by_field_name("object")
        tail = node.child_by_field_name("attribute")
        if head is not None and tail is not None:
            prefix = name_path(head, source)
            if prefix and tail.type == "identifier":
                return (*prefix, text(tail, source))
    return ()


def is_python_type_alias(node: Any, source: bytes) -> bool:
    """Recognize a module alias with an unambiguous canonical TypeAlias marker.

    Marker aliases and nested alias declarations remain outside this initial
    subset. Merely spelling a local class or value ``TypeAlias`` is insufficient.
    """
    if node.type != "assignment" or node.parent is None or node.parent.type != "module":
        return False
    left = node.child_by_field_name("left")
    annotation = node.child_by_field_name("type")
    if (left is None or left.type != "identifier" or annotation is None
            or node.child_by_field_name("right") is None):
        return False
    marker = name_path(annotation, source)
    if marker not in {("TypeAlias",), ("typing", "TypeAlias"),
                       ("typing_extensions", "TypeAlias")}:
        return False
    root_name = marker[0]
    matches = []
    for child in node.parent.named_children:
        if child.type in {"import_statement", "import_from_statement"}:
            if any(item.type == "wildcard_import" for item in child.named_children):
                return False
            module = child.child_by_field_name("module_name")
            module_name = text(module, source) if module is not None else None
            for i, item in enumerate(child.children):
                if child.field_name_for_child(i) != "name":
                    continue
                alias = item.child_by_field_name("alias")
                original = item.child_by_field_name("name") if alias is not None else item
                spelling = text(original, source)
                bound = text(alias, source) if alias is not None else spelling.split(".")[0]
                if bound == root_name:
                    matches.append(child.start_byte < node.start_byte and (
                        (len(marker) == 1 and module_name in {"typing", "typing_extensions"}
                         and spelling == "TypeAlias")
                        or (len(marker) == 2 and module_name is None and spelling == root_name)
                    ))
            continue
        # A second module binding, including one under conditional syntax,
        # prevents a static claim that the marker has its canonical meaning.
        for nested in walk(child):
            if nested.type in {"import_statement", "import_from_statement"}:
                if any(item.type == "wildcard_import" for item in nested.named_children):
                    return False
                if any(text(item, source) == root_name for item in walk(nested) if item.type == "identifier"):
                    return False
            if nested.type in {"assignment", "augmented_assignment", "named_expression", "for_statement", "for_in_clause"}:
                target = nested.child_by_field_name("left") or nested.child_by_field_name("name")
                if target is not None and root_name in {text(n, source) for n in walk(target)
                                                       if n.type == "identifier"}:
                    return False
            if nested.type in {"as_pattern", "case_pattern", "delete_statement"}:
                if any(text(item, source) == root_name for item in walk(nested) if item.type == "identifier"):
                    return False
            if nested.type in {"function_definition", "class_definition"}:
                name = nested.child_by_field_name("name")
                if name is not None and text(name, source) == root_name:
                    return False
    return matches == [True]
