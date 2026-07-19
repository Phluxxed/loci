from __future__ import annotations

from pathlib import Path

import pytest

from loci.parser.imports import (
    GoPackageDeclaration,
    ImportExtractionBatch,
    ImportExtractionError,
    MAX_RUST_USE_LEAVES_PER_DECLARATION,
    RawImport,
    RustImportContext,
    extract_import_batch,
    extract_imports,
)


SOURCE_HASH = "a" * 64


def _extract(
    tmp_path: Path,
    *,
    name: str,
    source: str,
    language: str,
    source_file: str | None = None,
) -> list[RawImport]:
    path = tmp_path / name
    path.write_text(source, encoding="utf-8")
    return extract_imports(
        path,
        source_file=source_file or f"src/{name}",
        language=language,
        source_hash=SOURCE_HASH,
    )


def _extract_batch(
    tmp_path: Path,
    *,
    name: str,
    source: str,
    language: str,
    source_file: str | None = None,
) -> ImportExtractionBatch:
    path = tmp_path / name
    path.write_text(source, encoding="utf-8")
    return extract_import_batch(
        path,
        source_file=source_file or f"src/{name}",
        language=language,
        source_hash=SOURCE_HASH,
    )


def test_extracts_each_python_import_target_with_exact_evidence(tmp_path: Path):
    imports = _extract(
        tmp_path,
        name="consumer.py",
        language="python",
        source=(
            "import alpha, beta as local_beta\n"
            "from ..pkg import One, Two as LocalTwo\n"
            "from . import *\n"
        ),
    )

    assert imports == [
        RawImport(
            source_file="src/consumer.py",
            language="python",
            line=1,
            text="import alpha, beta as local_beta",
            specifier="alpha",
            imported_name=None,
            type_only=False,
            is_reexport=False,
            source_hash=SOURCE_HASH,
        ),
        RawImport(
            source_file="src/consumer.py",
            language="python",
            line=1,
            text="import alpha, beta as local_beta",
            specifier="beta",
            imported_name=None,
            type_only=False,
            is_reexport=False,
            source_hash=SOURCE_HASH,
        ),
        RawImport(
            source_file="src/consumer.py",
            language="python",
            line=2,
            text="from ..pkg import One, Two as LocalTwo",
            specifier="..pkg",
            imported_name="One",
            type_only=False,
            is_reexport=False,
            source_hash=SOURCE_HASH,
        ),
        RawImport(
            source_file="src/consumer.py",
            language="python",
            line=2,
            text="from ..pkg import One, Two as LocalTwo",
            specifier="..pkg",
            imported_name="Two",
            type_only=False,
            is_reexport=False,
            source_hash=SOURCE_HASH,
        ),
        RawImport(
            source_file="src/consumer.py",
            language="python",
            line=3,
            text="from . import *",
            specifier=".",
            imported_name=None,
            type_only=False,
            is_reexport=False,
            source_hash=SOURCE_HASH,
        ),
    ]


def test_classifies_typescript_type_imports_and_reexports(tmp_path: Path):
    imports = _extract(
        tmp_path,
        name="consumer.ts",
        language="typescript",
        source=(
            'import type {Shape} from "./types";\n'
            'import {type OnlyMetadata} from "./metadata";\n'
            'import {type Metadata, run} from "./mixed";\n'
            'export type {PublicShape} from "./public-types";\n'
            'export {value as publicValue} from "./runtime";\n'
            "export const localOnly = 1;\n"
        ),
    )

    assert [
        (item.line, item.text, item.specifier, item.type_only, item.is_reexport)
        for item in imports
    ] == [
        (1, 'import type {Shape} from "./types";', "./types", True, False),
        (2, 'import {type OnlyMetadata} from "./metadata";', "./metadata", True, False),
        (3, 'import {type Metadata, run} from "./mixed";', "./mixed", False, False),
        (4, 'export type {PublicShape} from "./public-types";', "./public-types", True, True),
        (5, 'export {value as publicValue} from "./runtime";', "./runtime", False, True),
    ]
    assert all(item.source_file == "src/consumer.ts" for item in imports)
    assert all(item.language == "typescript" for item in imports)
    assert all(item.imported_name is None for item in imports)
    assert all(item.source_hash == SOURCE_HASH for item in imports)


