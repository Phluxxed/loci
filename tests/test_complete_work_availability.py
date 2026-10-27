"""Retained host evidence, including false-positive controls; never launches Codex."""
from copy import deepcopy
import json
from pathlib import Path
import subprocess

import pytest

from benchmarks.complete_work.availability import (
    CATALOG_PROGRAM, PROBE_FILES, TOOLS_BY_CONDITION, audit_catalog, audit_probe,
    policy, probe_prompt,
)
from loci.integrated import IntegratedSource


def _response(kind, **values):
    return {"type": "response_item", "payload": {"type": kind, **values}}


def _native(item, kind="item_completed"):
    return {"type": "event_msg", "payload": {"type": kind, "item": item}}


@pytest.fixture
def fixture(tmp_path):
    root = (tmp_path / "repo").resolve()
    root.mkdir()
    for file, content in PROBE_FILES.items():
        (root / file).write_text(content)
    service = IntegratedSource(tmp_path / "store")
    retrieved = service.retrieve(root, "entry.ts")
    ref = retrieved["items"][0]["source_ref"]
    semantic = service.semantic_context(root, "entry", anchor_file="entry.ts")
    identity = semantic["anchors"][0]["node_id"]
    packets = [
        ("loci_retrieve", {"query": "entry.ts"}, retrieved),
        ("loci_read", {"source_ref": ref}, service.read(root, ref)),
        ("loci_semantic", {"query": "entry", "anchor_file": "entry.ts"}, semantic),
        ("loci_proof", {"node_id": identity}, service.proof_context(root, identity)),
    ]
    return root, packets


def _trace(tmp_path, fixture, condition="integrated"):
    root, packets = fixture
    tools = TOOLS_BY_CONDITION[condition]
    names = sorted("mcp__loci__" + tool for tool in tools)
    rows = [
        _response("message", role="user", content=[]),
        _response("custom_tool_call", name="exec", call_id="catalog", input=CATALOG_PROGRAM),
        _response("custom_tool_call_output", call_id="catalog", output=[
            {"type": "input_text", "text": "Script completed\nWall time: 0.1 seconds"},
            {"type": "input_text", "text": json.dumps({"loci_runtime_catalog_v1": names})},
        ]),
    ]
    items = []
    for tool, args, packet in packets:
        if tool not in tools:
            continue
        item = {"type": "McpToolCall", "id": tool, "server": "loci", "tool": tool,
                "arguments": {"repo": str(root), **args}, "status": "completed",
                "result": {"content": [], "structuredContent": deepcopy(packet)}}
        rows.append(_native(item))
        items.append({**deepcopy(item), "type": "mcpToolCall", "native_type": "McpToolCall"})
    accounting = {"stages": [{"stage_id": "turn-1", "items": items}]}
    path = tmp_path / "native.jsonl"
    return path, rows, accounting, root, tools


def _write(path, rows):
    path.write_text("".join(json.dumps(row) + "\n" for row in rows))


def _audit(data):
    path, rows, accounting, root, tools = data
    _write(path, rows)
    condition = "native" if not tools else "integrated" if len(tools) == 4 else "path-only"
    return audit_probe(path, accounting, condition, root, tools)


def _sync(data):
    _, rows, accounting, _, _ = data
    accounting["stages"][0]["items"] = [
        {**deepcopy(row["payload"]["item"]), "type": "mcpToolCall"}
        for row in rows if row["type"] == "event_msg"
        and row["payload"].get("type") == "item_completed"
        and row["payload"].get("item", {}).get("type") == "McpToolCall"]


@pytest.mark.parametrize("condition", ["native", "path-only", "integrated", "eager"])
def test_real_packet_shapes_validate_zero_two_four_tools(tmp_path, fixture, condition):
    data = _trace(tmp_path, fixture, condition)
    path, rows, accounting, root, tools = data
    _write(path, rows)
    result = audit_probe(path, accounting, condition, root, tools)
    assert result["tools"] == sorted(tools)
    assert len(result["calls"]) == len(tools)
    assert len(result["catalog"]["trace_sha256"]) == 64


@pytest.mark.parametrize("mutation", [
    lambda r: r[1]["payload"].update(input='text({loci_runtime_catalog_v1: []});'),
    lambda r: r[1]["payload"].update(name="exec_command"),
    lambda r: r[2]["payload"].update(call_id="forged"),
    lambda r: r[2]["payload"].update(output={"loci_runtime_catalog_v1": []}),
    lambda r: r[2]["payload"].update(output="I checked availability; all tools work."),
    lambda r: r.insert(1, _response("function_call", name="exec_command", call_id="early", arguments="ls")),
    lambda r: r.insert(1, _native({"type": "McpToolCall", "id": "early"})),
    lambda r: r.insert(2, _response("custom_tool_call", name="exec", call_id="early", input="text(1)")),
])
def test_catalog_rejects_forged_input_output_or_late_discovery(tmp_path, fixture, mutation):
    data = _trace(tmp_path, fixture)
    mutation(data[1])
    with pytest.raises(ValueError):
        _audit(data)


