from pathlib import Path

import pytest

from loci.service import index_repo
from loci.storage.index_store import IndexStore


def _index_default_export(tmp_path, monkeypatch, suffix, source):
    base = tmp_path / "cache"
    monkeypatch.setenv("LOCI_BASE_DIR", str(base))
    repo = tmp_path / "repo"
    repo.mkdir()
    files = {
        f"number{suffix}": source,
        f"distractor{suffix}": "export default function num() { return 999; }\n",
        f"consumer{suffix}": (
            'import convert from "./number.js";\n'
            "export function useNumber() { return convert(1); }\n"
        ),
    }
    for name, content in files.items():
        (repo / name).write_text(content, encoding="utf-8")
    index_repo(repo, incremental=False)
    return IndexStore(base_dir=base).load(repo.resolve())


@pytest.mark.parametrize("suffix", [".js", ".ts", ".tsx"])
@pytest.mark.parametrize(
    ("source", "definition", "export_text", "export_line", "definition_line"),
    [
        (
            "function num(value) { return value; }\nexport default num;\n",
            "function num(value) { return value; }",
            "export default num;", 2, 1,
        ),
        (
            "const num = (value) => value;\nexport default num;\n",
            "num = (value) => value",
            "export default num;", 2, 1,
        ),
        (
            "export default function num(value) { return value; }\n",
            "function num(value) { return value; }",
            "export default function num(value) { return value; }", 1, 1,
        ),
        (
            "export /* authored */ default num;\nfunction num(value) { return value; }\n",
            "function num(value) { return value; }",
            "export /* authored */ default num;", 1, 2,
        ),
    ],
    ids=["separate-function", "separate-arrow", "inline-control", "forward-with-comment"],
)
def test_default_identifier_preserves_exact_target_and_evidence(
    tmp_path: Path, monkeypatch, suffix, source, definition,
    export_text, export_line, definition_line,
):
    index = _index_default_export(tmp_path, monkeypatch, suffix, source)
    graph = index["graph"]
    target = f"number{suffix}::num#function"
    caller = f"consumer{suffix}::useNumber#function"
    symbol, = [item for item in index["symbols"] if item["id"] == target]
    assert source.encode()[
        symbol["byte_offset"]:symbol["byte_offset"] + symbol["byte_length"]
    ] == definition.encode()
    export, = [item for item in graph["exports"] if item["source_file"] == f"number{suffix}"]
    assert (export["local_name"], export["exported_name"], export["type_only"]) == (
        "num", "default", False,
    )
    assert (export["text"], export["line"]) == (export_text, export_line)
    assert source.encode()[
        export["definition_start_byte"]:export["definition_end_byte"]
    ] == definition.encode()
    reference, = graph["symbol_references"]
    assert (reference["status"], reference["target_id"]) == ("resolved", target)
    assert [(item["kind"], item["line"]) for item in reference["support"]] == [
        ("import_binding", 1), ("local_export", export_line),
        ("definition", definition_line),
    ]
    call, = graph["calls"]
    assert (call["status"], call["caller_id"], call["target_id"]) == (
        "resolved", caller, target,
    )
    assert {
        (edge["from"], edge["to"], edge["type"])
        for edge in graph["edges"] if edge["type"] in {"references", "calls"}
    } == {(caller, target, "references"), (caller, target, "calls")}


@pytest.mark.parametrize(
    ("source", "has_export"),
    [
        ("export default num;\n", True),
        ("function num() {}\nfunction num() {}\nexport default num;\n", True),
        ("const obj = {};\nexport default obj.num;\n", False),
        ("export default function () {};\n", False),
    ],
    ids=["missing", "ambiguous", "member-expression", "anonymous-expression"],
)
def test_unproven_default_export_never_selects_a_distractor(
    tmp_path: Path, monkeypatch, source, has_export,
):
    graph = _index_default_export(tmp_path, monkeypatch, ".ts", source)["graph"]
    exports = [item for item in graph["exports"] if item["source_file"] == "number.ts"]
    assert len(exports) == int(has_export)
    if exports:
        assert exports[0]["definition_start_byte"] is None
        assert exports[0]["definition_end_byte"] is None
    reference, = graph["symbol_references"]
    assert reference["status"] == "unresolved"
    assert reference["target_id"] is None
    call, = graph["calls"]
    assert call["status"] == "unresolved"
    assert call["target_id"] is None
    assert not [edge for edge in graph["edges"] if edge["type"] in {"references", "calls"}]
