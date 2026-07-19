import pytest
import json
import time
import time as time_module
from dataclasses import replace
from pathlib import Path
from loci.graph.contracts import (
    GRAPH_STATE_SCHEMA_VERSION,
    GraphContractError,
    GraphEdge,
    GraphEvidence,
)
from loci.graph.imports import ImportRecord
from loci.graph.state import GraphIndexState
from loci.parser.imports import RawImport
from loci.parser.symbols import Symbol, make_file_symbol
from loci.storage.index_store import (
    EXTRACTOR_VERSION,
    INDEX_SCHEMA_VERSION,
    IndexStore,
    index_versions_current,
)


@pytest.fixture
def store(tmp_path: Path) -> IndexStore:
    return IndexStore(base_dir=tmp_path / ".codeindex")


@pytest.fixture
def sample_symbols() -> list[Symbol]:
    return [
        Symbol(
            id="src/auth.py::login#function",
            name="login",
            qualified_name="login",
            kind="function",
            language="python",
            file_path="src/auth.py",
            byte_offset=10,
            byte_length=100,
            signature="def login(username: str) -> bool",
            docstring="Authenticate a user.",
            summary="",
        ),
        Symbol(
            id="src/auth.py::User#class",
            name="User",
            qualified_name="User",
            kind="class",
            language="python",
            file_path="src/auth.py",
            byte_offset=120,
            byte_length=200,
        ),
    ]


def _markdown_symbols() -> list[Symbol]:
    parent_id = "guide.md::Guide#section"
    child_id = "guide.md::Guide > Install#section"
    return [
        Symbol(
            id=parent_id,
            name="Guide",
            qualified_name="Guide",
            kind="section",
            language="markdown",
            file_path="guide.md",
            byte_offset=0,
            byte_length=40,
            content_hash="a" * 64,
            line=1,
            end_line=7,
            metadata={"markdown": {"parent_id": "", "root_id": parent_id}},
        ),
        Symbol(
            id=child_id,
            name="Install",
            qualified_name="Guide > Install",
            kind="section",
            language="markdown",
            file_path="guide.md",
            byte_offset=10,
            byte_length=30,
            content_hash="b" * 64,
            line=5,
            end_line=7,
            metadata={"markdown": {"parent_id": parent_id, "root_id": parent_id}},
        ),
    ]


def _contains_edge(**overrides) -> GraphEdge:
    values = {
        "from_id": "guide.md::Guide#section",
        "to_id": "guide.md::Guide > Install#section",
        "type": "contains",
        "directed": True,
        "namespace": "loci",
        "resolution": "exact",
        "evidence": GraphEvidence(
            file="guide.md",
            line=5,
            content_hash="b" * 64,
        ),
    }
    values.update(overrides)
    return GraphEdge(**values)


def _import_graph(
    source_hash: str,
    target_hash: str,
) -> tuple[list[Symbol], GraphEdge, ImportRecord, GraphIndexState]:
    source = make_file_symbol(
        "src/source.py",
        language="python",
        content_hash=source_hash,
    )
    target = make_file_symbol(
        "src/target.py",
        language="python",
        content_hash=target_hash,
    )
    raw = RawImport(
        source_file="src/source.py",
        language="python",
        line=1,
        text="from target import value",
        specifier="target",
        imported_name="value",
        type_only=False,
        is_reexport=False,
        source_hash=source_hash,
    )
    record = ImportRecord(
        raw=raw,
        source_id=source.id,
        target_file="src/target.py",
        target_package=None,
        target_crate=None,
        target_kind="file",
        target_id=target.id,
        status="resolved",
        unresolved_reason=None,
    )
    edge = GraphEdge(
        from_id=source.id,
        to_id=target.id,
        type="imports",
        directed=True,
        namespace="loci",
        resolution="import-resolved",
        evidence=GraphEvidence(
            file="src/source.py",
            line=1,
            content_hash=source_hash,
        ),
    )
    graph_state = replace(
        GraphIndexState.empty(edges=[edge]),
        imports=(record,),
    )
    return [source, target], edge, record, graph_state


def test_store_write_creates_index_file(store: IndexStore, tmp_path: Path, sample_symbols):
    source_path = tmp_path / "repo"
    source_path.mkdir()
    (source_path / "src").mkdir()
    (source_path / "src" / "auth.py").write_text("def login(): pass\n\nclass User: pass")

    store.write(source_path, sample_symbols, file_hashes={"src/auth.py": "abc123"})

    index_file = store._index_path(source_path)
    assert index_file.exists()


def test_store_write_load_roundtrip(store: IndexStore, tmp_path: Path, sample_symbols):
    source_path = tmp_path / "repo"
    source_path.mkdir()
    (source_path / "src").mkdir()
    (source_path / "src" / "auth.py").write_text("def login(): pass\n\nclass User: pass")

    store.write(source_path, sample_symbols, file_hashes={"src/auth.py": "abc123"})
    loaded = store.load(source_path)

    assert loaded is not None
    assert len(loaded["symbols"]) == 2
    assert loaded["symbols"][0]["id"] == "src/auth.py::login#function"
    assert loaded["file_hashes"]["src/auth.py"] == "abc123"


def test_store_write_load_round_trips_graph_envelope(store: IndexStore, tmp_path: Path):
    source_path = tmp_path / "repo"
    source_path.mkdir()
    (source_path / "guide.md").write_text("# Guide\n\n## Install\n\nBody.\n")
    symbols = _markdown_symbols()
    edge = _contains_edge()

    store.write(
        source_path,
        symbols,
        file_hashes={"guide.md": "abc123"},
        graph_state=GraphIndexState.empty(edges=[edge]),
    )
    loaded = store.load(source_path)

    assert loaded is not None
    assert loaded["graph"]["schema_version"] == GRAPH_STATE_SCHEMA_VERSION
    assert loaded["graph"]["edges"] == [edge.to_dict()]
    assert store.get_graph_state(source_path) == GraphIndexState.empty(edges=[edge])
    assert store.get_graph_edges(source_path) == [edge]


