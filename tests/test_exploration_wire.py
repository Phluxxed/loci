from __future__ import annotations

import json
import os
from pathlib import Path
import select
import subprocess
import sys
import tempfile


def _send(process: subprocess.Popen[bytes], message: dict) -> None:
    assert process.stdin is not None
    process.stdin.write(
        (json.dumps(message, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
    )
    process.stdin.flush()


def _receive(process: subprocess.Popen[bytes], timeout: float = 30.0) -> tuple[bytes, dict]:
    assert process.stdout is not None
    ready, _, _ = select.select([process.stdout], [], [], timeout)
    if not ready:
        raise TimeoutError("MCP subprocess produced no JSON-RPC response")
    raw_line = process.stdout.readline()
    if not raw_line:
        raise AssertionError("MCP subprocess closed stdout before responding")
    return raw_line, json.loads(raw_line.decode("utf-8"))


def _result_value_bytes(raw_line: bytes) -> tuple[dict, bytes]:
    """Decode result while measuring the exact original JSON value bytes."""
    text = raw_line.decode("utf-8")
    marker = '"result"'
    marker_start = text.find(marker)
    assert marker_start >= 0, raw_line
    colon = text.find(":", marker_start + len(marker))
    assert colon >= 0, raw_line
    value_start = colon + 1
    while text[value_start].isspace():
        value_start += 1
    value, value_end = json.JSONDecoder().raw_decode(text, value_start)
    assert isinstance(value, dict)
    return value, text[value_start:value_end].encode("utf-8")


def test_loci_explore_wire_bytes_preserve_unicode_clipped_source() -> None:
    with tempfile.TemporaryDirectory(prefix="loci-wire-explore-") as directory:
        root = Path(directory)
        repo = root / "repo"
        repo.mkdir()
        source_path = repo / "café.ts"
        source_path.write_text(
            "function café(): void {\n" + "// 世界 π\n" * 1000 + "}\n",
            encoding="utf-8",
        )
        cache = root / "store"
        env = os.environ.copy()
        env.update({
            "LOCI_BASE_DIR": str(cache),
            "LOCI_STORE_NAMESPACE": "wire-test",
            "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src"),
        })
        process = subprocess.Popen(
            [sys.executable, "-m", "loci.mcp_server"],
            cwd=Path(__file__).resolve().parents[1],
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        try:
            _send(process, {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2026-07-28",
                    "capabilities": {},
                    "clientInfo": {"name": "wire-test", "version": "0"},
                },
            })
            _, initialized = _receive(process)
            assert initialized["id"] == 1
            _send(process, {
                "jsonrpc": "2.0",
                "method": "notifications/initialized",
                "params": {},
            })
            _send(process, {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {
                    "name": "loci_explore",
                    "arguments": {
                        "repo": str(repo),
                        "intent": "locate",
                        "seed_ids": ["café.ts::café#function"],
                        "max_output_bytes": 2048,
                    },
                },
            })
            raw_line, response = _receive(process)
            assert response["id"] == 2
            raw_result, result_value_bytes = _result_value_bytes(raw_line)
            assert set(raw_result) == {"content", "isError", "structuredContent"}
            assert raw_result["isError"] is False
            structured = raw_result["structuredContent"]
            assert structured["usage"]["output_bytes"] == len(result_value_bytes)
            assert len(result_value_bytes) <= 2048
            assert structured["items"][0]["complete"] is False
            assert structured["omissions"] == [{"reason": "source_clipped", "count": 1}]
            source = structured["sources"][0]
            fixture_bytes = source_path.read_bytes()
            assert source["content"].encode("utf-8") == fixture_bytes[
                source["start_byte"]:source["end_byte"]
            ]
            assert source["content"].startswith("function café(): void {")
            assert source["content"].endswith("\n")
        finally:
            if process.stdin is not None:
                process.stdin.close()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
            if process.returncode != 0:
                stderr = process.stderr.read().decode("utf-8", errors="replace") if process.stderr else ""
                raise AssertionError(f"MCP subprocess exited {process.returncode}: {stderr[-2000:]}")
