from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from benchmarks.complete_work.runtime import AppServer, Journal, RuntimeFailure


def _server_script(body: str) -> list[str]:
    return [sys.executable, "-u", "-c", body]


def _rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_initialize_buffers_notifications_and_preserves_wire_journal(tmp_path: Path) -> None:
    script = '''
import json, sys
for line in sys.stdin:
    message = json.loads(line)
    if message["method"] == "initialize":
        print(json.dumps({"method": "thread/notice", "params": {"value": 1}}), flush=True)
        print(json.dumps({"id": message["id"], "result": {"server": "ready"}}), flush=True)
    elif message["method"] == "ping":
        print(json.dumps({"id": message["id"], "result": {"pong": True}}), flush=True)
'''
    journal_path = tmp_path / "wire.jsonl"
    journal = Journal(journal_path)
    server = AppServer(_server_script(script), journal, tmp_path / "stderr.txt", cwd=tmp_path)
    try:
        assert server.initialize() == {"server": "ready"}
        assert server.next_event(1) == {"method": "thread/notice", "params": {"value": 1}}
        assert server.call("ping", {"value": 2}, timeout=1) == {"pong": True}
    finally:
        server.close()
        journal.close()
    rows = _rows(journal_path)
    assert [row["ordinal"] for row in rows] == list(range(1, len(rows) + 1))
    assert [row["direction"] for row in rows].count("sent") == 3
    assert [row["direction"] for row in rows].count("received") == 3
    assert rows[0]["message"]["method"] == "initialize"
    assert any(row["message"].get("method") == "thread/notice" for row in rows)


@pytest.mark.parametrize(
    ("script", "match"),
    [
        ("import sys; print('not json', flush=True)", "Expecting value"),
        ("import json,sys; print(json.dumps({'id':'server','method':'approval/request','params':{}}), flush=True)", "unexpected server request"),
    ],
)
def test_malformed_or_server_request_is_a_useful_transport_failure(tmp_path: Path, script: str, match: str) -> None:
    journal = Journal(tmp_path / "wire.jsonl")
    server = AppServer(_server_script(script), journal, tmp_path / "stderr.txt", cwd=tmp_path)
    try:
        with pytest.raises(RuntimeFailure, match=match):
            server.call("initialize", {}, timeout=1)
    finally:
        server.close()
        journal.close()
    rows = _rows(tmp_path / "wire.jsonl")
    assert rows[0]["direction"] == "sent"
    assert rows[0]["message"]["method"] == "initialize"


def test_stream_close_and_close_are_retained_as_failures_without_retry(tmp_path: Path) -> None:
    journal = Journal(tmp_path / "wire.jsonl")
    server = AppServer(_server_script(""), journal, tmp_path / "stderr.txt", cwd=tmp_path)
    try:
        with pytest.raises(RuntimeFailure, match="stream closed"):
            server.call("initialize", {}, timeout=1)
        assert server.sequence == 1
    finally:
        server.close()
        journal.close()
    rows = _rows(tmp_path / "wire.jsonl")
    assert len(rows) == 1
    assert rows[0]["message"]["id"] == 1
