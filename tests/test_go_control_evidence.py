from __future__ import annotations

import hashlib
from pathlib import Path
from types import SimpleNamespace

import pytest

from loci.exploration import _ControlEvidence, _Source


class _Store:
    def __init__(self, files: dict[str, bytes]) -> None:
        self.files = files

    def get_file_content(self, _repo: Path, path: str) -> dict[str, str] | None:
        data = self.files.get(path)
        return None if data is None else {"content": data.decode("utf-8")}


def _source(repo: Path, files: dict[str, bytes], nodes: dict[str, dict] | None = None) -> _Source:
    return _Source(repo, _Store(files), nodes or {})


def test_go_control_evidence_delivers_complete_bytes_including_trailing_lines(tmp_path: Path):
    data = b"module example.com/demo\n\ngo 1.23\n\n"
    (tmp_path / "go.mod").write_bytes(data)

    span = _source(tmp_path, {}).control(
        _ControlEvidence("go.mod", hashlib.sha256(data).hexdigest())
    )

    assert (span.start_byte, span.end_byte, span.start_line, span.end_line) == (0, len(data), 1, 4)
    assert span.content.encode("utf-8") == data


@pytest.mark.parametrize("mode", ["changed", "missing", "symlink"])
def test_go_control_evidence_fails_closed_when_current_file_is_not_the_indexed_control(
    tmp_path: Path, mode: str,
):
    data = b"module example.com/demo\n"
    control = tmp_path / "go.mod"
    control.write_bytes(data)
    evidence = _ControlEvidence("go.mod", hashlib.sha256(data).hexdigest())
    if mode == "changed":
        control.write_bytes(b"module example.com/changed\n")
    elif mode == "missing":
        control.unlink()
    else:
        target = tmp_path / "real.mod"
        target.write_bytes(data)
        control.unlink()
        control.symlink_to(target)

    with pytest.raises(ValueError):
        _source(tmp_path, {}).control(evidence)


def test_go_import_binding_evidence_is_the_complete_grouped_declaration(tmp_path: Path):
    data = (
        b"package app\n\n"
        b"import (\n"
        b"\t\"example.com/one\"\n"
        b"\talias \"example.com/two\"\n"
        b")\n\n"
        b"func Run() {}\n"
    )
    digest = hashlib.sha256(data).hexdigest()
    nodes = {
        "app/main.go::__file__#file": {
            "kind": "file", "file_path": "app/main.go", "language": "go",
            "content_hash": digest,
        }
    }
    support = SimpleNamespace(
        kind="import_binding", file="app/main.go", line=4,
        content_hash=digest, endpoint_id=None,
    )

    span = _source(tmp_path, {"app/main.go": data}, nodes).support(support)

    start = data.index(b"import (")
    end = data.index(b")\n") + 1
    assert (span.start_byte, span.end_byte) == (start, end)
    assert span.content.encode("utf-8") == data[start:end]