def test_store_rejects_invalid_graph_endpoint(store: IndexStore, tmp_path: Path):
    source_path = tmp_path / "repo"
    source_path.mkdir()
    (source_path / "guide.md").write_text("# Guide\n")
    symbols = _markdown_symbols()[:1]

    with pytest.raises(GraphContractError) as exc_info:
        store.write(
            source_path,
            symbols,
            file_hashes={"guide.md": "abc123"},
            graph_state=GraphIndexState.empty(edges=[_contains_edge()]),
        )

    assert exc_info.value.code == "GRAPH_ENDPOINT_NOT_FOUND"
    assert not store._index_path(source_path).exists()


def test_store_rejects_invalid_graph_evidence(store: IndexStore, tmp_path: Path):
    source_path = tmp_path / "repo"
    source_path.mkdir()
    (source_path / "guide.md").write_text("# Guide\n\n## Install\n")
    invalid_edge = _contains_edge(evidence=GraphEvidence(
        file="guide.md",
        line=5,
        content_hash="c" * 64,
    ))

    with pytest.raises(GraphContractError) as exc_info:
        store.write(
            source_path,
            _markdown_symbols(),
            file_hashes={"guide.md": "abc123"},
            graph_state=GraphIndexState.empty(edges=[invalid_edge]),
        )

    assert exc_info.value.code == "GRAPH_EVIDENCE_INVALID"
    assert not store._index_path(source_path).exists()


def test_store_write_load_round_trips_valid_import_edge(
    store: IndexStore,
    tmp_path: Path,
):
    source_path = tmp_path / "repo"
    (source_path / "src").mkdir(parents=True)
    source_file = source_path / "src" / "source.py"
    target_file = source_path / "src" / "target.py"
    source_file.write_text("from target import value\n")
    target_file.write_text("value = 1\n")
    source_hash = store.hash_file(source_file)
    target_hash = store.hash_file(target_file)
    symbols, edge, record, graph_state = _import_graph(source_hash, target_hash)

    store.write(
        source_path,
        symbols,
        file_hashes={
            "src/source.py": source_hash,
            "src/target.py": target_hash,
        },
        graph_state=graph_state,
    )

    loaded = store.get_graph_state(source_path)
    assert loaded.edges == (edge,)
    assert loaded.imports == (record,)


def test_store_rejects_import_edge_without_matching_target_record(
    store: IndexStore,
    tmp_path: Path,
):
    source_path = tmp_path / "repo"
    (source_path / "src").mkdir(parents=True)
    source_file = source_path / "src" / "source.py"
    target_file = source_path / "src" / "target.py"
    source_file.write_text("from target import value\n")
    target_file.write_text("value = 1\n")
    source_hash = store.hash_file(source_file)
    target_hash = store.hash_file(target_file)
    symbols, _, record, graph_state = _import_graph(source_hash, target_hash)
    corrupt_state = replace(
        graph_state,
        imports=(replace(record, target_id="src/other.py::__file__#file"),),
    )

    with pytest.raises(GraphContractError) as exc_info:
        store.write(
            source_path,
            symbols,
            file_hashes={
                "src/source.py": source_hash,
                "src/target.py": target_hash,
            },
            graph_state=corrupt_state,
        )

    assert exc_info.value.code == "GRAPH_EVIDENCE_INVALID"
    assert exc_info.value.details["field"] == "import_record"
    assert not store._index_path(source_path).exists()


def test_store_rejects_extension_namespace_using_reserved_import_type(
    store: IndexStore,
    tmp_path: Path,
):
    source_path = tmp_path / "repo"
    (source_path / "src").mkdir(parents=True)
    source_file = source_path / "src" / "source.py"
    target_file = source_path / "src" / "target.py"
    source_file.write_text("from target import value\n")
    target_file.write_text("value = 1\n")
    source_hash = store.hash_file(source_file)
    target_hash = store.hash_file(target_file)
    symbols, edge, _, graph_state = _import_graph(source_hash, target_hash)
    reserved_edge = replace(
        edge,
        namespace="llm-wiki",
        resolution="declared",
    )
    corrupt_state = replace(graph_state, edges=(reserved_edge,))

    with pytest.raises(GraphContractError) as exc_info:
        store.write(
            source_path,
            symbols,
            file_hashes={
                "src/source.py": source_hash,
                "src/target.py": target_hash,
            },
            graph_state=corrupt_state,
        )

    assert exc_info.value.code == "GRAPH_EDGE_TYPE_UNSUPPORTED"
    assert exc_info.value.details["namespace"] == "llm-wiki"
    assert not store._index_path(source_path).exists()


def test_store_writes_empty_graph_for_repo_without_edges(
    store: IndexStore,
    tmp_path: Path,
    sample_symbols,
):
    source_path = tmp_path / "repo"
    source_path.mkdir()
    (source_path / "src").mkdir()
    (source_path / "src" / "auth.py").write_text("def login(): pass\n")

    store.write(source_path, sample_symbols, file_hashes={})
    loaded = store.load(source_path)

    assert loaded is not None
    assert loaded["graph"] == GraphIndexState.empty().to_dict()


def test_store_load_returns_none_if_missing(store: IndexStore, tmp_path: Path):
    assert store.load(tmp_path / "nonexistent") is None


