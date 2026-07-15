from loci.parser.languages import get_language_spec, EXTENSION_MAP


def test_import_node_types_match_supported_language_grammars():
    assert get_language_spec("python").import_node_types == (
        "import_statement",
        "import_from_statement",
    )
    assert get_language_spec("typescript").import_node_types == (
        "import_statement",
        "export_statement",
    )
    assert get_language_spec("javascript").import_node_types == (
        "import_statement",
        "export_statement",
    )
    assert get_language_spec("go").import_node_types == ("import_spec",)
    assert get_language_spec("rust").import_node_types == ("use_declaration",)


def test_unused_tsx_spec_does_not_duplicate_import_configuration():
    assert EXTENSION_MAP[".tsx"] == "typescript"
    assert get_language_spec("tsx").import_node_types == ()


def test_python_spec_exists():
    spec = get_language_spec("python")
    assert spec is not None
    assert spec.ts_language == "python"


def test_typescript_spec_exists():
    spec = get_language_spec("typescript")
    assert spec is not None
    assert spec.ts_language == "typescript"


def test_unknown_language_returns_none():
    assert get_language_spec("cobol") is None


def test_extension_map_python():
    assert EXTENSION_MAP[".py"] == "python"


def test_extension_map_typescript():
    assert EXTENSION_MAP[".ts"] == "typescript"
    assert EXTENSION_MAP[".tsx"] == "typescript"


def test_python_spec_has_function_node():
    spec = get_language_spec("python")
    assert "function_definition" in spec.symbol_node_types
    assert spec.symbol_node_types["function_definition"] == "function"


def test_python_spec_has_class_node():
    spec = get_language_spec("python")
    assert "class_definition" in spec.symbol_node_types
    assert spec.symbol_node_types["class_definition"] == "class"


def test_typescript_spec_has_function_node():
    spec = get_language_spec("typescript")
    assert "function_declaration" in spec.symbol_node_types


def test_python_docstring_strategy():
    spec = get_language_spec("python")
    assert spec.docstring_strategy == "next_sibling_string"


def test_typescript_docstring_strategy():
    spec = get_language_spec("typescript")
    assert spec.docstring_strategy == "preceding_comment"
