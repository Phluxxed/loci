import pytest
from pathlib import Path
from loci.parser.extractor import parse_file
from loci.parser.symbols import Symbol


@pytest.fixture
def sample_py(fixtures_dir: Path) -> Path:
    return fixtures_dir / "sample.py"


@pytest.fixture
def sample_ts(fixtures_dir: Path) -> Path:
    return fixtures_dir / "sample.ts"


# ── Python tests ──────────────────────────────────────────────────────────────

def test_parse_python_returns_symbols(sample_py: Path):
    symbols = parse_file(sample_py)
    assert len(symbols) > 0
    assert all(isinstance(s, Symbol) for s in symbols)


def test_parse_python_finds_function(sample_py: Path):
    symbols = parse_file(sample_py)
    names = [s.name for s in symbols]
    assert "add" in names


def test_parse_python_finds_class(sample_py: Path):
    symbols = parse_file(sample_py)
    kinds = {s.kind for s in symbols}
    assert "class" in kinds


def test_parse_python_finds_method(sample_py: Path):
    symbols = parse_file(sample_py)
    methods = [s for s in symbols if s.kind == "method"]
    assert len(methods) >= 2
    method_names = [s.name for s in methods]
    assert "multiply" in method_names


def test_parse_python_byte_offsets_valid(sample_py: Path):
    symbols = parse_file(sample_py)
    source = sample_py.read_bytes()
    for sym in symbols:
        assert sym.byte_offset >= 0
        assert sym.byte_length > 0
        assert sym.byte_offset + sym.byte_length <= len(source)


def test_parse_python_byte_offset_matches_source(sample_py: Path):
    symbols = parse_file(sample_py)
    source = sample_py.read_bytes()
    add_sym = next(s for s in symbols if s.name == "add")
    extracted = source[add_sym.byte_offset:add_sym.byte_offset + add_sym.byte_length].decode()
    assert "def add" in extracted


def test_parse_python_line_numbers(sample_py: Path):
    symbols = parse_file(sample_py)
    add_sym = next(s for s in symbols if s.name == "add")
    assert add_sym.line > 0
    assert add_sym.end_line >= add_sym.line


def test_parse_python_keywords(sample_py: Path):
    symbols = parse_file(sample_py)
    add_sym = next(s for s in symbols if s.name == "add")
    # "add" → single word, stays as keyword
    assert "add" in add_sym.keywords


def test_parse_python_stable_ids(sample_py: Path):
    symbols = parse_file(sample_py)
    add_sym = next(s for s in symbols if s.name == "add")
    assert "::" in add_sym.id
    assert "#function" in add_sym.id


def test_parse_python_method_qualified_name(sample_py: Path):
    symbols = parse_file(sample_py)
    multiply = next(s for s in symbols if s.name == "multiply")
    assert multiply.qualified_name == "Calculator.multiply"


@pytest.mark.parametrize(
    ("filename", "source", "expected_qualified_name"),
    [
        (
            "nested.py",
            "def outer():\n    def inner():\n        pass\n    inner()\n",
            "outer.inner",
        ),
        (
            "nested.js",
            "function outer() { function inner() {} inner(); }\n",
            "outer.inner",
        ),
        (
            "nested.ts",
            "function outer(): void { function inner(): void {} inner(); }\n",
            "outer.inner",
        ),
        (
            "nested.rs",
            "fn outer() { fn inner() {} inner(); }\n",
            "outer.inner",
        ),
        (
            "nested_method.py",
            (
                "class Runner:\n"
                "    def run(self):\n"
                "        def inner():\n"
                "            pass\n"
                "        inner()\n"
            ),
            "Runner.run.inner",
        ),
    ],
)
def test_parse_file_indexes_named_nested_functions_as_functions(
    tmp_path: Path,
    filename: str,
    source: str,
    expected_qualified_name: str,
):
    path = tmp_path / filename
    path.write_text(source, encoding="utf-8")

    nested = next(symbol for symbol in parse_file(path) if symbol.name == "inner")

    assert nested.kind == "function"
    assert nested.qualified_name == expected_qualified_name


def test_parse_python_docstring_extracted(sample_py: Path):
    symbols = parse_file(sample_py)
    add_sym = next(s for s in symbols if s.name == "add")
    assert "Add two numbers" in add_sym.docstring


def test_parse_python_signature_extracted(sample_py: Path):
    symbols = parse_file(sample_py)
    add_sym = next(s for s in symbols if s.name == "add")
    assert "add" in add_sym.signature
    assert "int" in add_sym.signature


def test_parse_unknown_extension_returns_empty(tmp_path: Path):
    f = tmp_path / "test.rb"
    f.write_text("def hello; end")
    assert parse_file(f) == []


