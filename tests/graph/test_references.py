from __future__ import annotations

import hashlib
from dataclasses import replace
from pathlib import Path

import pytest

from loci.graph import _python_references
from loci.graph.contracts import GraphContractError
from loci.graph.imports import resolve_imports
from loci.graph.javascript_modules import (
    build_javascript_resolution_index,
    load_javascript_module_context,
)
from loci.graph.references import (
    build_reference_resolver_index,
    resolve_symbol_references,
)
from loci.parser.extractor import parse_file
from loci.parser.imports import ImportExtractionBatch, extract_import_batch
from loci.parser.symbols import Symbol, make_file_symbol, make_symbol_id


def _resolve_python_tree(
    tmp_path: Path,
    files: dict[str, str],
) -> tuple[list, list[Symbol], list[ImportExtractionBatch]]:
    symbols: list[Symbol] = []
    batches: list[ImportExtractionBatch] = []
    file_nodes: dict[str, Symbol] = {}
    for relative_path, source in files.items():
        path = tmp_path / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding="utf-8")
        source_hash = hashlib.sha256(source.encode()).hexdigest()
        file_node = make_file_symbol(
            relative_path,
            language="python",
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
                language="python",
                source_hash=source_hash,
            )
        )

    imports = resolve_imports(
        [raw for batch in batches for raw in batch.imports],
        file_nodes=file_nodes,
    )
    exports = [export for batch in batches for export in batch.exports]
    observations = [reference for batch in batches for reference in batch.references]
    index = build_reference_resolver_index(symbols, imports, exports)
    return (
        resolve_symbol_references(observations, imports=imports, index=index),
        symbols,
        batches,
    )


def _javascript_language(relative_path: str) -> str:
    return (
        "typescript"
        if Path(relative_path).suffix in {".ts", ".tsx", ".mts", ".cts"}
        else "javascript"
    )


def _resolve_javascript_tree(
    tmp_path: Path,
    files: dict[str, str],
    *,
    controls: dict[str, str] | None = None,
) -> tuple[list, list[Symbol], list[ImportExtractionBatch]]:
    symbols: list[Symbol] = []
    batches: list[ImportExtractionBatch] = []
    file_nodes: dict[str, Symbol] = {}
    for relative_path, source in files.items():
        path = tmp_path / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding="utf-8")
        source_hash = hashlib.sha256(source.encode()).hexdigest()
        language = _javascript_language(relative_path)
        file_node = make_file_symbol(
            relative_path,
            language=language,
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
                language=language,
                source_hash=source_hash,
            )
        )

    control_paths: list[Path] = []
    for relative_path, source in (controls or {}).items():
        path = tmp_path / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding="utf-8")
        control_paths.append(path)
    loaded = load_javascript_module_context(tmp_path, control_paths)
    assert loaded.problems == ()
    javascript_index = build_javascript_resolution_index(
        loaded.context,
        file_nodes=file_nodes,
    )
    assert javascript_index.problems == ()
    imports = resolve_imports(
        [raw for batch in batches for raw in batch.imports],
        file_nodes=file_nodes,
        javascript_modules=javascript_index.index,
    )
    exports = [export for batch in batches for export in batch.exports]
    observations = [reference for batch in batches for reference in batch.references]
    index = build_reference_resolver_index(symbols, imports, exports)
    return (
        resolve_symbol_references(observations, imports=imports, index=index),
        symbols,
        batches,
    )


def test_resolves_javascript_named_namespace_default_and_type_only_bindings(
    tmp_path: Path,
):
    records, _, _ = _resolve_javascript_tree(
        tmp_path,
        {
            "src/model.ts": (
                "export class Thing {}\n"
                "export interface Shape {}\n"
                "export default function Factory() {}\n"
            ),
            "src/wrong.ts": "export class Thing {}\n",
            "src/use.ts": (
                'import Factory, {Thing as Alias, type Shape} from "./model.js";\n'
                'import * as model from "./model.js";\n'
                "function run(value: Shape) { Alias; model.Thing; Factory; }\n"
            ),
        },
    )

    selected = [record for record in records if record.raw.source_file == "src/use.ts"]

    assert [record.raw.text for record in selected] == [
        "Shape",
        "Alias",
        "model.Thing",
        "Factory",
    ]
    assert [record.target_id for record in selected] == [
        "src/model.ts::Shape#interface",
        "src/model.ts::Thing#class",
        "src/model.ts::Thing#class",
        "src/model.ts::Factory#function",
    ]
    assert [record.resolution_basis for record in selected] == [
        "direct_binding",
        "direct_binding",
        "qualified_member",
        "direct_binding",
    ]
    assert [record.binding.type_only for record in selected if record.binding] == [
        True,
        False,
        False,
        False,
    ]
    assert {record.status for record in selected} == {"resolved"}


