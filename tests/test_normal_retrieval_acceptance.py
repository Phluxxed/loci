"""Independent normal-service scenarios for W1.7.2.4 acceptance."""
import hashlib
import json

import pytest

from loci import service
from loci.mcp_output_models import LociRetrieveOutput
from tests.test_type_relation_service import _setup


def _packet(repo, **request):
    result = service.retrieve(repo, **request)
    LociRetrieveOutput.model_validate(result)
    raw = json.dumps({"content": [], "structuredContent": result, "isError": False},
                     ensure_ascii=False, separators=(",", ":")).encode()
    assert len(raw) == result["usage"]["output_bytes"] <= 16384
    assert result["usage"]["nodes_examined"] <= 64
    assert result["usage"]["evidence_bytes"] <= 8192
    assert len(result["items"]) <= 12
    sources = {s["id"]: s for s in result["sources"]}
    for source in sources.values():
        file = (repo / source["file"]).read_bytes()
        assert hashlib.sha256(file).hexdigest() == source["content_hash"]
        assert source["content"].encode() == file[source["start_byte"]:source["end_byte"]]
    for relation in result["relationships"]:
        evidence = relation["edge"]["evidence"]
        assert any(sources[i]["file"] == evidence["file"]
                   and sources[i]["content_hash"] == evidence["content_hash"]
                   and sources[i]["start_line"] <= evidence["line"] <= sources[i]["end_line"]
                   for i in relation["source_ids"])
    return result


@pytest.mark.parametrize("root,leaf", [("orchard", "telescope"), ("packetize", "resolve_record")])
def test_renamed_local_cycle_and_explicit_endpoints_keep_relationship_proof(tmp_path, monkeypatch, root, leaf):
    repo, _ = _setup(tmp_path, monkeypatch, {"module.py":
        f"def {root}():\n    return {leaf}()\n\ndef {leaf}():\n    return {root}()\n"})
    root_id = f"module.py::{root}#function"
    leaf_id = f"module.py::{leaf}#function"
    result = _packet(repo, seed_ids=[root_id, leaf_id])
    assert any(r["edge"]["from"] == root_id and r["edge"]["to"] == leaf_id
               and r["edge"]["type"] == "calls" for r in result["relationships"])
    assert result == service.retrieve(repo, seed_ids=[root_id, leaf_id])


def test_large_anchor_leaves_room_for_short_call_proof_and_exact_expansion(tmp_path, monkeypatch):
    body = "def assemble_record():\n" + "    # Padding documents independent business conditions.\n" * 300
    body += "    return target()\n"
    repo, _ = _setup(tmp_path, monkeypatch, {
        "main.py": "from helper import target\n\n" + body,
        "helper.py": "def target():\n    return 7\n",
    })
    result = _packet(repo, seed_ids=["main.py::assemble_record#function"])
    assert any(r["edge"]["type"] == "calls" and r["edge"]["to"] == "helper.py::target#function"
               for r in result["relationships"])
    item = next(i for i in result["items"] if i["node_id"] == "main.py::assemble_record#function")
    assert item["complete"] is False
    ref = item["source_ref"]
    source = []
    while ref:
        page = service.read(repo, ref)
        source.append(page["source"]["content"])
        ref = page["next_source_ref"]
    assert "".join(source).rstrip("\n") == body.rstrip("\n")


def test_rust_module_types_and_imports_keep_cargo_and_module_proof(tmp_path, monkeypatch):
    repo, _ = _setup(tmp_path, monkeypatch, {
        "Cargo.toml": '[package]\nname = "normal_context_fixture"\nversion = "0.1.0"\nedition = "2021"\n',
        "src/lib.rs": "mod fields;\nuse crate::fields::Packet;\npub fn measure(value: Packet) -> i32 { value.value }\n",
        "src/fields.rs": "pub struct Packet { pub value: i32 }\n",
    })
    result = _packet(repo, query="measure")
    assert any(r["edge"]["type"] == "uses_type" and r["edge"]["to"].endswith("::Packet#struct")
               for r in result["relationships"])
    assert any(s["file"] == "Cargo.toml" for s in result["sources"])
    assert any("mod fields;" in s["content"] for s in result["sources"])


def test_unsupported_dynamic_call_is_not_invented(tmp_path, monkeypatch):
    repo, _ = _setup(tmp_path, monkeypatch, {
        "dynamic.py": "def dispatch(callback):\n    return callback()\n",
    })
    result = _packet(repo, seed_ids=["dynamic.py::dispatch#function"])
    assert not result["relationships"]
    assert result["scope"]["exhaustive"] is False
    assert result["omissions"]


def test_query_ambiguity_is_reported_beyond_retained_candidates(tmp_path, monkeypatch):
    repo, _ = _setup(tmp_path, monkeypatch, {
        "first.py": "def transform():\n    return 'first'\n",
        "second.py": "def transform():\n    return 'second'\n",
        "decoy.py": "def separate():\n    return 'not transform'\n",
    })
    result = _packet(repo, query="transform")
    assert result["selection"]["candidate_count"] >= 2
    assert {a["node_id"] for a in result["anchors"]} <= {
        "first.py::transform#function", "second.py::transform#function"}
    assert result["anchors"]
    assert result["selection"]["candidate_count"] == len(result["anchors"]) + result["selection"]["omitted_candidates"]
    assert any(o["reason"] == "ambiguous_anchor" for o in result["omissions"])


def test_high_fanout_keeps_neighbor_and_delivery_limits_explicit(tmp_path, monkeypatch):
    functions = "\n".join(f"def leaf_{i:02d}():\n    return {i}\n" for i in range(40))
    root = "def fanout_root():\n" + "".join(f"    leaf_{i:02d}()\n" for i in range(40))
    repo, _ = _setup(tmp_path, monkeypatch, {"fanout.py": root + "\n" + functions})
    result = _packet(repo, query="fanout_root")
    assert result["usage"]["eligible_edges_considered"] >= 40
    assert any(o["reason"] == "neighbor_limit" and o["count"] >= 8 for o in result["omissions"])
    assert result["relationships"]
    assert result == service.retrieve(repo, query="fanout_root")


def test_javascript_package_mapping_retains_named_control_proof(tmp_path, monkeypatch):
    repo, _ = _setup(tmp_path, monkeypatch, {
        "package.json": '{"name":"fixture","type":"module","imports":{"#shared":"./shared.js"}}\n',
        "main.js": 'import { target } from "#shared";\nexport function assemble() { return target(); }\n',
        "shared.js": 'export function target() { return "ok"; }\n',
    })
    result = _packet(repo, query="assemble")
    imports = [r for r in result["relationships"] if r["edge"]["type"] == "imports"]
    assert imports
    sources = {s["id"]: s for s in result["sources"]}
    assert any(sources[i]["file"] == "package.json" for i in imports[0]["source_ids"])


def test_oversized_mandatory_identity_returns_source_free_budget_error(tmp_path, monkeypatch):
    first, second = "first_" + "a" * 4096, "second_" + "b" * 4096
    repo, _ = _setup(tmp_path, monkeypatch, {"long.py":
        f"def {first}():\n    return 1\n\ndef {second}():\n    return 2\n"})
    with pytest.raises(service.LociError) as exc:
        service.retrieve(repo, seed_ids=[f"long.py::{first}#function", f"long.py::{second}#function"])
    assert exc.value.code == "OUTPUT_BUDGET_EXCEEDED"
