"""Exact source hydration preserves bytes, freshness and fixed public budgets."""
import base64
import hashlib
import json

import pytest

from loci import service
from loci._exploration_output import Span
from loci.retrieval_io import source_ref
from tests.test_type_relation_service import _setup


def _reference(repo, file, raw):
    return source_ref(repo, Span(file, 0, len(raw), 1,
                                max(1, raw[:-1].count(b"\n") + 1),
                                hashlib.sha256(raw).hexdigest(), raw.decode()))


@pytest.mark.parametrize("text", ["# Text\n" + "🙂" * 6000, "# Text\n" + '\\"' * 10000], ids=["unicode", "json-escaping"])
def test_pages_reconstruct_exact_utf8_extent_under_complete_result_budget(tmp_path, monkeypatch, text):
    repo, _ = _setup(tmp_path, monkeypatch, {"text.md": text})
    raw = text.encode()
    reference = _reference(repo, "text.md", raw)
    parts = []
    previous_end = 0
    while reference is not None:
        result = service.read(repo, reference)
        source = result["source"]
        assert source["start_byte"] == previous_end
        assert source["end_byte"] > previous_end
        assert source["content"].encode() == raw[source["start_byte"]:source["end_byte"]]
        assert source["content_hash"] == hashlib.sha256(raw).hexdigest()
        encoded = json.dumps({"content": [], "structuredContent": result, "isError": False},
                             ensure_ascii=False, separators=(",", ":")).encode()
        assert len(encoded) == result["usage"]["output_bytes"] <= 16384
        assert len(source["content"].encode()) == result["usage"]["evidence_bytes"] <= 8192
        previous_end = source["end_byte"]
        parts.append(source["content"])
        reference = result["next_source_ref"]
        assert result["complete"] == (reference is None)
    assert "".join(parts) == text


def test_source_reference_refuses_changed_source_before_and_after_refresh(tmp_path, monkeypatch):
    text = "# Initial\nExact text.\n"
    repo, _ = _setup(tmp_path, monkeypatch, {"text.md": text})
    reference = _reference(repo, "text.md", text.encode())
    (repo / "text.md").write_text("# Changed\nDifferent offsets.\n")
    for ensure_fresh in (False, True):
        with pytest.raises(service.LociError) as exc:
            service.read(repo, reference, ensure_fresh=ensure_fresh)
        assert exc.value.code == "SOURCE_STALE"


@pytest.mark.parametrize("change", [
    {"repo": "/elsewhere"}, {"file": "../text.md"}, {"offset": True},
    {"start": 1, "offset": 1}, {"end": 10000}, {"file": "unknown.md"},
])
def test_invalid_locators_cannot_change_repository_extent_or_utf8_boundary(tmp_path, monkeypatch, change):
    text = "🙂 heading\n"
    repo, _ = _setup(tmp_path, monkeypatch, {"text.md": text})
    reference = _reference(repo, "text.md", text.encode())
    value = json.loads(base64.urlsafe_b64decode(reference + "=" * (-len(reference) % 4)))
    value.update(change)
    encoded = base64.urlsafe_b64encode(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                                separators=(",", ":")).encode()).decode().rstrip("=")
    with pytest.raises(service.LociError) as exc:
        service.read(repo, encoded)
    assert exc.value.code == "INVALID_SOURCE_REF"


def test_source_reference_rejects_outside_symlink_after_selection(tmp_path, monkeypatch):
    text = "# Source\n"
    repo, _ = _setup(tmp_path, monkeypatch, {"text.md": text})
    reference = _reference(repo, "text.md", text.encode())
    outside = tmp_path / "outside.md"
    outside.write_text(text)
    (repo / "text.md").unlink()
    (repo / "text.md").symlink_to(outside)
    with pytest.raises(service.LociError) as exc:
        service.read(repo, reference)
    assert exc.value.code == "SOURCE_UNAVAILABLE"
