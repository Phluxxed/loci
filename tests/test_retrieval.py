from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest
import jsonschema

from loci import service
from loci.graph.contracts import GraphContractError, GraphEdge, GraphEvidence
from loci.graph.traversal import GraphTraversalStep
from loci.retrieval import _is_type_bridge_step, retrieve_context


def _indexed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, files: dict[str, str]):
    repo = tmp_path / "repo"
    for relative, content in files.items():
        path = repo / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    monkeypatch.setenv("LOCI_BASE_DIR", str(tmp_path / "store"))
    service.index_repo(repo, incremental=False)
    store = service.get_store()
    index = store.load(repo)
    assert index is not None
    nodes = {node["id"]: node for node in index["symbols"]}
    state = store.validate_graph_state(index)
    return repo, store, nodes, state


def _retrieve(indexed, query="", *, seed_ids=None):
    repo, store, nodes, state = indexed
    return retrieve_context(repo, store, nodes, state, query, seed_ids=seed_ids,
                            coverage="complete")


def _symbol(nodes: dict[str, dict], name: str) -> str:
    matches = [node["id"] for node in nodes.values() if node.get("name") == name]
    assert len(matches) == 1
    return matches[0]


def _envelope_bytes(result: dict) -> int:
    return len(json.dumps(
        {"content": [], "structuredContent": result, "isError": False},
        ensure_ascii=False, separators=(",", ":"),
    ).encode("utf-8"))


def _assert_schema(result: dict) -> None:
    schema = json.loads((Path(__file__).parents[1] /
                         ".scratch/deterministic-graph-retrieval/contract.schema.json").read_text())
    jsonschema.validate(result, {**schema, "$ref": "#/$defs/retrieve_response"})


