from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
from tree_sitter import Parser
from tree_sitter_language_pack import SupportedLanguage, get_language

from loci.parser._binding_context import collect_syntax_context
from loci.parser.imports import (
    ImportExtractionBatch,
    ImportExtractionError,
    extract_import_batch,
)
from loci.parser.references import extract_reference_batch
from loci.parser.reference_models import (
    MAX_LOCAL_EXPORTS_PER_FILE,
    MAX_REFERENCE_PATH_SEGMENTS,
    MAX_REFERENCE_RESOLUTION_CANDIDATES,
    ImportBinding,
    RawLocalExport,
    RawSymbolReference,
    ReferenceExtractionBatch,
)


SOURCE_HASH = "a" * 64


def _extract_batch(
    tmp_path: Path,
    *,
    name: str,
    source: str,
    language: str,
) -> ImportExtractionBatch:
    path = tmp_path / name
    path.write_text(source, encoding="utf-8")
    return extract_import_batch(
        path,
        source_file=f"src/{name}",
        language=language,
        source_hash=SOURCE_HASH,
    )


@pytest.mark.parametrize(
    ("name", "source", "language", "tree_sitter_language"),
    [
        (
            "consumer.py",
            "from model import Thing\ndef run():\n    Thing()\n",
            "python",
            "python",
        ),
        (
            "consumer.js",
            'import {Thing} from "./model.js";\nfunction run() { Thing(); }\n',
            "javascript",
            "javascript",
        ),
        (
            "consumer.ts",
            'import {Thing} from "./model";\nfunction run(): void { Thing(); }\n',
            "typescript",
            "typescript",
        ),
        (
            "consumer.go",
            'package consumer\nimport model "example/model"\nfunc run() { model.Thing() }\n',
            "go",
            "go",
        ),
        (
            "consumer.rs",
            "use crate::model::Thing;\nfn run() { Thing(); }\n",
            "rust",
            "rust",
        ),
    ],
)
def test_explicit_shared_syntax_context_preserves_reference_extraction(
    tmp_path: Path,
    name: str,
    source: str,
    language: str,
    tree_sitter_language: SupportedLanguage,
):
    batch = _extract_batch(
        tmp_path,
        name=name,
        source=source,
        language=language,
    )
    encoded = source.encode()
    root = Parser(get_language(tree_sitter_language)).parse(encoded).root_node
    context = collect_syntax_context(root, encoded, language)

    explicit = extract_reference_batch(
        root,
        encoded,
        source_file=f"src/{name}",
        language=language,
        source_hash=SOURCE_HASH,
        imports=batch.imports,
        context=context,
    )

    assert isinstance(context.local_bindings, tuple)
    assert isinstance(context.excluded_subtrees, frozenset)
    assert isinstance(context.unsupported_import_starts, frozenset)
    assert explicit.exports == batch.exports
    assert explicit.references == batch.references
    assert explicit.references


def _binding(**overrides) -> ImportBinding:
    values = {
        "local_name": "Alias",
        "imported_name": "Thing",
        "exported_name": None,
        "kind": "symbol",
        "type_only": False,
        "module_level": True,
        "declaration_start_byte": 0,
        "scope_start_byte": 0,
        "scope_end_byte": 80,
        "import_line": 1,
        "import_text": "from model import Thing as Alias",
        "import_specifier": "model",
    }
    values.update(overrides)
    return ImportBinding(**values)


def _export(**overrides) -> RawLocalExport:
    values = {
        "source_file": "src/model.py",
        "language": "python",
        "line": 3,
        "text": "class Thing: ...",
        "local_name": "Thing",
        "exported_name": "Thing",
        "type_only": False,
        "definition_start_byte": 10,
        "definition_end_byte": 26,
        "source_hash": SOURCE_HASH,
    }
    values.update(overrides)
    return RawLocalExport(**values)


def _reference(**overrides) -> RawSymbolReference:
    values = {
        "source_file": "src/use.py",
        "language": "python",
        "line": 4,
        "column": 12,
        "start_byte": 45,
        "end_byte": 50,
        "text": "Alias",
        "path": ("Alias",),
        "candidate_bindings": (_binding(),),
        "binding_state": "definite",
        "source_hash": SOURCE_HASH,
    }
    values.update(overrides)
    return RawSymbolReference(**values)


