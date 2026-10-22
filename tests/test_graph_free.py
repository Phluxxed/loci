"""The isolated graph-free arm retrieves current source without semantic state."""
import base64
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from loci.graph_free import GraphFreeError, GraphFreeSource
from loci.mcp_output_models import LociReadOutput, NormalSource


def _repo(tmp_path: Path, files: dict[str, str]) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    for name, content in files.items():
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    return root


def _all_pages(source: GraphFreeSource, repo: Path, ref: str) -> str:
    parts = []
    while ref is not None:
        page = source.read(repo, ref)
        LociReadOutput.model_validate(page)
        parts.append(page["source"]["content"])
        assert page["usage"]["evidence_bytes"] <= 8192
        assert page["usage"]["output_bytes"] <= 16384
        assert page["usage"]["output_bytes"] == _mcp_bytes(page)
        ref = page["next_source_ref"]
    return "".join(parts)


def _mcp_bytes(packet: dict) -> int:
    return len(json.dumps({"content": [], "structuredContent": packet,
                           "isError": False}, ensure_ascii=False,
                          separators=(",", ":")).encode("utf-8"))


def test_inventory_search_and_source_followup_without_graph_state(tmp_path):
    root = _repo(tmp_path, {
        "src/app.py": "def launch():\n    handler.execute()\n",
        "src/handler.py": "class Handler:\n    def execute(self):\n        return 'ready'\n",
        "config/app.toml": "name = 'demo'\n",
        "README.md": "The handler is used by the app.\n",
        "ignored/secret.txt": "private token\n",
        ".gitignore": "ignored/\n",
    })
    subprocess.run(["git", "-C", str(root), "add", "-f", "ignored/secret.txt"], check=True)
    source = GraphFreeSource(tmp_path / "isolated-store")
    stats = source.index_repo(root)
    inventory = source.inventory(root)
    assert stats["files_indexed"] >= 4
    assert "ignored/secret.txt" not in inventory["file_hashes"]
    assert "config/app.toml" in inventory["file_hashes"]
    assert "graph" not in inventory
    assert all(len(digest) == 64 for digest in inventory["file_hashes"].values())
    assert set(json.loads(Path(stats["index_path"]).read_text())) == {
        "schema_version", "repo_path", "file_hashes", "omissions", "snapshot",
    }

    packet = source.retrieve(root, "src/app.py")
    assert packet["policy"] == "graph-free-file-v1"
    assert packet["scope"]["matching"] == "exact_file"
    assert packet["relationships"] == packet["nodes"] == packet["anchors"] == []
    assert packet["sources"][0]["content"] == (root / "src/app.py").read_text()
    NormalSource.model_validate(packet["sources"][0])
    assert packet["usage"]["output_bytes"] == _mcp_bytes(packet)
    assert _all_pages(source, root, packet["items"][0]["source_ref"]) == (
        root / "src/app.py").read_text()

    # The observed identifier is a valid subsequent search query. No graph ID
    # or parser-derived symbol is required to locate the implementing source.
    observed = "handler.execute"
    literal = source.retrieve(root, observed)
    assert literal["sources"][0]["file"] == "src/app.py"
    followup = source.retrieve(root, "def execute")
    assert followup["sources"][0]["file"] == "src/handler.py"
    assert "def execute" in followup["sources"][0]["content"]
    assert source.retrieve(root, "private token")["sources"] == []


def test_unicode_pages_are_exact_bounded_and_stale_references_fail(tmp_path):
    text = "🙂 repeated\n" * 2000
    root = _repo(tmp_path, {"long.txt": text})
    source = GraphFreeSource(tmp_path / "store")
    packet = source.retrieve(root, "long.txt")
    ref = packet["items"][0]["source_ref"]
    assert packet["items"][0]["complete"] is False
    assert _all_pages(source, root, ref) == text
    assert packet["items"][0]["extent"]["content_hash"] == hashlib.sha256(text.encode()).hexdigest()

    (root / "long.txt").write_text("changed\n")
    with pytest.raises(GraphFreeError, match="changed") as error:
        source.read(root, ref)
    assert error.value.code == "SOURCE_STALE"
    source.index_repo(root)
    with pytest.raises(GraphFreeError) as error:
        source.read(root, ref)
    assert error.value.code == "SOURCE_STALE"