def test_store_file_hash(store: IndexStore, tmp_path: Path):
    f = tmp_path / "sample.py"
    f.write_text("def hello(): pass")
    h1 = store.hash_file(f)
    h2 = store.hash_file(f)
    assert h1 == h2
    assert len(h1) == 64  # SHA-256 hex

    f.write_text("def hello(): return 1")
    h3 = store.hash_file(f)
    assert h1 != h3


def test_store_mirrors_source(store: IndexStore, tmp_path: Path, sample_symbols):
    source_path = tmp_path / "repo"
    source_path.mkdir()
    (source_path / "src").mkdir()
    (source_path / "src" / "auth.py").write_text("def login(): pass")

    store.write(source_path, sample_symbols, file_hashes={})

    mirror = store._sources_dir(source_path) / "src" / "auth.py"
    assert mirror.exists()
    assert "login" in mirror.read_text()


def test_store_atomic_write(store: IndexStore, tmp_path: Path, sample_symbols):
    source_path = tmp_path / "repo"
    source_path.mkdir()
    (source_path / "src").mkdir()
    (source_path / "src" / "auth.py").write_text("def login(): pass")

    store.write(source_path, sample_symbols, file_hashes={})
    index_file = store._index_path(source_path)
    # Verify it's valid JSON (not partial)
    data = json.loads(index_file.read_text())
    assert "symbols" in data


def test_store_write_persists_index_versions(store: IndexStore, tmp_path: Path, sample_symbols):
    source_path = tmp_path / "repo"
    source_path.mkdir()
    (source_path / "src").mkdir()
    (source_path / "src" / "auth.py").write_text("def login(): pass")

    store.write(source_path, sample_symbols, file_hashes={})

    data = json.loads(store._index_path(source_path).read_text())
    assert data["schema_version"] == INDEX_SCHEMA_VERSION
    assert data["extractor_version"] == EXTRACTOR_VERSION


def test_index_versions_rejects_old_extractor_version():
    assert EXTRACTOR_VERSION == 9
    assert index_versions_current({
        "schema_version": INDEX_SCHEMA_VERSION,
        "extractor_version": EXTRACTOR_VERSION - 1,
    }) is False


def test_verify_index_uses_whole_file_hash_for_file_nodes(
    store: IndexStore,
    tmp_path: Path,
):
    source_path = tmp_path / "repo"
    source_path.mkdir()
    source_file = source_path / "module.py"
    source_file.write_text("VALUE = 1\n", encoding="utf-8")
    content_hash = store.hash_file(source_file)
    file_node = make_file_symbol(
        "module.py",
        language="python",
        content_hash=content_hash,
    )
    store.write(
        source_path,
        [file_node],
        file_hashes={"module.py": content_hash},
    )

    assert store.verify_index(source_path)["failed"] == []

    source_file.write_text("VALUE = 2\n", encoding="utf-8")

    assert store.verify_index(source_path)["failed"] == [{
        "id": "module.py::__file__#file",
        "name": "module.py",
        "kind": "file",
        "file": "module.py",
        "issue": "content_drift",
    }]


def test_verify_index_uses_anchor_file_hash_for_go_package_nodes(
    store: IndexStore,
    tmp_path: Path,
):
    source_path = tmp_path / "repo"
    source_file = source_path / "store" / "store.go"
    source_file.parent.mkdir(parents=True)
    source_file.write_text("package store\n", encoding="utf-8")
    content_hash = store.hash_file(source_file)
    package_node = Symbol(
        id="store::example.com/project/store#package",
        name="store",
        qualified_name="example.com/project/store",
        kind="package",
        language="go",
        file_path="store/store.go",
        byte_offset=0,
        byte_length=0,
        signature="example.com/project/store",
        content_hash=content_hash,
        metadata={
            "loci": {
                "go_package_node": True,
                "directory": "store",
                "import_path": "example.com/project/store",
                "package_name": "store",
            }
        },
        line=1,
        end_line=1,
    )
    store.write(
        source_path,
        [package_node],
        file_hashes={"store/store.go": content_hash},
    )

    assert store.verify_index(source_path)["failed"] == []

    source_file.write_text("package store\n\nconst Changed = true\n", encoding="utf-8")

    assert store.verify_index(source_path)["failed"] == [{
        "id": "store::example.com/project/store#package",
        "name": "store",
        "kind": "package",
        "file": "store/store.go",
        "issue": "content_drift",
    }]


def test_verify_index_uses_root_file_hash_for_rust_crate_nodes(
    store: IndexStore,
    tmp_path: Path,
):
    source_path = tmp_path / "repo"
    source_file = source_path / "src" / "lib.rs"
    source_file.parent.mkdir(parents=True)
    source_file.write_text("pub fn run() {}\n", encoding="utf-8")
    content_hash = store.hash_file(source_file)
    crate_node = Symbol(
        id="Cargo.toml::lib:demo#crate",
        name="demo",
        qualified_name="Cargo.toml::lib:demo",
        kind="crate",
        language="rust",
        file_path="src/lib.rs",
        byte_offset=0,
        byte_length=0,
        signature="Cargo.toml::lib:demo",
        content_hash=content_hash,
        metadata={
            "loci": {
                "rust_crate_node": True,
                "manifest": "Cargo.toml",
                "package_name": "demo-kit",
                "package_root": ".",
                "target_kind": "lib",
                "target_name": "demo-kit",
                "crate_name": "demo",
                "crate_root": "src/lib.rs",
                "edition": "2021",
                "required_features": [],
            }
        },
        line=1,
        end_line=1,
    )
    store.write(
        source_path,
        [crate_node],
        file_hashes={"src/lib.rs": content_hash},
    )

    assert store.verify_index(source_path)["failed"] == []

    source_file.write_text("pub fn changed() {}\n", encoding="utf-8")

    assert store.verify_index(source_path)["failed"] == [{
        "id": "Cargo.toml::lib:demo#crate",
        "name": "demo",
        "kind": "crate",
        "file": "src/lib.rs",
        "issue": "content_drift",
    }]