def test_fixed_policy_delivers_bidirectional_calls_types_and_native_imports(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    indexed = _indexed(tmp_path, monkeypatch, {
        "schema.ts": "export interface WireEnvelope { value: string }\n"
                     "export interface WireEnvelopeView { value: string }\n",
        "public.ts": "export {\n  type WireEnvelope,\n  type WireEnvelopeView,\n} from './schema';\n",
        "assemble.ts": "import { type WireEnvelope } from './public';\n"
                       "export function encodeEnvelope(value: WireEnvelope) { return value.value; }\n"
                       "export function assembleEnvelope(value: WireEnvelope) { return encodeEnvelope(value); }\n",
        "entry.ts": "import { assembleEnvelope } from './assemble';\n"
                    "export function start() { return assembleEnvelope({ value: 'x' }); }\n",
    })
    result = _retrieve(indexed, "assembleEnvelope")
    edges = {(item["edge"]["from"], item["edge"]["type"], item["edge"]["to"],
              item["traversed"]) for item in result["relationships"]}
    assemble = _symbol(indexed[2], "assembleEnvelope")
    encode = _symbol(indexed[2], "encodeEnvelope")
    start = _symbol(indexed[2], "start")
    wire = _symbol(indexed[2], "WireEnvelope")
    assert (assemble, "calls", encode, "forward") in edges
    assert (start, "calls", assemble, "reverse") in edges
    assert any(source["content"].startswith("export {\n") and "WireEnvelopeView" in source["content"]
               for source in result["sources"])
    assert any(edge[1] in {"uses_type", "references_type"} and edge[2] == wire for edge in edges)
    assert any(edge[1] in {"imports", "imports_type"} for edge in edges)
    assert all(relation["proof"] == "complete" and relation["source_ids"]
               for relation in result["relationships"])
    assert all(relation["edge"]["from"] in {node["id"] for node in result["nodes"]}
               and relation["edge"]["to"] in {node["id"] for node in result["nodes"]}
               for relation in result["relationships"])
    assert result["usage"]["output_bytes"] == _envelope_bytes(result)
    assert result["usage"]["evidence_bytes"] <= result["limits"]["max_evidence_bytes"]
    _assert_schema(result)


def test_native_go_package_endpoint_keeps_import_and_package_control_proof(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    indexed = _indexed(tmp_path, monkeypatch, {
        "go.mod": "module example.test/retrieve\n\ngo 1.22\n",
        "a/a.go": "package a\n\nimport (\n    \"example.test/retrieve/b\"\n)\n\nfunc Read() string { return b.Value() }\n",
        "b/b.go": "package b\n\nfunc Value() string { return \"ok\" }\n",
    })
    read_id = _symbol(indexed[2], "Read")
    result = _retrieve(indexed, seed_ids=[read_id])
    imports = [relation for relation in result["relationships"]
               if relation["edge"]["type"] == "imports"]
    assert imports
    relation = imports[0]
    node_by_id = {node["id"]: node for node in result["nodes"]}
    assert node_by_id[relation["edge"]["from"]]["kind"] == "file"
    assert node_by_id[relation["edge"]["to"]]["kind"] == "package"
    proof = [result["sources"][source_id - 1]["content"]
             for source_id in relation["source_ids"]]
    assert any("example.test/retrieve/b" in value for value in proof)
    assert any(value.startswith("package b") for value in proof)
    assert any(value.startswith("module example.test/retrieve") for value in proof)
    assert any(item["basis"] == "go_package" for item in result["ownership"])
    _assert_schema(result)


def test_python_multiline_import_proof_is_complete(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    indexed = _indexed(tmp_path, monkeypatch, {
        "values.py": "def remote_value():\n    return 7\n",
        "consumer.py": "from values import (\n    remote_value,\n)\n\ndef consume():\n    return remote_value()\n",
    })
    result = _retrieve(indexed, seed_ids=[_symbol(indexed[2], "consume")])
    imports = [item for item in result["relationships"]
               if item["edge"]["type"] == "imports"]
    assert imports
    proof = [result["sources"][source_id - 1]["content"]
             for source_id in imports[0]["source_ids"]]
    assert "from values import (\n    remote_value,\n)" in proof


def test_markdown_exact_file_and_literal_use_real_page_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    indexed = _indexed(tmp_path, monkeypatch, {
        "guide.md": "# Guide\n\nIntro.\n\n## Hidden detail\n\nA literal-only telescope §§§.\n",
    })
    exact = _retrieve(indexed, "./guide.md")
    assert exact["selection"]["mode"] == "file"
    assert exact["scope"]["matching"] == "exact_file"
    assert exact["nodes"][0]["kind"] == "section"
    assert all(node["kind"] != "file" for node in exact["nodes"])

    literal = _retrieve(indexed, "§§§")
    assert literal["selection"]["mode"] == "literal"
    assert literal["scope"]["matching"] == "source_literal"
    assert literal["items"]


def test_exact_program_file_anchor_retains_representative_members(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    indexed = _indexed(tmp_path, monkeypatch, {
        "entry.ts": (
            "export function first() { return 1; }\n"
            "export function second() { return 2; }\n"
            "export function third() { return 3; }\n"
            "export function fourth() { return 4; }\n"
        ),
    })

    result = _retrieve(indexed, "entry.ts")

    assert result["scope"]["matching"] == "exact_file"
    assert result["items"][0]["node_id"] == "entry.ts::__file__#file"
    assert {item["node_id"] for item in result["items"][1:]} == {
        "entry.ts::first#function",
        "entry.ts::second#function",
        "entry.ts::third#function",
    }


def test_request_validation_is_utf8_bounded_and_requires_input(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    indexed = _indexed(tmp_path, monkeypatch, {"a.py": "def value():\n    return 1\n"})
    with pytest.raises(GraphContractError, match="query or seed_ids"):
        _retrieve(indexed)
    with pytest.raises(GraphContractError, match="4096 UTF-8 bytes"):
        _retrieve(indexed, "é" * 2049)
    value_id = _symbol(indexed[2], "value")
    with pytest.raises(GraphContractError, match="unique IDs"):
        _retrieve(indexed, seed_ids=[value_id, value_id])


def test_insertion_order_does_not_change_semantic_packet(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    indexed = _indexed(tmp_path, monkeypatch, {
        "a.py": "def leaf():\n    return 1\n\ndef root():\n    return leaf()\n",
        "b.py": "from a import root\n\ndef caller():\n    return root()\n",
    })
    root_id = _symbol(indexed[2], "root")
    first = _retrieve(indexed, seed_ids=[root_id])
    repo, store, nodes, state = indexed
    reversed_state = replace(
        state,
        edges=tuple(reversed(state.edges)),
        imports=tuple(reversed(state.imports)),
        symbol_references=tuple(reversed(state.symbol_references)),
        calls=tuple(reversed(state.calls)),
        type_relations=tuple(reversed(state.type_relations)),
    )
    second = retrieve_context(repo, store, dict(reversed(list(nodes.items()))),
                              reversed_state,
                              seed_ids=[root_id], coverage="complete")
    assert first == second


def test_large_anchor_preview_does_not_starve_short_relationship(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    body = "".join(f"    value_{index} = {index}\n" for index in range(240))
    indexed = _indexed(tmp_path, monkeypatch, {
        "large.py": "def leaf():\n    return 1\n\ndef large():\n" + body + "    return leaf()\n",
    })
    large_id = _symbol(indexed[2], "large")
    leaf_id = _symbol(indexed[2], "leaf")
    result = _retrieve(indexed, seed_ids=[large_id])
    anchor = next(item for item in result["items"] if item["node_id"] == large_id)
    assert anchor["complete"] is False
    assert anchor["extent"]["end_byte"] - anchor["extent"]["start_byte"] > len(
        result["sources"][anchor["source_ids"][0] - 1]["content"].encode("utf-8")
    )
    assert anchor["source_ref"]
    assert any(relation["edge"]["from"] == large_id
               and relation["edge"]["to"] == leaf_id
               and relation["edge"]["type"] == "calls"
               for relation in result["relationships"]), result
    assert result["usage"]["evidence_bytes"] <= result["limits"]["max_evidence_bytes"]


def test_relation_between_two_explicit_anchors_is_still_delivered(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    indexed = _indexed(tmp_path, monkeypatch, {
        "pair.py": "def callee():\n    return 1\n\ndef caller():\n    return callee()\n",
    })
    caller = _symbol(indexed[2], "caller")
    callee = _symbol(indexed[2], "callee")
    result = _retrieve(indexed, seed_ids=[caller, callee])
    assert any(relation["edge"]["from"] == caller
               and relation["edge"]["to"] == callee
               and relation["edge"]["type"] == "calls"
               for relation in result["relationships"])


def test_selected_anchors_stage_shared_type_bridge_before_body_calls(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    indexed = _indexed(tmp_path, monkeypatch, {
        "service.ts": (
            "export type WorkBinding = { id: string };\n"
            "type CommandOptions = { binding: WorkBinding };\n"
            "function bodyCall() { return 1; }\n"
            "export function capture(options: CommandOptions) {\n"
            "  bodyCall();\n"
            "  return options.binding;\n"
            "}\n"
        ),
    })
    capture = _symbol(indexed[2], "capture")
    options = _symbol(indexed[2], "CommandOptions")
    binding = _symbol(indexed[2], "WorkBinding")

    result = _retrieve(indexed, seed_ids=[capture, binding])
    first_edges = [
        (relation["edge"]["from"], relation["edge"]["type"], relation["edge"]["to"])
        for relation in result["relationships"][:2]
    ]

    assert first_edges == [
        (capture, "uses_type", options),
        (options, "uses_type", binding),
    ]
    assert all(
        relation["proof"] == "complete" and relation["source_ids"]
        for relation in result["relationships"][:2]
    )


def test_shared_bridge_target_does_not_promote_a_call_to_that_target():
    evidence = GraphEvidence("service.ts", 1, "a" * 64)
    type_step = GraphTraversalStep(
        "anchor",
        "shared",
        GraphEdge("anchor", "shared", "uses_type", True, "loci", "exact", evidence),
        "forward",
    )
    call_step = GraphTraversalStep(
        "anchor",
        "shared",
        GraphEdge("anchor", "shared", "calls", True, "loci", "exact", evidence),
        "forward",
    )

    assert _is_type_bridge_step(type_step, {"shared": 0}) is True
    assert _is_type_bridge_step(call_step, {"shared": 0}) is False


def test_explicit_anchor_relationship_precedes_neighbor_limit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    leaves = "".join(
        f"def leaf_{index:02d}():\n    return {index}\n\n"
        for index in range(40)
    )
    calls = " + ".join([*(f"leaf_{index:02d}()" for index in range(40)), "zz_target()"])
    indexed = _indexed(tmp_path, monkeypatch, {
        "many.py": (
            f"{leaves}"
            "def zz_target():\n    return 100\n\n"
            f"def root():\n    return {calls}\n"
        ),
    })
    root_id = _symbol(indexed[2], "root")
    target_id = _symbol(indexed[2], "zz_target")

    result = _retrieve(indexed, seed_ids=[root_id, target_id])

    assert any(relation["edge"]["from"] == root_id
               and relation["edge"]["to"] == target_id
               and relation["edge"]["type"] == "calls"
               for relation in result["relationships"])
    assert any(item["reason"] == "neighbor_limit" for item in result["omissions"])


def test_anchor_type_proof_precedes_incidental_owner_context_under_output_pressure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    padding = "x" * 520
    indexed = _indexed(tmp_path, monkeypatch, {
        "package.json": json.dumps({
            "name": "retrieval-pressure-fixture",
            "type": "module",
            "description": "p" * 620,
        }) + "\n",
        "tsconfig.json": json.dumps({
            "compilerOptions": {"module": "nodenext", "strict": True},
            "include": ["*.ts"],
            "fixturePadding": "t" * 320,
        }) + "\n",
        "binding.ts": (
            f"export type BindingNoiseOne = {{ value: '{padding}' }};\n"
            f"export type BindingNoiseTwo = {{ value: '{padding}' }};\n"
            f"export type BindingNoiseThree = {{ value: '{padding}' }};\n"
            "export type WorkContextBinding = { id: string; status: 'active' };\n"
        ),
        "public.ts": (
            "export type {\n"
            "  BindingNoiseOne,\n"
            "  BindingNoiseTwo,\n"
            "  BindingNoiseThree,\n"
            "  WorkContextBinding,\n"
            "} from './binding.ts';\n"
        ),
        "service.ts": (
            "import type { WorkContextBinding } from './public.ts';\n"
            f"type ServiceNoiseOne = {{ value: '{padding}' }};\n"
            f"type ServiceNoiseTwo = {{ value: '{padding}' }};\n"
            f"type ServiceNoiseThree = {{ value: '{padding}' }};\n"
            "type CaptureCommandResultOptions = { binding: WorkContextBinding };\n"
        ),
    })
    capture = _symbol(indexed[2], "CaptureCommandResultOptions")
    binding = _symbol(indexed[2], "WorkContextBinding")

    for result in (
        _retrieve(indexed, "CaptureCommandResultOptions"),
        _retrieve(indexed, "binding contract", seed_ids=[capture, binding]),
    ):
        relation = next(
            item for item in result["relationships"]
            if item["edge"]["from"] == capture
            and item["edge"]["to"] == binding
            and item["edge"]["type"] == "uses_type"
        )
        assert relation["edge"]["resolution"] == "import-resolved"
        assert relation["proof"] == "complete"
        proof_files = {
            result["sources"][source_id - 1]["file"]
            for source_id in relation["source_ids"]
        }
        assert proof_files == {
            "binding.ts", "package.json", "public.ts", "service.ts", "tsconfig.json",
        }
        ownership = {
            (item["owner_id"], item["member_id"], item["basis"])
            for item in result["ownership"]
        }
        assert ("service.ts::__file__#file", capture, "indexed_file") in ownership
        assert ("binding.ts::__file__#file", binding, "indexed_file") in ownership
        assert result["usage"]["output_bytes"] <= result["limits"]["max_output_bytes"]
        assert result["usage"]["evidence_bytes"] <= result["limits"]["max_evidence_bytes"]


def test_family_rounds_interleave_two_high_fanout_anchors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    indexed = _indexed(tmp_path, monkeypatch, {
        "a.py": "def a1(): return 1\ndef a2(): return 2\ndef a3(): return 3\n"
                "def root_a(): return a1() + a2() + a3()\n",
        "b.py": "def b1(): return 1\ndef b2(): return 2\ndef b3(): return 3\n"
                "def root_b(): return b1() + b2() + b3()\n",
    })
    root_a = _symbol(indexed[2], "root_a")
    root_b = _symbol(indexed[2], "root_b")
    result = _retrieve(indexed, seed_ids=[root_a, root_b])
    call_sources = [relation["edge"]["from"] for relation in result["relationships"]
                    if relation["edge"]["type"] == "calls"
                    and relation["edge"]["from"] in {root_a, root_b}]
    assert len(call_sources) == 6
    assert call_sources == [root_a if index % 2 == 0 else root_b
                            for index in range(len(call_sources))]


def test_edge_proof_must_match_complete_stored_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    indexed = _indexed(tmp_path, monkeypatch, {
        "a.py": "def leaf():\n    return 1\n\ndef root():\n    return leaf()\n",
    })
    repo, store, nodes, state = indexed
    root_id = _symbol(nodes, "root")
    changed = tuple(
        replace(edge, evidence=replace(edge.evidence, content_hash="f" * 64))
        if edge.type == "calls" else edge
        for edge in state.edges
    )
    result = retrieve_context(repo, store, nodes, replace(state, edges=changed),
                              seed_ids=[root_id], coverage="complete")
    assert not any(relation["edge"]["type"] == "calls"
                   for relation in result["relationships"])
    assert any(item["reason"] == "proof_unavailable" for item in result["omissions"])


def test_missing_anchor_definition_is_reported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    indexed = _indexed(tmp_path, monkeypatch, {"a.py": "def root():\n    return 1\n"})
    repo, store, nodes, state = indexed
    root_id = _symbol(nodes, "root")
    changed_nodes = {key: dict(value) for key, value in nodes.items()}
    changed_nodes[root_id]["content_hash"] = "f" * 64
    result = retrieve_context(repo, store, changed_nodes, state,
                              seed_ids=[root_id], coverage="complete")
    assert not any(item["node_id"] == root_id for item in result["items"])
    assert any(item["reason"] == "source_unavailable" for item in result["omissions"])


def test_javascript_named_control_proves_import_reference_and_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    indexed = _indexed(tmp_path, monkeypatch, {
        "package.json": '{"name":"fixture","type":"module","imports":{"#shared":"./shared.js"}}\n',
        "main.js": 'import { target } from "#shared";\n'
                   "export function assemble() { return target(); }\n",
        "shared.js": 'export function target() { return "ok"; }\n',
    })
    result = _retrieve(indexed, "assemble")
    sources = {source["id"]: source for source in result["sources"]}
    controlled = [
        relation for relation in result["relationships"]
        if relation["edge"]["type"] in {"imports", "references", "calls"}
        and relation["edge"]["resolution"] == "import-resolved"
    ]
    assert {relation["edge"]["type"] for relation in controlled} == {
        "imports", "references", "calls",
    }, result
    assert all(any(sources[source_id]["file"] == "package.json"
                   for source_id in relation["source_ids"])
               for relation in controlled)


def test_missing_named_javascript_control_withholds_complete_proof(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    indexed = _indexed(tmp_path, monkeypatch, {
        "package.json": '{"name":"fixture","type":"module","imports":{"#shared":"./shared.js"}}\n',
        "main.js": 'import { target } from "#shared";\n'
                   "export function assemble() { return target(); }\n",
        "shared.js": 'export function target() { return "ok"; }\n',
    })
    repo, store, nodes, state = indexed
    changed_hashes = dict(state.input_hashes)
    assert changed_hashes.pop("package.json", None) is not None
    result = retrieve_context(repo, store, nodes, replace(state, input_hashes=changed_hashes),
                              "assemble", coverage="complete")
    assert not any(relation["edge"]["resolution"] == "import-resolved"
                   for relation in result["relationships"])
    assert any(item["reason"] == "proof_unavailable" for item in result["omissions"])
