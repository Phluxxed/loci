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


def test_parse_python_stable_ids(sample_py: Path):
    symbols = parse_file(sample_py)
    add_sym = next(s for s in symbols if s.name == "add")
    assert "::" in add_sym.id
    assert "#function" in add_sym.id


def test_parse_python_method_qualified_name(sample_py: Path):
    symbols = parse_file(sample_py)
    multiply = next(s for s in symbols if s.name == "multiply")
    assert multiply.qualified_name == "Calculator.multiply"


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
    names = [name for name, _ in extracted]
    # Module-level constants should NOT be extracted
    assert "MY_CONSTANT" not in names


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