@pytest.mark.parametrize(
    ("name", "language"),
    [
        ("consumer.ts", "typescript"),
        ("consumer.tsx", "typescript"),
        ("consumer.mts", "typescript"),
        ("consumer.cts", "typescript"),
        ("consumer.js", "javascript"),
        ("consumer.jsx", "javascript"),
        ("consumer.mjs", "javascript"),
        ("consumer.cjs", "javascript"),
    ],
)
def test_extracts_every_javascript_and_typescript_source_extension(
    tmp_path: Path,
    name: str,
    language: str,
):
    imports = _extract(
        tmp_path,
        name=name,
        language=language,
        source='import {value} from "./runtime";\n',
    )

    assert len(imports) == 1
    assert imports[0].specifier == "./runtime"
    assert imports[0].line == 1
    assert imports[0].text == 'import {value} from "./runtime";'
    assert imports[0].type_only is False
    assert imports[0].is_reexport is False


def test_extracts_grouped_go_import_specs_recursively(tmp_path: Path):
    imports = _extract(
        tmp_path,
        name="main.go",
        language="go",
        source=(
            "package main\n\n"
            "import (\n"
            '    "fmt"\n'
            '    alias "example.com/project/pkg"\n'
            '    _ "example.com/project/sideeffects"\n'
            ")\n"
        ),
    )

    assert [
        (item.line, item.text, item.specifier, item.imported_name)
        for item in imports
    ] == [
        (4, '"fmt"', "fmt", None),
        (5, 'alias "example.com/project/pkg"', "example.com/project/pkg", None),
        (6, '_ "example.com/project/sideeffects"', "example.com/project/sideeffects", None),
    ]
    assert all(item.source_hash == SOURCE_HASH for item in imports)


def test_go_batch_extracts_imports_and_exact_package_clause_from_one_parse(
    tmp_path: Path,
):
    batch = _extract_batch(
        tmp_path,
        name="reader.go",
        language="go",
        source=(
            "// generated\n"
            "package store\n\n"
            "import (\n"
            '    "fmt"\n'
            '    "example.com/project/model"\n'
            ")\n"
        ),
    )

    assert batch.go_package == GoPackageDeclaration(name="store", line=2)
    assert [item.specifier for item in batch.imports] == [
        "fmt",
        "example.com/project/model",
    ]
    assert extract_imports(
        tmp_path / "reader.go",
        source_file="src/reader.go",
        language="go",
        source_hash=SOURCE_HASH,
    ) == list(batch.imports)


def test_import_batch_has_no_go_package_for_other_languages(tmp_path: Path):
    batch = _extract_batch(
        tmp_path,
        name="consumer.py",
        language="python",
        source="import package\n",
    )

    assert batch.go_package is None
    assert [item.specifier for item in batch.imports] == ["package"]


def test_go_batch_returns_no_declaration_for_comment_only_source(tmp_path: Path):
    batch = _extract_batch(
        tmp_path,
        name="empty.go",
        language="go",
        source="// no package declaration\n",
    )

    assert batch == ImportExtractionBatch(imports=(), go_package=None)


def test_expands_rust_use_trees_into_strict_dependency_observations(tmp_path: Path):
    imports = _extract(
        tmp_path,
        name="lib.rs",
        language="rust",
        source=(
            "use std::collections::HashMap;\n"
            "use crate::{alpha, beta::{Thing as Alias, self, *}, empty::{}};\n"
            "use crate::trailing::self;\n"
        ),
    )

    expected_context = RustImportContext(
        kind="use",
        lexical_module_path=(),
        visibility="private",
        module_level=True,
        configuration="unconditional",
    )
    assert [
        (item.line, item.specifier, item.imported_name, item.rust)
        for item in imports
    ] == [
        (1, "std::collections::HashMap", "HashMap", expected_context),
        (2, "crate::alpha", "alpha", expected_context),
        (2, "crate::beta::Thing", "Alias", expected_context),
        (2, "crate::beta", "beta", expected_context),
        (2, "crate::beta::*", None, expected_context),
        (3, "crate::trailing", "trailing", expected_context),
    ]
    assert all(item.type_only is False for item in imports)
    assert all(item.is_reexport is False for item in imports)
    assert all(item.source_hash == SOURCE_HASH for item in imports)