@pytest.mark.parametrize(
    "record",
    [
        _binding(),
        _export(),
        _reference(),
        ReferenceExtractionBatch(exports=(_export(),), references=(_reference(),)),
    ],
)
def test_reference_parser_models_round_trip_strictly(record):
    serialized = record.to_dict()

    assert type(record).from_dict(serialized) == record

    missing = dict(serialized)
    missing.pop(next(iter(missing)))
    with pytest.raises(ValueError, match="fields"):
        type(record).from_dict(missing)

    unknown = dict(serialized)
    unknown["unknown"] = True
    with pytest.raises(ValueError, match="fields"):
        type(record).from_dict(unknown)


@pytest.mark.parametrize(
    "overrides",
    [
        {"local_name": ""},
        {"kind": "guess"},
        {"kind": []},
        {"type_only": 1},
        {"declaration_start_byte": -1},
        {"scope_start_byte": 2, "declaration_start_byte": 1},
        {"scope_end_byte": 0},
        {"import_line": 0},
        {"import_text": ""},
        {"import_specifier": ""},
        {
            "kind": "side_effect",
            "local_name": "Alias",
            "imported_name": None,
        },
        {"kind": "glob", "local_name": "Alias", "imported_name": None},
    ],
)
def test_import_binding_rejects_malformed_or_impossible_states(overrides):
    with pytest.raises(ValueError):
        _binding(**overrides)


@pytest.mark.parametrize(
    "overrides",
    [
        {"source_file": "/tmp/model.py"},
        {"source_file": "src/../model.py"},
        {"line": 0},
        {"type_only": "false"},
        {"definition_start_byte": 10, "definition_end_byte": None},
        {"definition_start_byte": 26, "definition_end_byte": 10},
        {"source_hash": "not-a-sha256"},
    ],
)
def test_raw_local_export_rejects_malformed_fields(overrides):
    with pytest.raises(ValueError):
        _export(**overrides)


@pytest.mark.parametrize(
    "overrides",
    [
        {"column": 0},
        {"start_byte": 50, "end_byte": 45},
        {"path": ()},
        {"path": ("Alias", "")},
        {"path": ("segment",) * (MAX_REFERENCE_PATH_SEGMENTS + 1)},
        {"candidate_bindings": ()},
        {"binding_state": "definite", "candidate_bindings": (_binding(), _binding())},
        {"binding_state": "ambiguous", "candidate_bindings": (_binding(),)},
        {"binding_state": "guess"},
        {"binding_state": []},
        {
            "candidate_bindings": (
                _binding(
                    kind="glob",
                    local_name=None,
                    imported_name=None,
                ),
            )
        },
        {
            "binding_state": "deferred",
            "candidate_bindings": (
                _binding(
                    kind="namespace",
                    local_name=None,
                    imported_name=None,
                ),
            ),
        },
        {
            "candidate_bindings": (
                replace(_binding(), scope_start_byte=51, declaration_start_byte=51),
            )
        },
        {"source_hash": "0" * 63},
    ],
)
def test_raw_symbol_reference_rejects_malformed_or_impossible_states(overrides):
    with pytest.raises(ValueError):
        _reference(**overrides)


def test_reference_parser_models_enforce_collection_bounds():
    binding = _binding()
    with pytest.raises(ValueError, match="candidate"):
        _reference(
            binding_state="ambiguous",
            candidate_bindings=(binding,) * (MAX_REFERENCE_RESOLUTION_CANDIDATES + 1),
        )

    export = _export()
    with pytest.raises(ValueError, match="exports"):
        ReferenceExtractionBatch(
            exports=(export,) * (MAX_LOCAL_EXPORTS_PER_FILE + 1),
            references=(),
        )


def test_reference_parser_models_require_immutable_tuple_collections():
    with pytest.raises(ValueError, match="path"):
        _reference(path=["Alias"])

    with pytest.raises(ValueError, match="candidate"):
        _reference(candidate_bindings=[_binding()])

    with pytest.raises(ValueError, match="exports"):
        ReferenceExtractionBatch(exports=[_export()], references=())


