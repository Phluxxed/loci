from __future__ import annotations

from pathlib import Path

import pytest

from loci.graph.contracts import GRAPH_SCHEMA_VERSION
from loci.service import LociError, graph_references, index_repo


def _reference_repo(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Path:
    monkeypatch.setenv("LOCI_BASE_DIR", str(tmp_path / ".codeindex"))
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "target.py").write_text(
        "class Thing:\n    pass\n",
        encoding="utf-8",
    )
    (repo / "consumer.py").write_text(
        (
            "from target import Thing\n"
            "from missing import Lost\n\n"
            "def build():\n"
            "    return Thing()\n\n"
            "def broken():\n"
            "    return Lost()\n"
        ),
        encoding="utf-8",
    )
    index_repo(repo, incremental=False)
    return repo


def test_graph_references_returns_stable_bounded_record_page(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    repo = _reference_repo(tmp_path, monkeypatch)

    result = graph_references(repo, limit=1)

    assert result["schema_version"] == GRAPH_SCHEMA_VERSION
    assert result["repo"] == str(repo.resolve())
    assert result["file"] is None
    assert result["status"] == "all"
    assert result["counts"] == {
        "total": 2,
        "resolved": 1,
        "unresolved": 1,
        "returned": 1,
    }
    assert result["pagination"] == {
        "offset": 0,
        "limit": 1,
        "next_offset": 1,
    }
    assert len(result["items"]) == 1
    item = result["items"][0]
    assert set(item) == {
        "raw",
        "binding",
        "source_file",
        "source_id",
        "source_kind",
        "import_source_id",
        "import_target_id",
        "target_file",
        "target_id",
        "target_kind",
        "status",
        "resolution",
        "unresolved_reason",
        "import_unresolved_reason",
        "resolution_basis",
        "support",
        "resolution_control_files",
        "resolution_configuration",
    }
    assert item["source_file"] == "consumer.py"
    assert item["source_id"] == "consumer.py::build#function"
    assert item["import_source_id"] == "consumer.py::__file__#file"
    assert item["import_target_id"] == "target.py::__file__#file"
    assert item["target_id"] == "target.py::Thing#class"
    assert item["status"] == "resolved"
    assert item["resolution"] == "import-resolved"
    assert item["raw"]["path"] == ["Thing"]
    assert item["binding"]["local_name"] == "Thing"
    assert [support["kind"] for support in item["support"]] == [
        "import_binding",
        "definition",
    ]


def test_graph_references_filters_before_counts_status_and_pagination(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    repo = _reference_repo(tmp_path, monkeypatch)

    unresolved = graph_references(
        repo,
        file="consumer.py",
        status="unresolved",
        limit=1,
    )
    second = graph_references(repo, offset=1, limit=1)
    empty = graph_references(repo, file="not-indexed.py", status="resolved")

    assert unresolved["counts"] == {
        "total": 2,
        "resolved": 1,
        "unresolved": 1,
        "returned": 1,
    }
    assert unresolved["items"][0]["raw"]["path"] == ["Lost"]
    assert unresolved["items"][0]["status"] == "unresolved"
    assert unresolved["items"][0]["unresolved_reason"] == "import_unresolved"
    assert unresolved["items"][0]["import_unresolved_reason"] == "not_indexed"
    assert unresolved["items"][0]["resolution"] is None
    assert unresolved["pagination"]["next_offset"] is None
    assert second["items"][0]["raw"]["path"] == ["Lost"]
    assert second["pagination"]["next_offset"] is None
    assert empty["counts"] == {
        "total": 0,
        "resolved": 0,
        "unresolved": 0,
        "returned": 0,
    }
    assert empty["items"] == []
    assert empty["pagination"]["next_offset"] is None


@pytest.mark.parametrize(
    ("kwargs", "field"),
    [
        ({"file": ""}, "file"),
        ({"file": "../consumer.py"}, "file"),
        ({"file": "./consumer.py"}, "file"),
        ({"file": "/consumer.py"}, "file"),
        ({"file": "consumer\\file.py"}, "file"),
        ({"file": 1}, "file"),
        ({"status": "RESOLVED"}, "status"),
        ({"status": None}, "status"),
        ({"status": []}, "status"),
        ({"offset": -1}, "offset"),
        ({"offset": True}, "offset"),
        ({"offset": "0"}, "offset"),
        ({"limit": 0}, "limit"),
        ({"limit": 501}, "limit"),
        ({"limit": True}, "limit"),
        ({"limit": "1"}, "limit"),
    ],
)
def test_graph_references_rejects_invalid_filters_and_pagination(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    kwargs: dict[str, object],
    field: str,
):
    repo = _reference_repo(tmp_path, monkeypatch)

    with pytest.raises(LociError) as exc_info:
        graph_references(repo, **kwargs)

    assert exc_info.value.code == "INVALID_INPUT"
    assert exc_info.value.details["field"] == field
