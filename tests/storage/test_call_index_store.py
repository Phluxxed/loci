from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest

from loci.graph.contracts import GraphContractError
from loci.graph.materialize import materialize_graph
from loci.graph.state import GraphIndexState
from loci.parser.extractor import parse_file
from loci.parser.imports import extract_import_batch
from loci.parser.symbols import Symbol, make_file_symbol, make_symbol_id
from loci.storage.index_store import IndexStore


def _call_fixture(
    store: IndexStore,
    tmp_path: Path,
) -> tuple[Path, list[Symbol], dict[str, str], GraphIndexState]:
    repo = tmp_path / "repo"
    repo.mkdir()
    files = {
        "target.py": "def target():\n    return 1\n",
        "use.py": (
            "from target import target\n"
            "\n"
            "def caller():\n"
            "    return target()\n"
        ),
    }
    symbols: list[Symbol] = []
    batches = []
    file_hashes: dict[str, str] = {}
    for relative_path, source in files.items():
        path = repo / relative_path
        path.write_text(source, encoding="utf-8")
        source_hash = hashlib.sha256(source.encode()).hexdigest()
        file_hashes[relative_path] = source_hash
        symbols.append(make_file_symbol(
            relative_path,
            language="python",
            content_hash=source_hash,
        ))
        symbols.extend(
            replace(
                symbol,
                id=make_symbol_id(
                    relative_path,
                    symbol.qualified_name,
                    symbol.kind,
                ),
                file_path=relative_path,
            )
            for symbol in parse_file(path)
        )
        batches.append(extract_import_batch(
            path,
            source_file=relative_path,
            language="python",
            source_hash=source_hash,
        ))
    state = materialize_graph(
        repo,
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
    )
    assert len(state.calls) == 1
    assert state.calls[0].status == "resolved"
    return repo, symbols, file_hashes, state


def test_store_round_trips_validated_call_state_byte_stably(tmp_path: Path):
    store = IndexStore(base_dir=tmp_path / ".codeindex")
    repo, symbols, file_hashes, state = _call_fixture(store, tmp_path)

    store.write(repo, symbols, file_hashes, graph_state=state)

    fresh_store = IndexStore(base_dir=store.base_dir)
    loaded = fresh_store.get_graph_state(repo)
    assert loaded == state
    assert json.dumps(loaded.to_dict(), separators=(",", ":")) == json.dumps(
        state.to_dict(),
        separators=(",", ":"),
    )


def test_store_rejects_stale_call_record_before_atomic_write(tmp_path: Path):
    store = IndexStore(base_dir=tmp_path / ".codeindex")
    repo, symbols, file_hashes, state = _call_fixture(store, tmp_path)
    stale_support = tuple(
        replace(item, content_hash="0" * 64)
        if item.kind in {"call_site", "symbol_reference"}
        else item
        for item in state.calls[0].support
    )
    stale_record = replace(
        state.calls[0],
        raw=replace(state.calls[0].raw, source_hash="0" * 64),
        support=stale_support,
    )

    with pytest.raises(GraphContractError, match="stale"):
        store.write(
            repo,
            symbols,
            file_hashes,
            graph_state=replace(state, calls=(stale_record,)),
        )

    assert not store._index_path(repo).exists()


def test_store_rejects_call_edge_without_backing_record(tmp_path: Path):
    store = IndexStore(base_dir=tmp_path / ".codeindex")
    repo, symbols, file_hashes, state = _call_fixture(store, tmp_path)

    with pytest.raises(GraphContractError) as exc_info:
        store.write(
            repo,
            symbols,
            file_hashes,
            graph_state=replace(state, calls=()),
        )

    assert exc_info.value.code == "GRAPH_EVIDENCE_INVALID"
    assert exc_info.value.details["field"] == "call_record"
    assert not store._index_path(repo).exists()


def test_fresh_store_rejects_schema_seven_call_state(tmp_path: Path):
    store = IndexStore(base_dir=tmp_path / ".codeindex")
    repo, symbols, file_hashes, state = _call_fixture(store, tmp_path)
    store.write(repo, symbols, file_hashes, graph_state=state)
    index_path = store._index_path(repo)
    payload = json.loads(index_path.read_text())
    payload["graph"]["schema_version"] = 7
    index_path.write_text(json.dumps(payload))

    fresh_store = IndexStore(base_dir=store.base_dir)
    with pytest.raises(GraphContractError, match="Unsupported graph state"):
        fresh_store.get_graph_state(repo)


def test_fresh_store_rejects_model_valid_but_stale_call_record(tmp_path: Path):
    store = IndexStore(base_dir=tmp_path / ".codeindex")
    repo, symbols, file_hashes, state = _call_fixture(store, tmp_path)
    store.write(repo, symbols, file_hashes, graph_state=state)
    index_path = store._index_path(repo)
    payload = json.loads(index_path.read_text())
    record = payload["graph"]["calls"][0]
    record["raw"]["source_hash"] = "0" * 64
    for support in record["support"]:
        if support["kind"] in {"call_site", "symbol_reference"}:
            support["content_hash"] = "0" * 64
    index_path.write_text(json.dumps(payload))

    fresh_store = IndexStore(base_dir=store.base_dir)
    with pytest.raises(GraphContractError, match="stale"):
        fresh_store.get_graph_state(repo)


def test_fresh_store_rejects_call_edge_without_current_record(tmp_path: Path):
    store = IndexStore(base_dir=tmp_path / ".codeindex")
    repo, symbols, file_hashes, state = _call_fixture(store, tmp_path)
    store.write(repo, symbols, file_hashes, graph_state=state)
    index_path = store._index_path(repo)
    payload = json.loads(index_path.read_text())
    payload["graph"]["calls"] = []
    index_path.write_text(json.dumps(payload))

    fresh_store = IndexStore(base_dir=store.base_dir)
    with pytest.raises(GraphContractError) as exc_info:
        fresh_store.get_graph_state(repo)

    assert exc_info.value.code == "GRAPH_EVIDENCE_INVALID"
    assert exc_info.value.details["field"] == "call_record"
