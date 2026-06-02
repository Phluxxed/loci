from __future__ import annotations
from dataclasses import dataclass
from typing import Optional


@dataclass
class LanguageSpec:
    ts_language: str
    symbol_node_types: dict[str, str]       # AST node type → symbol kind
    name_fields: list[str]                   # field names to try for symbol name
    param_fields: list[str]                  # field names for parameters
    return_type_fields: list[str]            # field names for return type
    docstring_strategy: str                  # "next_sibling_string" | "preceding_comment"
    container_node_types: list[str]          # node types whose children become methods
    constant_name_pattern: str = ""          # regex; if set, only extract constants whose name matches
    decorator_child_type: str = ""           # child node type that represents a decorator/attribute
    decorator_sibling_type: str = ""         # preceding-sibling node type for decorators (e.g. Rust attribute_item)


_SPECS: dict[str, LanguageSpec] = {
    "python": LanguageSpec(
        ts_language="python",
        symbol_node_types={
            "function_definition": "function",
            "class_definition": "class",
            "decorated_definition": "function",  # resolved during walk
            "assignment": "constant",
        },
        # "left" is the name field for assignment nodes; "name" for function/class
        name_fields=["name", "left"],
        param_fields=["parameters"],
        return_type_fields=["return_type"],
        docstring_strategy="next_sibling_string",
        container_node_types=["class_definition"],
        constant_name_pattern=r"^[A-Z][A-Z0-9_]*$",
        decorator_child_type="decorator",
    ),
    "typescript": LanguageSpec(
        ts_language="typescript",
        symbol_node_types={
            "function_declaration": "function",
            "class_declaration": "class",
            "method_definition": "method",
            "type_alias_declaration": "type",
            "interface_declaration": "interface",
            "variable_declarator": "constant",
        },
        name_fields=["name"],
        param_fields=["parameters"],
        return_type_fields=["return_type"],
        docstring_strategy="preceding_comment",
        container_node_types=["class_declaration", "class_body"],
        constant_name_pattern=r"^[A-Z][A-Z0-9_]*$",
        decorator_child_type="decorator",
    ),
    "tsx": LanguageSpec(
        ts_language="tsx",
        symbol_node_types={
            "function_declaration": "function",
            "class_declaration": "class",
            "method_definition": "method",
            "type_alias_declaration": "type",
            "interface_declaration": "interface",
            "variable_declarator": "constant",
        },
        name_fields=["name"],
        param_fields=["parameters"],
        return_type_fields=["return_type"],
        docstring_strategy="preceding_comment",
        container_node_types=["class_declaration", "class_body"],
        constant_name_pattern=r"^[A-Z][A-Z0-9_]*$",
        decorator_child_type="decorator",
    ),
    "go": LanguageSpec(
        ts_language="go",
        symbol_node_types={
            "function_declaration": "function",
            "method_declaration": "method",
            "type_spec": "type",
            "const_spec": "constant",
        },
        name_fields=["name"],
        param_fields=["parameters"],
        return_type_fields=["result"],
        docstring_strategy="preceding_comment",
        container_node_types=[],
    ),
    "rust": LanguageSpec(
        ts_language="rust",
        symbol_node_types={
            "function_item": "function",
            "struct_item": "struct",
            "enum_item": "enum",
            "trait_item": "trait",
            "impl_item": "impl",
            "const_item": "constant",
        },
        # impl_item has no "name" field — falls back to "type" (the implementing type)
        name_fields=["name", "type"],
        param_fields=["parameters"],
        return_type_fields=["return_type"],
        docstring_strategy="preceding_comment",
        container_node_types=["impl_item"],
        decorator_sibling_type="attribute_item",
    ),
    "javascript": LanguageSpec(
        ts_language="javascript",
        symbol_node_types={
            "function_declaration": "function",
            "class_declaration": "class",
            "method_definition": "method",
            "variable_declarator": "constant",
        },
        name_fields=["name"],
        param_fields=["parameters"],
        return_type_fields=[],
        docstring_strategy="preceding_comment",
        container_node_types=["class_declaration", "class_body"],
        constant_name_pattern=r"^[A-Z][A-Z0-9_]*$",
        decorator_child_type="decorator",
    ),
}

EXTENSION_MAP: dict[str, str] = {
    ".py": "python",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".go": "go",
    ".rs": "rust",
    ".js": "javascript",
}


def get_language_spec(language: str) -> Optional[LanguageSpec]:
    return _SPECS.get(language)