def test_get_symbol_content_returns_source(store: IndexStore, tmp_path: Path):
    source_path = tmp_path / "repo"
    source_path.mkdir()
    (source_path / "src").mkdir()
    source_text = "# header\ndef login(): pass\n\nclass User: pass\n"
    (source_path / "src" / "auth.py").write_text(source_text)

    source_bytes = source_text.encode()
    symbols = [
        Symbol(
            id="src/auth.py::login#function",
            name="login",
            qualified_name="login",
            kind="function",
            language="python",
            file_path="src/auth.py",
            byte_offset=source_bytes.index(b"def login"),
            byte_length=len(b"def login(): pass"),
        )
    ]
    store.write(source_path, symbols, file_hashes={})

    content = store.get_symbol_content(source_path, "src/auth.py::login#function")
    assert content is not None
    assert "def login" in content


def test_get_symbol_content_returns_none_for_missing_id(store: IndexStore, tmp_path: Path, sample_symbols):
    source_path = tmp_path / "repo"
    source_path.mkdir()
    (source_path / "src").mkdir()
    (source_path / "src" / "auth.py").write_text("def login(): pass")
    store.write(source_path, sample_symbols, file_hashes={})

    result = store.get_symbol_content(source_path, "src/auth.py::nonexistent#function")
    assert result is None


@pytest.fixture
def store_with_data(store: IndexStore, tmp_path: Path) -> tuple[IndexStore, Path]:
    source_path = tmp_path / "repo"
    source_path.mkdir()
    (source_path / "src").mkdir()
    (source_path / "src" / "auth.py").write_text("def login(): pass\n\nclass User: pass")
    (source_path / "src").mkdir(exist_ok=True)
    # Create utils.py too
    (source_path / "src" / "utils.py").write_text("def hash_password(): pass")

    symbols = [
        Symbol(
            id="src/auth.py::login#function",
            name="login",
            qualified_name="login",
            kind="function",
            language="python",
            file_path="src/auth.py",
            byte_offset=0,
            byte_length=20,
            signature="def login(username: str) -> bool",
            docstring="Authenticate a user by checking credentials.",
            summary="Validates username and password against the database.",
        ),
        Symbol(
            id="src/auth.py::User#class",
            name="User",
            qualified_name="User",
            kind="class",
            language="python",
            file_path="src/auth.py",
            byte_offset=22,
            byte_length=50,
            signature="class User",
            docstring="Represents an authenticated user.",
            summary="",
        ),
        Symbol(
            id="src/utils.py::hash_password#function",
            name="hash_password",
            qualified_name="hash_password",
            kind="function",
            language="python",
            file_path="src/utils.py",
            byte_offset=0,
            byte_length=80,
            signature="def hash_password(password: str) -> str",
            docstring="Hash a password using bcrypt.",
            summary="",
        ),
    ]
    store.write(source_path, symbols, file_hashes={})
    return store, source_path


def test_search_exact_name_match_scores_highest(store_with_data):
    store, path = store_with_data
    results = store.search(path, "login")
    assert results[0]["id"] == "src/auth.py::login#function"


def test_search_returns_list(store_with_data):
    store, path = store_with_data
    results = store.search(path, "user")
    assert isinstance(results, list)


def test_search_respects_limit(store_with_data):
    store, path = store_with_data
    results = store.search(path, "password", limit=1)
    assert len(results) <= 1


def test_search_filters_by_kind(store_with_data):
    store, path = store_with_data
    results = store.search(path, "user", kind="class")
    assert all(r["kind"] == "class" for r in results)


def test_search_filters_by_lang(store_with_data):
    store, path = store_with_data
    results = store.search(path, "login", lang="python")
    assert all(r["language"] == "python" for r in results)


def test_search_returns_score(store_with_data):
    store, path = store_with_data
    results = store.search(path, "login")
    assert all("score" in r for r in results)
    assert results[0]["score"] > 0


def test_search_empty_query_returns_all(store_with_data):
    store, path = store_with_data
    results = store.search(path, "")
    assert len(results) == 3


def test_search_tokenizes_hyphenated_query_words(store: IndexStore, tmp_path: Path):
    source_path = tmp_path / "repo"
    source_path.mkdir()
    (source_path / "ideas.md").write_text("# Governed Pipeline\n")
    symbols = [
        Symbol(
            id="ideas.md::Governed Pipeline#section",
            name="Governed Pipeline",
            qualified_name="Governed Pipeline",
            kind="section",
            language="markdown",
            file_path="ideas.md",
            byte_offset=0,
            byte_length=20,
            keywords=["retrieval", "governance"],
        )
    ]
    store.write(source_path, symbols, file_hashes={})

    results = store.search(source_path, "retrieval-governance", lang="markdown")

    assert [r["id"] for r in results] == ["ideas.md::Governed Pipeline#section"]