def test_parse_python_no_duplicate_ids(sample_py: Path):
    symbols = parse_file(sample_py)
    ids = [s.id for s in symbols]
    assert len(ids) == len(set(ids))


# ── TypeScript tests ──────────────────────────────────────────────────────────

def test_parse_typescript_returns_symbols(sample_ts: Path):
    symbols = parse_file(sample_ts)
    assert len(symbols) > 0


def test_parse_typescript_finds_function(sample_ts: Path):
    symbols = parse_file(sample_ts)
    names = [s.name for s in symbols]
    assert "greet" in names


def test_parse_typescript_finds_class(sample_ts: Path):
    symbols = parse_file(sample_ts)
    classes = [s for s in symbols if s.kind == "class"]
    assert any(c.name == "User" for c in classes)


def test_parse_typescript_finds_method(sample_ts: Path):
    symbols = parse_file(sample_ts)
    methods = [s for s in symbols if s.kind == "method"]
    assert any(m.name == "getDisplayName" for m in methods)


def test_parse_typescript_docstring_extracted(sample_ts: Path):
    symbols = parse_file(sample_ts)
    greet = next(s for s in symbols if s.name == "greet")
    assert greet.docstring != ""


def test_parse_typescript_byte_offsets_valid(sample_ts: Path):
    symbols = parse_file(sample_ts)
    source = sample_ts.read_bytes()
    for sym in symbols:
        assert sym.byte_offset >= 0
        assert sym.byte_length > 0
        assert sym.byte_offset + sym.byte_length <= len(source)


def test_parse_typescript_no_duplicate_ids(sample_ts: Path):
    symbols = parse_file(sample_ts)
    ids = [s.id for s in symbols]
    assert len(ids) == len(set(ids))


@pytest.mark.parametrize(
    ("suffix", "language"),
    [
        (".ts", "typescript"),
        (".tsx", "typescript"),
        (".mts", "typescript"),
        (".cts", "typescript"),
        (".js", "javascript"),
        (".jsx", "javascript"),
        (".mjs", "javascript"),
        (".cjs", "javascript"),
    ],
)
def test_parse_javascript_typescript_extension_family(
    tmp_path: Path,
    suffix: str,
    language: str,
):
    source = tmp_path / f"module{suffix}"
    source.write_text("export function extensionFamily() { return 1; }\n")

    symbols = parse_file(source)

    assert any(symbol.name == "extensionFamily" for symbol in symbols)
    assert all(symbol.language == language for symbol in symbols)


# ── Ground-truth fixture tests ──────────────────────────────────────────────

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"

# (name, kind) pairs that MUST appear in sample.py
PYTHON_EXPECTED = [
    ("add", "function"),
    ("decorator", "function"),
    ("decorated_function", "function"),
    ("Calculator", "class"),
    ("multiply", "method"),
    ("divide", "method"),
    ("Outer", "class"),
    ("Inner", "class"),
    ("inner_method", "method"),
    ("MY_CONSTANT", "constant"),
]

# (name, kind) pairs that MUST appear in sample.ts
# Note: constructor omitted until confirmed working - add ("constructor", "method") once verified.
TS_EXPECTED = [
    ("greet", "function"),
    ("User", "class"),
    ("getDisplayName", "method"),
    ("UserId", "type"),
    ("UserRepository", "interface"),
]


def _extracted(fixture_name: str) -> list[tuple[str, str]]:
    path = FIXTURES_DIR / fixture_name
    symbols = parse_file(path)
    return [(s.name, s.kind) for s in symbols]


def test_python_fixture_ground_truth():
    extracted = _extracted("sample.py")
    for name, kind in PYTHON_EXPECTED:
        assert (name, kind) in extracted, (
            f"Expected ({name!r}, {kind!r}) in sample.py symbols, got: {extracted}"
        )


def test_python_fixture_no_spurious_symbols():
    extracted = _extracted("sample.py")
    kinds = {kind for _, kind in extracted}
    # Lowercase assignments inside functions should NOT become constants
    # (the walker doesn't recurse into function bodies)
    assert kinds <= {"function", "class", "method", "constant"}


def test_ts_fixture_ground_truth():
    extracted = _extracted("sample.ts")
    for name, kind in TS_EXPECTED:
        assert (name, kind) in extracted, (
            f"Expected ({name!r}, {kind!r}) in sample.ts symbols, got: {extracted}"
        )


def test_ts_fixture_no_spurious_symbols():
    extracted = _extracted("sample.ts")
    names = [name for name, _ in extracted]
    assert "helper" not in names  # arrow function const, should not be extracted


# ── Go ground-truth ─────────────────────────────────────────────────────────

GO_EXPECTED = [
    ("Greet", "function"),
    ("helper", "function"),
    ("Calculator", "type"),
    ("Add", "method"),
    ("Reset", "method"),
    ("Shape", "type"),
    ("Vector", "type"),
    ("PI", "constant"),
]


