from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from loci.graph.contracts import GraphContractError
from loci.graph.imports import ImportRecord
from loci.graph.references import (
    ReferenceSupport,
    SymbolReferenceRecord,
    materialize_reference_edges,
)
from loci.graph.state import GraphIndexState
from loci.parser.imports import RawImport
from loci.parser.reference_models import (
    ImportBinding,
    RawLocalExport,
    RawSymbolReference,
)
from loci.parser.symbols import Symbol, make_file_symbol
from loci.storage.index_store import IndexStore


SOURCE_FILE = "src/use.py"
TARGET_FILE = "src/model.py"
SOURCE_FILE_ID = f"{SOURCE_FILE}::__file__#file"
TARGET_FILE_ID = f"{TARGET_FILE}::__file__#file"
SOURCE_ID = f"{SOURCE_FILE}::run#function"
TARGET_ID = f"{TARGET_FILE}::Thing#class"
SOURCE_TEXT = "from .model import Thing as Alias\n\n\ndef run():\n    return Alias()\n"
TARGET_TEXT = "class Thing:\n    pass\n"


@pytest.fixture
def store(tmp_path: Path) -> IndexStore:
    return IndexStore(base_dir=tmp_path / ".codeindex")


def _reference_fixture(
    store: IndexStore,
    tmp_path: Path,
) -> tuple[
    Path,
    list[Symbol],
    dict[str, str],
    GraphIndexState,
    SymbolReferenceRecord,
]:
    repo = tmp_path / "repo"
    source_path = repo / SOURCE_FILE
    target_path = repo / TARGET_FILE
    source_path.parent.mkdir(parents=True)
    source_path.write_text(SOURCE_TEXT, encoding="utf-8")
    target_path.write_text(TARGET_TEXT, encoding="utf-8")
    source_hash = store.hash_file(source_path)
    target_hash = store.hash_file(target_path)

    source_start = SOURCE_TEXT.index("def run")
    reference_start = SOURCE_TEXT.rindex("Alias")
    target_start = TARGET_TEXT.index("class Thing")
    binding = ImportBinding(
        local_name="Alias",
        imported_name="Thing",
        exported_name=None,
        kind="symbol",
        type_only=False,
        module_level=True,
        declaration_start_byte=0,
        scope_start_byte=0,
        scope_end_byte=len(SOURCE_TEXT.encode()),
        import_line=1,
        import_text="from .model import Thing as Alias",
        import_specifier=".model",
    )
    raw_import = RawImport(
        source_file=SOURCE_FILE,
        language="python",
        line=1,
        text="from .model import Thing as Alias",
        specifier=".model",
        imported_name="Thing",
        type_only=False,
        is_reexport=False,
        source_hash=source_hash,
        bindings=(binding,),
    )
    import_record = ImportRecord(
        raw=raw_import,
        source_id=SOURCE_FILE_ID,
        target_file=TARGET_FILE,
        target_package=None,
        target_crate=None,
        target_kind="file",
        target_id=TARGET_FILE_ID,
        status="resolved",
        unresolved_reason=None,
    )
    export = RawLocalExport(
        source_file=TARGET_FILE,
        language="python",
        line=1,
        text="class Thing:",
        local_name="Thing",
        exported_name="Thing",
        type_only=False,
        definition_start_byte=target_start,
        definition_end_byte=len(TARGET_TEXT.encode()),
        source_hash=target_hash,
    )
    raw_reference = RawSymbolReference(
        source_file=SOURCE_FILE,
        language="python",
        line=5,
        column=12,
        start_byte=reference_start,
        end_byte=reference_start + len("Alias"),
        text="Alias",
        path=("Alias",),
        candidate_bindings=(binding,),
        binding_state="definite",
        source_hash=source_hash,
    )
    record = SymbolReferenceRecord(
        raw=raw_reference,
        binding=binding,
        source_id=SOURCE_ID,
        source_kind="function",
        import_source_id=SOURCE_FILE_ID,
        import_target_id=TARGET_FILE_ID,
        target_file=TARGET_FILE,
        target_id=TARGET_ID,
        target_kind="class",
        status="resolved",
        unresolved_reason=None,
        import_unresolved_reason=None,
        resolution_basis="direct_binding",
        support=(
            ReferenceSupport(
                kind="import_binding",
                file=SOURCE_FILE,
                line=1,
                content_hash=source_hash,
                endpoint_id=TARGET_FILE_ID,
            ),
            ReferenceSupport(
                kind="definition",
                file=TARGET_FILE,
                line=1,
                content_hash=target_hash,
                endpoint_id=TARGET_ID,
            ),
        ),
        resolution_control_files=(),
        resolution_configuration=None,
    )
    symbols = [
        make_file_symbol(SOURCE_FILE, language="python", content_hash=source_hash),
        Symbol(
            id=SOURCE_ID,
            name="run",
            qualified_name="run",
            kind="function",
            language="python",
            file_path=SOURCE_FILE,
            byte_offset=source_start,
            byte_length=len(SOURCE_TEXT.encode()) - source_start,
            content_hash=source_hash,
            line=4,
            end_line=5,
        ),
        make_file_symbol(TARGET_FILE, language="python", content_hash=target_hash),
        Symbol(
            id=TARGET_ID,
            name="Thing",
            qualified_name="Thing",
            kind="class",
            language="python",
            file_path=TARGET_FILE,
            byte_offset=target_start,
            byte_length=len(TARGET_TEXT.encode()),
            content_hash=target_hash,
            line=1,
            end_line=2,
        ),
    ]
    edge = materialize_reference_edges([record])[0]
    state = replace(
        GraphIndexState.empty(edges=[edge]),
        imports=(import_record,),
        exports=(export,),
        symbol_references=(record,),
    )
    return (
        repo,
        symbols,
        {SOURCE_FILE: source_hash, TARGET_FILE: target_hash},
        state,
        record,
    )


