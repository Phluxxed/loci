from __future__ import annotations

import hashlib

import pytest

from loci.parser.extractor import parse_file
from loci.parser.type_observations import TypeExtractionError, extract_type_observations


def _extract(tmp_path, source: str):
    path = tmp_path / "sample.go"
    path.write_text(source, encoding="utf-8")
    symbols = parse_file(path)
    for symbol in symbols:
        symbol.file_path = "sample.go"
    return symbols, extract_type_observations(
        path,
        source_file="sample.go",
        language="go",
        source_hash=hashlib.sha256(source.encode()).hexdigest(),
        symbols=symbols,
    )


def test_go_authored_type_sites_keep_alias_generic_and_embedding_meaning(tmp_path):
    source = """package model
import (
    alias "example.com/acme/alias"
    "example.com/acme/schema"
    "example.com/acme/other"
    _ "example.com/acme/blank"
    . "example.com/acme/dot"
)

type UserID int64
type AliasID = UserID
type Number interface { ~int | ~int64 }
type Page[T Number] struct { Value T; Remote schema.Payload; Explicit alias.Payload }
type Audit struct { Created int64 }
type Entity struct { Audit }
type Runner interface { Run() error }
type Combined interface { Runner }

func Build(id AliasID) Page[UserID] { return Page[UserID]{} }
"""
    symbols, records = _extract(tmp_path, source)

    alias = next(symbol for symbol in symbols if symbol.name == "AliasID")
    assert alias.kind == "type"
    assert source.encode()[alias.byte_offset:alias.byte_offset + alias.byte_length] == b"AliasID = UserID"
    assert {record.text for record in records if record.owner.kind == "type"} >= {
        "UserID", "Number", "T", "schema.Payload", "alias.Payload", "Audit", "Runner",
    }

    bare = [record for record in records if record.text == "UserID"]
    assert bare and all(record.binding_state == "package" for record in bare)
    assert all(not record.local_bindings and not record.import_bindings for record in bare)
    explicit = next(record for record in records if record.text == "alias.Payload")
    assert explicit.path == ("alias", "Payload")
    assert explicit.binding_state == "imported"
    assert [binding.local_name for binding in explicit.import_bindings] == ["alias"]
    deferred = next(record for record in records if record.text == "schema.Payload")
    assert deferred.binding_state == "deferred"
    assert deferred.path == ("schema", "Payload")
    assert {binding.local_name for binding in deferred.import_bindings} == {None}
    assert len(deferred.import_bindings) == 2

    assert {
        (record.text, record.relation, record.context)
        for record in records
    } >= {
        ("Audit", "embeds", "struct_embedding"),
        ("Runner", "embeds", "interface_embedding"),
        ("Number", "uses_type", "constraint"),
        ("T", "uses_type", "property"),
        ("UserID", "uses_type", "type_argument"),
    }
    approximation = [record for record in records if "~int" in record.text]
    assert approximation and all(record.binding_state == "unsupported" for record in approximation)
    assert all(record.unsupported_reason == "unsupported_approximation_or_union" for record in approximation)
    assert not any(record.text in {"int", "int64", "error"} for record in records)
    for record in records:
        assert source.encode()[record.start_byte:record.end_byte] == record.text.encode()


def test_go_type_parameters_and_value_shadowing_block_package_guesses(tmp_path):
    source = """package model
import api "example.com/acme/api"

type Request struct{}
type Box[Request any] struct { Value Request }
type Pair[A, B Number] struct { First A; Second B }
func (b Box[T]) Copy(value T) T { return value }
func Probe(api int) api.Request { type Local api.Request; return api.Request{} }
type Tglobal int
func LocalTypes() { type T string; type X T }
func Many(left, right int) { type Inside right }
func LocalFunction() { _ = func(value Request) Request { return value } }
"""
    _, records = _extract(tmp_path, source)

    box_value = next(record for record in records if record.text == "Request" and record.context == "property")
    assert box_value.binding_state == "shadowed"
    assert box_value.local_bindings[0].kind == "type_parameter"
    assert box_value.local_bindings[0].namespace == "type"
    method_values = [record for record in records if record.text == "T" and record.owner.kind == "method"]
    assert method_values and all(record.binding_state == "shadowed" for record in method_values)
    assert all(record.local_bindings[0].kind == "type_parameter" for record in method_values)
    pair_values = [record for record in records if record.text in {"A", "B"}]
    assert {record.text for record in pair_values} == {"A", "B"}
    assert all(record.binding_state == "shadowed" for record in pair_values)
    assert all(record.local_bindings[0].kind == "type_parameter" for record in pair_values)

    return_type = next(record for record in records if record.text == "api.Request" and record.context == "return")
    assert return_type.binding_state == "imported"
    shadowed = next(record for record in records if record.text == "api.Request" and record.context == "alias")
    assert shadowed.binding_state == "shadowed"
    assert shadowed.import_bindings == ()
    assert shadowed.local_bindings[0].kind == "unindexed"
    assert shadowed.local_bindings[0].namespace == "both"

    local_type = next(record for record in records if record.text == "T" and record.context == "alias")
    assert local_type.binding_state == "local"
    assert local_type.local_bindings[0].kind == "type"
    assert local_type.owner.kind == "type"
    assert local_type.local_bindings[0].declaration_start_byte == source.index("T string")

    parameter_shadow = next(record for record in records if record.text == "right")
    assert parameter_shadow.binding_state == "shadowed"
    assert parameter_shadow.local_bindings[0].kind == "unindexed"

    literal = next(record for record in records if record.text == "Request" and record.owner.kind == "unindexed")
    assert literal.owner.start_byte == source.index("func(value Request)")


def test_go_type_extraction_reports_stale_or_entirely_invalid_source(tmp_path):
    path = tmp_path / "sample.go"
    path.write_text("package sample\nfunc Build(value Missing) {}\n", encoding="utf-8")
    with pytest.raises(TypeExtractionError, match="changed after symbol extraction"):
        extract_type_observations(
            path,
            source_file="sample.go",
            language="go",
            source_hash="0" * 64,
            symbols=parse_file(path),
        )

    path.write_text("package sample\ntype Broken struct {\n", encoding="utf-8")
    with pytest.raises(TypeExtractionError, match="could not be parsed"):
        extract_type_observations(
            path,
            source_file="sample.go",
            language="go",
            source_hash=hashlib.sha256(path.read_bytes()).hexdigest(),
            symbols=(),
        )