def test_search_matches_markdown_frontmatter_metadata(store: IndexStore, tmp_path: Path):
    source_path = tmp_path / "repo"
    source_path.mkdir()
    (source_path / "ideas.md").write_text("# Governed Pipeline\n")
    symbols = [
        Symbol(
            id="ideas.md::Governed Pipeline#section",
            name="Governed Pipeline",
            qualified_name="Governed Pipeline",
            kind="section",
            language="markdown",
            file_path="ideas.md",
            byte_offset=0,
            byte_length=20,
            metadata={
                "frontmatter": {
                    "type": "ideas",
                    "category": "Retrieval Governance",
                    "description": "Build bounded graph/vector context packs.",
                    "tags": ["retrieval-governance"],
                }
            },
        )
    ]
    store.write(source_path, symbols, file_hashes={})

    tag_results = store.search(source_path, "retrieval-governance", lang="markdown")
    category_results = store.search(source_path, "Retrieval Governance", lang="markdown")
    description_results = store.search(source_path, "context packs", lang="markdown")

    assert [r["id"] for r in tag_results] == ["ideas.md::Governed Pipeline#section"]
    assert [r["id"] for r in category_results] == ["ideas.md::Governed Pipeline#section"]
    assert [r["id"] for r in description_results] == ["ideas.md::Governed Pipeline#section"]
    assert "page_frontmatter.tags" in tag_results[0]["match_scope"]


def test_search_downranks_markdown_templates_for_metadata_query(store: IndexStore, tmp_path: Path):
    source_path = tmp_path / "repo"
    source_path.mkdir()
    (source_path / "_templates").mkdir()
    (source_path / "ideas").mkdir()
    (source_path / "_templates" / "idea.md").write_text("# Idea Template\n")
    (source_path / "ideas" / "governed.md").write_text("# Governed Pipeline\n")
    metadata = {
        "frontmatter": {
            "category": "Retrieval Governance",
            "tags": ["retrieval-governance"],
        }
    }
    symbols = [
        Symbol(
            id="_templates/idea.md::Idea Template#section",
            name="Idea Template",
            qualified_name="Idea Template",
            kind="section",
            language="markdown",
            file_path="_templates/idea.md",
            byte_offset=0,
            byte_length=20,
            metadata=metadata,
        ),
        Symbol(
            id="ideas/governed.md::Governed Pipeline#section",
            name="Governed Pipeline",
            qualified_name="Governed Pipeline",
            kind="section",
            language="markdown",
            file_path="ideas/governed.md",
            byte_offset=0,
            byte_length=20,
            metadata=metadata,
        ),
    ]
    store.write(source_path, symbols, file_hashes={})

    results = store.search(source_path, "retrieval-governance", lang="markdown")

    assert results[0]["id"] == "ideas/governed.md::Governed Pipeline#section"


def test_search_exposes_markdown_retrieval_cost_fields(store: IndexStore, tmp_path: Path):
    source_path = tmp_path / "repo"
    source_path.mkdir()
    (source_path / "ideas.md").write_text("# Governed Pipeline\n\n## Proposed Graph Move\n\nBody.\n")
    symbols = [
        Symbol(
            id="ideas.md::Governed Pipeline#section",
            name="Governed Pipeline",
            qualified_name="Governed Pipeline",
            kind="section",
            language="markdown",
            file_path="ideas.md",
            byte_offset=0,
            byte_length=900,
            metadata={
                "markdown": {
                    "page_root": True,
                    "synthetic_name": False,
                    "heading_level": 1,
                    "parent_id": "",
                    "root_id": "ideas.md::Governed Pipeline#section",
                    "file_bytes": 1000,
                    "saved_pct": 10,
                    "span_kind": "page_root",
                }
            },
        )
    ]
    store.write(source_path, symbols, file_hashes={})

    results = store.search(source_path, "governed", lang="markdown")

    assert results[0]["file_bytes"] == 1000
    assert results[0]["saved_pct"] == 10
    assert results[0]["span_kind"] == "page_root"
    assert results[0]["match_scope"] == ["section_heading"]


def test_search_surfaces_inherited_markdown_metadata_child_candidates(
    store: IndexStore,
    tmp_path: Path,
):
    source_path = tmp_path / "repo"
    source_path.mkdir()
    (source_path / "ideas.md").write_text(
        "# Governed Hybrid Retrieval Pipeline\n\n"
        "Root body.\n\n"
        "## Proposed Graph Move\n\n"
        "Use page-level governance metadata to route bounded context.\n"
    )
    root_id = "ideas.md::Governed Hybrid Retrieval Pipeline#section"
    child_id = "ideas.md::Governed Hybrid Retrieval Pipeline > Proposed Graph Move#section"
    symbols = [
        Symbol(
            id=root_id,
            name="Governed Hybrid Retrieval Pipeline",
            qualified_name="Governed Hybrid Retrieval Pipeline",
            kind="section",
            language="markdown",
            file_path="ideas.md",
            byte_offset=0,
            byte_length=950,
            metadata={
                "frontmatter": {
                    "title": "Governed Hybrid Retrieval Pipeline",
                    "category": "Retrieval Governance",
                    "tags": ["retrieval-governance"],
                    "description": "Build bounded context packs.",
                },
                "markdown": {
                    "page_root": True,
                    "synthetic_name": False,
                    "heading_level": 1,
                    "parent_id": "",
                    "root_id": root_id,
                    "file_bytes": 1000,
                    "saved_pct": 5,
                    "span_kind": "page_root",
                },
            },
        ),
        Symbol(
            id=child_id,
            name="Proposed Graph Move",
            qualified_name="Governed Hybrid Retrieval Pipeline > Proposed Graph Move",
            kind="section",
            language="markdown",
            file_path="ideas.md",
            byte_offset=40,
            byte_length=180,
            docstring="Use page-level governance metadata to route bounded context.",
            metadata={
                "markdown": {
                    "page_root": False,
                    "synthetic_name": False,
                    "heading_level": 2,
                    "parent_id": root_id,
                    "root_id": root_id,
                    "file_bytes": 1000,
                    "saved_pct": 82,
                    "span_kind": "section",
                },
            },
        ),
    ]
    store.write(source_path, symbols, file_hashes={})

    results = store.search(source_path, "retrieval-governance", lang="markdown")

    assert [r["id"] for r in results[:2]] == [child_id, root_id]
    assert "section_summary" in results[0]["match_scope"]
    assert "inherited_page_frontmatter.tags" in results[0]["match_scope"]
    assert results[0]["saved_pct"] == 82
    assert "page_frontmatter.tags" in results[1]["match_scope"]