def test_expands_root_self_alias_and_glob_rust_use_forms(tmp_path: Path):
    imports = _extract(
        tmp_path,
        name="forms.rs",
        language="rust",
        source=(
            "use {alpha, beta as local_beta};\n"
            "use ::external::Thing;\n"
            "use self::local::*;\n"
            "use crate as root;\n"
            "use crate::aliased::self as local_parent;\n"
        ),
    )

    assert [(item.specifier, item.imported_name) for item in imports] == [
        ("alpha", "alpha"),
        ("beta", "local_beta"),
        ("::external::Thing", "Thing"),
        ("self::local::*", None),
        ("crate", "root"),
        ("crate::aliased", "local_parent"),
    ]


def test_non_rust_observations_keep_null_rust_context(tmp_path: Path):
    imports = _extract(
        tmp_path,
        name="consumer.py",
        language="python",
        source="import package\n",
    )

    assert len(imports) == 1
    assert imports[0].rust is None


def test_extracts_rust_extern_crates_modules_and_lexical_scope(tmp_path: Path):
    imports = _extract(
        tmp_path,
        name="scope.rs",
        language="rust",
        source=(
            "extern crate actual as local;\n"
            "extern crate self as current;\n"
            "pub extern crate public_crate;\n"
            "#[cfg(unix)]\n"
            "pub(crate) mod inline {\n"
            "    #[path = r#\"nested/other.rs\"#]\n"
            "    pub(in crate::inline) mod external;\n"
            "    pub(super) use super::Thing;\n"
            "    fn local() {\n"
            "        use crate::local::Value;\n"
            "        extern crate block_dep;\n"
            "    }\n"
            "}\n"
            "mod inline_without_dependencies {}\n"
        ),
    )

    assert [
        (
            item.specifier,
            item.imported_name,
            item.is_reexport,
            item.rust,
        )
        for item in imports
    ] == [
        (
            "actual",
            "local",
            False,
            RustImportContext(
                kind="extern_crate",
                lexical_module_path=(),
                visibility="private",
                module_level=True,
                configuration="unconditional",
            ),
        ),
        (
            "self",
            "current",
            False,
            RustImportContext(
                kind="extern_crate",
                lexical_module_path=(),
                visibility="private",
                module_level=True,
                configuration="unconditional",
            ),
        ),
        (
            "public_crate",
            "public_crate",
            True,
            RustImportContext(
                kind="extern_crate",
                lexical_module_path=(),
                visibility="pub",
                module_level=True,
                configuration="unconditional",
            ),
        ),
        (
            "inline",
            "inline",
            False,
            RustImportContext(
                kind="module",
                lexical_module_path=(),
                visibility="pub(crate)",
                module_level=True,
                configuration="conditional",
                inline=True,
            ),
        ),
        (
            "external",
            "external",
            False,
            RustImportContext(
                kind="module",
                lexical_module_path=("inline",),
                lexical_module_visibilities=("pub(crate)",),
                lexical_module_configurations=("conditional",),
                visibility="pub(in crate::inline)",
                module_level=True,
                configuration="unconditional",
                path_override="nested/other.rs",
            ),
        ),
        (
            "super::Thing",
            "Thing",
            True,
            RustImportContext(
                kind="use",
                lexical_module_path=("inline",),
                lexical_module_visibilities=("pub(crate)",),
                lexical_module_configurations=("conditional",),
                visibility="pub(super)",
                module_level=True,
                configuration="unconditional",
            ),
        ),
        (
            "crate::local::Value",
            "Value",
            False,
            RustImportContext(
                kind="use",
                lexical_module_path=("inline",),
                lexical_module_visibilities=("pub(crate)",),
                lexical_module_configurations=("conditional",),
                visibility="private",
                module_level=False,
                configuration="unconditional",
            ),
        ),
        (
            "block_dep",
            "block_dep",
            False,
            RustImportContext(
                kind="extern_crate",
                lexical_module_path=("inline",),
                lexical_module_visibilities=("pub(crate)",),
                lexical_module_configurations=("conditional",),
                visibility="private",
                module_level=False,
                configuration="unconditional",
            ),
        ),
        (
            "inline_without_dependencies",
            "inline_without_dependencies",
            False,
            RustImportContext(
                kind="module",
                lexical_module_path=(),
                visibility="private",
                module_level=True,
                configuration="unconditional",
                inline=True,
            ),
        ),
    ]