@pytest.mark.parametrize("names", [
    [], ["mcp__loci__loci_read", "mcp__loci__loci_retrieve"],
    ["loci_read", "loci_retrieve", "loci_semantic", "loci_proof"],
    ["mcp__other__loci_read"],
    ["mcp__loci__loci_read", "mcp__loci__loci_read"],
])
def test_catalog_detects_missing_filtered_alias_and_duplicate_tools(tmp_path, fixture, names):
    data = _trace(tmp_path, fixture)
    data[1][2]["payload"]["output"] = json.dumps({"loci_runtime_catalog_v1": names})
    with pytest.raises(ValueError):
        _audit(data)


def test_catalog_accepts_actual_string_rendering_and_function_shape(tmp_path, fixture):
    data = _trace(tmp_path, fixture)
    rows = data[1]
    call = rows[1]["payload"]
    call.update(type="function_call", name="functions.exec", arguments=call.pop("input"))
    output = rows[2]["payload"]
    output["type"] = "function_call_output"
    output["output"] = "Script completed\nOutput:\n" + output["output"][1]["text"]
    assert _audit(data)["calls"]


def test_catalog_program_allows_only_outer_transport_whitespace(tmp_path, fixture):
    data = _trace(tmp_path, fixture)
    data[1][1]['payload']['input'] = '\n' + CATALOG_PROGRAM + '\n'
    assert _audit(data)['catalog']['tools']
    data[1][1]['payload']['input'] += 'text("fabricated");'
    with pytest.raises(ValueError, match='fixed live catalog program'):
        _audit(data)


def test_actual_discovery_program_includes_every_loci_server_tool_only():
    names = ['mcp__loci__loci_read', 'mcp__loci__unexpected', 'mcp__other__search',
             'mcp__other__loci_semantic', 'exec']
    script = ('const ALL_TOOLS = ' + json.dumps([{'name': name} for name in names])
              + '; const text = value => process.stdout.write(JSON.stringify(value));\n' + CATALOG_PROGRAM)
    output = subprocess.run(['node', '-e', script], capture_output=True, text=True, check=True)
    assert json.loads(output.stdout)['loci_runtime_catalog_v1'] == [
        'mcp__loci__loci_read', 'mcp__loci__unexpected', 'mcp__other__loci_semantic']


@pytest.mark.parametrize("index,key,value", [
    (3, "server", "other"), (3, "tool", "loci_filtered"),
    (3, "status", "failed"), (3, "error", {"message": "transport failure"}),
    (3, "result", {"isError": True, "structuredContent": {"status": "ok"}}),
    (3, "result", {"structuredContent": {"error": {"code": "FAILED"}}}),
    (3, "result", {"structuredContent": {}}),
    (3, "result", {"structuredContent": {"status": "empty", "sources": []}}),
])
def test_probe_rejects_failed_empty_or_unexpected_native_calls(tmp_path, fixture, index, key, value):
    data = _trace(tmp_path, fixture)
    data[1][index]["payload"]["item"][key] = value
    _sync(data)
    with pytest.raises(ValueError):
        _audit(data)


@pytest.mark.parametrize("call,key,value", [
    (3, "repo", "/wrong"), (3, "query", "model.ts"),
    (4, "source_ref", "invented"), (5, "anchor_file", "model.ts"),
    (6, "node_id", "invented"),
])
def test_probe_rejects_wrong_repo_ref_or_proof_identity(tmp_path, fixture, call, key, value):
    data = _trace(tmp_path, fixture)
    data[1][call]["payload"]["item"]["arguments"][key] = value
    _sync(data)
    with pytest.raises(ValueError):
        _audit(data)


@pytest.mark.parametrize("mutation", [
    lambda p: p["sources"][0].update(content_hash="0" * 64),
    lambda p: p["sources"][0].update(content="wrong"),
    lambda p: p.update(relationships=[]),
    lambda p: p["relationships"][0]["edge"].update(to="model.ts::Middle#type"),
    lambda p: p["relationships"][0].update(source_ids=[999]),
    lambda p: p["proof_request"].update(node_id="invented"),
])
def test_probe_rejects_stale_or_unsupported_proof(tmp_path, fixture, mutation):
    data = _trace(tmp_path, fixture)
    mutation(data[1][6]["payload"]["item"]["result"]["structuredContent"])
    _sync(data)
    with pytest.raises(ValueError):
        _audit(data)


