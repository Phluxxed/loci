"""Production subprocess checks for the trial-local Pi bridge, without inference."""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest


BRIDGE = Path(__file__).resolve().parents[1] / "evals/search_ablation/agent_loci.py"


@pytest.fixture
def trial(tmp_path):
    repo = tmp_path / "source"
    repo.mkdir()
    (repo / "worker.py").write_text("def transform(value):\n    return value + 7\n")
    (repo / "entry.py").write_text("from worker import transform\n\ndef execute(value):\n    return transform(value)\n")
    return repo, tmp_path / "store"


def call(trial, tool, arguments, mode="true", **overrides):
    repo, store = trial
    env = dict(os.environ, LOCI_AGENT_REPO=str(repo), LOCI_AGENT_STORE=str(store),
               LOCI_AGENT_GRAPH_ENRICHMENT=mode, **overrides)
    result = subprocess.run([sys.executable, str(BRIDGE)], cwd=repo, env=env,
                            input=json.dumps({"tool": tool, "arguments": arguments}),
                            capture_output=True, text=True, timeout=60, check=True)
    return json.loads(result.stdout)


def test_real_anchor_selection_graph_binding_and_durable_source_refs(trial):
    full = call(trial, "loci_retrieve", {"query": "execute"})
    anchor_trial = trial[0], trial[1].with_name("anchor-store")
    anchor = call(anchor_trial, "loci_retrieve", {"query": "execute"}, "false")
    assert full["status"] in {"ok", "partial"}
    assert anchor["status"] in {"ok", "partial"}
    assert full["anchors"] == anchor["anchors"]
    assert full["anchors"]
    assert full["relationships"] and not anchor["relationships"]
    assert len(full["items"]) > len(anchor["items"])
    for bound, packet in [(trial, full), (anchor_trial, anchor)]:
        source = packet["sources"][0]
        assert source["source_ref"].startswith("sr1_")
        page = call(bound, "loci_read", {"source_ref": source["source_ref"]})
        assert page["status"] == "ok" and page["complete"]
        assert page["source"]["content"] == source["content"]
        # Each call is a fresh process. A handle from another independent store
        # cannot resolve even though the repository path and source are equal.
        absent = call((trial[0], trial[1].with_name("empty-store")),
                      "loci_read", {"source_ref": source["source_ref"]})
        assert absent["error"]["code"] == "INVALID_SOURCE_REF"


def test_errors_remain_explicit_and_model_cannot_override_binding(trial):
    for arguments in [{"query": "execute", "repo": "/tmp"},
                      {"query": "execute", "graph_enrichment": False},
                      {"query": " "}, {"query": "execute", "seed_ids": ["x", "x"]}]:
        assert call(trial, "loci_retrieve", arguments)["error"]["code"] == "ValueError"
    assert call(trial, "loci_read", {"source_ref": "bad"})["error"]["code"] == "INVALID_SOURCE_REF"
    assert call(trial, "loci_retrieve", {"query": "execute"}, "invalid")["error"]["code"] == "ValueError"
    result = call(trial, "loci_retrieve", {"query": "execute"})
    reference = result["sources"][0]["source_ref"]
    (trial[0] / result["sources"][0]["file"]).write_text("# changed\n")
    assert call(trial, "loci_read", {"source_ref": reference})["error"]["code"] == "SOURCE_STALE"
