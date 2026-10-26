"""Combined source/navigation/optional proof behavior over the actual R1 surface."""
import asyncio
from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from benchmarks.architecture import ROOT, acquire, validate_packets
from benchmarks.architecture_cases import load_suite, prepare_snapshots, requests, score_acquisition
from benchmarks.architecture_integrated import run, verify
from loci.graph_free import GraphFreeError
from loci.integrated import IntegratedSource


def _source(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    (root / "entry.ts").write_text(
        "import type { Public } from './model';\n"
        "export function entry(value: Public): Public { return value; }\n")
    (root / "model.ts").write_text(
        "export type Base = string;\nexport type Middle = Base;\nexport type Public = Middle;\n")
    return root, IntegratedSource(tmp_path / "store")


def test_source_only_workflow_loads_no_semantics_and_returns_candidates(tmp_path):
    program = '''import json,sys
from pathlib import Path
from loci.integrated import IntegratedSource
root=Path(sys.argv[1]); root.mkdir()
(root/'entry.ts').write_text('export { value } from "./model";\\n')
(root/'model.ts').write_text('export const value = 1;\\n')
service=IntegratedSource(Path(sys.argv[2]))
packet=service.retrieve(root,'entry.ts')
assert packet['navigation']['candidates'][0]['path']=='model.ts'
assert packet['navigation']['exhaustive'] is False
assert packet['relationships']==packet['nodes']==[]
item=packet['items'][0]
again=service.retrieve(root,seed_ids=[item['node_id']])
assert again['sources']==packet['sources']
page=service.read(root,item['source_ref'])
assert page['source']['content']==packet['sources'][0]['content']
for payload in (packet,again,page):
    envelope={'content':[],'structuredContent':payload,'isError':False}
    assert payload['usage']['output_bytes']==len(json.dumps(envelope,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode())
assert not any(name in {'loci.parser','loci.graph','loci.storage'} or name.startswith(('loci.parser.','loci.graph.','loci.storage.')) for name in sys.modules)
'''
    subprocess.run([sys.executable, "-c", program, str(tmp_path / "repo"), str(tmp_path / "store")],
                   check=True, cwd=ROOT, env=dict(os.environ, PYTHONPATH=str(ROOT / "src")))


def test_combined_cache_freshness_and_identity_proof(tmp_path, monkeypatch):
    root, service = _source(tmp_path)
    source = service.retrieve(root, "entry.ts")
    assert source["navigation"]["candidates"][0]["path"] == "model.ts"
    assert service.semantic_observer()["index"] is None
    with pytest.raises(GraphFreeError) as hidden:
        service.proof_context(root, "entry.ts::entry#function")
    assert hidden.value.code == "UNKNOWN_PROOF_ID"
    first = service.semantic_context(root, "entry", anchor_file="entry.ts")
    first_work = service.semantic_observer()["work"]
    assert first_work["parsed_paths"] and not first_work["cache_hit"]
    identity = first["anchors"][0]["node_id"]
    assert service.retrieve(root, seed_ids=[identity])["sources"][0]["file"] == "entry.ts"
    repeated = service.semantic_context(root, "entry", anchor_file="entry.ts")
    assert repeated == first
    warm = service.semantic_observer()["work"]
    assert warm["cache_hit"] and warm["parsed_paths"] == []
    assert {row["name"] for row in warm["phases"]} >= {"cachevalidate", "cache_freshness"}
    resolve = service._resolve_slice
    monkeypatch.setattr(service, "_resolve_slice", lambda *args: pytest.fail("proof resolved again"))
    proof = service.proof_context(root, identity)
    assert proof["proof_request"] == {"node_id": identity, "scope": "same_computed_slice"}
    assert service.proof_observer()["parsed_paths"] == []
    assert service.proof_observer()["native_resolution_calls"] == 0
    semantic_ref = first["sources"][0]["source_ref"]
    assert service.read(root, semantic_ref)["source"]["content"] == first["sources"][0]["content"]
    (root / "model.ts").write_text((root / "model.ts").read_text().replace("string", "number"))
    with pytest.raises(GraphFreeError) as stale:
        service.proof_context(root, identity)
    assert stale.value.code == "SOURCE_STALE"
    monkeypatch.setattr(service, "_resolve_slice", resolve)
    changed = service.semantic_context(root, "entry", anchor_file="entry.ts")
    assert not service.semantic_observer()["work"]["cache_hit"]
    assert service.semantic_observer()["work"]["parsed_paths"]
    assert changed["snapshot"] != first["snapshot"]
    service.proof_context(root, changed["anchors"][0]["node_id"])


def test_control_mutation_invalidates_semantic_cache_and_stale_reads_are_refused(tmp_path):
    root, service = _source(tmp_path)
    control = root / "package.json"
    control.write_text('{"name":"fixture","type":"module"}\n')
    source = service.retrieve(root, "entry.ts")
    first = service.semantic_context(root, "entry", anchor_file="entry.ts")
    service.semantic_context(root, "entry", anchor_file="entry.ts")
    assert service.semantic_observer()["work"]["cache_hit"]
    control.write_text('{"name":"fixture","type":"commonjs"}\n')
    with pytest.raises(GraphFreeError) as stale:
        service.proof_context(root, first["anchors"][0]["node_id"])
    assert stale.value.code == "SOURCE_STALE"
    refreshed = service.semantic_context(root, "entry", anchor_file="entry.ts")
    assert refreshed["snapshot"] != first["snapshot"]
    assert not service.semantic_observer()["work"]["cache_hit"]
    semantic_ref = next(row["source_ref"] for row in refreshed["sources"] if row["file"] == "entry.ts")
    (root / "entry.ts").write_text((root / "entry.ts").read_text() + "// changed\n")
    for reference in (source["items"][0]["source_ref"], semantic_ref):
        with pytest.raises(GraphFreeError) as stale:
            service.read(root, reference)
        assert stale.value.code == "SOURCE_STALE"


def test_continuation_preserves_original_schema_and_exact_envelope_bytes(tmp_path):
    root, service = _source(tmp_path)
    (root / "entry.ts").write_text((root / "entry.ts").read_text() + "// padding\n" * 2000)
    first = service.retrieve(root, "entry.ts")
    assert not first["items"][0]["complete"]
    page = service.read(root, first["items"][0]["source_ref"])
    envelope = {"content": [], "structuredContent": page, "isError": False}
    assert "navigation" not in page
    validate_packets([envelope])
    assert page["usage"]["output_bytes"] == len(json.dumps(
        envelope, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode())
    assert page["usage"]["output_bytes"] <= 16384


def test_combined_native_uncertainty_is_retained_without_promotion(tmp_path):
    from tests.test_focused_uncertainty import _rust_repo, _unresolved_native_counts

    root = _rust_repo(tmp_path)
    service = IntegratedSource(tmp_path / "store")
    source = service.retrieve(root, "src/lib.rs")
    assert any(item["path"] == "src/model.rs" for item in source["navigation"]["candidates"])
    semantic = service.semantic_context(root, "probe", anchor_file="src/lib.rs")
    index = service.semantic_observer()["index"]
    counts, total = _unresolved_native_counts(index)
    uncertainty = semantic["uncertainty"]
    assert {(row["family"], row["reason"], row["consumer_reason"]): row["count"]
            for row in uncertainty["counts"]} == dict(counts)
    assert len(uncertainty["examples"]) + uncertainty["examples_omitted"] == total
    assert {row["reason"] for row in semantic["omissions"]} >= {
        "ambiguous_relation", "inaccessible_relation", "external_relation",
        "unresolved_relation", "configuration_dependent_relation"}
    assert uncertainty["configuration_possible_count"] > 0
    assert any(row["resolution_configuration"] == "declared_possible" for row in semantic["relationships"])
    proof = service.proof_context(root, semantic["anchors"][0]["node_id"])
    assert proof["uncertainty"] == uncertainty
    assert proof["scope"]["exhaustive"] is False


@pytest.mark.parametrize("extension,text", [("py", "def entry(value):\n    return value\n"),
                                           ("go", "package main\nfunc entry() {}\n")])
def test_unsupported_semantics_never_become_proven(tmp_path, extension, text):
    root = tmp_path / "repo"
    root.mkdir()
    (root / f"entry.{extension}").write_text(text)
    service = IntegratedSource(tmp_path / "store")
    assert service.retrieve(root, f"entry.{extension}")["sources"]
    packet = service.semantic_context(root, f"entry.{extension}")
    assert packet["relationships"] == []
    assert "unsupported_language" in {row["reason"] for row in packet["omissions"]}


def test_combined_acquisition_uses_strict_existing_proof_and_negative_controls(tmp_path):
    corpus = load_suite(ROOT / "benchmarks/corpora/typescript-context-v3")
    case = next(case for case in corpus["cases"] if case["id"] == "imported_interface")
    corpus["cases"] = [case]
    corpus["snapshots"] = {case["snapshot"]: corpus["snapshots"][case["snapshot"]]}
    root = Path(prepare_snapshots(corpus, tmp_path / "fixtures")[case["snapshot"]])
    service = IntegratedSource(tmp_path / "store")
    service.index_repo(root)
    inventory = {"schema_version": 1, "files": {name: {"sha256": value,
        "size": (root / name).stat().st_size} for name, value in service.inventory(root)["file_hashes"].items()}}
    packets, trace = acquire(service, root, requests(corpus)[0], inventory, [],
                             graph_free=True, enrichment=True, demand=True, focused=True, path_navigation=True)
    index = service.semantic_observer()["index"]
    def score(delivered, acquisition):
        return score_acquisition(corpus, case["id"], root, index, delivered, acquisition, inventory,
                                 demand=True, focused=True, path_navigation=True)
    scored = score(packets, trace)
    assert scored["acquisition_integrity_ok"] and trace["focused_calls"]
    assert scored["preserved_guarantees"]["task_answer_correct"] is None
    forged = deepcopy(packets)
    semantic = next(row["structuredContent"] for row in reversed(forged) if row["structuredContent"].get("relationships"))
    semantic["sources"][0]["content"] = "forged"
    assert not score(forged, trace)["acquisition_integrity_ok"]
    privileged = deepcopy(trace)
    next(row for row in privileged["queries"] if row.get("operation") == "focused_proof")["query"] = "gold-only"
    with pytest.raises(ValueError, match="frozen gold-blind policy"):
        score(packets, privileged)
    stripped = deepcopy(packets)
    for row in stripped:
        for relation in row["structuredContent"].get("relationships", []):
            relation["source_ids"] = []
    assert not score(stripped, trace)["acquisition_integrity_ok"]


@pytest.mark.parametrize("source_only", [False, True])
def test_actual_stdio_catalog_and_source_to_optional_proof(tmp_path, source_only):
    from mcp import Client, StdioServerParameters
    from mcp.client.stdio import stdio_client

    root, _ = _source(tmp_path)
    async def check():
        params = StdioServerParameters(command=sys.executable, args=["-m", "loci.integrated_mcp"],
            env=dict(os.environ, PYTHONPATH=str(ROOT / "src"), LOCI_R1_STORE=str(tmp_path / "mcp-store"),
                     LOCI_R1_SOURCE_ONLY="1" if source_only else "0"), cwd=ROOT)
        async with Client(stdio_client(params)) as session:
            names = {tool.name for tool in (await session.list_tools()).tools}
            assert names == ({"loci_retrieve", "loci_read"} if source_only else
                             {"loci_retrieve", "loci_read", "loci_semantic", "loci_proof"})
            source = await session.call_tool("loci_retrieve", arguments={"repo": str(root), "query": "entry.ts"})
            assert not source.is_error
            payload = source.structured_content
            assert payload["navigation"]["candidates"][0]["path"] == "model.ts"
            page = await session.call_tool("loci_read", arguments={"repo": str(root),
                "source_ref": payload["items"][0]["source_ref"]})
            assert not page.is_error and page.structured_content["source"]["file"] == "entry.ts"
            if source_only:
                return
            denied = await session.call_tool("loci_proof", arguments={"repo": str(root), "node_id": "hidden"})
            assert denied.is_error and denied.structured_content["error"]["code"] == "UNKNOWN_PROOF_ID"
            semantic = await session.call_tool("loci_semantic", arguments={"repo": str(root), "query": "entry",
                                                                         "anchor_file": "entry.ts"})
            assert not semantic.is_error
            payload = semantic.structured_content
            proof = await session.call_tool("loci_proof", arguments={"repo": str(root),
                "node_id": payload["anchors"][0]["node_id"]})
            assert not proof.is_error and proof.structured_content["proof_request"]["scope"] == "same_computed_slice"
            semantic_read = await session.call_tool("loci_read", arguments={"repo": str(root),
                "source_ref": payload["sources"][0]["source_ref"]})
            assert not semantic_read.is_error
    asyncio.run(check())


def test_actual_stdio_serializes_concurrent_service_operations(tmp_path):
    from mcp import Client, StdioServerParameters
    from mcp.client.stdio import stdio_client

    root, _ = _source(tmp_path)
    observed = tmp_path / "concurrency.json"
    program = '''import json,os,threading,time
from pathlib import Path
from loci.integrated import IntegratedSource
guard=threading.Lock()
active=maximum=calls=0
def instrument(original):
    def wrapped(*args,**kwargs):
        global active,maximum,calls
        with guard:
            active+=1
            maximum=max(active,maximum)
            calls+=1
        try:
            time.sleep(0.01)
            return original(*args,**kwargs)
        finally:
            with guard:
                active-=1
                Path(os.environ['R1_CONCURRENCY_RECORD']).write_text(json.dumps({'maximum':maximum,'calls':calls}))
    return wrapped
for name in ('retrieve','semantic_context'):
    setattr(IntegratedSource,name,instrument(getattr(IntegratedSource,name)))
from loci.integrated_mcp import main
main()
'''
    async def check():
        params = StdioServerParameters(command=sys.executable, args=["-c", program], cwd=ROOT,
            env=dict(os.environ, PYTHONPATH=str(ROOT / "src"), LOCI_R1_STORE=str(tmp_path / "mcp-store"),
                     LOCI_R1_SOURCE_ONLY="0", R1_CONCURRENCY_RECORD=str(observed)))
        async with Client(stdio_client(params)) as session:
            actions = [("loci_retrieve", {"repo": str(root), "query": "entry.ts"})] * 8
            actions += [("loci_semantic", {"repo": str(root), "query": "entry", "anchor_file": "entry.ts"})] * 2
            responses = await asyncio.gather(*(session.call_tool(name, arguments=arguments)
                                               for name, arguments in actions))
            assert all(not response.is_error for response in responses)
    asyncio.run(check())
    assert json.loads(observed.read_text()) == {"maximum": 1, "calls": 10}


def test_qualification_archives_actual_repeats_and_independently_replays(tmp_path):
    output = tmp_path / "qualification"
    result = run(output, [ROOT / "benchmarks/corpora/typescript-context-v3"], cases=["imported_interface"])
    assert result["status"] == "completed"
    assert verify(output) == {"status": "verified", "case_executions": 4}
    for entry in result["runs"]:
        report = json.loads((output / entry["artifacts"] / "worker.json").read_text())
        assert report["semantic_modules_before_questions"] == []
        assert report["phase_totals"]["end_to_end"]["elapsed_ns"] > 0
        assert report["phase_totals"]["repeat_end_to_end"]["elapsed_ns"] > 0
        if entry["arm"] == "integrated":
            assert report["cases"][0]["repeat_semantic_work"]["cache_hit"]
    packet = next(output.glob("integrated-*/packets/*.json"))
    packet.write_text("[]")
    with pytest.raises(ValueError, match="inventory/hash mismatch"):
        verify(output)
