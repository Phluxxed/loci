"""JavaScript value-scope evidence for authored direct class bases."""
from __future__ import annotations

from typing import Any, Sequence

from ._binding_context import collect_syntax_context
from .symbols import Symbol
from .type_models import LocalTypeBinding


def heritage_bindings(root: Any, source: bytes, symbols: Sequence[Symbol]):
    # These records share the type family's owner/provenance contract, while
    # JavaScript bases use value bindings rather than TypeScript namespaces.
    from .type_observations import _Binding, _matching_symbol, _walk

    nodes = {node.start_byte: node for node in reversed(tuple(_walk(root)))}
    result = []
    for raw in collect_syntax_context(root, source, "javascript").local_bindings:
        declaration = nodes.get(raw.declaration_start_byte)
        symbol = (_matching_symbol(declaration, source, symbols, "class")
                  if declaration is not None and declaration.type == "class_declaration" else None)
        if symbol is not None and symbol.name == raw.name:
            kind, namespace = "class", "both"
            start, end = symbol.byte_offset, symbol.byte_offset + symbol.byte_length
        else:
            kind, namespace = "unindexed", "value"
            start, end = raw.declaration_start_byte, raw.declaration_end_byte
            # Parameter/catch context may identify its enclosing syntax rather
            # than an indexed declaration. Keep it explicitly unindexed.
            if not raw.scope_start_byte <= start < end <= raw.scope_end_byte:
                start, end = raw.scope_start_byte, raw.scope_end_byte
        result.append(_Binding(LocalTypeBinding(
            name=raw.name, kind=kind, namespace=namespace,
            declaration_start_byte=start, declaration_end_byte=end,
            scope_start_byte=raw.scope_start_byte, scope_end_byte=raw.scope_end_byte,
        )))
    return tuple(result)