def test_store_round_trips_validated_reference_state_byte_stably(
    store: IndexStore,
    tmp_path: Path,
):
    repo, symbols, file_hashes, state, _ = _reference_fixture(store, tmp_path)

    store.write(repo, symbols, file_hashes, graph_state=state)

    loaded = store.get_graph_state(repo)
    assert loaded == state
    assert json.dumps(
        loaded.to_dict(),
        separators=(",", ":"),
    ) == json.dumps(state.to_dict(), separators=(",", ":"))


def test_store_rejects_stale_reference_record_before_atomic_write(
    store: IndexStore,
    tmp_path: Path,
):
    repo, symbols, file_hashes, state, record = _reference_fixture(store, tmp_path)
    stale_raw = replace(record.raw, source_hash="0" * 64)
    stale_record = replace(record, raw=stale_raw)
    stale_state = replace(state, symbol_references=(stale_record,))

    with pytest.raises(GraphContractError, match="stale"):
        store.write(repo, symbols, file_hashes, graph_state=stale_state)

    assert not store._index_path(repo).exists()


def test_store_rejects_stale_export_evidence_without_reference_records(
    store: IndexStore,
    tmp_path: Path,
):
    repo, symbols, file_hashes, state, _ = _reference_fixture(store, tmp_path)
    stale_export = replace(state.exports[0], source_hash="0" * 64)
    export_only_state = replace(
        state,
        edges=(),
        exports=(stale_export,),
        symbol_references=(),
    )

    with pytest.raises(GraphContractError, match="export source evidence is stale"):
        store.write(repo, symbols, file_hashes, graph_state=export_only_state)

    assert not store._index_path(repo).exists()


def test_store_rejects_reference_edge_without_backing_record(
    store: IndexStore,
    tmp_path: Path,
):
    repo, symbols, file_hashes, state, _ = _reference_fixture(store, tmp_path)
    unbacked_state = replace(state, symbol_references=())

    with pytest.raises(GraphContractError) as exc_info:
        store.write(repo, symbols, file_hashes, graph_state=unbacked_state)

    assert exc_info.value.code == "GRAPH_EVIDENCE_INVALID"
    assert exc_info.value.details["field"] == "reference_record"
    assert not store._index_path(repo).exists()


def test_store_rejects_extension_namespace_using_reserved_reference_type(
    store: IndexStore,
    tmp_path: Path,
):
    repo, symbols, file_hashes, state, _ = _reference_fixture(store, tmp_path)
    reserved_edge = replace(
        state.edges[0],
        namespace="llm-wiki",
        resolution="declared",
    )
    reserved_state = replace(state, edges=(reserved_edge,))

    with pytest.raises(GraphContractError) as exc_info:
        store.write(repo, symbols, file_hashes, graph_state=reserved_state)

    assert exc_info.value.code == "GRAPH_EDGE_TYPE_UNSUPPORTED"
    assert exc_info.value.details["namespace"] == "llm-wiki"
    assert not store._index_path(repo).exists()


def test_store_rejects_schema_six_graph_state_instead_of_loading_partially(
    store: IndexStore,
    tmp_path: Path,
):
    repo, symbols, file_hashes, state, _ = _reference_fixture(store, tmp_path)
    store.write(repo, symbols, file_hashes, graph_state=state)
    index_path = store._index_path(repo)
    payload = json.loads(index_path.read_text())
    payload["graph"]["schema_version"] = 6
    index_path.write_text(json.dumps(payload))

    with pytest.raises(GraphContractError, match="Unsupported graph state"):
        store.get_graph_state(repo)