def test_go_fixture_ground_truth():
    extracted = _extracted("sample.go")
    for name, kind in GO_EXPECTED:
        assert (name, kind) in extracted, (
            f"Expected ({name!r}, {kind!r}) in sample.go symbols, got: {extracted}"
        )


def test_go_fixture_no_spurious_symbols():
    extracted = _extracted("sample.go")
    kinds = {kind for _, kind in extracted}
    assert kinds <= {"function", "method", "type", "constant"}


# ── Rust ground-truth ────────────────────────────────────────────────────────

RUST_EXPECTED = [
    ("add", "function"),
    ("Counter", "struct"),
    ("Counter", "impl"),
    ("new", "method"),
    ("increment", "method"),
    ("value", "method"),
    ("Describable", "trait"),
    ("Color", "enum"),
    ("MAX_COUNT", "constant"),
]


def test_rust_fixture_ground_truth():
    extracted = _extracted("sample.rs")
    for name, kind in RUST_EXPECTED:
        assert (name, kind) in extracted, (
            f"Expected ({name!r}, {kind!r}) in sample.rs symbols, got: {extracted}"
        )


def test_rust_fixture_derive_decorator():
    path = FIXTURES_DIR / "sample.rs"
    symbols = parse_file(path)
    counter = next(s for s in symbols if s.name == "Counter" and s.kind == "struct")
    assert "derive" in counter.decorators


def test_rust_items_record_lexical_visibility_scope_and_configuration(
    tmp_path: Path,
):
    path = tmp_path / "items.rs"
    path.write_text(
        """
#[cfg(feature = "outer")]
mod outer {
    pub mod inner {
        pub fn public_item() {}
        pub(crate) fn crate_item() {}
        pub(super) fn parent_item() {}
        pub(self) fn self_item() {}
        pub(in crate::outer) fn restricted_item() {}
        fn private_item() {}
    }
}
""".lstrip(),
        encoding="utf-8",
    )

    items = {symbol.name: symbol for symbol in parse_file(path)}

    expected = {
        "public_item": ("pub", None),
        "crate_item": ("pub(crate)", []),
        "parent_item": ("pub(super)", ["outer"]),
        "self_item": ("pub(self)", ["outer", "inner"]),
        "restricted_item": ("pub(in crate::outer)", ["outer"]),
        "private_item": ("private", ["outer", "inner"]),
    }
    for name, (visibility, scope) in expected.items():
        assert items[name].metadata == {
            "loci": {
                "rust_item": {
                    "lexical_module_path": ["outer", "inner"],
                    "visibility": visibility,
                    "visibility_scope": scope,
                    "configuration": "declared_possible",
                }
            }
        }


def test_rust_external_module_items_keep_resolvable_relative_visibility(
    tmp_path: Path,
):
    path = tmp_path / "child.rs"
    path.write_text(
        """
pub(super) fn parent_item() {}
pub(in crate::outer) fn restricted_item() {}
pub(self) fn self_item() {}
fn private_item() {}
""".lstrip(),
        encoding="utf-8",
    )

    items = {symbol.name: symbol for symbol in parse_file(path)}

    assert items["parent_item"].metadata["loci"]["rust_item"] == {
        "lexical_module_path": [],
        "visibility": "pub(super)",
        "visibility_scope": [],
        "configuration": "unconditional",
    }
    assert items["restricted_item"].metadata["loci"]["rust_item"] == {
        "lexical_module_path": [],
        "visibility": "pub(in crate::outer)",
        "visibility_scope": ["outer"],
        "configuration": "unconditional",
    }
    assert items["self_item"].metadata["loci"]["rust_item"][
        "visibility_scope"
    ] == []
    assert items["private_item"].metadata["loci"]["rust_item"][
        "visibility_scope"
    ] == []


def test_rust_fixture_no_spurious_symbols():
    extracted = _extracted("sample.rs")
    kinds = {kind for _, kind in extracted}
    assert kinds <= {"function", "method", "struct", "enum", "trait", "impl", "constant"}


# ── JavaScript ground-truth ──────────────────────────────────────────────────

JS_EXPECTED = [
    ("greet", "function"),
    ("User", "class"),
    ("getDisplayName", "method"),
    ("UserRepository", "class"),
    ("findById", "method"),
]


def test_js_fixture_ground_truth():
    extracted = _extracted("sample.js")
    for name, kind in JS_EXPECTED:
        assert (name, kind) in extracted, (
            f"Expected ({name!r}, {kind!r}) in sample.js symbols, got: {extracted}"
        )


def test_js_fixture_no_spurious_symbols():
    extracted = _extracted("sample.js")
    names = [name for name, _ in extracted]
    assert "helper" not in names  # arrow function const, should not be extracted
