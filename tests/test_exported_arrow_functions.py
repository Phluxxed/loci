from __future__ import annotations

import hashlib
from dataclasses import replace
from pathlib import Path

import pytest

from loci.graph.javascript_modules import (
    build_javascript_resolution_index,
    load_javascript_module_context,
)
from loci.graph.materialize import materialize_graph
from loci.parser.extractor import parse_file
from loci.parser.imports import extract_import_batch
from loci.parser.symbols import Symbol, make_file_symbol, make_symbol_id


_ARROW_FORMS = (
    pytest.param(
        ".js",
        "javascript",
        "num",
        "export const num = (value) => value;\n",
        id="javascript-lowercase",
    ),
    pytest.param(
        ".ts",
        "typescript",
        "num",
        "export const num = (value: unknown): number => 1;\n",
        id="typescript-lowercase",
    ),
    pytest.param(
        ".tsx",
        "typescript",
        "NUM",
        "export const NUM = (value: number): number => value;\n",
        id="tsx-uppercase",
    ),
)


@pytest.mark.parametrize(
    ("suffix", "language", "name", "arrow_source"),
    _ARROW_FORMS,
)
def test_direct_variable_bound_arrows_are_function_symbols(
    tmp_path: Path,
    suffix: str,
    language: str,
    name: str,
    arrow_source: str,
):
    path = tmp_path / f"module{suffix}"
    path.write_text(
        arrow_source
        + "export const VALUE = 1;\n"
        + "export function named(value) { return value; }\n",
        encoding="utf-8",
    )

    symbols = parse_file(path)
    by_name = {symbol.name: symbol for symbol in symbols}

    assert by_name[name].kind == "function"
    assert sum(symbol.name == name for symbol in symbols) == 1
    arrow = by_name[name]
    expected_source = arrow_source.removeprefix("export const ").removesuffix(";\n")
    assert path.read_bytes()[arrow.byte_offset:arrow.byte_offset + arrow.byte_length] == expected_source.encode()
    assert by_name["VALUE"].kind == "constant"
    assert by_name["named"].kind == "function"


def test_arrow_body_preserves_nested_declaration_ownership(tmp_path: Path):
    path = tmp_path / "nested.ts"
    path.write_text(
        "export const outer = () => {\n"
        "  const inner = () => 1;\n"
        "  function named() { return 2; }\n"
        "  return inner;\n"
        "}, other = () => 3;\n",
        encoding="utf-8",
    )
    assert [(symbol.qualified_name, symbol.kind) for symbol in parse_file(path)] == [
        ("outer", "function"),
        ("outer.inner", "function"),
        ("outer.named", "function"),
        ("other", "function"),
    ]


def _materialize_arrow_tree(
    tmp_path: Path,
    *,
    suffix: str,
    language: str,
    name: str,
    arrow_source: str,
):
    files = {
        f"lib{suffix}": (
            arrow_source
            + "export const VALUE = 1;\n"
            + "export function named(value) { return value; }\n"
        ),
        f"decoy/lib{suffix}": (
            f"export const {name} = (value) => 999;\n"
        ),
        f"use{suffix}": (
            f'import {{ {name} }} from "./lib.js";\n'
            f"export function useNumber() {{ return {name}(1); }}\n"
        ),
    }
    symbols: list[Symbol] = []
    file_nodes: dict[str, Symbol] = {}
    batches = []
    file_hashes: dict[str, str] = {}

    for relative_path, source in files.items():
        path = tmp_path / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding="utf-8")
        source_hash = hashlib.sha256(source.encode()).hexdigest()
        file_hashes[relative_path] = source_hash
        file_language = language
        file_node = make_file_symbol(
            relative_path,
            language=file_language,
            content_hash=source_hash,
        )
        file_nodes[relative_path] = file_node
        symbols.append(file_node)
        symbols.extend(
            replace(
                symbol,
                id=make_symbol_id(relative_path, symbol.qualified_name, symbol.kind),
                file_path=relative_path,
            )
            for symbol in parse_file(path)
        )
        batches.append(
            extract_import_batch(
                path,
                source_file=relative_path,
                language=file_language,
                source_hash=source_hash,
            )
        )

    loaded = load_javascript_module_context(tmp_path, [])
    assert loaded.problems == ()
    javascript_index = build_javascript_resolution_index(
        loaded.context,
        file_nodes=file_nodes,
    )
    assert javascript_index.problems == ()

    return materialize_graph(
        tmp_path,
        symbols,
        file_hashes,
        [],
        [],
        raw_imports=[raw for batch in batches for raw in batch.imports],
        raw_exports=[raw for batch in batches for raw in batch.exports],
        raw_symbol_references=[
            raw for batch in batches for raw in batch.references
        ],
        raw_calls=[raw for batch in batches for raw in batch.calls],
        javascript_modules=javascript_index.index,
        input_hashes=loaded.input_hashes,
    )


@pytest.mark.parametrize(
    ("suffix", "language", "name", "arrow_source"),
    _ARROW_FORMS,
)
def test_exported_arrow_import_has_exact_reference_and_call_target(
    tmp_path: Path,
    suffix: str,
    language: str,
    name: str,
    arrow_source: str,
):
    state = _materialize_arrow_tree(
        tmp_path,
        suffix=suffix,
        language=language,
        name=name,
        arrow_source=arrow_source,
    )

    target_id = f"lib{suffix}::{name}#function"
    caller_id = f"use{suffix}::useNumber#function"
    decoy_id = f"decoy/lib{suffix}::{name}#function"

    assert [reference.target_id for reference in state.symbol_references] == [target_id]
    reference = state.symbol_references[0]
    assert reference.status == "resolved"
    assert reference.target_id == target_id
    assert reference.target_file == f"lib{suffix}"

    assert [call.target_id for call in state.calls] == [target_id]
    call = state.calls[0]
    assert call.status == "resolved"
    assert call.caller_id == caller_id
    assert call.target_id == target_id

    relationship_edges = {
        (edge.from_id, edge.to_id, edge.type, edge.resolution)
        for edge in state.edges
        if edge.type in {"references", "calls"}
    }
    assert relationship_edges == {
        (caller_id, target_id, "references", "import-resolved"),
        (caller_id, target_id, "calls", "import-resolved"),
    }
    assert decoy_id not in {
        endpoint
        for edge in state.edges
        for endpoint in (edge.from_id, edge.to_id)
    }
