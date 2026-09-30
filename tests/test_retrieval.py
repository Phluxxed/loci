"""Source selection, excerpts and exact continuation under normal budgets."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from loci import service
from loci.graph.contracts import GraphContractError
from loci.retrieval import retrieve_context
from loci.retrieval_io import read_source
from loci.mcp_output_models import LociRetrieveOutput


def _indexed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, files: dict[str, str]):
    repo = tmp_path / "repo"
    for relative, content in files.items():
        path = repo / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    monkeypatch.setenv("LOCI_BASE_DIR", str(tmp_path / "store"))
    service.index_repo(repo, incremental=False)
    store = service.get_store()
    index = store.load(repo)
    assert index is not None
    nodes = {node["id"]: node for node in index["symbols"]}
    return repo, store, nodes, index["file_hashes"]


def _retrieve(indexed, query="", *, seed_ids=None):
    repo, store, nodes, state = indexed
    return retrieve_context(repo, store, nodes, state, query, seed_ids=seed_ids,
                            coverage="complete")


def _symbol(nodes: dict[str, dict], name: str) -> str:
    matches = [node["id"] for node in nodes.values() if node.get("name") == name]
    assert len(matches) == 1
    return matches[0]


def _envelope_bytes(result: dict) -> int:
    return len(json.dumps(
        {"content": [], "structuredContent": result, "isError": False},
        ensure_ascii=False, separators=(",", ":"),
    ).encode("utf-8"))


def _assert_schema(result: dict) -> None:
    LociRetrieveOutput.model_validate(result)


def test_markdown_exact_file_and_literal_use_real_page_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    indexed = _indexed(tmp_path, monkeypatch, {
        "guide.md": "# Guide\n\nIntro.\n\n## Hidden detail\n\nA literal-only telescope §§§.\n",
    })
    exact = _retrieve(indexed, "./guide.md")
    assert exact["selection"]["mode"] == "file"
    assert exact["scope"]["matching"] == "exact_file"
    assert exact["nodes"][0]["kind"] == "section"
    assert all(node["kind"] != "file" for node in exact["nodes"])

    literal = _retrieve(indexed, "§§§")
    assert literal["selection"]["mode"] == "literal"
    assert literal["scope"]["matching"] == "source_literal"
    assert literal["items"]


def test_request_validation_is_utf8_bounded_and_requires_input(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    indexed = _indexed(tmp_path, monkeypatch, {"a.py": "def value():\n    return 1\n"})
    with pytest.raises(GraphContractError, match="query or seed_ids"):
        _retrieve(indexed)
    with pytest.raises(GraphContractError, match="4096 UTF-8 bytes"):
        _retrieve(indexed, "é" * 2049)
    value_id = _symbol(indexed[2], "value")
    with pytest.raises(GraphContractError, match="unique IDs"):
        _retrieve(indexed, seed_ids=[value_id, value_id])


def test_insertion_order_does_not_change_source_packet(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    indexed = _indexed(tmp_path, monkeypatch, {
        "a.py": "def leaf():\n    return 1\n\ndef root():\n    return leaf()\n",
        "b.py": "from a import root\n\ndef caller():\n    return root()\n",
    })
    root_id = _symbol(indexed[2], "root")
    first = _retrieve(indexed, seed_ids=[root_id])
    repo, store, nodes, state = indexed
    second = retrieve_context(repo, store, dict(reversed(list(nodes.items()))),
                              dict(reversed(list(state.items()))),
                              seed_ids=[root_id], coverage="complete")
    assert first == second


def test_fitting_anchor_stays_complete_without_incidental_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    body = "".join(f"    value_{index} = {index}\n" for index in range(240))
    indexed = _indexed(tmp_path, monkeypatch, {
        "large.py": "def leaf():\n    return 1\n\ndef large():\n" + body + "    return leaf()\n",
    })
    large_id = _symbol(indexed[2], "large")
    leaf_id = _symbol(indexed[2], "leaf")
    result = _retrieve(indexed, seed_ids=[large_id])
    anchor = next(item for item in result["items"] if item["node_id"] == large_id)
    assert anchor["complete"] is True
    assert anchor["extent"]["end_byte"] - anchor["extent"]["start_byte"] == len(
        result["sources"][anchor["source_ids"][0] - 1]["content"].encode("utf-8")
    )
    assert anchor["source_ref"]
    assert result["relationships"] == []
    assert [item["node_id"] for item in result["items"]] == [large_id]
    assert result["usage"]["evidence_bytes"] <= result["limits"]["max_evidence_bytes"]


def test_literal_source_outranks_unrelated_metadata_and_keeps_late_match(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    literal = "connection reset §42§"
    body = "".join(f"    value_{index} = '{index:04d}'\n" for index in range(600))
    indexed = _indexed(tmp_path, monkeypatch, {
        "connection.py": "def unrelated():\n    return 1\n",
        "worker.py": "def execute():\n" + body + f"    raise RuntimeError('{literal}')\n",
    })
    result = _retrieve(indexed, literal)
    execute_id = _symbol(indexed[2], "execute")
    assert result["scope"]["matching"] == "source_literal"
    assert result["anchors"][0]["node_id"] == execute_id
    anchor = next(item for item in result["items"] if item["node_id"] == execute_id)
    assert anchor["complete"] is False
    source = result["sources"][anchor["source_ids"][0] - 1]
    assert literal in source["content"]
    assert anchor["extent"]["start_byte"] <= source["start_byte"]
    assert source["end_byte"] <= anchor["extent"]["end_byte"]
    assert source["content"] == (indexed[0] / "worker.py").read_bytes()[
        source["start_byte"]:source["end_byte"]
    ].decode("utf-8")
    repo, store, _, _ = indexed
    chunks = []
    reference = anchor["source_ref"]
    while reference:
        page = read_source(repo, store, store.load(repo), reference)
        chunks.append(page["source"]["content"])
        reference = page["next_source_ref"]
    assert "".join(chunks) == (repo / "worker.py").read_bytes()[
        anchor["extent"]["start_byte"]:anchor["extent"]["end_byte"]
    ].decode("utf-8")
    assert result["usage"]["evidence_bytes"] <= 8192
    assert result["usage"]["output_bytes"] <= 16384


def test_anchor_definition_over_old_preview_cap_is_complete_when_it_fits(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    body = "".join(f"    value_{index} = {index}\n" for index in range(120))
    indexed = _indexed(tmp_path, monkeypatch, {
        "work.py": "def execute():\n" + body + "    return value_119\n",
    })
    execute_id = _symbol(indexed[2], "execute")
    result = _retrieve(indexed, seed_ids=[execute_id])
    anchor = next(item for item in result["items"] if item["node_id"] == execute_id)
    source = result["sources"][anchor["source_ids"][0] - 1]
    assert len(source["content"].encode("utf-8")) > 1024
    assert anchor["complete"] is True
    assert source["start_byte"] == anchor["extent"]["start_byte"]
    assert source["end_byte"] == anchor["extent"]["end_byte"]


@pytest.mark.parametrize("lines", [220, 600])
def test_oversized_explicit_anchors_share_source_budget(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, lines: int,
):
    body = "".join(f"    value_{index} = '{index:04d}'\n" for index in range(lines))
    indexed = _indexed(tmp_path, monkeypatch, {
        "a.py": "def first():\n" + body + "    return 1\n",
        "b.py": "def second():\n" + body + "    return 2\n",
    })
    ids = [_symbol(indexed[2], name) for name in ("first", "second")]
    result = _retrieve(indexed, seed_ids=ids)
    anchors = [item for item in result["items"] if item["node_id"] in ids]
    assert len(anchors) == 2
    assert all(not item["complete"] for item in anchors)
    assert all(len(result["sources"][item["source_ids"][0] - 1]["content"].encode("utf-8"))
               > 1024 for item in anchors)
    assert result["usage"]["evidence_bytes"] <= 8192
    assert result["usage"]["output_bytes"] <= 16384


def test_literal_excerpt_respects_escaped_json_output_budget(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    literal = "connection reset §42§"
    indexed = _indexed(tmp_path, monkeypatch, {
        "worker.py": "def execute():\n    # " + '\\"' * 3700 +
                     f"\n    raise RuntimeError('{literal}')\n",
    })
    repo, store, nodes, state = indexed
    result = retrieve_context(repo, store, nodes, state, literal,
                              coverage="complete")
    execute_id = _symbol(indexed[2], "execute")
    anchor = next(item for item in result["items"] if item["node_id"] == execute_id)
    source = result["sources"][anchor["source_ids"][0] - 1]
    assert literal in source["content"]
    assert anchor["complete"] is False
    assert result["usage"]["evidence_bytes"] <= 8192
    assert result["usage"]["output_bytes"] == _envelope_bytes(result)
    assert result["usage"]["output_bytes"] <= 16384


def test_joint_json_budget_keeps_every_selected_source(tmp_path, monkeypatch):
    indexed = _indexed(tmp_path, monkeypatch, {
        f"{name}.md": f"# {name}\n" + "\x01" * 5000 + "\n"
        for name in ("first", "second", "third")
    })
    ids = [node["id"] for node in indexed[2].values() if node["kind"] == "section"]
    result = _retrieve(indexed, seed_ids=ids)
    assert {item["node_id"] for item in result["items"]} == set(ids)
    assert all(not item["complete"] for item in result["items"])
    assert all(source["content"] for source in result["sources"])
    assert result["usage"]["output_bytes"] == _envelope_bytes(result) <= 16384
    _assert_schema(result)


def test_overlapping_selected_definitions_stay_complete_when_joint_packet_fits(tmp_path, monkeypatch):
    body = "".join(f"        value_{i} = {i}\n" for i in range(230))
    indexed = _indexed(tmp_path, monkeypatch, {
        "a.py": "class Container:\n    def execute(self):\n" + body + "        return 1\n",
    })
    ids = [_symbol(indexed[2], name) for name in ("Container", "execute")]
    result = _retrieve(indexed, seed_ids=ids)
    assert all(item["complete"] for item in result["items"])
    assert len(result["items"]) == 2
    assert result["usage"]["evidence_bytes"] <= 8192
    _assert_schema(result)


def test_missing_anchor_definition_is_reported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    indexed = _indexed(tmp_path, monkeypatch, {"a.py": "def root():\n    return 1\n"})
    repo, store, nodes, state = indexed
    root_id = _symbol(nodes, "root")
    changed_nodes = {key: dict(value) for key, value in nodes.items()}
    changed_nodes[root_id]["content_hash"] = "f" * 64
    result = retrieve_context(repo, store, changed_nodes, state,
                              seed_ids=[root_id], coverage="complete")
    assert not any(item["node_id"] == root_id for item in result["items"])
    assert any(item["reason"] == "source_unavailable" for item in result["omissions"])
