"""Acceptance for the fixed complete-work graph control and source receipts."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from mcp.types import CallToolResult
import pytest

from benchmarks.complete_work.control import (
    ControlConfig,
    ReceiptStore,
    load_receipts,
    receipt_source_bytes,
)


ROOT = Path(__file__).parents[1]


def _write_config(
    path: Path,
    *,
    target: Path,
    arm: str,
    store: Path,
    receipts: Path,
) -> None:
    path.write_text(json.dumps({
        "schema_version": 1,
        "target_root": str(target.resolve()),
        "arm": arm,
        "store_dir": str(store.resolve()),
        "receipt_dir": str(receipts.resolve()),
        "store_namespace": "complete-work-control-v1",
    }), encoding="utf-8")


@pytest.mark.parametrize("arm", ["on", "off"])
def test_retired_graph_arms_fail_before_store_or_server_startup(tmp_path: Path, arm: str) -> None:
    from benchmarks.complete_work.control import create_server, prepare_target_index

    target = tmp_path / "target"
    target.mkdir()
    config_path = tmp_path / "config.json"
    store = tmp_path / "store"
    _write_config(config_path, target=target, arm=arm,
                  store=store, receipts=tmp_path / "receipts")
    config = ControlConfig.load(config_path)
    for operation in (create_server, prepare_target_index):
        with pytest.raises(ValueError, match="pinned legacy"):
            operation(config)
    assert not store.exists()


def test_receipt_validation_turns_a_bad_extent_into_a_retained_failure(tmp_path: Path) -> None:
    repo = tmp_path / "target"
    repo.mkdir()
    raw = b"value = 1\n"
    (repo / "sample.py").write_bytes(raw)
    config_path = tmp_path / "config.json"
    receipts = tmp_path / "receipts"
    _write_config(
        config_path,
        target=repo,
        arm="off",
        store=tmp_path / "store",
        receipts=receipts,
    )
    store = ReceiptStore(ControlConfig.load(config_path))
    bad = CallToolResult(content=[], structured_content={
        "schema_version": 1,
        "status": "ok",
        "source": {
            "file": "sample.py",
            "content_hash": hashlib.sha256(raw).hexdigest(),
            "start_byte": 0,
            "end_byte": len(raw),
            "start_line": 1,
            "end_line": 1,
            "content": "wrong\n",
        },
    }, is_error=False)
    returned = store.record(
        "loci_read", {"repo": str(repo), "source_ref": "test"}, bad,
        started_unix_ns=1,
    )
    assert returned.is_error is True
    assert returned.structured_content["error"]["code"] == "SOURCE_RECEIPT_FAILED"
    receipt = load_receipts(receipts)[0]
    assert receipt["operation_outcome"] == "success"
    assert receipt["outcome"] == "error"
    assert receipt["validation"]["status"] == "failed"
    assert receipt["operation_packet"] != receipt["packet"]
    assert receipt_source_bytes(receipts, hashlib.sha256(raw).hexdigest()) == raw


def test_config_rejects_target_that_contains_control_and_oracles(tmp_path: Path) -> None:
    config = tmp_path / "unsafe.json"
    _write_config(
        config,
        target=ROOT,
        arm="on",
        store=tmp_path / "store",
        receipts=tmp_path / "receipts",
    )
    with pytest.raises(ValueError, match="control/oracle"):
        ControlConfig.load(config)
