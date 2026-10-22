"""Exact-source harness integration and retained replay."""
from __future__ import annotations

import json
import subprocess
import sys

import pytest

from benchmarks.architecture import ROOT, verify
from benchmarks.architecture_reads import build_small_suite, check_case, comparable


def test_exact_source_fresh_reader_isolated_replay_and_negative_inventory(tmp_path):
    suite = build_small_suite(tmp_path / "suite")
    output = tmp_path / "direct"
    result = subprocess.run([
        sys.executable, "-B", "-m", "benchmarks.architecture", "run", "--output", str(output),
        "--corpus", str(suite), "--operation", "exact-source", "--mechanism", "service.read baseline",
        "--read-file", "imported_interface:unicode.md", "--read-negatives",
    ], cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr + (output / "result.json").read_text()
    report = json.loads((output / "result.json").read_text())
    assert report["operation"] == "exact-source"
    assert report["mechanism"] == "service.read baseline"
    assert report["primary_unchanged"]
    assert report["comparisons"][0]["exact_output_equivalent"]
    assert all(row["status"] == "completed" for row in report["runs"])
    assert len({row["binding"]["store_id"] for row in report["runs"]}) == 2
    for row in report["runs"]:
        assert row["enrichment"] == "on"
        assert row["phase_totals"]["indexing"]["operations"] == 1
        assert row["phase_totals"]["first_read"]["operations"] == 1
        assert row["phase_totals"]["repeat_read"]["operations"] == 1
        assert row["phase_totals"]["read_without_refresh"]["operations"] == 1
        assert row["phase_totals"]["freshness_restore"]["operations"] == 1
        assert (row["observed_service_calls"]["store_load"]
                + row["observed_service_calls"]["store_load_source_index"]) >= 1
        assert row["process_resources"]["peak_rss_bytes"] > 0
        assert row["index_process_resources"]["peak_rss_bytes"] > 0
        assert row["cases"][0]["case_id"] == "read-1"
        receipt = json.loads((output / row["cases"][0]["packets"]).read_text())
        assert len(receipt["pages"]) > 1
        assert {"foreign", "extent", "hash", "unindexed", "malformed",
                "stale", "stale_refresh", "outside_symlink", "utf8_boundary"} <= receipt["negatives"].keys()
    assert verify(output) == 0
    packet = output / report["runs"][0]["cases"][0]["packets"]
    packet.write_text("{}")
    with pytest.raises(ValueError, match="inventory/hash mismatch"):
        verify(output)


def test_independent_read_check_rejects_truncated_and_misaccounted_pages(tmp_path):
    repo = tmp_path / "source"
    repo.mkdir()
    raw = b"alpha\nbeta\n"
    (repo / "a.md").write_bytes(raw)
    request = {"case_id": "read-1", "file": "a.md", "size": len(raw), "negatives": True,
               "sha256": __import__("hashlib").sha256(raw).hexdigest()}
    page = {"schema_version": 1, "status": "ok", "complete": True, "next_source_ref": None,
            "source": {"id": 1, "file": "a.md", "start_byte": 0, "end_byte": len(raw),
                       "start_line": 1, "end_line": 2, "content_hash": request["sha256"],
                       "content": raw.decode(), "source_ref": "sr1_example"},
            "usage": {"evidence_bytes": len(raw), "output_bytes": 0,
                      "output_encoding": "mcp_result_json_utf8"}}
    envelope = {"content": [], "structuredContent": page, "isError": False}
    for _ in range(4):
        page["usage"]["output_bytes"] = len(json.dumps(envelope, ensure_ascii=False,
                                                         separators=(",", ":")).encode())
    names = {"foreign": "INVALID_SOURCE_REF", "extent": "INVALID_SOURCE_REF",
             "hash": "SOURCE_STALE", "unindexed": "INVALID_SOURCE_REF",
             "malformed": "INVALID_SOURCE_REF", "stale": "SOURCE_STALE",
             "stale_refresh": "SOURCE_STALE", "outside_symlink": "SOURCE_UNAVAILABLE"}
    receipt = {"pages": [page], "repeat": page, "without_refresh": page,
               "negatives": {name: {"code": code, "message": name, "details": {}}
                             for name, code in names.items()}}
    assert check_case(repo, request, receipt)["integrity_ok"]
    assert comparable(receipt)["pages"][0]["source"]["content"] == raw.decode()
    page["source"]["content"] = "wrong"
    with pytest.raises(ValueError):
        check_case(repo, request, receipt)


def test_frozen_small_suite_resolver_controls_are_readable(tmp_path):
    suite = build_small_suite(tmp_path / "suite")
    output = tmp_path / "controls"
    command = [sys.executable, "-B", "-m", "benchmarks.architecture", "run",
               "--output", str(output), "--corpus", str(suite), "--operation", "exact-source",
               "--mechanism", "service.read resolver controls"]
    for file in ("go.mod", "Cargo.toml", "jsconfig.json"):
        command.extend(("--read-file", f"imported_interface:{file}"))
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr + (output / "result.json").read_text()
    report = json.loads((output / "result.json").read_text())
    assert report["comparisons"][0]["exact_output_equivalent"]
    assert all([case["file"] for case in json.loads((output / run["capability"]).read_text())]
               == ["go.mod", "Cargo.toml", "jsconfig.json"] for run in report["runs"])
    assert verify(output) == 0
