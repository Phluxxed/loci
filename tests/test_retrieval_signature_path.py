from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from loci import service
from loci._retrieval_output import LIMITS
from loci.graph.contracts import GraphEdge, GraphEvidence
from loci.graph.state import GraphIndexState
from loci.retrieval import _selected_signature_type_paths, retrieve_context


def _indexed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    repo = tmp_path / "repo"
    noise_functions = "".join(
        f"function bodyNoise{index}() {{ return '{'x' * 420}'; }}\n"
        for index in range(6)
    )
    noise_calls = "\n".join(f"  bodyNoise{index}();" for index in range(6))
    files = {
        "package.json": '{"name":"signature-path","type":"module"}\n',
        "tsconfig.json": '{"compilerOptions":{"module":"nodenext","strict":true}}\n',
        "binding.ts": (
            "export type WorkContextBinding = { id: string; session: string };\n"
        ),
        "public.ts": "export type { WorkContextBinding } from './binding.ts';\n",
        "receipt.ts": "export type ResultReceipt = { opaqueId: string };\n",
        "service.ts": "".join((
            "import type { WorkContextBinding } from './public.ts';\n",
            "import type { ResultReceipt } from './receipt.ts';\n",
            "type Clock = () => number;\n",
            "type BodyOnly = { value: string };\n",
            "type ConstraintPayload = { constrained: string };\n",
            "export type CaptureOptions = { binding: WorkContextBinding; clock: Clock };\n",
            "function bodyCall() { return 'opaque'; }\n",
            noise_functions,
            "export function capture<T extends (x: ConstraintPayload) => void>"
            "(options: CaptureOptions): ResultReceipt {\n",
            noise_calls,
            "\n  const local: BodyOnly = { value: 'body' };",
            "\n  return { opaqueId: bodyCall() };\n",
            "}\n",
        )),
        "caller.ts": (
            "import { capture } from './service.ts';\n"
            "export function caller() {\n"
            "  return capture({ binding: { id: 'i', session: 's' } });\n"
            "}\n"
        ),
    }
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


def _symbol(nodes: dict[str, dict], name: str) -> str:
    matches = [node["id"] for node in nodes.values() if node.get("name") == name]
    assert len(matches) == 1
    return matches[0]


def test_ordinary_function_lookup_stages_input_contract_path_before_incidental_edges(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    repo, store, nodes, state = _indexed(tmp_path, monkeypatch)
    capture = _symbol(nodes, "capture")
    options = _symbol(nodes, "CaptureOptions")
    binding = _symbol(nodes, "WorkContextBinding")
    receipt = _symbol(nodes, "ResultReceipt")
    body = _symbol(nodes, "bodyCall")
    caller = _symbol(nodes, "caller")
    body_only = _symbol(nodes, "BodyOnly")
    constraint = _symbol(nodes, "ConstraintPayload")

    paths = _selected_signature_type_paths((capture,), state, nodes)
    assert paths == ((capture, options, binding),)
    assert all(body_only not in path for path in paths)
    assert all(constraint not in path for path in paths)

    first = retrieve_context(repo, store, nodes, state, "capture", coverage="complete")
    second = retrieve_context(
        repo,
        store,
        dict(reversed(list(nodes.items()))),
        replace(
            state,
            edges=tuple(reversed(state.edges)),
            type_relations=tuple(reversed(state.type_relations)),
        ),
        "capture",
        coverage="complete",
    )

    assert first == second
    edges = [
        (relation["edge"]["from"], relation["edge"]["type"], relation["edge"]["to"])
        for relation in first["relationships"]
    ]
    assert edges[:2] == [
        (capture, "uses_type", options),
        (options, "uses_type", binding),
    ]
    incidental = {
        (capture, "uses_type", receipt),
        (capture, "calls", body),
        (caller, "calls", capture),
    }
    assert all(edge not in incidental for edge in edges[:2])
    assert (capture, "calls", body) in edges
    assert (caller, "calls", capture) in edges

    relation = first["relationships"][1]
    assert relation["proof"] == "complete"
    assert {first["sources"][source_id - 1]["file"] for source_id in relation["source_ids"]} == {
        "binding.ts", "package.json", "public.ts", "service.ts", "tsconfig.json",
    }
    assert first["usage"]["output_bytes"] <= 16_384
    assert first["limits"]["max_hops"] == 2
    assert any(omission["reason"] == "output_budget" for omission in first["omissions"])


def test_signature_path_and_ordinary_pass_share_one_neighbor_cap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    repo, store, nodes, state = _indexed(tmp_path, monkeypatch)
    capture = _symbol(nodes, "capture")
    options = _symbol(nodes, "CaptureOptions")
    binding = _symbol(nodes, "WorkContextBinding")
    clock = _symbol(nodes, "Clock")
    monkeypatch.setitem(LIMITS, "max_neighbors", 1)

    result = retrieve_context(repo, store, nodes, state, "capture", coverage="complete")
    edges = [
        (relation["edge"]["from"], relation["edge"]["type"], relation["edge"]["to"])
        for relation in result["relationships"]
    ]

    assert edges[:2] == [
        (capture, "uses_type", options),
        (options, "uses_type", binding),
    ]
    assert [edge for edge in edges if edge[0] == options] == [
        (options, "uses_type", binding),
    ]
    assert (options, "uses_type", clock) not in edges
    assert any(omission["reason"] == "neighbor_limit" for omission in result["omissions"])


def test_failed_input_proof_does_not_admit_its_dependency(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    repo, store, nodes, state = _indexed(tmp_path, monkeypatch)
    capture = _symbol(nodes, "capture")
    options = _symbol(nodes, "CaptureOptions")
    binding = _symbol(nodes, "WorkContextBinding")
    changed = tuple(
        replace(edge, evidence=replace(edge.evidence, content_hash="f" * 64))
        if edge.from_id == capture and edge.to_id == options and edge.type == "uses_type"
        else edge
        for edge in state.edges
    )

    result = retrieve_context(
        repo, store, nodes, replace(state, edges=changed), "capture", coverage="complete",
    )
    edges = {
        (relation["edge"]["from"], relation["edge"]["type"], relation["edge"]["to"])
        for relation in result["relationships"]
    }

    assert (capture, "uses_type", options) not in edges
    assert (options, "uses_type", binding) not in edges
    assert any(omission["reason"] == "proof_unavailable" for omission in result["omissions"])


def test_signature_path_requires_indexed_input_role_evidence():
    evidence = GraphEvidence("service.ts", 1, "a" * 64)
    edge = GraphEdge(
        "service.ts::capture#function",
        "service.ts::CaptureOptions#type",
        "uses_type",
        True,
        "loci",
        "exact",
        evidence,
    )
    nodes = {
        edge.from_id: {"id": edge.from_id, "kind": "function"},
        edge.to_id: {"id": edge.to_id, "kind": "type"},
    }

    assert _selected_signature_type_paths(
        (edge.from_id,), GraphIndexState.empty(edges=(edge,)), nodes,
    ) == ()
