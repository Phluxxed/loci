"""Complete TypeScript proof declarations retain existing relationship identity."""
import pytest

from loci import service
from loci.exploration import explore_context
from tests.test_exploration import _verify_packet
from tests.test_type_relation_service import _setup


@pytest.mark.parametrize("extension", ["ts", "tsx"])
def test_multiline_type_barrel_is_delivered_whole_with_correct_identity(tmp_path, monkeypatch, extension):
    statement = 'export type {\n  WireEnvelope,\n  WireEnvelopeView,\n} from "./schema";'
    repo, _ = _setup(tmp_path, monkeypatch, {
        "schema.ts": "export interface WireEnvelope { id: string }\nexport interface WireEnvelopeView { display: string }\n",
        f"public.{extension}": statement + "\n",
        "assemble.ts": 'import type {\n  WireEnvelope,\n} from "./public";\nexport function assemble(value: WireEnvelope): void {}\n',
    })
    result = service.explore(repo, intent="type_dependencies", seed_ids=["assemble.ts::assemble#function"])
    _verify_packet(repo, result)
    assert len(result["relationships"]) == 1
    relationship = result["relationships"][0]
    assert relationship["edge"]["to"] == "schema.ts::WireEnvelope#interface"
    assert relationship["edge"]["resolution"] == "import-resolved"
    proof = [s for s in result["sources"] if s["id"] in relationship["source_ids"]]
    assert any(s["file"] == f"public.{extension}" and s["content"] == statement for s in proof)
    assert any(s["file"] == "assemble.ts" and s["content"] == 'import type {\n  WireEnvelope,\n} from "./public";' for s in proof)

    store, nodes, state = service._load_graph_context(repo, ensure_fresh=False)
    cache = store._sources_dir(repo) / f"public.{extension}"
    cache.write_text(cache.read_text().replace("WireEnvelope,", "WrongEnvelope,"))
    stale = explore_context(repo, store, nodes, state, intent="type_dependencies",
                            seed_ids=["assemble.ts::assemble#function"])
    assert not stale["relationships"]
    assert any(o["reason"] == "source_unavailable" for o in stale["omissions"])


def test_multiple_exports_on_same_recorded_line_do_not_guess_proof(tmp_path, monkeypatch):
    repo, _ = _setup(tmp_path, monkeypatch, {
        "schema.ts": "export interface WireEnvelope { id: string }\nexport interface Other { n: number }\n",
        "public.ts": 'export type { WireEnvelope } from "./schema"; export type { Other } from "./schema";\n',
        "assemble.ts": 'import type { WireEnvelope } from "./public";\nfunction assemble(value: WireEnvelope): void {}\n',
    })
    result = service.explore(repo, intent="type_dependencies", seed_ids=["assemble.ts::assemble#function"])
    assert not result["relationships"]
    assert any(o["reason"] == "source_unavailable" for o in result["omissions"])