def test_go_default_package_reference_is_the_only_deferred_binding_state():
    binding = _binding(
        kind="namespace",
        local_name=None,
        imported_name=None,
    )

    reference = _reference(
        source_file="cmd/app/main.go",
        language="go",
        path=("store", "Thing"),
        text="store.Thing",
        candidate_bindings=(binding,),
        binding_state="deferred",
    )

    assert RawSymbolReference.from_dict(reference.to_dict()) == reference


def test_reference_parser_model_unknown_non_string_field_fails_closed():
    serialized = _binding().to_dict()
    serialized[1] = True

    with pytest.raises(ValueError, match="fields"):
        ImportBinding.from_dict(serialized)


def test_extracts_python_exports_maximal_paths_and_function_shadowing(
    tmp_path: Path,
):
    source = (
        "from .model import Thing as Alias\n"
        "import pkg.mod\n"
        "class Public:\n"
        "    pass\n"
        "def run():\n"
        "    π = 1; Alias()\n"
        "    pkg.mod.Thing()\n"
        "def shadow(Alias):\n"
        "    Alias()\n"
    )

    batch = _extract_batch(
        tmp_path,
        name="consumer.py",
        source=source,
        language="python",
    )

    assert [
        (item.local_name, item.exported_name, item.definition_start_byte)
        for item in batch.exports
    ] == [
        ("Alias", "Alias", None),
        ("Public", "Public", source.encode().index(b"class Public")),
        ("run", "run", source.encode().index(b"def run")),
        ("shadow", "shadow", source.encode().index(b"def shadow")),
    ]
    assert [
        (
            item.line,
            item.column,
            item.text,
            item.path,
            item.binding_state,
            tuple(binding.local_name for binding in item.candidate_bindings),
        )
        for item in batch.references
    ] == [
        (
            6,
            len("    π = 1; ".encode()) + 1,
            "Alias",
            ("Alias",),
            "definite",
            ("Alias",),
        ),
        (7, 5, "pkg.mod.Thing", ("pkg", "mod", "Thing"), "definite", ("pkg",)),
        (9, 5, "Alias", ("Alias",), "shadowed", ("Alias",)),
    ]
    assert batch.references[0].start_byte == source.encode().index(b"Alias()")
    assert batch.references[0].end_byte == batch.references[0].start_byte + len(b"Alias")


def test_extracts_typescript_exports_type_references_and_unsupported_computed_members(
    tmp_path: Path,
):
    source = (
        'import {type Shape as S, Thing as Alias} from "./m";\n'
        'import * as ns from "./n";\n'
        "export class Public {}\n"
        "export type Kind = string;\n"
        "const local = 1;\n"
        "export {local as renamed};\n"
        'export {Thing as Remote} from "./r";\n'
        "function run(value: S) { Alias(value); ns.Member; }\n"
        "function shadow(Alias: S) { Alias(); }\n"
        "const computed = ns[key];\n"
    )

    batch = _extract_batch(
        tmp_path,
        name="consumer.ts",
        source=source,
        language="typescript",
    )

    assert [
        (item.local_name, item.exported_name, item.type_only)
        for item in batch.exports
    ] == [
        ("Public", "Public", False),
        ("Kind", "Kind", True),
        ("local", "renamed", False),
    ]
    assert [
        (
            item.text,
            item.path,
            item.binding_state,
            item.candidate_bindings[0].type_only,
        )
        for item in batch.references
    ] == [
        ("S", ("S",), "definite", True),
        ("Alias", ("Alias",), "definite", False),
        ("ns.Member", ("ns", "Member"), "definite", False),
        ("S", ("S",), "definite", True),
        ("Alias", ("Alias",), "shadowed", False),
        ("ns[key]", ("ns",), "unsupported", False),
    ]