def test_search_exact_markdown_page_title_keeps_root_first(store: IndexStore, tmp_path: Path):
    source_path = tmp_path / "repo"
    source_path.mkdir()
    (source_path / "ideas.md").write_text(
        "# Governed Hybrid Retrieval Pipeline\n\n"
        "Root body.\n\n"
        "## Proposed Graph Move\n\n"
        "Governed Hybrid Retrieval Pipeline local text.\n"
    )
    root_id = "ideas.md::Governed Hybrid Retrieval Pipeline#section"
    child_id = "ideas.md::Governed Hybrid Retrieval Pipeline > Proposed Graph Move#section"
    metadata = {
        "frontmatter": {
            "title": "Governed Hybrid Retrieval Pipeline",
            "tags": ["retrieval-governance"],
        },
        "markdown": {
            "page_root": True,
            "synthetic_name": False,
            "heading_level": 1,
            "parent_id": "",
            "root_id": root_id,
            "file_bytes": 1000,
            "saved_pct": 5,
            "span_kind": "page_root",
        },
    }
    symbols = [
        Symbol(
            id=root_id,
            name="Governed Hybrid Retrieval Pipeline",
            qualified_name="Governed Hybrid Retrieval Pipeline",
            kind="section",
            language="markdown",
            file_path="ideas.md",
            byte_offset=0,
            byte_length=950,
            metadata=metadata,
        ),
        Symbol(
            id=child_id,
            name="Proposed Graph Move",
            qualified_name="Governed Hybrid Retrieval Pipeline > Proposed Graph Move",
            kind="section",
            language="markdown",
            file_path="ideas.md",
            byte_offset=40,
            byte_length=180,
            docstring="Governed Hybrid Retrieval Pipeline local text.",
            metadata={
                "markdown": {
                    "page_root": False,
                    "synthetic_name": False,
                    "heading_level": 2,
                    "parent_id": root_id,
                    "root_id": root_id,
                    "file_bytes": 1000,
                    "saved_pct": 82,
                    "span_kind": "section",
                },
            },
        ),
    ]
    store.write(source_path, symbols, file_hashes={})

    results = store.search(source_path, "Governed Hybrid Retrieval Pipeline", lang="markdown")

    assert results[0]["id"] == root_id
    assert "page_frontmatter.title" in results[0]["match_scope"]


def test_log_retrieval_includes_kind_and_language(tmp_path):
    store = IndexStore(tmp_path)
    store.log_retrieval(
        "src/foo.py::bar", symbol_bytes=100, file_bytes=1000,
        repo_path="/repo", kind="function", language="python"
    )
    entries = [json.loads(l) for l in (tmp_path / "session.jsonl").read_text().splitlines()]
    assert entries[0]["event"] == "get"
    assert entries[0]["kind"] == "function"
    assert entries[0]["language"] == "python"


def test_log_retrieval_includes_search_correlation(tmp_path):
    store = IndexStore(tmp_path)
    store.log_retrieval(
        "src/foo.py::bar", symbol_bytes=100, file_bytes=1000,
        repo_path="/repo", kind="function", language="python",
        search_id="abc123", search_rank=2
    )
    entry = json.loads((tmp_path / "session.jsonl").read_text().strip())
    assert entry["search_id"] == "abc123"
    assert entry["search_rank"] == 2


def test_log_retrieval_search_correlation_defaults_to_null(tmp_path):
    store = IndexStore(tmp_path)
    store.log_retrieval("src/foo.py::bar", symbol_bytes=100, file_bytes=1000, repo_path="/repo")
    entry = json.loads((tmp_path / "session.jsonl").read_text().strip())
    assert entry["search_id"] is None
    assert entry["search_rank"] is None


def test_log_retrieval_old_stats_aggregation_unaffected(tmp_path):
    """get_session_stats must still work with enriched entries."""
    store = IndexStore(tmp_path)
    store.log_retrieval("src/foo.py::bar", symbol_bytes=100, file_bytes=1000,
                        repo_path="/repo", kind="function", language="python")
    stats = store.get_session_stats()
    assert stats["total_gets"] == 1
    assert stats["symbol_bytes_retrieved"] == 100


# ── reset_session: must never lose data ─────────────────────────────────────

def test_reset_session_backs_up_before_clearing(tmp_path):
    store = IndexStore(tmp_path)
    store.log_retrieval("src/foo.py::bar", symbol_bytes=100, file_bytes=1000, repo_path="/repo")
    store.log_retrieval("src/foo.py::baz", symbol_bytes=50, file_bytes=500, repo_path="/repo")
    original = (tmp_path / "session.jsonl").read_text()

    backup = store.reset_session()

    # Live log is cleared...
    assert store.get_session_stats()["total_gets"] == 0
    # ...but the prior content survives verbatim in the returned backup.
    assert backup is not None
    assert backup.exists()
    assert backup.read_text() == original
    assert backup.name.startswith("session.jsonl.")
    assert backup.name.endswith(".bak")


def test_reset_session_no_backup_when_empty(tmp_path):
    store = IndexStore(tmp_path)
    backup = store.reset_session()
    assert backup is None
    assert not list(tmp_path.glob("session.jsonl*.bak"))


