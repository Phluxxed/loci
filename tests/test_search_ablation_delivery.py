"""Focused independent coverage and source-protection checks for the ablation."""
import hashlib
import json
from pathlib import Path

import pytest

from evals.search_ablation import delivery


def _fixture(tmp_path, *, start=1, end=120):
    root = tmp_path / "repo"
    root.mkdir()
    raw = ("# exact UTF-8: café 🌳 with quoted \"content\" and backslash \\\n" * 120).encode()
    (root / "entry.py").write_bytes(raw)
    required = b"".join(raw.splitlines(keepends=True)[start - 1:end])
    case = {"id": "synthetic", "file": "entry.py", "start_line": start,
            "end_line": end, "content_sha256": hashlib.sha256(required).hexdigest()}
    config = {"source_root": root, "output_dir": tmp_path / "private"}
    return root, raw, case, config


@pytest.mark.parametrize("mode", ["r1", "direct"])
def test_exact_required_bytes_and_envelope_accounting(tmp_path, monkeypatch, mode):
    root, raw, case, config = _fixture(tmp_path, start=3, end=105)
    monkeypatch.setattr(delivery, "DIRECT_MAX_BYTES", 501)
    monkeypatch.setattr(delivery, "DIRECT_MAX_LINES", 4)
    result = delivery.run_case(case, mode, config)
    assert result["error"] is None
    assert result["complete"]
    assert result["required_sha256"] == result["delivered_required_sha256"]
    assert result["covered_required_bytes"] == result["required_bytes"]
    receipt = json.loads(Path(result["receipt_path"]).read_bytes())
    assert result["tool_calls"] == len(receipt["packets"])
    assert result["encoded_output_bytes"] == sum(len(delivery._canonical(
        {"content": [], "structuredContent": row["packet"], "isError": False}))
        for row in receipt["packets"])
    assert result["elapsed_ns"] > 0
    if mode == "direct":
        assert result["tool_calls"] > 1
        assert result["extra_source_bytes"] == result["duplicate_source_bytes"] == 0
        assert not result["source_extent_complete"]
        for row in receipt["packets"]:
            source = row["packet"]["source"]
            assert len(source["content"].encode()) <= 501
            assert source["content"].count("\n") <= 4
    else:
        assert result["extra_source_bytes"] > 0
        assert result["duplicate_source_bytes"] > 0  # initial preview is redelivered
    # The scorer compares original byte positions, not only claimed metadata.
    forged = {"file": "entry.py", "content_hash": hashlib.sha256(raw).hexdigest(),
              "start_byte": 0, "end_byte": 1, "content": "x"}
    with pytest.raises(ValueError, match="independent original bytes"):
        delivery._coverage([forged], raw, "entry.py", 0, 1)


@pytest.mark.parametrize("mode", ["r1", "direct"])
def test_change_during_delivery_is_retained_as_failure(tmp_path, monkeypatch, mode):
    root, raw, case, config = _fixture(tmp_path)
    if mode == "direct":
        monkeypatch.setattr(delivery, "DIRECT_MAX_BYTES", 500)
        original = delivery._direct_page

        def changed(*args):
            page = original(*args)
            (root / "entry.py").write_bytes(raw.replace(b"exact", b"other"))
            return page

        monkeypatch.setattr(delivery, "_direct_page", changed)
    else:
        original = delivery.IntegratedSource.retrieve

        def changed(*args, **kwargs):
            packet = original(*args, **kwargs)
            (root / "entry.py").write_bytes(raw.replace(b"exact", b"other"))
            return packet

        monkeypatch.setattr(delivery.IntegratedSource, "retrieve", changed)
    result = delivery.run_case(case, mode, config)
    assert not result["complete"]
    assert result["error"]["code"] == "SOURCE_STALE"
    assert result["tool_calls"] == 2
    assert 0 < result["covered_required_bytes"] < result["required_bytes"]
    receipt = json.loads(Path(result["receipt_path"]).read_bytes())
    assert receipt["packets"][-1]["packet"]["error"]["code"] == "SOURCE_STALE"


@pytest.mark.parametrize("mode", ["r1", "direct"])
def test_symlink_containment_and_frozen_case_hash(tmp_path, mode):
    root, raw, case, config = _fixture(tmp_path)
    case["content_sha256"] = "0" * 64
    result = delivery.run_case(case, mode, config)
    assert result["error"]["code"] == "FIXTURE_STALE" and result["tool_calls"] == 0
    outside = tmp_path / "outside.py"
    outside.write_bytes(raw)
    (root / "entry.py").unlink()
    (root / "entry.py").symlink_to(outside)
    case["content_sha256"] = hashlib.sha256(raw).hexdigest()
    result = delivery.run_case(case, mode, config)
    assert not result["complete"] and result["error"]["code"] == "SOURCE_UNAVAILABLE"


def test_full_refresh_control_uses_existing_inventory_with_identical_pages(tmp_path, monkeypatch):
    root, raw, case, config = _fixture(tmp_path, start=3, end=105)
    monkeypatch.setattr(delivery, "DIRECT_MAX_BYTES", 501)
    refreshes = []
    original = delivery.IntegratedSource.index_repo

    def refresh(service, repo):
        result = original(service, repo)
        refreshes.append(result)
        return result

    monkeypatch.setattr(delivery.IntegratedSource, "index_repo", refresh)
    plain = delivery.run_case(case, "direct", config)
    assert refreshes == []
    controlled = delivery.run_case(case, "direct_full_refresh", config)
    assert plain["error"] is controlled["error"] is None
    assert plain["complete"] and controlled["complete"]
    assert len(refreshes) == controlled["tool_calls"] > 1
    assert all(row["files_indexed"] == 1 and row["bytes_scanned"] == len(raw)
               for row in refreshes)
    assert plain["delivered_required_sha256"] == controlled["delivered_required_sha256"]
    assert plain["encoded_output_bytes"] == controlled["encoded_output_bytes"]
    packets = [json.loads(Path(row["receipt_path"]).read_bytes())["packets"]
               for row in (plain, controlled)]
    assert packets[0] == packets[1]