def test_extracts_javascript_named_default_and_reexport_surface_evidence(
    tmp_path: Path,
):
    batch = _extract_batch(
        tmp_path,
        name="surface.ts",
        source=(
            "export default function Factory() {}\n"
            'export {default as Named, type Shape as PublicShape} from "./model.js";\n'
            'export * from "./star.js";\n'
            'export * as model from "./model.js";\n'
        ),
        language="typescript",
    )
    anonymous = _extract_batch(
        tmp_path,
        name="anonymous.js",
        source="export default function () {}\n",
        language="javascript",
    )

    assert [
        (item.local_name, item.exported_name, item.type_only)
        for item in batch.exports
    ] == [("Factory", "default", False)]
    assert [
        [
            (binding.kind, binding.imported_name, binding.exported_name, binding.type_only)
            for binding in raw.bindings
        ]
        for raw in batch.imports
    ] == [
        [
            ("symbol", "default", "Named", False),
            ("symbol", "Shape", "PublicShape", True),
        ],
        [("glob", None, None, False)],
        [("namespace", None, "model", False)],
    ]
    assert anonymous.exports == ()


def test_extracts_imported_component_references_from_tsx(tmp_path: Path):
    batch = _extract_batch(
        tmp_path,
        name="component.tsx",
        source=(
            'import {Widget as View} from "./view";\n'
            "export function App() { return <View />; }\n"
        ),
        language="typescript",
    )

    assert [item.exported_name for item in batch.exports] == ["App"]
    assert [(item.text, item.path, item.binding_state) for item in batch.references] == [
        ("View", ("View",), "definite")
    ]


def test_extracts_go_exports_explicit_and_deferred_package_references(
    tmp_path: Path,
):
    source = (
        "package consumer\n"
        'import store "example/store"\n'
        'import "example/default"\n'
        "const Public = 1\n"
        "type Record struct{}\n"
        "func Use() { store.Record{}; defaultpkg.Value }\n"
        "func shadow(store int) { store.Value }\n"
    )

    batch = _extract_batch(
        tmp_path,
        name="consumer.go",
        source=source,
        language="go",
    )

    assert [(item.local_name, item.exported_name) for item in batch.exports] == [
        ("Public", "Public"),
        ("Record", "Record"),
        ("Use", "Use"),
    ]
    assert [
        (
            item.text,
            item.path,
            item.binding_state,
            tuple(binding.local_name for binding in item.candidate_bindings),
        )
        for item in batch.references
    ] == [
        ("store.Record", ("store", "Record"), "definite", ("store",)),
        ("defaultpkg.Value", ("defaultpkg", "Value"), "deferred", (None,)),
        ("store.Value", ("store", "Value"), "shadowed", ("store",)),
    ]


def test_extracts_rust_exports_paths_and_declaration_order_shadowing(
    tmp_path: Path,
):
    source = (
        "use crate::model::Thing as Alias;\n"
        "use crate::module;\n"
        "pub struct Public;\n"
        "struct Private;\n"
        "pub use crate::other::Remote;\n"
        "fn use_it() { Alias; module::Member; }\n"
        "fn shadow(Alias: i32) { Alias; }\n"
        "fn ordered() { Alias; let Alias = 1; Alias; }\n"
    )

    batch = _extract_batch(
        tmp_path,
        name="consumer.rs",
        source=source,
        language="rust",
    )

    assert [(item.local_name, item.exported_name) for item in batch.exports] == [
        ("Public", "Public"),
        ("Private", "Private"),
        ("use_it", "use_it"),
        ("shadow", "shadow"),
        ("ordered", "ordered"),
    ]
    assert [
        (item.text, item.path, item.binding_state)
        for item in batch.references
    ] == [
        ("Alias", ("Alias",), "definite"),
        ("module::Member", ("module", "Member"), "definite"),
        ("Alias", ("Alias",), "shadowed"),
        ("Alias", ("Alias",), "definite"),
        ("Alias", ("Alias",), "shadowed"),
    ]


def test_reference_extraction_bounds_fail_the_whole_import_batch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr("loci.parser.references.MAX_SYMBOL_REFERENCES_PER_FILE", 1)

    with pytest.raises(ImportExtractionError, match="reference extraction failed"):
        _extract_batch(
            tmp_path,
            name="consumer.py",
            source="from model import Thing\nThing()\nThing()\n",
            language="python",
        )