def test_reset_session_consecutive_resets_do_not_clobber(tmp_path):
    store = IndexStore(tmp_path)
    store.log_retrieval("src/a.py::one", symbol_bytes=1, file_bytes=10, repo_path="/repo")
    first = store.reset_session()
    store.log_retrieval("src/b.py::two", symbol_bytes=2, file_bytes=20, repo_path="/repo")
    second = store.reset_session()

    assert first is not None and second is not None
    assert first != second
    assert first.exists() and second.exists()
    assert "one" in first.read_text()
    assert "two" in second.read_text()


def test_log_search_writes_event_and_last_search_file(tmp_path):
    store = IndexStore(tmp_path)
    store.log_search("abc123", "get_user", "/repo", ["src/users.py::get_user", "src/auth.py::get_user_by_id"])
    # Check session.jsonl
    entry = json.loads((tmp_path / "session.jsonl").read_text().strip())
    assert entry["event"] == "search"
    assert entry["search_id"] == "abc123"
    assert entry["query"] == "get_user"
    assert entry["repo"] == "/repo"
    assert entry["result_ids"] == ["src/users.py::get_user", "src/auth.py::get_user_by_id"]
    assert entry["result_count"] == 2
    # Check last_search.json was also written
    last = json.loads((tmp_path / "last_search.json").read_text())
    assert last["search_id"] == "abc123"
    assert last["result_ids"] == ["src/users.py::get_user", "src/auth.py::get_user_by_id"]


def test_log_miss_search_empty(tmp_path):
    store = IndexStore(tmp_path)
    store.log_miss("search_empty", repo_path="/repo", query="handle_error")
    entry = json.loads((tmp_path / "session.jsonl").read_text().strip())
    assert entry["event"] == "miss"
    assert entry["miss_type"] == "search_empty"
    assert entry["query"] == "handle_error"


def test_log_miss_get_not_found(tmp_path):
    store = IndexStore(tmp_path)
    store.log_miss("get_not_found", repo_path="/repo", symbol_id="src/foo.py::missing")
    entry = json.loads((tmp_path / "session.jsonl").read_text().strip())
    assert entry["event"] == "miss"
    assert entry["miss_type"] == "get_not_found"
    assert entry["symbol_id"] == "src/foo.py::missing"


def test_last_search_path(tmp_path):
    store = IndexStore(tmp_path)
    assert store._last_search_path() == tmp_path / "last_search.json"


def test_write_and_read_last_search(tmp_path):
    store = IndexStore(tmp_path)
    store._write_last_search("abc123", "get_user", ["id1", "id2"])
    data = store._read_last_search()
    assert data is not None
    assert data["search_id"] == "abc123"
    assert data["query"] == "get_user"
    assert data["result_ids"] == ["id1", "id2"]


def test_read_last_search_returns_none_when_missing(tmp_path):
    store = IndexStore(tmp_path)
    assert store._read_last_search() is None


def test_read_last_search_returns_none_when_stale(tmp_path):
    store = IndexStore(tmp_path)
    store._write_last_search("abc123", "q", ["id1"])
    stale_ts = time_module.time() - 400
    data = json.loads((tmp_path / "last_search.json").read_text())
    data["ts"] = stale_ts
    (tmp_path / "last_search.json").write_text(json.dumps(data))
    assert store._read_last_search() is None


def test_resolve_search_correlation_found(tmp_path):
    store = IndexStore(tmp_path)
    store._write_last_search("abc123", "get_user", ["id1", "id2", "id3"])
    search_id, rank = store.resolve_search_correlation("id2")
    assert search_id == "abc123"
    assert rank == 1


def test_resolve_search_correlation_not_in_results(tmp_path):
    store = IndexStore(tmp_path)
    store._write_last_search("abc123", "get_user", ["id1", "id2"])
    search_id, rank = store.resolve_search_correlation("id_other")
    assert search_id == "abc123"
    assert rank is None  # preceded by a search but symbol not in results


def test_resolve_search_correlation_no_recent_search(tmp_path):
    store = IndexStore(tmp_path)
    search_id, rank = store.resolve_search_correlation("id1")
    assert search_id is None
    assert rank is None


def _write_log(path, entries):
    (path / "session.jsonl").write_text("\n".join(json.dumps(e) for e in entries) + "\n")


def test_analyze_search_miss_finding(tmp_path):
    store = IndexStore(tmp_path)
    _write_log(tmp_path, [
        {"ts": time.time(), "event": "miss", "miss_type": "search_empty",
         "query": "handle_error", "repo": "/r"},
        {"ts": time.time(), "event": "miss", "miss_type": "search_empty",
         "query": "handle_error", "repo": "/r"},
        {"ts": time.time(), "event": "miss", "miss_type": "search_empty",
         "query": "BaseModel", "repo": "/r"},
    ])
    result = store.analyze()
    finding = next(f for f in result["findings"] if f["type"] == "search_miss")
    assert set(finding["data"]["queries"]) == {"handle_error", "BaseModel"}
    assert finding["severity"] == "high"
    assert "suggestion" in finding


def test_analyze_search_blind_spot_finding(tmp_path):
    store = IndexStore(tmp_path)
    _write_log(tmp_path, [
        {"ts": time.time(), "event": "get", "symbol_id": "c", "symbol_bytes": 100,
         "file_bytes": 1000, "repo": "/r", "kind": "function", "language": "python",
         "search_id": "s1", "search_rank": None},
        {"ts": time.time(), "event": "get", "symbol_id": "d", "symbol_bytes": 100,
         "file_bytes": 1000, "repo": "/r", "kind": "function", "language": "python",
         "search_id": "s1", "search_rank": None},
        {"ts": time.time(), "event": "get", "symbol_id": "e", "symbol_bytes": 100,
         "file_bytes": 1000, "repo": "/r", "kind": "function", "language": "python",
         "search_id": "s1", "search_rank": None},
    ])
    result = store.analyze()
    finding = next((f for f in result["findings"] if f["type"] == "search_blind_spot"), None)
    assert finding is not None
    assert finding["severity"] == "high"


