"""Normal retrieval uses short references without weakening exact source reads."""
import hashlib
import re

import pytest

from loci import service
from loci.storage.source_refs import SourceRefStore
from tests.test_type_relation_service import _setup


def _short(reference):
    return isinstance(reference, str) and re.fullmatch(r"sr1_[a-z2-7]{26}", reference)


def test_normal_references_are_short_stable_and_reconstruct_the_owning_extent(tmp_path, monkeypatch):
    text = "# Source\n" + "🙂 exact source\n" * 1500
    repo, _ = _setup(tmp_path, monkeypatch, {"text.md": text})
    result = service.retrieve(repo, "text.md")
    assert result == service.retrieve(repo, "text.md")
    assert all(_short(item["source_ref"]) for item in (*result["items"], *result["sources"]))
    item = next(item for item in result["items"] if item["role"] == "anchor")
    reference = item["source_ref"]
    raw = text.encode()
    extent = item["extent"]
    offset = extent["start_byte"]
    parts = []
    while reference is not None:
        assert _short(reference)
        page = service.read(repo, reference)
        source = page["source"]
        assert _short(source["source_ref"])
        assert source["start_byte"] == offset
        assert source["end_byte"] > offset
        assert source["content_hash"] == hashlib.sha256(raw).hexdigest()
        assert source["content"].encode() == raw[offset:source["end_byte"]]
        assert page["usage"]["evidence_bytes"] <= 8192
        assert page["usage"]["output_bytes"] <= 16384
        parts.append(source["content"])
        offset = source["end_byte"]
        reference = page["next_source_ref"]
    assert offset == extent["end_byte"]
    assert "".join(parts).encode() == raw[extent["start_byte"]:extent["end_byte"]]


def test_short_reference_rejects_source_changes_before_and_after_refresh(tmp_path, monkeypatch):
    repo, _ = _setup(tmp_path, monkeypatch, {"text.md": "# Original\nExact content.\n"})
    reference = service.retrieve(repo, "text.md")["items"][0]["source_ref"]
    assert _short(reference)
    (repo / "text.md").write_text("# Changed\nDifferent content.\n")
    for fresh in (False, True):
        with pytest.raises(service.LociError) as error:
            service.read(repo, reference, ensure_fresh=fresh)
        assert error.value.code == "SOURCE_STALE"


def test_short_reference_cannot_be_used_in_another_repository(tmp_path, monkeypatch):
    repo, _ = _setup(tmp_path, monkeypatch, {"text.md": "# Exact\nSame bytes.\n"})
    reference = service.retrieve(repo, "text.md")["items"][0]["source_ref"]
    other = tmp_path / "other"
    other.mkdir()
    (other / "text.md").write_bytes((repo / "text.md").read_bytes())
    service.index_repo(other)
    with pytest.raises(service.LociError) as error:
        service.read(other, reference)
    assert error.value.code == "INVALID_SOURCE_REF"


@pytest.mark.parametrize("change", [{"offset": True}, {"end": 10000}, {"start": 1, "offset": 1}])
def test_short_reference_resolution_still_validates_extent_and_utf8(tmp_path, monkeypatch, change):
    raw = "🙂 source\n".encode()
    repo, store = _setup(tmp_path, monkeypatch, {"text.md": raw.decode()})
    references = SourceRefStore(repo, store)
    value = {"v": 1, "repo": str(repo.resolve()), "file": "text.md",
             "hash": hashlib.sha256(raw).hexdigest(), "start": 0,
             "end": len(raw), "offset": 0, **change}
    reference = references.stage(value)
    references.flush([reference])
    with pytest.raises(service.LociError) as error:
        service.read(repo, reference)
    assert error.value.code == "INVALID_SOURCE_REF"


def test_short_reference_refuses_source_replaced_with_outside_symlink(tmp_path, monkeypatch):
    repo, _ = _setup(tmp_path, monkeypatch, {"text.md": "# Source\nExact bytes.\n"})
    reference = service.retrieve(repo, "text.md")["items"][0]["source_ref"]
    outside = tmp_path / "outside.md"
    outside.write_bytes((repo / "text.md").read_bytes())
    (repo / "text.md").unlink()
    (repo / "text.md").symlink_to(outside)
    with pytest.raises(service.LociError) as error:
        service.read(repo, reference)
    assert error.value.code == "SOURCE_UNAVAILABLE"