def test_python_scope_order_distinguishes_function_class_and_nested_imports(
    tmp_path: Path,
):
    source = (
        "from first import Alias\n"
        "class Example:\n"
        "    Alias\n"
        "    Alias = 1\n"
        "    Alias\n"
        "    def method(self):\n"
        "        Alias\n"
        "def assigned():\n"
        "    Alias\n"
        "    Alias = 1\n"
        "    Alias\n"
        "def nested():\n"
        "    Alias\n"
        "    from second import Alias\n"
        "    Alias\n"
    )

    batch = _extract_batch(
        tmp_path,
        name="scopes.py",
        source=source,
        language="python",
    )

    assert [item.binding_state for item in batch.references] == [
        "definite",
        "shadowed",
        "definite",
        "shadowed",
        "shadowed",
        "shadowed",
        "definite",
    ]
    assert [
        item.candidate_bindings[0].import_specifier for item in batch.references[-2:]
    ] == ["first", "second"]


def test_python_parameter_annotations_remain_reference_sites(tmp_path: Path):
    batch = _extract_batch(
        tmp_path,
        name="annotations.py",
        source="from model import Kind\ndef build(value: Kind):\n    return Kind()\n",
        language="python",
    )

    assert [(item.text, item.binding_state) for item in batch.references] == [
        ("Kind", "definite"),
        ("Kind", "definite"),
    ]


def test_python_exports_preserve_source_order_and_import_evidence(tmp_path: Path):
    batch = _extract_batch(
        tmp_path,
        name="exports.py",
        source=(
            "class First: pass\n"
            "from model import Later\n"
            "class Final: pass\n"
        ),
        language="python",
    )

    assert [item.exported_name for item in batch.exports] == [
        "First",
        "Later",
        "Final",
    ]
    assert batch.exports[1].text == "from model import Later"


def test_python_decorated_export_span_matches_the_indexed_symbol(tmp_path: Path):
    source = "@decorator\ndef Exported():\n    pass\n"

    batch = _extract_batch(
        tmp_path,
        name="decorated.py",
        source=source,
        language="python",
    )

    assert [
        (item.exported_name, item.definition_start_byte, item.definition_end_byte)
        for item in batch.exports
    ] == [("Exported", 0, len(source.encode().rstrip(b"\n")))]


def test_python_definition_body_does_not_resolve_its_name_to_an_old_import(
    tmp_path: Path,
):
    batch = _extract_batch(
        tmp_path,
        name="recursive.py",
        source=(
            "from model import Alias\n"
            "def Alias():\n"
            "    return Alias()\n"
        ),
        language="python",
    )

    assert [(item.text, item.binding_state) for item in batch.references] == [
        ("Alias", "shadowed")
    ]


def test_python_loop_context_catch_pattern_and_delete_bindings_fail_closed(
    tmp_path: Path,
):
    batch = _extract_batch(
        tmp_path,
        name="bindings.py",
        source=(
            "from model import Alias\n"
            "def loop(items):\n"
            "    Alias\n"
            "    for Alias in items: Alias\n"
            "def context(manager):\n"
            "    Alias\n"
            "    with manager as Alias: Alias\n"
            "def handler():\n"
            "    Alias\n"
            "    try: pass\n"
            "    except Error as Alias: Alias\n"
            "def pattern(value):\n"
            "    Alias\n"
            "    match value:\n"
            "        case Alias: Alias\n"
            "def remove():\n"
            "    Alias\n"
            "    del Alias\n"
            "    Alias\n"
        ),
        language="python",
    )

    assert len(batch.references) == 10
    assert {item.binding_state for item in batch.references} == {"shadowed"}


def test_python_future_and_conditional_imports_never_become_definite_references(
    tmp_path: Path,
):
    batch = _extract_batch(
        tmp_path,
        name="conditional.py",
        source=(
            "from __future__ import annotations\n"
            "if enabled:\n"
            "    from model import Alias\n"
            "Alias\n"
            "annotations\n"
        ),
        language="python",
    )

    assert batch.exports == ()
    assert [(item.text, item.binding_state) for item in batch.references] == [
        ("Alias", "unsupported")
    ]


def test_python_class_import_does_not_leak_into_method_scope(tmp_path: Path):
    batch = _extract_batch(
        tmp_path,
        name="class_scope.py",
        source=(
            "from outer import Alias\n"
            "class Example:\n"
            "    from inner import Alias\n"
            "    Alias\n"
            "    def method(self):\n"
            "        return Alias\n"
        ),
        language="python",
    )

    assert [
        item.candidate_bindings[0].import_specifier for item in batch.references
    ] == ["inner", "outer"]