def test_analyze_search_ranking_poor_finding(tmp_path):
    store = IndexStore(tmp_path)
    entries = []
    for i in range(5):
        entries.append({"ts": time.time(), "event": "get", "symbol_id": f"s{i}",
                        "symbol_bytes": 100, "file_bytes": 1000, "repo": "/r",
                        "kind": "function", "language": "python",
                        "search_id": "abc", "search_rank": 4})
    _write_log(tmp_path, entries)
    result = store.analyze()
    finding = next((f for f in result["findings"] if f["type"] == "search_ranking_poor"), None)
    assert finding is not None
    assert finding["severity"] == "medium"


def test_analyze_kind_dead_weight_finding(tmp_path):
    """kind_dead_weight triggers when a kind is indexed but never fetched."""
    store = IndexStore(tmp_path)
    repo_path = tmp_path / "fakerepo"
    repo_path.mkdir()
    # Use store's own path helper — avoids replicating internal hashing logic
    index_path = store._index_path(repo_path)
    index_path.parent.mkdir(parents=True, exist_ok=True)
    fake_symbols = [
        {"id": f"src/c.py::CONST_{i}#constant", "name": f"CONST_{i}", "kind": "constant",
         "language": "python", "file_path": "src/c.py", "byte_offset": i * 20, "byte_length": 10,
         "signature": f"CONST_{i} = {i}", "docstring": "", "summary": "", "content_hash": "",
         "decorators": [], "keywords": [], "line": i + 1, "end_line": i + 1}
        for i in range(60)
    ]
    index_path.write_text(json.dumps({
        "repo_path": str(repo_path), "indexed_at": time.time(), "symbols": fake_symbols
    }))
    # Log only function fetches — no constants
    _write_log(tmp_path, [
        {"ts": time.time(), "event": "get", "symbol_id": "src/foo.py::bar",
         "symbol_bytes": 100, "file_bytes": 1000, "repo": str(repo_path),
         "kind": "function", "language": "python", "search_id": None, "search_rank": None},
    ])
    result = store.analyze()
    finding = next((f for f in result["findings"] if f["type"] == "kind_dead_weight"), None)
    assert finding is not None
    assert finding["data"]["kind"] == "constant"
    assert finding["data"]["indexed_count"] >= 50
    assert finding["data"]["fetched_count"] == 0
    assert finding["severity"] == "low"


def test_analyze_poor_extraction_finding(tmp_path):
    store = IndexStore(tmp_path)
    _write_log(tmp_path, [
        {"ts": time.time(), "event": "get", "symbol_id": "src/foo.rs::bar",
         "symbol_bytes": 800, "file_bytes": 1000, "repo": "/r",
         "kind": "function", "language": "rust",
         "search_id": None, "search_rank": None},
    ] * 5)
    result = store.analyze()
    finding = next((f for f in result["findings"] if f["type"] == "poor_extraction"), None)
    assert finding is not None
    assert finding["data"]["language"] == "rust"
    assert finding["severity"] == "medium"


def test_analyze_refetch_hotspot_finding(tmp_path):
    store = IndexStore(tmp_path)
    _write_log(tmp_path, [
        {"ts": time.time(), "event": "get", "symbol_id": "src/foo.py::bar",
         "symbol_bytes": 100, "file_bytes": 1000, "repo": "/r",
         "kind": "function", "language": "python",
         "search_id": None, "search_rank": None},
    ] * 4)
    result = store.analyze()
    finding = next((f for f in result["findings"] if f["type"] == "refetch_hotspot"), None)
    assert finding is not None
    assert finding["data"]["symbols"][0]["symbol_id"] == "src/foo.py::bar"
    assert finding["data"]["symbols"][0]["fetch_count"] == 4


def test_analyze_summary_fields_are_floats(tmp_path):
    """miss_rate and correlated_pct are floats 0.0–1.0 per spec schema."""
    store = IndexStore(tmp_path)
    _write_log(tmp_path, [
        {"ts": time.time(), "event": "get", "symbol_id": "s1",
         "symbol_bytes": 100, "file_bytes": 1000, "repo": "/r",
         "kind": "function", "language": "python", "search_id": "x", "search_rank": 0},
        {"ts": time.time(), "event": "search", "search_id": "x", "query": "foo",
         "repo": "/r", "result_ids": ["s1"], "result_count": 1},
        {"ts": time.time(), "event": "miss", "miss_type": "search_empty",
         "query": "bar", "repo": "/r"},
    ])
    result = store.analyze()
    assert result["summary"]["total_gets"] == 1
    assert result["summary"]["total_searches"] == 1
    assert result["summary"]["total_misses"] == 1
    assert isinstance(result["summary"]["miss_rate"], float)
    assert 0.0 <= result["summary"]["miss_rate"] <= 1.0
    assert isinstance(result["summary"]["correlated_pct"], float)
    assert 0.0 <= result["summary"]["correlated_pct"] <= 1.0
    assert "period" in result
    assert "findings" in result


def test_analyze_empty_log(tmp_path):
    store = IndexStore(tmp_path)
    result = store.analyze()
    assert result["findings"] == []
    assert result["summary"]["total_gets"] == 0


def test_analyze_since_days_filter(tmp_path):
    store = IndexStore(tmp_path)
    old_ts = time.time() - (35 * 86400)
    _write_log(tmp_path, [
        {"ts": old_ts, "event": "miss", "miss_type": "search_empty",
         "query": "old_query", "repo": "/r"},
    ])
    result = store.analyze(since_days=30)
    assert all(f["type"] != "search_miss" for f in result["findings"])
