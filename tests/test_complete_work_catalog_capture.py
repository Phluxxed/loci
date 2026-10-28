"""Native registry capture contracts, with local native-tool mocks only."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess

import pytest

from benchmarks.complete_work import availability


def _catalog(path, values):
    raw = json.dumps(values, ensure_ascii=False, separators=(",", ":")).encode() + b"\n"
    path.write_bytes(raw)
    return raw


def _run(destination, values, failure=None):
    wrapper = r'''
const fs = require("node:fs"), cp = require("node:child_process");
const ALL_TOOLS = JSON.parse(fs.readFileSync(0, "utf8"));
const failure = FAILURE;
const text = value => process.stdout.write(JSON.stringify(value));
const tools = {
  apply_patch: async patch => {
    if (failure === "write") throw new Error("private full description must not leak");
    const prefix = "*** Begin Patch\n*** Add File: " + DESTINATION + "\n+";
    if (!patch.startsWith(prefix) || !patch.endsWith("\n*** End Patch")) throw new Error("patch mismatch");
    fs.writeFileSync(DESTINATION, patch.slice(prefix.length, -"\n*** End Patch".length) + "\n");
    if (failure === "tamper") fs.appendFileSync(DESTINATION, " ");
    return {};
  },
  exec_command: async args => {
    if (failure === "read") return {exit_code: 1, output: "private details"};
    if (failure === "json") return {exit_code: 0, output: "wrong"};
    if (failure === "shape") return {exit_code: 0, output: JSON.stringify({count: 1, sha256: "0".repeat(64)})};
    const completed = cp.spawnSync(args.cmd, {shell: true, encoding: "utf8"});
    return {exit_code: completed.status, output: completed.stdout};
  }
};
(async () => { PROGRAM })().catch(error => {process.stderr.write(error.message); process.exitCode = 1;});
'''
    wrapper = wrapper.replace("FAILURE", json.dumps(failure)).replace("DESTINATION", json.dumps(str(destination)))
    wrapper = wrapper.replace("PROGRAM", availability.capture_program(destination))
    return subprocess.run(["node", "-e", wrapper], input=json.dumps(values), capture_output=True,
                          text=True, cwd=destination.parent)


def test_capture_large_catalog_retains_bytes_without_model_output_dump(tmp_path):
    destination = tmp_path / "common-tool-catalog.json"
    values = [{"name": f"tool_{i:04}", "description": ('café 中文 🙂 "quotes"\n' * 100)} for i in range(600)]
    completed = _run(destination, list(reversed(values)) + [{"name": "mcp__loci__loci_read", "description": "excluded"}])
    assert completed.returncode == 0, completed.stderr
    raw = destination.read_bytes()
    assert len(raw) > 800_000
    assert json.loads(raw) == values
    receipt = json.loads(completed.stdout)
    assert receipt == {"loci_runtime_catalog_v1": ["mcp__loci__loci_read"],
                       "common_runtime_catalog_v1": {"count": 600, "sha256": hashlib.sha256(raw[:-1]).hexdigest()},
                       "native_access_v1": {"apply_patch": True, "exec_command": True}}
    assert len(completed.stdout) < 350
    assert "café" not in completed.stdout


@pytest.mark.parametrize("failure", ["write", "read", "json", "shape", "tamper"])
def test_capture_failure_is_bounded_and_fails_closed(tmp_path, failure):
    completed = _run(tmp_path / "common-tool-catalog.json", [{"name": "tool", "description": "private"}], failure)
    assert completed.returncode != 0
    assert completed.stdout == ""
    assert "Catalog capture failed:" in completed.stderr
    assert "private" not in completed.stderr


def test_readback_quotes_path_and_cannot_import_project_modules(tmp_path, monkeypatch):
    observer = tmp_path / "observer 'quoted' 中文"
    observer.mkdir()
    (observer / "json.py").write_text("raise RuntimeError('project module loaded')")
    (observer / "sitecustomize.py").write_text("raise RuntimeError('project startup loaded')")
    monkeypatch.setenv("PYTHONPATH", str(observer))
    completed = _run(observer / "common-tool-catalog.json", [{"name": "tool", "description": "private"}])
    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout)["native_access_v1"]["exec_command"] is True


@pytest.mark.parametrize("value", [[], [{"name": "a"}], [{"name": "a", "description": 4}],
                                    [{"name": "a", "description": "x", "extra": True}],
                                    [{"name": "mcp__loci__loci_read", "description": "x"}],
                                    [{"name": "z", "description": "x"}, {"name": "a", "description": "y"}],
                                    [{"name": "a", "description": "x"}, {"name": "a", "description": "y"}]])
def test_artifact_rejects_invalid_shape_order_duplicates_and_loci(tmp_path, value):
    artifact = tmp_path / "common-tool-catalog.json"
    _catalog(artifact, value)
    with pytest.raises(ValueError, match="catalog artifact"):
        availability._catalog_artifact(artifact)


def test_artifact_missing_and_catalog_difference_do_not_return_descriptions(tmp_path):
    left, right = tmp_path / "left", tmp_path / "right"
    with pytest.raises(ValueError, match="missing or malformed"):
        availability._catalog_artifact(left)
    _catalog(left, [{"name": "a", "description": "secret old"}, {"name": "b", "description": "gone"}])
    _catalog(right, [{"name": "a", "description": "secret new"}, {"name": "c", "description": "added"}])
    difference = availability.catalog_difference(left, right)
    assert difference == {"added": ["c"], "removed": ["b"], "changed": [{
        "name": "a", "left_sha256": hashlib.sha256(b"secret old").hexdigest(),
        "right_sha256": hashlib.sha256(b"secret new").hexdigest()}]}
    assert "secret" not in json.dumps(difference)


def test_capture_policy_is_explicit_and_legacy_policy_unchanged(tmp_path):
    legacy = availability.context_policy("rules")
    capture = availability.capture_policy("rules")
    assert legacy["schema"] == "r1-common-context-v1"
    assert capture["schema"] == "r1-common-context-v2"
    assert capture["root_agents_md"] == legacy["root_agents_md"]
    assert availability.COMMON_CATALOG_PROGRAM in legacy["measured_prefix"]
    path = tmp_path / "has 'quotes'" / "common-tool-catalog.json"
    assert availability.capture_program(path) in availability.capture_prefix(path)
    assert "python3 -I -c" in availability.capture_check_command(path)
    with pytest.raises(ValueError, match="absolute"):
        availability.capture_program(Path("common-tool-catalog.json"))


def _trace(tmp_path):
    destination = Path("/original/observer/common-tool-catalog.json")
    artifact = tmp_path / "common-tool-catalog.json"
    raw = _catalog(artifact, [{"name": "a", "description": "full private description"}])
    fingerprint = {"count": 1, "sha256": hashlib.sha256(raw[:-1]).hexdigest()}
    receipt = {"loci_runtime_catalog_v1": [], "common_runtime_catalog_v1": fingerprint,
               "native_access_v1": {"apply_patch": True, "exec_command": True}}
    def response(kind, **values):
        return {"type": "response_item", "payload": {"type": kind, **values}}
    def event(item):
        return {"type": "event_msg", "payload": {"type": "item_completed", "item": item}}
    rows = [response("custom_tool_call", name="exec", call_id="first", input=availability.capture_program(destination)),
            event({"type": "FileChange", "id": "write", "status": "completed", "stderr": "",
                   "changes": {str(destination): {"type": "add", "content": raw.decode()}}}),
            event({"type": "CommandExecution", "id": "check", "status": "completed", "exit_code": 0,
                   "command": ["/bin/zsh", "-lc", availability.capture_check_command(destination)],
                   "aggregated_output": json.dumps(fingerprint) + "\n"}),
            response("custom_tool_call_output", call_id="first", output=json.dumps(receipt))]
    return tmp_path / "trace.jsonl", rows, artifact, destination


def _audit(data):
    trace, rows, artifact, destination = data
    trace.write_text("".join(json.dumps(row) + "\n" for row in rows))
    return availability.audit_catalog(trace, [], common_context=True,
                                      catalog_artifact=artifact, catalog_destination=destination)


def test_first_native_receipt_binds_replayed_artifact_and_native_operations(tmp_path):
    data = _trace(tmp_path)
    result = _audit(data)
    assert result["catalog_artifact"] == {"filename": "common-tool-catalog.json", "bytes": data[2].stat().st_size,
                                          "sha256": hashlib.sha256(data[2].read_bytes()).hexdigest()}
    assert result["native_access_v1"] == {"apply_patch": True, "exec_command": True}
    assert str(tmp_path) not in json.dumps(result)
    assert "private" not in json.dumps(result)
    # A replay may relocate the artifact while the native write identity stays fixed.
    moved = tmp_path / "archive" / "common-tool-catalog.json"
    moved.parent.mkdir()
    moved.write_bytes(data[2].read_bytes())
    assert _audit((data[0], data[1], moved, data[3])) == result


def test_capture_audit_accepts_joined_native_started_events(tmp_path):
    data = _trace(tmp_path)
    for at in (2, 1):
        start = deepcopy(data[1][at])
        start["payload"]["type"] = "item_started"
        start["payload"]["item"]["status"] = "inProgress"
        data[1].insert(at, start)
    assert _audit(data)["native_access_v1"]["apply_patch"] is True


@pytest.mark.parametrize("mutation", [
    lambda rows: rows[0]["payload"].update(input=availability.COMMON_CATALOG_PROGRAM),
    lambda rows: rows[-1]["payload"].update(call_id="another"),
    lambda rows: rows[1]["payload"]["item"]["changes"].update({"/other/file": {"type": "add", "content": "wrong"}}),
    lambda rows: rows[1]["payload"]["item"].update(status="failed"),
    lambda rows: rows[2]["payload"]["item"].update(command=["/bin/zsh", "-lc", "cat /other/file"]),
    lambda rows: rows[2]["payload"]["item"].update(exit_code=1),
    lambda rows: rows[2]["payload"]["item"].update(aggregated_output='{"count":1,"sha256":"wrong"}'),
    lambda rows: rows.insert(2, {"type": "event_msg", "payload": {"type": "item_completed", "item": {"type": "McpToolCall"}}}),
    lambda rows: rows.insert(2, {"type": "response_item", "payload": {"type": "custom_tool_call", "name": "exec", "call_id": "extra", "input": "text(1)"}}),
    lambda rows: rows.insert(2, deepcopy(rows[1])),
    lambda rows: rows.pop(1),
    lambda rows: rows.__setitem__(slice(1, 3), list(reversed(rows[1:3]))),
])
def test_capture_audit_rejects_unbound_receipts_and_undeclared_native_operations(tmp_path, mutation):
    data = _trace(tmp_path)
    mutation(data[1])
    with pytest.raises(ValueError):
        _audit(data)


def test_capture_audit_rejects_missing_changed_artifact_and_partial_configuration(tmp_path):
    data = _trace(tmp_path)
    _audit(data)
    with pytest.raises(ValueError, match="requires common context"):
        availability.audit_catalog(data[0], [], common_context=True, catalog_artifact=data[2])
    data[2].write_bytes(data[2].read_bytes().replace(b"private", b"changed"))
    with pytest.raises(ValueError, match="differs from first native receipt"):
        _audit(data)
    data[2].unlink()
    with pytest.raises(ValueError, match="missing or malformed"):
        _audit(data)


def _syntax_retry(data, program="const broken = 00xa81a664b;"):
    failed = {"type": "response_item", "payload": {"type": "custom_tool_call", "name": "exec",
              "call_id": "parse-failure", "input": program}}
    output = {"type": "response_item", "payload": {"type": "custom_tool_call_output",
              "call_id": "parse-failure", "output": [
                  {"type": "input_text", "text": "Script failed\nWall time 0.0 seconds\nOutput:\n"},
                  {"type": "input_text", "text": "Script error:\nSyntaxError: Invalid or unexpected token"}]}}
    data[1][0:0] = [failed, output]
    return data


def test_parse_rejected_attempt_is_retained_before_exact_capture_retry(tmp_path):
    data = _syntax_retry(_trace(tmp_path))
    result = _audit(data)
    assert result["row"] == 2 and result["output_row"] == 5
    assert result["pre_capture_failures"] == [{"row": 0, "output_row": 1, "call_id": "parse-failure",
        "status": "syntax_rejected_before_execution",
        "program_sha256": hashlib.sha256(data[1][0]["payload"]["input"].encode()).hexdigest(),
        "native_error": "Script error:\nSyntaxError: Invalid or unexpected token"}]
    assert result["native_access_v1"] == {"apply_patch": True, "exec_command": True}


@pytest.mark.parametrize("program", [
    'throw new SyntaxError("Invalid or unexpected token");',
    'await tools.exec_command({cmd:"cat source.js"}); throw new SyntaxError("Invalid or unexpected token");',
    'text({loci_runtime_catalog_v1:[]});',
])
def test_reported_syntax_error_cannot_hide_executable_work(tmp_path, program):
    data = _syntax_retry(_trace(tmp_path), program)
    with pytest.raises(ValueError, match="independently parse-invalid"):
        _audit(data)


@pytest.mark.parametrize("mutation", [
    lambda rows: rows[1]["payload"].update(call_id="unjoined"),
    lambda rows: rows.insert(2, deepcopy(rows[1])),
    lambda rows: rows.insert(1, {"type": "event_msg", "payload": {"type": "item_completed", "item": {"type": "CommandExecution"}}}),
    lambda rows: rows.insert(2, {"type": "event_msg", "payload": {"type": "item_completed", "item": {"type": "McpToolCall"}}}),
    lambda rows: rows.insert(2, {"type": "event_msg", "payload": {"type": "item_completed", "item": {"type": "FileChange"}}}),
    lambda rows: rows[1]["payload"]["output"][1].update(text="Script error:\nError: runtime failure"),
    lambda rows: rows[1]["payload"].update(output='SyntaxError: Invalid or unexpected token'),
    lambda rows: rows.append(deepcopy(rows[0])),
    lambda rows: rows.__setitem__(slice(1, 3), list(reversed(rows[1:3]))),
])
def test_capture_retry_rejects_unbound_errors_and_any_earlier_native_actions(tmp_path, mutation):
    data = _syntax_retry(_trace(tmp_path))
    mutation(data[1])
    with pytest.raises(ValueError):
        _audit(data)