def test_resolves_python_direct_alias_and_qualified_members_inside_exact_endpoint(
    tmp_path: Path,
):
    records, _, _ = _resolve_python_tree(
        tmp_path,
        {
            "pkg/__init__.py": "",
            "pkg/model.py": "class Thing:\n    pass\n",
            "wrong.py": "class Thing:\n    pass\n",
            "use.py": (
                "from pkg.model import Thing as Alias\n"
                "import pkg.model as model\n"
                "import pkg.model\n"
                "\n"
                "def run():\n"
                "    return Alias(), model.Thing(), pkg.model.Thing()\n"
            ),
        },
    )

    use_records = [record for record in records if record.raw.source_file == "use.py"]

    assert [record.raw.path for record in use_records] == [
        ("Alias",),
        ("model", "Thing"),
        ("pkg", "model", "Thing"),
    ]
    assert {record.status for record in use_records} == {"resolved"}
    assert {record.target_id for record in use_records} == {
        "pkg/model.py::Thing#class"
    }
    assert [record.resolution_basis for record in use_records] == [
        "direct_binding",
        "qualified_member",
        "qualified_member",
    ]
    assert {record.source_id for record in use_records} == {
        "use.py::run#function"
    }


def test_python_from_imported_submodule_resolves_member_inside_submodule(
    tmp_path: Path,
):
    records, _, _ = _resolve_python_tree(
        tmp_path,
        {
            "pkg/__init__.py": "",
            "pkg/model.py": "class Thing:\n    pass\n",
            "pkg/relative_use.py": (
                "from . import model as relative_model\n"
                "def build():\n"
                "    return relative_model.Thing()\n"
            ),
            "use.py": (
                "from pkg import model as absolute_model\n"
                "def build():\n"
                "    return absolute_model.Thing()\n"
            ),
        },
    )

    selected = [
        record
        for record in records
        if record.raw.source_file in {"pkg/relative_use.py", "use.py"}
    ]

    assert len(selected) == 2
    assert {record.status for record in selected} == {"resolved"}
    assert {record.target_id for record in selected} == {
        "pkg/model.py::Thing#class"
    }
    assert {record.resolution_basis for record in selected} == {
        "qualified_member"
    }


def test_source_owner_uses_smallest_symbol_and_module_code_uses_file_node(
    tmp_path: Path,
):
    records, _, _ = _resolve_python_tree(
        tmp_path,
        {
            "model.py": "class Thing:\n    pass\n",
            "use.py": (
                "from model import Thing\n"
                "Thing()\n"
                "\n"
                "class Factory:\n"
                "    def make(self):\n"
                "        return Thing()\n"
            ),
        },
    )

    assert [(record.source_id, record.source_kind) for record in records] == [
        ("use.py::__file__#file", "file"),
        ("use.py::Factory.make#method", "method"),
    ]


def test_equal_span_source_ambiguity_falls_back_to_file_without_guessing(
    tmp_path: Path,
):
    _, symbols, batches = _resolve_python_tree(
        tmp_path,
        {
            "model.py": "class Thing:\n    pass\n",
            "use.py": (
                "from model import Thing\n"
                "def run():\n"
                "    return Thing()\n"
            ),
        },
    )
    run = next(symbol for symbol in symbols if symbol.id == "use.py::run#function")
    duplicate = replace(
        run,
        id="use.py::run_alias#function",
        name="run_alias",
        qualified_name="run_alias",
    )
    file_nodes = {
        symbol.file_path: symbol for symbol in symbols if symbol.kind == "file"
    }
    imports = resolve_imports(
        [raw for batch in batches for raw in batch.imports],
        file_nodes=file_nodes,
    )
    exports = [export for batch in batches for export in batch.exports]
    observations = [reference for batch in batches for reference in batch.references]
    index = build_reference_resolver_index([*symbols, duplicate], imports, exports)

    record = resolve_symbol_references(observations, imports=imports, index=index)[0]

    assert record.status == "unresolved"
    assert record.unresolved_reason == "ambiguous_source"
    assert record.source_id == "use.py::__file__#file"
    assert record.source_kind == "file"
    assert record.target_id is None


def test_python_failures_are_retained_without_off_endpoint_name_matching(
    tmp_path: Path,
):
    records, _, _ = _resolve_python_tree(
        tmp_path,
        {
            "model.py": "class Thing:\n    pass\n",
            "wrong.py": "class Missing:\n    pass\n",
            "use.py": (
                "from model import Missing\n"
                "from nowhere import External\n"
                "from model import Thing\n"
                "\n"
                "def shadowed(Thing):\n"
                "    return Thing()\n"
                "\n"
                "def dynamic(name):\n"
                "    return Thing[name]\n"
                "\n"
                "def missing():\n"
                "    return Missing()\n"
                "\n"
                "def external():\n"
                "    return External()\n"
            ),
        },
    )

    outcomes = {
        record.raw.text: (
            record.status,
            record.unresolved_reason,
            record.import_unresolved_reason,
        )
        for record in records
        if record.raw.source_file == "use.py"
    }

    assert outcomes == {
        "Thing": ("unresolved", "binding_shadowed", None),
        "Thing[name]": ("unresolved", "unsupported_reference", None),
        "Missing": ("unresolved", "target_not_indexed", None),
        "External": ("unresolved", "import_unresolved", "not_indexed"),
    }


