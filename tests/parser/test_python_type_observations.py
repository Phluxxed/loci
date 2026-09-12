from __future__ import annotations

import hashlib

import pytest

from loci.parser.extractor import parse_file
from loci.parser.type_observations import TypeExtractionError, extract_type_observations


def _extract(tmp_path, source):
    path = tmp_path / "sample.py"
    path.write_text(source, encoding="utf-8")
    symbols = parse_file(path)
    for symbol in symbols:
        symbol.file_path = "sample.py"
    observations = extract_type_observations(
        path, source_file="sample.py", language="python",
        source_hash=hashlib.sha256(source.encode()).hexdigest(), symbols=symbols,
    )
    return symbols, observations


def test_python_definition_time_annotations_and_enclosing_shadow(tmp_path):
    source = (
        "from schema import Payload as P\n"
        "def direct(P: P) -> P:\n    return P\n"
        "def outer(P):\n    def nested(value: P) -> P:\n        return value\n"
        "def generic[P](value: P) -> P:\n    return value\n"
    )
    _, records = _extract(tmp_path, source)
    assert [r.binding_state for r in records if r.line == 2] == ["imported", "imported"]
    assert {r.binding_state for r in records if r.line == 5} == {"unsupported"}
    assert {r.binding_state for r in records if r.line == 7} == {"shadowed"}
    for record in records:
        assert source.encode()[record.start_byte:record.end_byte] == record.text.encode()


def test_decorated_ownership_fields_and_literal_forward_boundary(tmp_path):
    source = (
        "from schema import Payload as P\n"
        "@decorator\nclass Container:\n    field: list[P]\n"
        "def forward(value: 'P') -> \"schema.P\":\n    return value\n"
        "def dynamic(value: 'list[P]') -> make_type():\n    return value\n"
    )
    symbols, records = _extract(tmp_path, source)
    container = next(s for s in symbols if s.name == "Container")
    field = next(r for r in records if r.text == "P")
    assert field.owner.start_byte == container.byte_offset == source.index("@decorator")
    assert field.owner.end_byte == container.byte_offset + container.byte_length
    assert {(r.text, r.path) for r in records if r.line == 5} == {
        ("'P'", ("P",)), ('"schema.P"', ("schema", "P")),
    }
    assert {r.binding_state for r in records if r.line == 7} == {"unsupported"}


@pytest.mark.parametrize("marker", [
    "class TypeAlias: pass\n",
    "from other import TypeAlias\n",
    "from typing import TypeAlias\nTypeAlias = object()\n",
    "from typing import TypeAlias\nfrom other import *\n",
    "from typing import TypeAlias\nif enabled:\n    from other import TypeAlias\n",
    "from typing import TypeAlias\nfor TypeAlias in values:\n    pass\n",
])
def test_alias_marker_requires_canonical_unambiguous_binding(tmp_path, marker):
    symbols, records = _extract(tmp_path, marker + "Alias: TypeAlias = P\n")
    assert not any(s.name == "Alias" and s.kind == "type" for s in symbols)
    assert not any(r.context == "alias" for r in records)


@pytest.mark.parametrize("marker, annotation", [
    ("from typing import TypeAlias", "TypeAlias"),
    ("import typing", "typing.TypeAlias"),
])
def test_explicit_alias_is_an_exact_type_declaration(tmp_path, marker, annotation):
    source = marker + "\nfrom schema import Payload as P\n" + f"Alias: {annotation} = list[P]\n"
    symbols, records = _extract(tmp_path, source)
    alias = next(s for s in symbols if s.name == "Alias")
    assert alias.kind == "type"
    assert source.encode()[alias.byte_offset:alias.byte_offset + alias.byte_length] == f"Alias: {annotation} = list[P]".encode()
    assert alias.content_hash == hashlib.sha256(source.encode()[alias.byte_offset:alias.byte_offset + alias.byte_length]).hexdigest()
    payload = next(r for r in records if r.text == "P")
    assert payload.binding_state == "imported" and payload.owner.kind == "type"


def test_python_type_extraction_rejects_stale_source(tmp_path):
    path = tmp_path / "sample.py"
    path.write_text("def f(value: P): pass\n")
    with pytest.raises(TypeExtractionError, match="changed after symbol extraction"):
        extract_type_observations(path, source_file="sample.py", language="python",
                                  source_hash="0" * 64, symbols=parse_file(path))


def test_literal_values_and_annotated_metadata_are_not_forward_types(tmp_path):
    _, records = _extract(tmp_path,
        "from typing import Literal, Annotated\nfrom schema import Payload as P\n"
        "def f(value: Literal['P']) -> Annotated[P, 'P']:\n    return value\n")
    assert len(records) == 2
    assert {r.binding_state for r in records} == {"unsupported"}
    assert all(r.unsupported_reason == "unsupported_value_type_arguments" for r in records)


def test_pattern_capture_cannot_prove_an_enclosing_import(tmp_path):
    _, records = _extract(tmp_path,
        "from model import Payload as P\ndef outer(value):\n"
        "    match value:\n        case P:\n            def nested(x: P): pass\n")
    assert len(records) == 1 and records[0].binding_state == "unsupported"


def test_metaclass_keywords_remain_unresolved_beside_authored_direct_bases(tmp_path):
    _, records = _extract(tmp_path,
        "from model import Base, Meta\nclass Child(Base, metaclass=Meta): pass\n")
    base = next(r for r in records if r.text == "Base")
    assert base.relation == "extends" and base.binding_state == "imported"
    meta = next(r for r in records if r.text == "metaclass=Meta")
    assert meta.binding_state == "unsupported"