def test_reference_is_repo_bound_and_symlink_escape_is_rejected(tmp_path):
    root = _repo(tmp_path, {"src/file.txt": "same contents\n"})
    source = GraphFreeSource(tmp_path / "store")
    ref = source.retrieve(root, "src/file.txt")["items"][0]["source_ref"]
    other = tmp_path / "other"
    other.mkdir()
    (other / "src").mkdir()
    (other / "src/file.txt").write_text("same contents\n")
    source.index_repo(other)
    with pytest.raises(GraphFreeError) as error:
        source.read(other, ref)
    assert error.value.code == "INVALID_SOURCE_REF"

    outside = tmp_path / "outside.txt"
    outside.write_text("same contents\n")
    (root / "src/file.txt").unlink()
    (root / "src/file.txt").symlink_to(outside)
    with pytest.raises(GraphFreeError) as error:
        source.read(root, ref)
    assert error.value.code == "SOURCE_UNAVAILABLE"
    source.index_repo(root)
    assert "src/file.txt" not in source.inventory(root)["file_hashes"]


def test_read_rechecks_ignored_source_and_rejects_corrupt_inventory(tmp_path):
    root = _repo(tmp_path, {"file.txt": "current source\n"})
    source = GraphFreeSource(tmp_path / "store")
    ref = source.retrieve(root, "file.txt")["items"][0]["source_ref"]
    (root / ".gitignore").write_text("file.txt\n")
    with pytest.raises(GraphFreeError) as error:
        source.read(root, ref)
    assert error.value.code == "SOURCE_UNAVAILABLE"

    (root / ".gitignore").unlink()
    (root / "file.txt").unlink()
    with pytest.raises(GraphFreeError) as error:
        source.read(root, ref)
    assert error.value.code == "SOURCE_UNAVAILABLE"
    (root / "file.txt").write_text("current source\n")
    index = source.inventory(root)
    path = source._index_path(root)
    path.write_text(json.dumps({**index, "file_hashes": {"file.txt": "0" * 64}}))
    with pytest.raises(GraphFreeError) as error:
        source.read(root, ref)
    assert error.value.code == "INDEX_UNAVAILABLE"


def test_read_rejects_forged_utf8_offset_and_ancestor_symlink(tmp_path):
    root = _repo(tmp_path, {"src/unicode.txt": "🙂 source\n"})
    source = GraphFreeSource(tmp_path / "store")
    ref = source.retrieve(root, "src/unicode.txt")["items"][0]["source_ref"]
    raw = base64.urlsafe_b64decode(ref + "=" * (-len(ref) % 4))
    forged = {**json.loads(raw), "offset": 1}
    invalid = base64.urlsafe_b64encode(json.dumps(
        forged, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()).decode().rstrip("=")
    with pytest.raises(GraphFreeError) as error:
        source.read(root, invalid)
    assert error.value.code == "INVALID_SOURCE_REF"

    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "unicode.txt").write_text("🙂 source\n")
    (root / "src/unicode.txt").unlink()
    (root / "src").rmdir()
    (root / "src").symlink_to(outside, target_is_directory=True)
    with pytest.raises(GraphFreeError) as error:
        source.read(root, ref)
    assert error.value.code == "SOURCE_UNAVAILABLE"


def test_graph_free_import_does_not_load_parser_graph_or_storage(tmp_path):
    root = _repo(tmp_path, {"sample.txt": "one target\n"})
    command = [sys.executable, "-c", (
        "import json,sys; from loci.graph_free import GraphFreeSource; "
        "source=GraphFreeSource(sys.argv[2]); "
        "packet=source.retrieve(sys.argv[1], 'target'); "
        "source.read(sys.argv[1], packet['items'][0]['source_ref']); "
        "print(json.dumps(sorted(name for name in sys.modules "
        "if name in ('loci.graph', 'loci.parser', 'loci.storage') "
        "or name.startswith(('loci.graph.', 'loci.parser.', 'loci.storage.')))))"
    ), str(root), str(tmp_path / "isolated-store")]
    result = subprocess.run(command, check=True, capture_output=True, text=True,
                            env={**os.environ, "PYTHONPATH": "src"})
    assert json.loads(result.stdout) == []
