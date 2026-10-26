"""Novel, gold-free fixtures exercise path candidates and replay accounting."""
import json
from pathlib import Path
import subprocess
import sys

import pytest

from loci.path_navigation import candidate_paths, choose_next_query, next_acquisition_query


def _inventory(files):
    return {"files": {name: {"size": len(text.encode()), "sha256": "0" * 64}
                      for name, text in files.items()}}


def _packet(file, text, start=0):
    return {"structuredContent": {"sources": [{"file": file, "content": text,
            "start_byte": start, "end_byte": start + len(text.encode())}]}}


def test_relative_imports_reexports_and_ambiguous_inventory_alternatives():
    inventory = _inventory({"app/panel.ts": "", "app/model.ts": "", "app/model.js": "",
                            "app/widgets/index.ts": "", "shared/util.ts": ""})
    source = '''import type { Model as Renamed } from "./model.js";
export { helper } from '../shared/util';
const widgets = require('./widgets');
import('remote-package');
'''
    candidates = candidate_paths("app/panel.ts", source, inventory["files"])
    assert [row["path"] for row in candidates] == [
        "app/model.js", "app/model.ts", "shared/util.ts", "app/widgets/index.ts"]
    assert all(row["observed_in"] == "app/panel.ts" for row in candidates)
    assert all("binding" not in row for row in candidates)


def test_rust_module_and_use_paths_are_candidates_including_inactive_alternatives():
    files = {name: "" for name in ("pkg/Cargo.toml", "pkg/src/lib.rs", "pkg/src/detail.rs",
                                  "pkg/src/detail/mod.rs", "pkg/src/other.rs")}
    source = '#[cfg(feature="unknown")]\npub mod detail;\npub use crate::other::Item as Public;'
    rows = candidate_paths("pkg/src/lib.rs", source, files)
    assert [row["path"] for row in rows] == ["pkg/src/detail.rs", "pkg/src/detail/mod.rs",
                                            "pkg/src/other.rs", "pkg/Cargo.toml"]
    assert all("resolved" not in row["reason"] for row in rows)


def test_cargo_local_paths_require_delivered_controls_and_remain_alternatives():
    files = {"client/src/lib.rs": "use bridge::Public;", "client/Cargo.toml":
             '[dependencies]\nbridge = { workspace = true, optional = true }\n',
             "Cargo.toml": '[workspace.dependencies]\nbridge = { path = "backend" }\n',
             "backend/src/lib.rs": "pub struct Public;", "backend/Cargo.toml": ""}
    inventory = _inventory(files)
    packets = [_packet("client/src/lib.rs", files["client/src/lib.rs"])]
    asked = ["Public"]
    assert next_acquisition_query(inventory, packets, asked) == "client/Cargo.toml"
    asked.append("client/Cargo.toml")
    packets.append(_packet("client/Cargo.toml", files["client/Cargo.toml"]))
    assert next_acquisition_query(inventory, packets, asked) == "Cargo.toml"
    asked.append("Cargo.toml")
    packets.append(_packet("Cargo.toml", files["Cargo.toml"]))
    choice = choose_next_query(inventory, packets, asked)
    assert choice["query"] == "backend/src/lib.rs"
    assert choice["reason"] == "cargo_local_path_source_candidate"
    assert choice["observed_in"] == "Cargo.toml"


@pytest.mark.parametrize("path", ["../../outside", "/outside", "..\\outside", "bad\x00name"])
def test_import_paths_never_emit_uncontained_or_unadmitted_candidates(path):
    files = {"outside.ts": {}, "app/safe.ts": {}}
    assert candidate_paths("app/view.ts", f'import {{ a }} from "{path}";', files) == []


def test_same_root_cargo_path_and_invalid_toml_are_bounded():
    files = {"src/lib.rs": {}, "Cargo.toml": {}}
    assert candidate_paths("Cargo.toml", '[dependencies]\nlocal = { path = "." }', files)[0]["path"] == "src/lib.rs"
    assert candidate_paths("Cargo.toml", "[not complete", files) == [
        {"path": "Cargo.toml", "reason": "cargo_ancestor_control", "observed_in": "Cargo.toml"}]


