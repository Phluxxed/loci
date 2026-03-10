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


_SPECS: dict[str, LanguageSpec] = {
    "python": LanguageSpec(
        ts_language="python",
        symbol_node_types={
            "function_definition": "function",
            "class_definition": "class",
            "decorated_definition": "function",  # resolved during walk
        },
        name_fields=["name"],
        param_fields=["parameters"],
        return_type_fields=["return_type"],
        docstring_strategy="next_sibling_string",
        container_node_types=["class_definition"],
    ),
    "typescript": LanguageSpec(
        ts_language="typescript",
        symbol_node_types={
            "function_declaration": "function",
            "class_declaration": "class",
            "method_definition": "method",
            "type_alias_declaration": "type",
            "interface_declaration": "interface",
        },
        name_fields=["name"],
        param_fields=["parameters"],
        return_type_fields=["return_type"],
        docstring_strategy="preceding_comment",
        container_node_types=["class_declaration", "class_body"],
    ),
}

EXTENSION_MAP: dict[str, str] = {
    ".py": "python",
    ".ts": "typescript",
    ".tsx": "typescript",
}


def get_language_spec(language: str) -> Optional[LanguageSpec]:
    return _SPECS.get(language)
