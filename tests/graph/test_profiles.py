from __future__ import annotations

import json
from pathlib import Path

import pytest

from loci.graph.contracts import GraphContractError
from loci.graph.profiles import (
    GraphProfile,
    discover_graph_profile_paths,
    load_graph_profile,
    read_extension_json,
    required_frontmatter_fields,
)


FIXTURES = Path(__file__).parents[1] / "fixtures" / "graph_profiles"


def test_profile_round_trip_is_stable():
    payload = json.loads((FIXTURES / "llm-wiki.json").read_text())

    profile = GraphProfile.from_dict(payload)

    assert profile.to_dict() == payload
    assert required_frontmatter_fields([profile]) == frozenset({
        "knowledge_state",
        "mentioned_in",
    })


@pytest.mark.parametrize("namespace", ["loci", "LLM-Wiki", "wiki.thing", "école"])
def test_profile_rejects_reserved_or_noncanonical_namespace(namespace: str):
    payload = json.loads((FIXTURES / "generic.json").read_text())
    payload["namespace"] = namespace

    with pytest.raises(GraphContractError) as exc_info:
        GraphProfile.from_dict(payload)

    assert exc_info.value.code == "INVALID_GRAPH_PROFILE"
    assert exc_info.value.details["field"] == "namespace"


def test_profile_rejects_non_declared_domain_resolution():
    payload = json.loads((FIXTURES / "generic.json").read_text())
    payload["edge_types"][0]["allowed_resolutions"] = ["exact"]

    with pytest.raises(GraphContractError) as exc_info:
        GraphProfile.from_dict(payload)

    assert exc_info.value.code == "GRAPH_RESOLUTION_UNSUPPORTED"


def test_profile_rejects_unknown_fields():
    payload = json.loads((FIXTURES / "generic.json").read_text())
    payload["ranking"] = {}

    with pytest.raises(GraphContractError) as exc_info:
        GraphProfile.from_dict(payload)

    assert exc_info.value.code == "INVALID_GRAPH_PROFILE"
    assert exc_info.value.details["unknown"] == ["ranking"]


def test_loader_rejects_duplicate_json_keys(tmp_path: Path):
    profile_dir = tmp_path / ".loci" / "graph" / "profiles"
    profile_dir.mkdir(parents=True)
    path = profile_dir / "bad.json"
    path.write_text('{"schema_version":1,"schema_version":1}')

    with pytest.raises(GraphContractError) as exc_info:
        load_graph_profile(tmp_path, path)

    assert exc_info.value.code == "INVALID_GRAPH_PROFILE"
    assert exc_info.value.details["reason"] == "duplicate key"


def test_loader_rejects_non_finite_exponent_and_excessive_depth(tmp_path: Path):
    non_finite = tmp_path / "non-finite.json"
    non_finite.write_text('{"value": 1e999}')
    too_deep = tmp_path / "too-deep.json"
    too_deep.write_text("[" * 18 + "0" + "]" * 18)

    with pytest.raises(GraphContractError) as non_finite_error:
        read_extension_json(tmp_path, non_finite, record="profile")
    with pytest.raises(GraphContractError) as depth_error:
        read_extension_json(tmp_path, too_deep, record="profile")

    assert non_finite_error.value.code == "INVALID_GRAPH_PROFILE"
    assert "non-finite" in non_finite_error.value.message
    assert depth_error.value.code == "INVALID_GRAPH_PROFILE"
    assert depth_error.value.details["limit"] == 16


def test_discovery_is_lexical_and_rejects_symlink(tmp_path: Path):
    profile_dir = tmp_path / ".loci" / "graph" / "profiles"
    profile_dir.mkdir(parents=True)
    (profile_dir / "b.json").write_text((FIXTURES / "generic.json").read_text())
    (profile_dir / "a.json").write_text((FIXTURES / "llm-wiki.json").read_text())
    (profile_dir / "ignored.txt").write_text("{}")
    (profile_dir / "linked.json").symlink_to(profile_dir / "a.json")

    with pytest.raises(GraphContractError) as exc_info:
        discover_graph_profile_paths(tmp_path)

    assert exc_info.value.code == "INVALID_GRAPH_PROFILE"
    assert exc_info.value.details["source"].endswith("linked.json")

    (profile_dir / "linked.json").unlink()
    assert [path.name for path in discover_graph_profile_paths(tmp_path)] == [
        "a.json",
        "b.json",
    ]