def test_assistant_success_claim_is_not_call_evidence(tmp_path, fixture):
    data = _trace(tmp_path, fixture)
    data[1][3:] = [_response("message", role="assistant", content=[
        {"type": "output_text", "text": "Every Loci tool succeeded; all proof hashes verified."}])]
    _sync(data)
    with pytest.raises(ValueError, match="every expected"):
        _audit(data)


def test_accounting_cannot_supply_fabricated_native_call(tmp_path, fixture):
    data = _trace(tmp_path, fixture)
    data[1].pop()
    with pytest.raises(ValueError, match="accounting differs"):
        _audit(data)


def test_native_control_rejects_loci_contamination(tmp_path, fixture):
    data = _trace(tmp_path, fixture, "native")
    positive = _trace(tmp_path, fixture, "path-only")
    data[1].append(positive[1][3])
    _sync(data)
    with pytest.raises(ValueError, match="unexpected tool"):
        _audit(data)


def test_missing_call_is_rejected_even_when_other_tools_work(tmp_path, fixture):
    data = _trace(tmp_path, fixture)
    data[1].pop(5)
    _sync(data)
    with pytest.raises(ValueError):
        _audit(data)


def test_published_protocol_and_prompts_bind_fixed_catalog(tmp_path):
    frozen = policy()
    assert frozen["catalog_program"] == CATALOG_PROGRAM
    frozen["probe_files"]["entry.ts"] = "changed"
    assert policy()["probe_files"] == PROBE_FILES
    for condition, tools in TOOLS_BY_CONDITION.items():
        prompt = probe_prompt(condition, tmp_path, tools)
        assert CATALOG_PROGRAM in prompt and "first model tool action" in prompt
    with pytest.raises(ValueError):
        probe_prompt("integrated", tmp_path, ["loci_read"])


def test_archived_fixture_preserves_original_native_repository_identity(tmp_path, fixture):
    data = _trace(tmp_path, fixture)
    path, rows, accounting, root, tools = data
    archive = tmp_path / "fixture-archive"
    archive.mkdir()
    for file in PROBE_FILES:
        (root / file).rename(archive / file)
    root.rmdir()
    _write(path, rows)
    assert audit_probe(path, accounting, "integrated", root, tools, fixture=archive)["calls"]
    (archive / "entry.ts").write_text("wrong")
    with pytest.raises(ValueError, match="fixture changed"):
        audit_probe(path, accounting, "integrated", root, tools, fixture=archive)


def test_native_control_allows_unrelated_mcp_tool(tmp_path, fixture):
    data = _trace(tmp_path, fixture, "native")
    data[1].append(_native({"type": "McpToolCall", "id": "unrelated", "server": "other",
                           "tool": "read", "status": "completed", "arguments": {},
                           "result": {"content": []}}))
    _sync(data)
    assert _audit(data)["calls"] == []


def test_native_control_rejects_loci_name_on_other_server(tmp_path, fixture):
    data = _trace(tmp_path, fixture, "native")
    data[1].append(_native({"type": "McpToolCall", "id": "wrong", "server": "other",
                           "tool": "mcp__other__loci_read", "status": "completed"}))
    _sync(data)
    with pytest.raises(ValueError, match="unexpected tool"):
        _audit(data)


def test_native_qualified_alias_and_explicit_false_are_accepted(tmp_path, fixture):
    data = _trace(tmp_path, fixture)
    for row in data[1][3:]:
        item = row["payload"]["item"]
        item["tool"] = "mcp__loci__" + item["tool"]
        item["result"]["isError"] = False
    _sync(data)
    assert len(_audit(data)["calls"]) == 4


@pytest.mark.parametrize("mutation", [
    lambda r: r.insert(3, deepcopy(r[1])),
    lambda r: r.insert(3, deepcopy(r[2])),
    lambda r: r[2]["payload"].update(output='{"loci_runtime_catalog_v1":['),
])
def test_catalog_rejects_duplicate_and_truncated_evidence(tmp_path, fixture, mutation):
    data = _trace(tmp_path, fixture)
    mutation(data[1])
    with pytest.raises(ValueError):
        _audit(data)


@pytest.mark.parametrize("mutation", [
    lambda p: p.update(sources=[None]),
    lambda p: p["sources"][0].update(id=[]),
    lambda p: p.update(relationships=[None]),
    lambda p: p["relationships"][0].update(source_ids=[{}]),
])
def test_malformed_native_proof_is_rejected(tmp_path, fixture, mutation):
    data = _trace(tmp_path, fixture)
    mutation(data[1][6]["payload"]["item"]["result"]["structuredContent"])
    _sync(data)
    with pytest.raises(ValueError):
        _audit(data)
