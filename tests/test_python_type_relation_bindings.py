from __future__ import annotations

from loci import service
from loci.mcp_output_models import LociGraphReferencesOutput
from tests.test_type_relation_service import _setup


def test_python_qualified_types_require_exact_module_member_paths(tmp_path, monkeypatch):
    repo, _ = _setup(tmp_path, monkeypatch, {
        "pkg/__init__.py": "",
        "pkg/schema.py": "class Payload: pass\n",
        "consumer.py": (
            "import pkg.schema\nimport pkg.schema as model\n"
            "from pkg import schema as submodule\nfrom pkg.schema import Payload as P\n"
            "def exact(a: pkg.schema.Payload, b: model.Payload, c: submodule.Payload, d: P): pass\n"
            "def wrong(a: P.member, b: model.Payload.member, c: submodule.Payload.member): pass\n"
            "def forward(a: 'model.Payload'): pass\n"
        ),
    })
    page = service.graph_references(repo, family="type")
    LociGraphReferencesOutput.model_validate(page)
    records = page["items"]
    exact = [r for r in records if r["source_id"] == "consumer.py::exact#function"]
    assert len(exact) == 4
    assert all(r["status"] == "resolved" and r["target_id"] == "pkg/schema.py::Payload#class" for r in exact)
    wrong = [r for r in records if r["source_id"] == "consumer.py::wrong#function"]
    assert len(wrong) == 3 and all(r["unresolved_reason"] == "unsupported_reference" for r in wrong)
    forward = next(r for r in records if r["source_id"] == "consumer.py::forward#function")
    assert forward["status"] == "resolved" and forward["raw"]["text"] == "'model.Payload'"


def test_python_explicit_alias_can_be_imported_through_named_reexport(tmp_path, monkeypatch):
    repo, _ = _setup(tmp_path, monkeypatch, {
        "model.py": "from typing import TypeAlias\nclass Payload: pass\nAlias: TypeAlias = Payload\n",
        "barrel.py": "from model import Alias as Public\n",
        "consumer.py": "from barrel import Public as P\ndef use(value: P): pass\n",
    })
    result = service.explore(repo, intent="type_dependencies", seed_ids=["consumer.py::use#function"])
    assert {item["id"] for item in result["items"]} == {
        "consumer.py::use#function", "model.py::Alias#type", "model.py::Payload#class",
    }
    assert {source["file"] for source in result["sources"]} == {"consumer.py", "barrel.py", "model.py"}
    expanded = service.get_symbols_result(repo, ["consumer.py::use#function"], include_type_context=True)
    assert {symbol["id"] for symbol in expanded["type_context"]["symbols"]} == {
        "model.py::Alias#type", "model.py::Payload#class",
    }
