"""Fail-closed native-host catalog and callable-tool evidence for R1.

These helpers inspect retained native events. They do not launch a host, trust
an assistant's success report, or infer task use from a capability probe.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shlex
import subprocess
from copy import deepcopy
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

# An opt-in policy for new freezes. Keep the original protocol above byte-for-
# byte usable by retained runs; these controls do not change user configuration.
CATALOG_SHA256_PROGRAM = """function sha256(text) {
  const bytes = [];
  for (let i = 0; i < text.length; i++) {
    let c = text.codePointAt(i);
    if (c > 0xffff) i++;
    else if (c >= 0xd800 && c <= 0xdfff) c = 0xfffd;
    if (c < 0x80) bytes.push(c);
    else if (c < 0x800) bytes.push(0xc0 | c >>> 6, 0x80 | c & 63);
    else if (c < 0x10000) bytes.push(0xe0 | c >>> 12, 0x80 | c >>> 6 & 63, 0x80 | c & 63);
    else bytes.push(0xf0 | c >>> 18, 0x80 | c >>> 12 & 63, 0x80 | c >>> 6 & 63, 0x80 | c & 63);
  }
  const bits = bytes.length * 8;
  bytes.push(0x80);
  while (bytes.length % 64 !== 56) bytes.push(0);
  const high = Math.floor(bits / 0x100000000), low = bits >>> 0;
  for (const word of [high, low]) for (let shift = 24; shift >= 0; shift -= 8) bytes.push(word >>> shift & 255);
  const k = [0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5,
    0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,
    0xe49b69c1,0xefbe4786,0x0fc19dc6,0x240ca1cc,0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,
    0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,0xc6e00bf3,0xd5a79147,0x06ca6351,0x14292967,
    0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,
    0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3,0xd192e819,0xd6990624,0xf40e3585,0x106aa070,
    0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,
    0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2];
  const state = [0x6a09e667,0xbb67ae85,0x3c6ef372,0xa54ff53a,0x510e527f,0x9b05688c,0x1f83d9ab,0x5be0cd19];
  const rotate = (x, n) => x >>> n | x << (32 - n);
  const w = new Int32Array(64);
  for (let offset = 0; offset < bytes.length; offset += 64) {
    for (let i = 0; i < 16; i++) {
      const j = offset + i * 4;
      w[i] = bytes[j] << 24 | bytes[j + 1] << 16 | bytes[j + 2] << 8 | bytes[j + 3];
    }
    for (let i = 16; i < 64; i++) {
      const x = w[i - 15], y = w[i - 2];
      w[i] = (w[i - 16] + (rotate(x, 7) ^ rotate(x, 18) ^ x >>> 3)
        + w[i - 7] + (rotate(y, 17) ^ rotate(y, 19) ^ y >>> 10)) | 0;
    }
    let [a,b,c,d,e,f,g,h] = state;
    for (let i = 0; i < 64; i++) {
      const t1 = (h + (rotate(e, 6) ^ rotate(e, 11) ^ rotate(e, 25))
        + ((e & f) ^ (~e & g)) + k[i] + w[i]) | 0;
      const t2 = ((rotate(a, 2) ^ rotate(a, 13) ^ rotate(a, 22)) + ((a & b) ^ (a & c) ^ (b & c))) | 0;
      h = g; g = f; f = e; e = (d + t1) | 0; d = c; c = b; b = a; a = (t1 + t2) | 0;
    }
    const block = [a,b,c,d,e,f,g,h];
    for (let i = 0; i < 8; i++) state[i] = (state[i] + block[i]) | 0;
  }
  return state.map(word => (word >>> 0).toString(16).padStart(8, '0')).join('');
}
"""
COMMON_CATALOG_PROGRAM = (
    CATALOG_SHA256_PROGRAM
    + 'const isLoci = t => /^mcp__loci__/.test(t.name) || /(?:^|__)loci_[A-Za-z0-9_]+$/.test(t.name);\n'
    'const names = ALL_TOOLS.filter(isLoci).map(t => t.name).sort();\n'
    'const common = ALL_TOOLS.filter(t => !isLoci(t)).map(({name, description}) => ({name, description}))'
    '.sort((a, b) => a.name < b.name ? -1 : a.name > b.name ? 1 : 0);\n'
    'if (common.some((t, i) => typeof t.name !== "string" || !t.name || typeof t.description !== "string"'
    ' || (i > 0 && t.name === common[i - 1].name))) throw new Error("Invalid common tool metadata");\n'
    'text({loci_runtime_catalog_v1: names, common_runtime_catalog_v1: {count: common.length, sha256: sha256(JSON.stringify(common))}});'
)
COMMON_MEASURED_PREFIX = (
    "Before doing the task, your first model tool action must be functions.exec executing exactly "
    "this program, without additions or changes:\n" + COMMON_CATALOG_PROGRAM + "\n"
    "Compare the returned live Loci tool names with the expected tools below (qualified as "
    "mcp__loci__NAME). If discovery is unavailable or the set differs, stop and report the "
    "availability failure. Otherwise continue the original task; Loci use is optional. "
    "All normal native tools remain available. The bounded common catalog receipt fingerprints "
    "every complete tool name and description; it does not print the full catalog.\n"
)
SOURCE_CARD = (
    "loci_retrieve finds bounded current source by words or an exact relative file path; "
    "it can re-anchor one previously returned node_id in seed_ids. It does no semantic parsing. "
    "Use loci_read with a returned hash-bound source_ref and follow next_source_ref until complete. "
    "Source-path candidates are alternatives to inspect, not resolved relationships."
)
CAPABILITY_CARDS = {
    "native": "Use the normal native tools. No Loci tools are enabled.",
    "path-only": SOURCE_CARD,
    "integrated": SOURCE_CARD + " Optional loci_semantic supplies bounded static JS/TS/Rust relationships; "
                  "Python and Go semantics are unsupported. Optional loci_proof follows node IDs "
                  "actually delivered by the most recent semantic request or its proof followups. "
                  "Preserve ambiguity and omissions; missing proof never proves absence.",
    "eager": "Production loci_retrieve performs deterministic bounded static source and graph selection. "
             "Use words, an exact indexed relative file path, or up to five previously delivered seed IDs. "
             "Results include exact source, static relationship proof, ambiguity and omissions; "
             "relationships are non-exhaustive. Expand returned source_ref extents with loci_read, "
             "following next_source_ref. No separate semantic or proof endpoints are enabled.",
}


def context_policy(root_agents_md: str | None = None) -> dict:
    if root_agents_md is not None and not isinstance(root_agents_md, str):
        raise ValueError("common root AGENTS.md must be text or absent")
    return {"schema": "r1-common-context-v1", "cli_overrides": {"skills.include_instructions": False},
            "catalog_program": COMMON_CATALOG_PROGRAM, "measured_prefix": COMMON_MEASURED_PREFIX,
            "capability_cards": dict(CAPABILITY_CARDS), "root_agents_md": root_agents_md,
            "path_substitutions": ["workspace", "observer"],
            "allowed_loci_schema_namespace": "mcp__loci",
            "common_catalog_encoding": "SHA-256 of UTF-8 JSON.stringify of full name/description objects sorted by name",
            "common_catalog_export": "count and cryptographic fingerprint only; full descriptions are not exported",
            "instruction_updates": "reject"}


def capture_policy(root_agents_md: str | None = None) -> dict:
    """Explicit measurement-only successor; legacy freezes retain their policy."""
    result = context_policy(root_agents_md)
    result.update(schema="r1-common-context-v2", catalog_program="capture_program(catalog_destination)",
                  measured_prefix="capture_prefix(catalog_destination)",
                  common_catalog_export="private common-tool-catalog.json plus bounded count and SHA-256 receipt",
                  catalog_capture={"filename": "common-tool-catalog.json", "encoding": "UTF-8 JSON.stringify plus LF",
                                   "writer": "apply_patch", "readback": "isolated standard-library Python"})
    return result


def _capture_destination(destination: Path) -> Path:
    destination = Path(destination)
    if not destination.is_absolute() or destination.name != "common-tool-catalog.json" or "\n" in str(destination) or "\r" in str(destination):
        raise ValueError("catalog destination must be an absolute common-tool-catalog.json path")
    return destination


def capture_check_command(destination: Path) -> str:
    destination = _capture_destination(destination)
    script = ("import hashlib,json,sys; "
              "raw=open(sys.argv[1],'rb').read(); "
              "assert raw.endswith(b'\\n'), 'catalog requires final LF'; "
              "values=json.loads(raw); "
              "assert isinstance(values,list), 'catalog must be an array'; "
              "print(json.dumps({'count':len(values),'sha256':hashlib.sha256(raw[:-1]).hexdigest()},separators=(',',':')))")
    return "python3 -I -c " + shlex.quote(script) + " " + shlex.quote(str(destination))


def capture_program(destination: Path) -> str:
    """Snapshot before native calls; keep complete descriptions out of output."""
    destination = _capture_destination(destination)
    setup = COMMON_CATALOG_PROGRAM.rsplit("text(", 1)[0]
    return (setup
            + "const serialized = JSON.stringify(common);\n"
            + "const destination = " + json.dumps(str(destination)) + ";\n"
            + 'try { await tools.apply_patch("*** Begin Patch\\n*** Add File: " + destination + "\\n+" + serialized + "\\n*** End Patch"); }\n'
            + 'catch (_) { throw new Error("Catalog capture failed: native apply_patch could not write the observer artifact"); }\n'
            + "let readback;\n"
            + "try { readback = await tools.exec_command({cmd: " + json.dumps(capture_check_command(destination))
            + ', max_output_tokens: 2000}); }\n'
            + 'catch (_) { throw new Error("Catalog capture failed: native exec_command readback was unavailable"); }\n'
            + 'if (!readback || readback.exit_code !== 0 || typeof readback.output !== "string") '
            + 'throw new Error("Catalog capture failed: isolated Python readback did not exit successfully");\n'
            + 'let verified; try { verified = JSON.parse(readback.output); } '
            + 'catch (_) { throw new Error("Catalog capture failed: readback was not a bounded JSON receipt"); }\n'
            + 'const fingerprint = sha256(serialized);\n'
            + 'if (!verified || Object.keys(verified).sort().join(",") !== "count,sha256" '
            + '|| verified.count !== common.length || verified.sha256 !== fingerprint) '
            + 'throw new Error("Catalog capture failed: retained bytes differ from the first-call registry");\n'
            + 'text({loci_runtime_catalog_v1: names, common_runtime_catalog_v1: {count: common.length, sha256: fingerprint}, '
            + 'native_access_v1: {apply_patch: true, exec_command: true}});')


def capture_prefix(destination: Path) -> str:
    return ("The measurement step authorizes the exact observer file write and readback below. "
            "Task edit restrictions apply to the task workspace, not this observer artifact.\n"
            + COMMON_MEASURED_PREFIX.replace(COMMON_CATALOG_PROGRAM, capture_program(destination)).replace(
                "it does not print the full catalog.",
                "it retains a private observer artifact and does not print the full catalog."))


def _catalog_artifact(path: Path) -> tuple[bytes, list[dict]]:
    try:
        raw = Path(path).read_bytes()
        values = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("retained common catalog artifact is missing or malformed") from exc
    if (not raw.endswith(b"\n") or not isinstance(values, list) or not values
            or any(not isinstance(t, dict) or set(t) != {"name", "description"}
                   or not isinstance(t["name"], str) or not t["name"] or not isinstance(t["description"], str)
                   or re.search(r"^mcp__loci__|(?:^|__)loci_[A-Za-z0-9_]+$", t["name"]) for t in values)):
        raise ValueError("retained common catalog artifact has invalid metadata")
    names = [t["name"] for t in values]
    if names != sorted(set(names), key=lambda name: name.encode("utf-16-be", errors="surrogatepass")):
        raise ValueError("retained common catalog artifact must be sorted and unique")
    return raw, values


def catalog_difference(left_path: Path, right_path: Path) -> dict:
    _, left = _catalog_artifact(left_path)
    _, right = _catalog_artifact(right_path)
    left = {t["name"]: t["description"] for t in left}
    right = {t["name"]: t["description"] for t in right}
    digest = lambda description: hashlib.sha256(description.encode("utf-8", errors="surrogatepass")).hexdigest()
    return {"added": sorted(right.keys() - left.keys()), "removed": sorted(left.keys() - right.keys()),
            "changed": [{"name": name, "left_sha256": digest(left[name]), "right_sha256": digest(right[name])}
                        for name in sorted(left.keys() & right.keys()) if left[name] != right[name]]}


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


def probe_prompt(condition: str, repo: Path, expected_tools: list[str], *, common_context: bool = False) -> str:
    _condition(condition, expected_tools)
    prefix = COMMON_MEASURED_PREFIX if common_context else MEASURED_PREFIX
    card = "Capability card: " + CAPABILITY_CARDS[condition] + "\n" if common_context else ""
    prompt = (prefix + "Expected tools: " + json.dumps(expected_tools) + "\n" + card
              + "This is only an availability probe. Use only the fixture repository "
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


def _catalog_output(output: object, *, common_context: bool = False, capture: bool = False) -> dict:
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
                keys = {"loci_runtime_catalog_v1"}
                if common_context:
                    keys.add("common_runtime_catalog_v1")
                if capture:
                    keys.add("native_access_v1")
                if set(value) != keys:
                    raise ValueError("malformed live catalog receipt")
                receipts.append(value)
    if len(receipts) != 1 or not isinstance(receipts[0]["loci_runtime_catalog_v1"], list):
        raise ValueError("missing or duplicated live catalog receipt")
    names = receipts[0]["loci_runtime_catalog_v1"]
    if any(not isinstance(t, str) for t in names) or names != sorted(set(names)):
        raise ValueError("live catalog must be sorted and unique")
    if common_context:
        common = receipts[0]["common_runtime_catalog_v1"]
        if (not isinstance(common, dict) or set(common) != {"count", "sha256"}
                or type(common["count"]) is not int or common["count"] <= 0
                or not isinstance(common["sha256"], str) or not re.fullmatch(r"[a-f0-9]{64}", common["sha256"])):
            raise ValueError("common catalog must retain its count and full-description fingerprint")
    if capture:
        access = receipts[0]["native_access_v1"]
        if (not isinstance(access, dict) or set(access) != {"apply_patch", "exec_command"}
                or any(value is not True for value in access.values())):
            raise ValueError("catalog capture lacks successful native access evidence")
    return receipts[0]


def _audit_capture_events(events: list[tuple[str, dict]], destination: Path, raw: bytes) -> None:
    """Allow exactly the declared write and isolated readback inside the first cell."""
    expected_changes = {str(destination): {"type": "add", "content": raw.decode("utf-8")}}
    expected_readback = {"count": len(json.loads(raw)), "sha256": hashlib.sha256(raw[:-1]).hexdigest()}
    seen, completed, identities = set(), [], {}
    for phase, item in events:
        kind, identity = item["type"], item.get("id")
        if kind == "CommandExecution" and completed != ["FileChange"]:
            raise ValueError("catalog capture readback preceded its completed native write")
        if (not isinstance(identity, str) or not identity or (phase, kind) in seen
                or (kind in identities and identities[kind] != identity)
                or (identity in identities.values() and identities.get(kind) != identity)):
            raise ValueError("catalog capture has duplicated or unbound native operations")
        identities[kind] = identity
        seen.add((phase, kind))
        if kind == "FileChange":
            if item.get("changes") != expected_changes:
                raise ValueError("catalog capture wrote an undeclared file or different bytes")
        else:
            command = item.get("command")
            if (not isinstance(command, list) or len(command) != 3
                    or command[0] not in {"/bin/zsh", "/bin/bash", "/bin/sh"}
                    or command[1] not in {"-lc", "-c"} or command[2] != capture_check_command(destination)):
                raise ValueError("catalog capture ran an undeclared native command")
        if phase == "item_completed":
            if item.get("status") != "completed":
                raise ValueError("catalog capture native operation did not complete")
            if kind == "FileChange":
                if item.get("stderr") not in (None, ""):
                    raise ValueError("catalog capture native write reported an error")
            else:
                try:
                    checked = json.loads(item.get("aggregated_output", ""))
                except (TypeError, json.JSONDecodeError) as exc:
                    raise ValueError("catalog capture native readback has no JSON receipt") from exc
                if type(item.get("exit_code")) is not int or item["exit_code"] != 0 or checked != expected_readback:
                    raise ValueError("catalog capture native readback differs from retained bytes")
            completed.append(kind)
        elif (phase != "item_started" or ("item_completed", kind) in seen
              or item.get("status") not in (None, "inProgress", "in_progress")):
            raise ValueError("catalog capture native operation lifecycle is invalid")
    if completed != ["FileChange", "CommandExecution"]:
        raise ValueError("catalog capture requires exactly one native write followed by readback")


def _syntax_rejected_attempt(rows: list[dict], calls: list[tuple[int, dict]], position: int) -> dict:
    """Prove an earlier Code Mode attempt failed parsing, without executing it."""
    index, call = calls[position]
    program = call.get("input") if call["type"] == "custom_tool_call" else call.get("arguments")
    identity = call.get("call_id")
    if (call.get("name") not in {"exec", "functions.exec"} or not isinstance(program, str)
            or not isinstance(identity, str) or not identity
            or sum(p.get("call_id") == identity for _, p in calls) != 1):
        raise ValueError("first tool action is not the fixed live catalog program")
    outputs = [(i, row["payload"]) for i, row in enumerate(rows)
               if row.get("type") == "response_item" and row["payload"].get("call_id") == identity
               and row["payload"].get("type") == call["type"] + "_output"]
    if (position + 1 == len(calls) or len(outputs) != 1
            or not index < outputs[0][0] < calls[position + 1][0]):
        raise ValueError("catalog syntax failure lacks one completed output before its retry")
    output_index, output = outputs[0]
    blocks = output.get("output")
    # This is a host error, not an assistant's explanation or a JSON success
    # receipt. Independently check the syntax as well: valid JavaScript can
    # deliberately throw a SyntaxError after performing arbitrary work.
    if (not isinstance(blocks, list) or len(blocks) != 2
            or any(not isinstance(b, dict) or b.get("type") != "input_text"
                   or not isinstance(b.get("text"), str) for b in blocks)
            or not re.fullmatch(r"Script failed\nWall time [0-9.]+ seconds\nOutput:\n", blocks[0]["text"])
            or not re.fullmatch(r"Script error:\nSyntaxError: [^\n]+\n?", blocks[1]["text"])):
        raise ValueError("earlier catalog attempt is not a retained native syntax rejection")
    try:
        parsed = subprocess.run(["node", "--input-type=module", "--check"], input=program,
                                text=True, capture_output=True, check=False, timeout=5,
                                env={**os.environ, "NODE_OPTIONS": ""})
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValueError("could not independently verify catalog parse failure") from exc
    if parsed.returncode != 1 or "SyntaxError:" not in parsed.stderr:
        raise ValueError("earlier catalog attempt is not independently parse-invalid")
    return {"row": index, "output_row": output_index, "call_id": identity,
            "status": "syntax_rejected_before_execution",
            "program_sha256": hashlib.sha256(program.encode()).hexdigest(),
            "native_error": blocks[1]["text"].strip()}


def audit_catalog(trace: Path, expected_tools: list[str], *, common_context: bool = False,
                  catalog_artifact: Path | None = None, catalog_destination: Path | None = None) -> dict:
    capture = catalog_artifact is not None or catalog_destination is not None
    if capture and (not common_context or catalog_artifact is None or catalog_destination is None):
        raise ValueError("catalog capture requires common context, retained artifact and original destination")
    fixed_program = capture_program(catalog_destination) if capture else COMMON_CATALOG_PROGRAM if common_context else CATALOG_PROGRAM
    expected = _expected(expected_tools)
    raw, rows = _rows(trace)
    calls = [(i, r["payload"]) for i, r in enumerate(rows)
             if r.get("type") == "response_item"
             and r["payload"].get("type") in {"function_call", "custom_tool_call"}]
    if not calls:
        raise ValueError("live catalog discovery was not the first tool action")
    rejected = []
    position = 0
    while True:
        index, call = calls[position]
        program = call.get("input") if call["type"] == "custom_tool_call" else call.get("arguments")
        if (call.get("name") in {"exec", "functions.exec"} and isinstance(program, str)
                and program.strip() == fixed_program):
            break
        if not capture:
            raise ValueError("first tool action is not the fixed live catalog program")
        rejected.append(_syntax_rejected_attempt(rows, calls, position))
        position += 1
    identity = call.get("call_id")
    if not isinstance(identity, str) or not identity:
        raise ValueError("catalog call has no native identity")
    if sum(p.get("call_id") == identity for _, p in calls) != 1:
        raise ValueError("duplicated catalog call identity")
    if any(p.get("name") in {"exec", "functions.exec"}
           and isinstance(p.get("input") if p["type"] == "custom_tool_call" else p.get("arguments"), str)
           and (p.get("input") if p["type"] == "custom_tool_call" else p.get("arguments")).strip()
               == fixed_program
           for _, p in calls[position + 1:]):
        raise ValueError("duplicated live catalog discovery")
    outputs = [(i, r["payload"]) for i, r in enumerate(rows)
               if r.get("type") == "response_item" and r["payload"].get("call_id") == identity
               and r["payload"].get("type") == call["type"] + "_output"]
    if len(outputs) != 1 or outputs[0][0] <= index:
        raise ValueError("catalog lacks one joined native output")
    output_index, output = outputs[0]
    capture_events = []
    for i, row in enumerate(rows[:output_index]):
        p = row["payload"]
        if (row.get("type") == "event_msg" and p.get("type") in {"item_started", "item_completed"}
                and isinstance(p.get("item"), dict)
                and p["item"].get("type") in ({"McpToolCall", "CommandExecution", "FileChange"}
                                             if capture else {"McpToolCall", "CommandExecution"})):
            if not capture or i <= index or p["item"]["type"] == "McpToolCall":
                raise ValueError("native task operation preceded catalog discovery")
            capture_events.append((p["type"], p["item"]))
        if i > index and row.get("type") == "response_item" and p.get("type") in {"function_call", "custom_tool_call"}:
            raise ValueError("another tool action preceded catalog receipt")
    receipt = _catalog_output(output.get("output"), common_context=common_context, capture=capture)
    names = receipt["loci_runtime_catalog_v1"]
    if names != expected:
        raise ValueError("live catalog differs from expected tool set")
    result = {"tools": names, "row": index, "output_row": output_index, "call_id": identity,
              "trace_sha256": hashlib.sha256(raw).hexdigest()}
    if rejected:
        result["pre_capture_failures"] = rejected
    if common_context:
        result["common_catalog"] = receipt["common_runtime_catalog_v1"]
    if capture:
        artifact_raw, values = _catalog_artifact(catalog_artifact)
        common = result["common_catalog"]
        if len(values) != common["count"] or hashlib.sha256(artifact_raw[:-1]).hexdigest() != common["sha256"]:
            raise ValueError("retained common catalog artifact differs from first native receipt")
        _audit_capture_events(capture_events, catalog_destination, artifact_raw)
        result["catalog_artifact"] = {"filename": catalog_destination.name,
                                      "sha256": hashlib.sha256(artifact_raw).hexdigest(), "bytes": len(artifact_raw)}
        result["native_access_v1"] = receipt["native_access_v1"]
    return result


def audit_common_context(trace: Path, workspace: Path, observer: Path,
                         prompt: str, expected_tools: list[str], *, catalog_artifact: Path | None = None,
                         catalog_destination: Path | None = None) -> dict:
    """Retain actual ordered instruction parts and native schemas, never headings alone.

    Startup includes same-turn typed hooks assembled before the first model
    activity, even when they follow task submission. Their content is retained.
    Only explicit transport fields, assigned paths and declared Loci schemas
    vary. Later instruction updates fail; AGENTS tool output is source text.
    """
    from .accounting import _native_bootstrap_user

    catalog = audit_catalog(trace, expected_tools, common_context=True,
                            catalog_artifact=catalog_artifact, catalog_destination=catalog_destination)
    _, rows = _rows(trace)
    paths = {str(workspace): "{{r1.workspace}}", str(observer): "{{r1.observer}}"}
    if (len(paths) != 2 or any(not Path(path).is_absolute() for path in paths)
            or workspace == observer or workspace in observer.parents or observer in workspace.parents):
        raise ValueError("invalid assigned context paths")

    def normalize(value):
        if isinstance(value, str):
            if any(marker in value for marker in paths.values()):
                raise ValueError("reserved context path marker in native input")
            for path, marker in paths.items():
                value = value.replace(path, marker)
            return value
        if isinstance(value, list):
            return [normalize(item) for item in value]
        if isinstance(value, dict):
            return {key: normalize(item) for key, item in value.items()}
        return value

    expected = set(_expected(expected_tools))
    instructions, loci_contracts = [], []
    task_seen = bootstrap_seen = False
    tool_envelopes = developer_messages = 0
    turns = [r["payload"]["turn_id"] for r in rows if r.get("type") == "event_msg"
             and r["payload"].get("type") == "task_started" and "turn_id" in r["payload"]]
    if len(turns) != 1:
        raise ValueError("common context requires exactly one fresh native turn")
    model_started = False

    def startup_hook(payload):
        content = payload.get("content")
        metadata = payload.get("internal_chat_message_metadata_passthrough")
        if not isinstance(metadata, dict) or not isinstance(content, list) or not content:
            return False
        return (metadata.get("turn_id") == turns[0]
                and metadata.get("content_item_kinds") == ["hooks.additional_context"] * len(content)
                and isinstance(metadata.get("content_item_metadata"), list)
                and len(metadata["content_item_metadata"]) == len(content)
                and all(isinstance(item, dict)
                        and item.get("provenance") == {"type": "harness", "hook": True}
                        for item in metadata["content_item_metadata"]))

    for row in rows:
        payload = row["payload"]
        # Native completion events can precede the corresponding response item.
        if (row.get("type") == "event_msg"
                and payload.get("type") in {"item_started", "item_completed"}
                and isinstance(payload.get("item"), dict)
                and payload["item"].get("type") != "UserMessage"):
            model_started = True
        if row.get("type") == "token_usage_record":
            model_started = True
        if row.get("type") != "response_item":
            continue
        kind, role = payload.get("type"), payload.get("role")
        if kind in {"reasoning", "function_call", "custom_tool_call"} or (kind == "message" and role == "assistant"):
            model_started = True
        if kind == "additional_tools":
            if task_seen or role != "developer" or not isinstance(payload.get("tools"), list):
                raise ValueError("native tool schemas are missing or misplaced")
            tool_envelopes += 1
            common_tools = []
            declared_loci = []
            for tool in payload["tools"]:
                if not isinstance(tool, dict) or not isinstance(tool.get("name"), str):
                    raise ValueError("malformed native tool declaration")
                name = tool["name"]
                if name == "mcp__loci" and tool.get("type") == "namespace":
                    children = tool.get("tools")
                    if (not isinstance(children, list) or not children
                            or any(not isinstance(child, dict) or not isinstance(child.get("name"), str)
                                   for child in children)):
                        raise ValueError("malformed native Loci namespace")
                    names = ["mcp__loci__" + child["name"] for child in children]
                    if not names or len(names) != len(set(names)) or set(names) != expected:
                        raise ValueError("native Loci namespace differs from declared treatment")
                    loci_contracts.append(tool)
                    declared_loci.extend(names)
                elif name.startswith("mcp__loci__"):
                    if name not in expected:
                        raise ValueError("unexpected native Loci tool declaration")
                    loci_contracts.append(tool)
                    declared_loci.append(name)
                else:
                    common_tools.append(tool)
            if declared_loci and (len(declared_loci) != len(set(declared_loci)) or set(declared_loci) != expected):
                raise ValueError("native Loci declarations differ from declared treatment")
            value = deepcopy(payload)
            value["tools"] = common_tools
        elif kind == "message" and role in {"developer", "user"}:
            if task_seen and (model_started or role != "developer" or not startup_hook(payload)):
                raise ValueError("native instruction update after submitted task")
            content = payload.get("content")
            if (not isinstance(content, list) or not content
                    or any(not isinstance(c, dict) or c.get("type") != "input_text"
                           or not isinstance(c.get("text"), str) for c in content)):
                raise ValueError("malformed native instruction content")
            if role == "user":
                if _native_bootstrap_user(payload, turns[0]):
                    if bootstrap_seen:
                        raise ValueError("duplicate native bootstrap instructions")
                    bootstrap_seen = True
                else:
                    if not bootstrap_seen or "".join(c["text"] for c in content) != prompt:
                        raise ValueError("native submitted task differs from frozen prompt")
                    task_seen = True
                    instructions.append({"type": "submitted_task", "role": "user"})
                    continue
            else:
                developer_messages += 1
            value = deepcopy(payload)
        elif kind == "message" and role not in {"assistant"}:
            raise ValueError("unexpected native instruction role")
        else:
            continue
        # These are event identities, not delivered instruction text or schemas.
        for key in ("id", "thread_id"):
            value.pop(key, None)
        metadata = value.get("internal_chat_message_metadata_passthrough")
        if isinstance(metadata, dict):
            if "turn_id" in metadata and metadata["turn_id"] != turns[0]:
                raise ValueError("native instruction belongs to another turn")
            if "create_time" in metadata and (type(metadata["create_time"]) not in {int, float}
                                               or not math.isfinite(metadata["create_time"])):
                raise ValueError("invalid native instruction transport timestamp")
            for key in ("turn_id", "thread_id", "create_time"):
                metadata.pop(key, None)
        instructions.append(normalize(value))
    if not task_seen or not bootstrap_seen or not developer_messages or tool_envelopes != 1:
        raise ValueError("incomplete native common startup context")
    common = {"instructions": instructions, "catalog": catalog["common_catalog"]}
    contracts = normalize(loci_contracts)
    digest = lambda value: hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return {"schema": "r1-rendered-common-context-v1", "common": common,
            "common_sha256": digest(common), "loci_contracts": contracts,
            "loci_contracts_sha256": digest(contracts)}


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
                expected_tools: list[str], *, fixture: Path | None = None,
                common_context: bool = False, catalog_artifact: Path | None = None,
                catalog_destination: Path | None = None) -> dict:
    _condition(condition, expected_tools)
    catalog = audit_catalog(trace, expected_tools, common_context=common_context,
                            catalog_artifact=catalog_artifact, catalog_destination=catalog_destination)
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