def test_normalizes_every_supported_rust_visibility(tmp_path: Path):
    imports = _extract(
        tmp_path,
        name="visibility.rs",
        language="rust",
        source=(
            "use crate::private;\n"
            "pub use crate::public;\n"
            "pub(crate) use crate::crate_visible;\n"
            "pub(self) use crate::self_visible;\n"
            "pub(super) use crate::super_visible;\n"
            "pub(in crate :: outer) use crate::restricted;\n"
        ),
    )

    assert [item.rust.visibility for item in imports if item.rust is not None] == [
        "private",
        "pub",
        "pub(crate)",
        "pub(self)",
        "pub(super)",
        "pub(in crate::outer)",
    ]
    assert [item.is_reexport for item in imports] == [
        False,
        True,
        True,
        True,
        True,
        True,
    ]


def test_classifies_direct_rust_configuration_and_module_path_attributes(
    tmp_path: Path,
):
    imports = _extract(
        tmp_path,
        name="configuration.rs",
        language="rust",
        source=(
            "#[cfg(feature = \"optional\")]\n"
            "use crate::conditional;\n"
            "#[cfg_attr(unix, path = \"unix.rs\")]\n"
            "#[cfg(unix)]\n"
            "mod selected;\n"
            "#[path = concat!(\"generated\", \".rs\")]\n"
            "mod generated;\n"
            "#[path = \"nested/literal.rs\"]\n"
            "mod literal;\n"
            "#[path = r###\"nested/raw.rs\"###]\n"
            "mod raw_literal;\n"
        ),
    )

    assert [
        (item.specifier, item.rust.configuration, item.rust.path_override)
        for item in imports
        if item.rust is not None
    ] == [
        ("crate::conditional", "conditional", None),
        ("selected", "unsupported", None),
        ("generated", "unsupported", None),
        ("literal", "unconditional", "nested/literal.rs"),
        ("raw_literal", "unconditional", "nested/raw.rs"),
    ]


def test_rejects_rust_use_leaf_explosion_at_the_declaration_bound(tmp_path: Path):
    at_limit = ", ".join(
        f"item_{index}" for index in range(MAX_RUST_USE_LEAVES_PER_DECLARATION)
    )
    imports = _extract(
        tmp_path,
        name="bounded.rs",
        language="rust",
        source=f"use crate::{{{at_limit}}};\n",
    )
    assert len(imports) == MAX_RUST_USE_LEAVES_PER_DECLARATION

    over_limit = f"{at_limit}, one_too_many"
    with pytest.raises(ImportExtractionError, match="exceeds leaf limit"):
        _extract(
            tmp_path,
            name="too_many.rs",
            language="rust",
            source=f"use crate::{{{over_limit}}};\n",
        )


def test_ignores_supported_dynamic_import_syntax(tmp_path: Path):
    assert _extract(
        tmp_path,
        name="dynamic.ts",
        language="typescript",
        source='const modulePromise = import("./dynamic");\n',
    ) == []


def test_rejects_malformed_source_instead_of_returning_partial_observations(tmp_path: Path):
    path = tmp_path / "broken.py"
    path.write_text("import valid\nfrom broken import\n", encoding="utf-8")

    with pytest.raises(ImportExtractionError, match="could not be parsed"):
        extract_imports(
            path,
            source_file="src/broken.py",
            language="python",
            source_hash=SOURCE_HASH,
        )


def test_rejects_languages_without_import_extraction_support(tmp_path: Path):
    path = tmp_path / "consumer.cob"
    path.write_text("COPY ACCOUNT.", encoding="utf-8")

    with pytest.raises(ImportExtractionError, match="unsupported language: cobol"):
        extract_imports(
            path,
            source_file="src/consumer.cob",
            language="cobol",
            source_hash=SOURCE_HASH,
        )