def test_contiguous_pages_join_without_fabricating_imports_across_gaps():
    whole = 'import { Item } from "./unusual-name.ts";\n'
    files = {"view.ts": whole, "unusual-name.ts": "", "irrelevant/Item.ts": ""}
    inventory = _inventory(files)
    split = 25
    packets = [_packet("view.ts", whole[:split]), _packet("view.ts", whole[split:], split)]
    choice = choose_next_query(inventory, packets, ["Item", "view.ts"])
    assert choice["query"] == "unusual-name.ts"
    assert choice["work"]["source_bytes_received"] == len(whole.encode())
    assert choice["work"]["source_bytes_path_scan"] == len(whole.encode())
    assert choice["work"]["filesystem_source_bytes_read"] == 0
    gapped = [_packet("view.ts", whole[:split]), _packet("view.ts", whole[split + 2:], split + 2)]
    assert choose_next_query(inventory, gapped, ["Item", "view.ts"])["reason"] != "relative_import_or_export"
    assert choose_next_query(inventory, json.loads(json.dumps(packets)), ["Item", "view.ts"]) == choice


def test_partial_source_is_expanded_before_paths_and_lexical_fallback_survives():
    inventory = _inventory({"pkg/view.ts": 'import "./next";\n' + "more\n" * 20, "pkg/next.ts": ""})
    packets = [_packet("pkg/view.ts", 'import "./next";\n')]
    choice = choose_next_query(inventory, packets, ["request"])
    assert choice["query"] == "pkg/view.ts"
    assert choice["work"]["source_bytes_path_scan"] == 0
    fallback = choose_next_query(_inventory({"note.txt": "observed_name"}),
                                 [_packet("note.txt", "observed_name")], ["request"])
    assert fallback["query"] == "observed_name"
    assert fallback["reason"] == "lexical_identifier"


def test_scheduler_imports_no_semantic_modules_or_evaluator():
    program = '''import sys
from benchmarks.architecture_navigation import choose_next_query
assert choose_next_query({"files": {}}, [], ["query"])["query"] is None
assert not any(name.startswith(("loci.parser", "loci.graph", "loci.storage")) for name in sys.modules)
assert not any(name.startswith("benchmarks.") and name != "benchmarks.architecture_navigation" for name in sys.modules)
'''
    subprocess.run([sys.executable, "-c", program], check=True,
                   cwd=Path(__file__).resolve().parents[1])


def test_candidates_reuse_graph_free_source_safety_and_packet_contract(tmp_path):
    from loci.graph_free import GraphFreeError, GraphFreeSource

    root = tmp_path / "repo"
    root.mkdir()
    (root / "view.ts").write_text('export { value } from "./logic";\n')
    (root / "logic.ts").write_text("export const value = 4;\n")
    source = GraphFreeSource(tmp_path / "store")
    first = source.retrieve(root, "view.ts")
    inventory = {"files": {name: {"size": (root / name).stat().st_size}
                            for name in source.inventory(root)["file_hashes"]}}
    query = next_acquisition_query(inventory, [first], ["view.ts"])
    assert query == "logic.ts"
    second = source.retrieve(root, query)
    assert second["relationships"] == second["nodes"] == []
    reference = second["items"][0]["source_ref"]
    (root / "logic.ts").write_text("changed\n")
    with pytest.raises(GraphFreeError) as stale:
        source.read(root, reference)
    assert stale.value.code == "SOURCE_STALE"
    (root / "logic.ts").unlink()
    (tmp_path / "outside.ts").write_text("export const secret = 'outside';\n")
    (root / "logic.ts").symlink_to(tmp_path / "outside.ts")
    packet = source.retrieve(root, "logic.ts")
    assert all(span["file"] != "logic.ts" for span in packet["sources"])
    assert "logic.ts" not in source.inventory(root)["file_hashes"]
