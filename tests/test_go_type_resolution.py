"""Contained package resolution and refresh boundaries for authored Go types."""
from contextlib import contextmanager

import pytest

from benchmarks.typescript_context_corpus import _isolated_store
from loci import service
from loci.mcp_output_models import LociGraphReferencesOutput
from tests.test_python_context_delivery import _assert_packet


@contextmanager
def _repo(tmp_path, files):
    repo = tmp_path / "repo"
    repo.mkdir()
    for name, text in files.items():
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    with _isolated_store(tmp_path / "index"):
        service.index_repo(repo, incremental=False)
        yield repo


def _records(repo, file):
    result = service.graph_references(repo, file=file, family="type", ensure_fresh=True)
    LociGraphReferencesOutput.model_validate(result)
    return result["items"]


def test_go_package_universe_preserves_private_cross_file_and_local_type_ownership(tmp_path):
    with _repo(tmp_path, {
        "go.mod": "module example.com/local\n\ngo 1.23\n",
        "model/a.go": "package model\ntype private struct{}\ntype Public = private\n",
        "model/b.go": "package model\nfunc Use(x private) {}\nfunc Local() { type private int; type Alias private }\n",
        "wrong/a.go": "package model\ntype private string\n",
    }) as repo:
        records = _records(repo, "model/b.go")
        assert {(r["source_id"], r["target_id"], r["resolution_basis"]) for r in records if r["status"] == "resolved"} == {
            ("model/b.go::Use#function", "model/a.go::private#type", "package_binding"),
            ("model/b.go::Local.Alias#type", "model/b.go::Local.private#type", "lexical_binding"),
        }
        # Candidate changes in another file invalidate a previously unique route.
        (repo / "model/c.go").write_text("package model\ntype private string\n")
        use = next(r for r in _records(repo, "model/b.go") if r["source_id"] == "model/b.go::Use#function")
        assert use["status"] == "unresolved" and use["unresolved_reason"] == "ambiguous_target"


@pytest.mark.parametrize("configured_file, source", [
    ("model/tagged.go", "//go:build linux\n\npackage model\ntype Payload struct{}\n"),
    ("model/cgo.go", 'package model\nimport "C"\ntype Payload struct{}\n'),
    ("model/platform_linux.go", "package model\ntype Payload struct{}\n"),
])
def test_go_conditional_targets_are_not_claimed_exact(tmp_path, configured_file, source):
    with _repo(tmp_path, {
        "go.mod": "module example.com/local\n\ngo 1.23\n",
        configured_file: source,
        "app.go": 'package main\nimport "example.com/local/model"\nfunc Use(x model.Payload) {}\n',
    }) as repo:
        result = _records(repo, "app.go")
        assert len(result) == 1
        assert result[0]["status"] == "unresolved"
        assert result[0]["unresolved_reason"] == "unsupported_configuration"


def test_go_declared_package_names_shadow_ambiguity_and_external_types(tmp_path):
    with _repo(tmp_path, {
        "go.mod": "module example.com/local\n\ngo 1.23\n",
        "schema/types.go": "package wire\ntype Request struct{}\n",
        "one/types.go": "package shared\ntype Request int\n",
        "two/types.go": "package shared\ntype Request string\n",
        "app.go": '''package main
import (
    "example.com/local/schema"
    "example.com/local/one"
    "example.com/local/two"
    remote "external.invalid/model"
)
func Use(x wire.Request) {}
func Bad(x schema.Request, y shared.Request, z remote.Request) {}
func Shadow(wire int) wire.Request { type Local wire.Request; return wire.Request{} }
''',
    }) as repo:
        records = _records(repo, "app.go")
        assert {r["source_id"] for r in records if r["status"] == "resolved"} == {
            "app.go::Use#function", "app.go::Shadow#function",
        }
        assert not any(r["status"] == "resolved" for r in records if r["raw"]["text"] in {"schema.Request", "shared.Request", "remote.Request"})
        local = next(r for r in records if r["source_id"] == "app.go::Shadow.Local#type")
        assert local["unresolved_reason"] == "binding_shadowed"


def test_go_workspace_and_contained_replacement_controls_refresh_the_type_route(tmp_path):
    with _repo(tmp_path, {
        "go.work": "go 1.23\nuse (\n ./app\n ./dep\n)\n",
        "app/go.mod": "module example.com/app\n\ngo 1.23\n",
        "dep/go.mod": "module example.com/dep\n\ngo 1.23\n",
        "dep/types.go": "package wire\ntype Request struct{}\n",
        "app/main.go": 'package main\nimport "example.com/dep"\nfunc Use(x wire.Request) {}\n',
    }) as repo:
        result = service.explore(repo, intent="type_dependencies", seed_ids=["app/main.go::Use#function"])
        _assert_packet(repo, result)
        assert {s["file"] for s in result["sources"]} >= {"go.work", "app/go.mod", "dep/go.mod", "dep/types.go"}
        assert _records(repo, "app/main.go")[0]["target_id"] == "dep/types.go::Request#type"
        (repo / "go.work").write_text("go 1.23\nuse ./app\n")
        assert _records(repo, "app/main.go")[0]["status"] == "unresolved"
        (repo / "app/go.mod").write_text("module example.com/app\n\ngo 1.23\nrequire example.com/dep v1.0.0\nreplace example.com/dep => ../dep\n")
        assert _records(repo, "app/main.go")[0]["target_id"] == "dep/types.go::Request#type"
        (repo / "dep/types.go").write_text("package wire\ntype Replacement struct{}\n")
        assert _records(repo, "app/main.go")[0]["status"] == "unresolved"
        (repo / "app/main.go").write_text('package main\nimport "example.com/dep"\nfunc Use(x wire.Replacement) {}\n')
        assert _records(repo, "app/main.go")[0]["target_id"] == "dep/types.go::Replacement#type"


def test_go_replay_cannot_redirect_a_package_anchor_to_a_same_name_directory(tmp_path):
    from loci.graph.type_relations import resolve_type_relations
    from loci.parser.symbols import Symbol

    with _repo(tmp_path, {
        "go.mod": "module example.com/local\n\ngo 1.23\n",
        "good/types.go": "package model\ntype Payload int\n",
        "wrong/types.go": "package model\ntype Payload string\n",
        "app.go": 'package main\nimport "example.com/local/good"\nfunc Use(x model.Payload) {}\n',
    }) as repo:
        _, nodes, state = service._load_graph_context(repo, ensure_fresh=False)
        assert state.type_relations[0].target_id == "good/types.go::Payload#type"
        package = next(n for n in nodes.values() if n["kind"] == "package" and n["file_path"] == "good/types.go")
        package["metadata"]["loci"]["directory"] = "wrong"
        replay = resolve_type_relations(
            [r.raw for r in state.type_relations],
            symbols=[Symbol.from_dict(n) for n in nodes.values()],
            imports=state.imports, exports=state.exports,
            file_hashes={n["file_path"]: n["content_hash"] for n in nodes.values() if n["kind"] == "file"},
            input_hashes=state.input_hashes,
        )
        assert replay[0].status == "unresolved"
        assert replay[0].target_id is None