def test_javascript_lexical_binding_shadows_before_and_after_declaration(
    tmp_path: Path,
):
    batch = _extract_batch(
        tmp_path,
        name="scopes.js",
        source=(
            'import {Alias} from "./model";\n'
            "function run() { Alias; let Alias = 1; Alias; }\n"
        ),
        language="javascript",
    )

    assert [item.binding_state for item in batch.references] == [
        "shadowed",
        "shadowed",
    ]


def test_go_short_declaration_and_rust_let_take_effect_in_source_order(
    tmp_path: Path,
):
    go_batch = _extract_batch(
        tmp_path,
        name="scopes.go",
        source=(
            "package consumer\n"
            'import store "example/store"\n'
            "func run() { store.Before; store := 1; store.After }\n"
        ),
        language="go",
    )
    rust_batch = _extract_batch(
        tmp_path,
        name="scopes.rs",
        source=(
            "use crate::model::Alias;\n"
            "fn run() { Alias; let Alias = 1; Alias; }\n"
        ),
        language="rust",
    )

    assert [item.binding_state for item in go_batch.references] == [
        "definite",
        "shadowed",
    ]
    assert [item.binding_state for item in rust_batch.references] == [
        "definite",
        "shadowed",
    ]


def test_nested_rust_use_binding_wins_only_inside_its_block(tmp_path: Path):
    batch = _extract_batch(
        tmp_path,
        name="nested.rs",
        source=(
            "use crate::outer::Thing;\n"
            "fn run() { use crate::inner::Thing; Thing; }\n"
            "fn other() { Thing; }\n"
        ),
        language="rust",
    )

    assert [
        item.candidate_bindings[0].import_specifier for item in batch.references
    ] == ["crate::inner::Thing", "crate::outer::Thing"]


def test_rust_macro_reference_is_never_definite(tmp_path: Path):
    batch = _extract_batch(
        tmp_path,
        name="macro.rs",
        source="use crate::Alias;\nfn run() { Alias!(); }\n",
        language="rust",
    )

    assert [(item.text, item.path, item.binding_state) for item in batch.references] == [
        ("Alias!()", ("Alias",), "unsupported")
    ]


def test_import_and_reference_extraction_share_one_parser_invocation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    import tree_sitter

    real_parser = tree_sitter.Parser
    parse_calls = 0

    class CountingParser:
        def __init__(self, language):
            self._parser = real_parser(language)

        def parse(self, source):
            nonlocal parse_calls
            parse_calls += 1
            return self._parser.parse(source)

    monkeypatch.setattr(tree_sitter, "Parser", CountingParser)

    batch = _extract_batch(
        tmp_path,
        name="single_parse.py",
        source="from model import Thing\nThing()\n",
        language="python",
    )

    assert parse_calls == 1
    assert len(batch.imports) == 1
    assert len(batch.references) == 1


@pytest.mark.parametrize(
    ("module_name", "limit_name", "source", "language"),
    [
        (
            "loci.parser._reference_exports",
            "MAX_LOCAL_EXPORTS_PER_FILE",
            "class One: pass\nclass Two: pass\n",
            "python",
        ),
        (
            "loci.parser.references",
            "MAX_REFERENCE_RESOLUTION_CANDIDATES",
            'package p\nimport "one"\nimport "two"\nfunc run() { pkg.Value }\n',
            "go",
        ),
    ],
)
def test_reference_export_and_candidate_limits_fail_atomically(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    module_name: str,
    limit_name: str,
    source: str,
    language: str,
):
    monkeypatch.setattr(f"{module_name}.{limit_name}", 1)

    with pytest.raises(ImportExtractionError, match="reference extraction failed"):
        _extract_batch(
            tmp_path,
            name=f"limited.{ 'go' if language == 'go' else 'py' }",
            source=source,
            language=language,
        )


def test_reference_path_segment_limit_fails_atomically(tmp_path: Path):
    path = ".".join(["pkg", *(f"part{index}" for index in range(MAX_REFERENCE_PATH_SEGMENTS))])

    with pytest.raises(ImportExtractionError, match="reference extraction failed"):
        _extract_batch(
            tmp_path,
            name="deep.py",
            source=f"import pkg\n{path}\n",
            language="python",
        )