def test_python_named_reexport_chain_resolves_with_complete_support(
    tmp_path: Path,
):
    records, _, _ = _resolve_python_tree(
        tmp_path,
        {
            "pkg/__init__.py": "from .model import Thing\n",
            "pkg/model.py": "class Thing:\n    pass\n",
            "use.py": (
                "from pkg import Thing\n"
                "def run():\n"
                "    return Thing()\n"
            ),
        },
    )

    record = next(record for record in records if record.raw.source_file == "use.py")

    assert record.status == "resolved"
    assert record.target_id == "pkg/model.py::Thing#class"
    assert record.resolution_basis == "reexport_chain"
    assert [support.kind for support in record.support] == [
        "import_binding",
        "reexport",
        "definition",
    ]
    assert [support.file for support in record.support] == [
        "use.py",
        "pkg/__init__.py",
        "pkg/model.py",
    ]


def test_python_reexport_cycle_converges_only_when_it_has_one_exact_target(
    tmp_path: Path,
):
    records, _, _ = _resolve_python_tree(
        tmp_path,
        {
            "pkg/__init__.py": "",
            "pkg/a.py": "from .b import Thing\n",
            "pkg/b.py": "from .a import Thing\nclass Thing:\n    pass\n",
            "use.py": (
                "from pkg.a import Thing\n"
                "def run():\n"
                "    return Thing()\n"
            ),
        },
    )

    record = next(record for record in records if record.raw.source_file == "use.py")

    assert record.status == "resolved"
    assert record.target_id == "pkg/b.py::Thing#class"
    assert record.resolution_basis == "reexport_chain"


def test_python_unseeded_reexport_cycle_stays_ambiguous(tmp_path: Path):
    records, _, _ = _resolve_python_tree(
        tmp_path,
        {
            "pkg/__init__.py": "",
            "pkg/a.py": "from .b import Thing\n",
            "pkg/b.py": "from .a import Thing\n",
            "use.py": (
                "from pkg.a import Thing\n"
                "def run():\n"
                "    return Thing()\n"
            ),
        },
    )

    record = next(record for record in records if record.raw.source_file == "use.py")

    assert record.status == "unresolved"
    assert record.unresolved_reason == "ambiguous_target"
    assert record.target_id is None


def test_python_ambiguous_and_star_reexports_never_select_a_target(
    tmp_path: Path,
):
    records, _, _ = _resolve_python_tree(
        tmp_path,
        {
            "pkg/__init__.py": (
                "from .left import Thing\n"
                "from .right import Thing\n"
                "from .stars import *\n"
            ),
            "pkg/left.py": "class Thing:\n    pass\n",
            "pkg/right.py": "class Thing:\n    pass\n",
            "pkg/stars.py": "class StarThing:\n    pass\n",
            "use.py": (
                "from pkg import Thing, StarThing\n"
                "def run():\n"
                "    return Thing(), StarThing()\n"
            ),
        },
    )

    outcomes = {
        record.raw.path[0]: (record.unresolved_reason, record.target_id)
        for record in records
        if record.raw.source_file == "use.py"
    }

    assert outcomes == {
        "Thing": ("ambiguous_target", None),
        "StarThing": ("target_not_indexed", None),
    }


def test_python_reexport_pass_limit_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(_python_references, "MAX_REFERENCE_REEXPORT_PASSES", 1)

    records, _, _ = _resolve_python_tree(
        tmp_path,
        {
            "pkg/__init__.py": "",
            "pkg/a.py": "from .b import Thing\n",
            "pkg/b.py": "from .c import Thing\n",
            "pkg/c.py": "class Thing:\n    pass\n",
            "use.py": (
                "from pkg.a import Thing\n"
                "def run():\n"
                "    return Thing()\n"
            ),
        },
    )

    record = next(record for record in records if record.raw.source_file == "use.py")

    assert record.status == "unresolved"
    assert record.unresolved_reason == "ambiguous_target"
    assert record.target_id is None


def test_reference_index_rejects_stale_python_export_evidence(tmp_path: Path):
    _, symbols, batches = _resolve_python_tree(
        tmp_path,
        {
            "model.py": "class Thing:\n    pass\n",
            "use.py": "from model import Thing\nThing()\n",
        },
    )
    file_nodes = {
        symbol.file_path: symbol for symbol in symbols if symbol.kind == "file"
    }
    imports = resolve_imports(
        [raw for batch in batches for raw in batch.imports],
        file_nodes=file_nodes,
    )
    exports = [export for batch in batches for export in batch.exports]
    stale = replace(exports[0], source_hash="f" * 64)

    with pytest.raises(GraphContractError, match="stale"):
        build_reference_resolver_index(symbols, imports, [stale, *exports[1:]])
