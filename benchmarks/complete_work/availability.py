"""Fail-closed native-host catalog and callable-tool evidence for R1.

These helpers inspect retained native events. They do not launch a host, trust
an assistant's success report, or infer task use from a capability probe.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path


CATALOG_PROGRAM = ('const names = ALL_TOOLS.filter(t => /^mcp__loci__/.test(t.name) || /(?:^|__)loci_[A-Za-z0-9_]+$/.test(t.name))'
                   '.map(t => t.name).sort();\ntext({loci_runtime_catalog_v1: names});')
MEASURED_PREFIX = (
    "Before doing the task, your first model tool action must be functions.exec executing exactly "
    "this program, without additions or changes:\n" + CATALOG_PROGRAM + "\n"
    "Compare the returned live Loci tool names with the expected tools below (qualified as "
    "mcp__loci__NAME). If discovery is unavailable or the set differs, stop and report the "
    "availability failure. Otherwise continue the original task; Loci use is optional.\n"
)
PROBE_FILES = {
    "entry.ts": "import type { Public } from './model';\n"
                "export function entry(value: Public): Public { return value; }\n",
    "model.ts": "export type Base = string;\nexport type Middle = Base;\nexport type Public = Middle;\n",
    "package.json": '{"name":"loci-availability-probe","type":"module"}\n',
}
TOOLS_BY_CONDITION = {
    "native": [],
    "path-only": ["loci_retrieve", "loci_read"],
    "eager": ["loci_retrieve", "loci_read"],
    "integrated": ["loci_retrieve", "loci_read", "loci_semantic", "loci_proof"],
}


def policy() -> dict:
    return {"schema": "loci-native-availability-v1", "catalog_program": CATALOG_PROGRAM,
            "measured_prefix": MEASURED_PREFIX, "probe_files": dict(PROBE_FILES),
            "tools_by_condition": {k: list(v) for k, v in TOOLS_BY_CONDITION.items()}}


def _expected(tools: list[str]) -> list[str]:
    allowed = TOOLS_BY_CONDITION["integrated"]
    if (not isinstance(tools, list) or any(t not in allowed for t in tools)
            or len(tools) != len(set(tools))):
        raise ValueError("invalid expected Loci tools")
    return sorted("mcp__loci__" + t for t in tools)


def probe_prompt(condition: str, repo: Path, expected_tools: list[str]) -> str:
    _condition(condition, expected_tools)
    prompt = (MEASURED_PREFIX + "Expected tools: " + json.dumps(expected_tools) + "\n"
              "This is only an availability probe. Use only the fixture repository "
              + json.dumps(str(repo.resolve())) + ". Do not inspect or copy any pilot task.\n")
    if not expected_tools:
        return prompt + "The catalog must contain no Loci tools. Make no Loci calls, then finish.\n"
    prompt += (
        "After the catalog, inspect each discovered tool's complete live description and input "
        "declaration. Invoke every expected operation through this Codex host's tools. "
        "Call loci_retrieve with query entry.ts, then loci_read with a source_ref returned by "
        "that retrieve. Check returned source against the fixture. "
        "Do not use a local MCP client, import or call a server directly, launch another host, "
        "use shell source reads as proof, or fabricate success JSON. Stop on any error.\n"
    )
    if condition == "integrated":
        prompt += ("Call loci_semantic with query entry and anchor_file entry.ts, then loci_proof "
                   "with the entry anchor node_id actually returned by semantic. Inspect the "
                   "proof sources and the entry-to-Public type relationship.\n")
    return prompt + "Finish after the calls; report any availability failure accurately.\n"


def _condition(condition: str, tools: list[str]) -> None:
    _expected(tools)
    if condition not in TOOLS_BY_CONDITION or set(tools) != set(TOOLS_BY_CONDITION[condition]):
        raise ValueError("condition tool set differs from availability protocol")


def _rows(trace: Path) -> tuple[bytes, list[dict]]:
    raw = trace.read_bytes()
    try:
        rows = [json.loads(line) for line in raw.splitlines() if line.strip()]
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("malformed native availability trace") from exc
    if not rows or any(not isinstance(r, dict) or not isinstance(r.get("payload"), dict) for r in rows):
        raise ValueError("invalid native availability rows")
    return raw, rows


def _catalog_output(output: object) -> list[str]:
    if isinstance(output, str):
        texts = [output]
    elif isinstance(output, list) and all(isinstance(b, dict) and b.get("type") == "input_text"
                                         and isinstance(b.get("text"), str) for b in output):
        texts = [b["text"] for b in output]
    else:
        raise ValueError("catalog output is not a native text receipt")
    receipts = []
    for text in texts:
        # Native custom output includes a timing header plus an independent JSON
        # text block. Also accept the same rendering as one multiline string.
        for line in text.splitlines():
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict) and "loci_runtime_catalog_v1" in value:
                if set(value) != {"loci_runtime_catalog_v1"}:
                    raise ValueError("malformed live catalog receipt")
                receipts.append(value["loci_runtime_catalog_v1"])
    if len(receipts) != 1 or not isinstance(receipts[0], list):
        raise ValueError("missing or duplicated live catalog receipt")
    names = receipts[0]
    if any(not isinstance(t, str) for t in names) or names != sorted(set(names)):
        raise ValueError("live catalog must be sorted and unique")
    return names


def audit_catalog(trace: Path, expected_tools: list[str]) -> dict:
    expected = _expected(expected_tools)
    raw, rows = _rows(trace)
    calls = [(i, r["payload"]) for i, r in enumerate(rows)
             if r.get("type") == "response_item"
             and r["payload"].get("type") in {"function_call", "custom_tool_call"}]
    if not calls:
        raise ValueError("live catalog discovery was not the first tool action")
    index, call = calls[0]
    program = call.get("input") if call["type"] == "custom_tool_call" else call.get("arguments")
    if (call.get("name") not in {"exec", "functions.exec"} or not isinstance(program, str)
            or program.strip() != CATALOG_PROGRAM):
        raise ValueError("first tool action is not the fixed live catalog program")
    identity = call.get("call_id")
    if not isinstance(identity, str) or not identity:
        raise ValueError("catalog call has no native identity")
    if sum(p.get("call_id") == identity for _, p in calls) != 1:
        raise ValueError("duplicated catalog call identity")
    if any(p.get("name") in {"exec", "functions.exec"}
           and isinstance(p.get("input") if p["type"] == "custom_tool_call" else p.get("arguments"), str)
           and (p.get("input") if p["type"] == "custom_tool_call" else p.get("arguments")).strip() == CATALOG_PROGRAM
           for _, p in calls[1:]):
        raise ValueError("duplicated live catalog discovery")
    outputs = [(i, r["payload"]) for i, r in enumerate(rows)
               if r.get("type") == "response_item" and r["payload"].get("call_id") == identity
               and r["payload"].get("type") == call["type"] + "_output"]
    if len(outputs) != 1 or outputs[0][0] <= index:
        raise ValueError("catalog lacks one joined native output")
    output_index, output = outputs[0]
    for i, row in enumerate(rows[:output_index]):
        p = row["payload"]
        if (row.get("type") == "event_msg" and p.get("type") in {"item_started", "item_completed"}
                and isinstance(p.get("item"), dict)
                and p["item"].get("type") in {"McpToolCall", "CommandExecution"}):
            raise ValueError("native task operation preceded catalog discovery")
        if i > index and row.get("type") == "response_item" and p.get("type") in {"function_call", "custom_tool_call"}:
            raise ValueError("another tool action preceded catalog receipt")
    names = _catalog_output(output.get("output"))
    if names != expected:
        raise ValueError("live catalog differs from expected tool set")
    return {"tools": names, "row": index, "output_row": output_index, "call_id": identity,
            "trace_sha256": hashlib.sha256(raw).hexdigest()}


def _sources(packet: dict, *, read: bool = False) -> dict:
    sources = [packet.get("source")] if read else packet.get("sources")
    if not isinstance(sources, list) or not sources:
        raise ValueError("probe returned no source evidence")
    result = {}
    for source in sources:
        if not isinstance(source, dict) or source.get("file") not in PROBE_FILES:
            raise ValueError("probe source is outside fixture")
        raw = PROBE_FILES[source["file"]].encode()
        start, end = source.get("start_byte"), source.get("end_byte")
        if (type(start) is not int or type(end) is not int or not 0 <= start < end <= len(raw)
                or source.get("content_hash") != hashlib.sha256(raw).hexdigest()
                or source.get("content") != raw[start:end].decode()):
            raise ValueError("probe source bytes or hash differ from fixture")
        if type(source.get("id")) is not int or source["id"] in result:
            raise ValueError("duplicate source identity")
        result[source.get("id")] = source
    return result


def _proof(packet: dict, node_id: str) -> None:
    sources = _sources(packet)
    if packet.get("proof_request") != {"node_id": node_id, "scope": "same_computed_slice"}:
        raise ValueError("proof does not bind delivered semantic identity")
    relations = packet.get("relationships")
    if not isinstance(relations, list):
        raise ValueError("probe proof has no relationships")
    for relation in relations:
        if not isinstance(relation, dict) or not isinstance(relation.get("edge"), dict):
            raise ValueError("invalid probe relationship")
        edge = relation.get("edge", {})
        evidence = edge.get("evidence", {})
        ids = relation.get("source_ids", [])
        if (edge.get("from") == "entry.ts::entry#function"
                and edge.get("to") == "model.ts::Public#type"
                and edge.get("type") == "uses_type" and edge.get("resolution") == "import-resolved"
                and edge.get("namespace") == "loci" and edge.get("directed") is True
                and evidence == {"file": "entry.ts", "line": 2,
                                 "content_hash": hashlib.sha256(PROBE_FILES["entry.ts"].encode()).hexdigest()}
                and relation.get("proof") == "complete" and isinstance(ids, list) and ids
                and all(type(i) is int and i in sources for i in ids)):
            support = [sources[i] for i in ids]
            required = (("entry.ts", "import type { Public } from './model';"),
                        ("entry.ts", "function entry(value: Public): Public { return value; }"),
                        ("model.ts", "type Public = Middle;"))
            if all(any(s["file"] == file and text in s["content"] for s in support)
                   for file, text in required):
                return
    raise ValueError("probe proof lacks independently supported entry-to-Public relationship")


def audit_probe(trace: Path, accounting: dict, condition: str, repo: Path,
                expected_tools: list[str], *, fixture: Path | None = None) -> dict:
    _condition(condition, expected_tools)
    catalog = audit_catalog(trace, expected_tools)
    _, rows = _rows(trace)
    for file, content in PROBE_FILES.items():
        try:
            raw = ((fixture or repo) / file).read_bytes()
        except OSError as exc:
            raise ValueError("probe fixture unavailable") from exc
        if raw != content.encode():
            raise ValueError("probe fixture changed")
    calls, started = {}, set()
    for index, row in enumerate(rows):
        p = row["payload"]
        item = p.get("item")
        if (row.get("type") != "event_msg" or p.get("type") not in {"item_started", "item_completed"}
                or not isinstance(item, dict) or item.get("type") != "McpToolCall"):
            continue
        identity = item.get("id")
        if not isinstance(identity, str) or not identity:
            raise ValueError("probe native call lacks identity")
        if p["type"] == "item_started":
            started.add(identity)
            continue
        if identity in calls:
            if calls[identity][1] != item:
                raise ValueError("conflicting native probe call")
            continue
        calls[identity] = (index, item)
    if started - calls.keys():
        raise ValueError("probe native calls did not complete")
    stages = accounting.get("stages")
    if not isinstance(stages, list) or any(not isinstance(s, dict) or not isinstance(s.get("items"), list) for s in stages):
        raise ValueError("probe accounting has no native stage items")
    accounted = {i.get("id"): i for s in stages for i in s["items"]
                 if isinstance(i, dict) and i.get("type") == "mcpToolCall"}
    if set(accounted) != set(calls):
        raise ValueError("probe accounting differs from native calls")
    delivered_refs, delivered_ids, observed, evidence = set(), set(), set(), []
    for index, item in calls.values():
        if any(accounted[item["id"]].get(k) != item.get(k)
               for k in ("server", "tool", "arguments", "result", "status", "error")):
            raise ValueError("probe accounting differs from native call evidence")
        tool = item.get("tool", "")
        if not isinstance(tool, str):
            raise ValueError("invalid native probe tool name")
        if item.get("server") != "loci" and not re.search(r"(?:^|__)loci_", tool):
            # Unrelated host MCP tools remain usable in the native control.
            continue
        if isinstance(tool, str) and tool.startswith("mcp__loci__"):
            tool = tool.removeprefix("mcp__loci__")
        args, result = item.get("arguments"), item.get("result")
        if (item.get("server") != "loci" or tool not in expected_tools
                or not isinstance(args, dict) or args.get("repo") != str(repo.resolve())):
            raise ValueError("probe called an unexpected tool, server or repository")
        if (index <= catalog["output_row"] or item.get("status") != "completed"
                or item.get("error") not in (None, {}) or not isinstance(result, dict)
                or result.get("isError", False) is not False):
            raise ValueError("probe native call failed")
        packet = result.get("structuredContent")
        if not isinstance(packet, dict) or packet.get("error") is not None or packet.get("status") not in {"ok", "partial"}:
            raise ValueError("probe returned an error or empty packet")
        if tool == "loci_retrieve":
            sources = _sources(packet)
            if args.get("query") != "entry.ts" or not any(s["file"] == "entry.ts" for s in sources.values()):
                raise ValueError("retrieve did not select fixture entry")
            items = packet.get("items")
            if not isinstance(items, list):
                raise ValueError("retrieve delivered no source items")
            delivered_refs.update(i["source_ref"] for i in items
                                  if isinstance(i, dict) and isinstance(i.get("source_ref"), str)
                                  and isinstance(i.get("extent"), dict) and i["extent"].get("file") == "entry.ts"
                                  and any(s.get("source_ref") == i["source_ref"] and s["file"] == "entry.ts"
                                          for s in sources.values()))
            if not delivered_refs:
                raise ValueError("retrieve delivered no entry source_ref")
        elif tool == "loci_read":
            if args.get("source_ref") not in delivered_refs:
                raise ValueError("read does not bind a delivered source_ref")
            source = next(iter(_sources(packet, read=True).values()))
            if (source["file"] != "entry.ts" or source["content"] != PROBE_FILES["entry.ts"]
                    or source.get("source_ref") != args["source_ref"]):
                raise ValueError("read did not return fixture entry source")
        elif tool == "loci_semantic":
            _sources(packet)
            if args.get("query") != "entry" or args.get("anchor_file") != "entry.ts":
                raise ValueError("semantic did not select fixture entry")
            anchors = packet.get("anchors")
            nodes = packet.get("nodes")
            if not isinstance(anchors, list) or not isinstance(nodes, list):
                raise ValueError("semantic delivered no identities")
            delivered_ids.update(a.get("node_id") for a in anchors
                                 if isinstance(a, dict) and a.get("node_id") == "entry.ts::entry#function"
                                 and any(isinstance(n, dict) and n.get("id") == a["node_id"]
                                         and n.get("file") == "entry.ts" and n.get("name") == "entry" for n in nodes))
            if not delivered_ids:
                raise ValueError("semantic delivered no entry anchor")
        else:
            if args.get("node_id") not in delivered_ids:
                raise ValueError("proof does not bind a delivered semantic identity")
            _proof(packet, args["node_id"])
        observed.add(tool)
        evidence.append({"id": item["id"], "tool": tool, "row": index,
                         "arguments_sha256": hashlib.sha256(json.dumps(args, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
                         "result_sha256": hashlib.sha256(json.dumps(result, sort_keys=True, separators=(",", ":")).encode()).hexdigest()})
    if observed != set(expected_tools):
        raise ValueError("probe did not successfully call every expected tool")
    return {"schema": "loci-native-availability-v1", "condition": condition,
            "catalog": catalog, "calls": evidence, "tools": sorted(observed)}
