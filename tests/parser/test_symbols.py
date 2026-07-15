from loci.parser.symbols import (
    FILE_NODE_QUALIFIED_NAME,
    Symbol,
    make_file_symbol,
    make_symbol_id,
)


def test_make_symbol_id_function():
    sid = make_symbol_id("src/auth.py", "login", "function")
    assert sid == "src/auth.py::login#function"


def test_make_symbol_id_method():
    sid = make_symbol_id("src/auth.py", "User.login", "method")
    assert sid == "src/auth.py::User.login#method"


def test_make_file_symbol_has_stable_zero_width_shape():
    symbol = make_file_symbol(
        "src/loci/service.py",
        language="python",
        content_hash="a" * 64,
    )

    assert FILE_NODE_QUALIFIED_NAME == "__file__"
    assert symbol.to_dict() == {
        "id": "src/loci/service.py::__file__#file",
        "name": "service.py",
        "qualified_name": "__file__",
        "kind": "file",
        "language": "python",
        "file_path": "src/loci/service.py",
        "byte_offset": 0,
        "byte_length": 0,
        "signature": "src/loci/service.py",
        "docstring": "",
        "summary": "",
        "content_hash": "a" * 64,
        "decorators": [],
        "keywords": ["loci", "service"],
        "metadata": {"loci": {"file_node": True}},
        "line": 1,
        "end_line": 1,
    }


def test_symbol_id_field_matches():
    sym = Symbol(
        id=make_symbol_id("src/auth.py", "login", "function"),
        name="login",
        qualified_name="login",
        kind="function",
        language="python",
        file_path="src/auth.py",
        byte_offset=100,
        byte_length=200,
    )
    assert sym.id == "src/auth.py::login#function"
    assert sym.summary == ""
    assert sym.docstring == ""
    assert sym.signature == ""
    assert sym.metadata == {}


def test_symbol_to_dict():
    sym = Symbol(
        id="src/auth.py::login#function",
        name="login",
        qualified_name="login",
        kind="function",
        language="python",
        file_path="src/auth.py",
        byte_offset=100,
        byte_length=200,
        signature="def login(username: str) -> bool",
        docstring="Authenticate a user.",
        summary="",
        metadata={"frontmatter": {"tags": ["auth"]}},
    )
    d = sym.to_dict()
    assert d["id"] == "src/auth.py::login#function"
    assert d["byte_offset"] == 100
    assert d["signature"] == "def login(username: str) -> bool"
    assert d["metadata"] == {"frontmatter": {"tags": ["auth"]}}


def test_symbol_from_dict():
    data = {
        "id": "src/auth.py::login#function",
        "name": "login",
        "qualified_name": "login",
        "kind": "function",
        "language": "python",
        "file_path": "src/auth.py",
        "byte_offset": 100,
        "byte_length": 200,
        "signature": "",
        "docstring": "",
        "summary": "",
    }
    sym = Symbol.from_dict(data)
    assert sym.id == "src/auth.py::login#function"
    assert sym.byte_offset == 100
    assert sym.metadata == {}


def test_symbol_from_dict_loads_metadata():
    data = {
        "id": "docs/page.md::Page#section",
        "name": "Page",
        "qualified_name": "Page",
        "kind": "section",
        "language": "markdown",
        "file_path": "docs/page.md",
        "byte_offset": 0,
        "byte_length": 200,
        "metadata": {
            "frontmatter": {
                "type": "ideas",
                "tags": ["retrieval-governance"],
            }
        },
    }

    sym = Symbol.from_dict(data)

    assert sym.metadata == {
        "frontmatter": {
            "type": "ideas",
            "tags": ["retrieval-governance"],
        }
    }
