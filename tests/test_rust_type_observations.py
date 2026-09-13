from __future__ import annotations

import hashlib

from loci.parser.extractor import parse_file
from loci.parser.type_observations import extract_type_observations


def _extract(tmp_path, source: str):
    path = tmp_path / "sample.rs"
    path.write_text(source, encoding="utf-8")
    symbols = parse_file(path)
    for symbol in symbols:
        symbol.file_path = "sample.rs"
    observations = extract_type_observations(
        path,
        source_file="sample.rs",
        language="rust",
        source_hash=hashlib.sha256(source.encode()).hexdigest(),
        symbols=symbols,
    )
    return symbols, observations


def test_rust_declaration_sites_retain_exact_owners_and_imports(tmp_path):
    source = (
        "use crate::schema::{Payload as P, Marker};\n"
        "type Alias<T: Marker> = Vec<T>;\n"
        "trait Render: Marker {\n"
        "    fn render(value: P) -> P;\n"
        "}\n"
        "struct Envelope<T> where T: Marker { payload: P, values: Vec<T> }\n"
        "enum Event { One(P), Two { payload: P } }\n"
        "impl Render for Envelope<P> where P: Marker {\n"
        "    fn render(value: P) -> P { value }\n"
        "}\n"
        "impl Envelope<P> {\n"
        "    fn build(value: P) -> P { value }\n"
        "}\n"
    )
    symbols, records = _extract(tmp_path, source)

    alias = next(symbol for symbol in symbols if symbol.name == "Alias")
    envelope = next(symbol for symbol in symbols if symbol.name == "Envelope")
    event = next(symbol for symbol in symbols if symbol.name == "Event")
    render_trait = next(symbol for symbol in symbols if symbol.name == "Render")
    impls = [symbol for symbol in symbols if symbol.kind == "impl"]

    assert alias.kind == "type"
    assert any(record.owner.start_byte == alias.byte_offset and record.context == "alias" for record in records)
    assert any(record.owner.start_byte == envelope.byte_offset and record.context == "property" for record in records)
    assert any(record.owner.start_byte == event.byte_offset and record.context == "property" for record in records)
    assert any(
        record.owner.start_byte == render_trait.byte_offset
        and record.relation == "supertrait"
        and record.context == "supertrait"
        for record in records
    )
    assert any(record.relation == "impl_trait" and record.context == "impl_trait" for record in records)
    assert any(record.relation == "impl_self_type" and record.context == "impl_self_type" for record in records)
    assert impls and {record.owner.start_byte for record in records if record.owner.kind == "impl"} <= {
        symbol.byte_offset for symbol in impls
    }

    imported = [record for record in records if record.text == "P"]
    assert imported and all(record.binding_state == "imported" for record in imported)
    generic = [record for record in records if record.text == "T"]
    assert generic and all(record.binding_state == "shadowed" for record in generic)
    for record in records:
        assert source.encode()[record.start_byte:record.end_byte] == record.text.encode()


def test_rust_type_parameters_shadow_imports_and_signature_owner_does_not_transfer(tmp_path):
    source = (
        "use crate::schema::T;\n"
        "trait Contract {\n"
        "    fn apply<T: Bound>(value: T) -> T;\n"
        "}\n"
    )
    symbols, records = _extract(tmp_path, source)
    contract = next(symbol for symbol in symbols if symbol.name == "Contract")

    generic = [record for record in records if record.text == "T"]
    assert generic and all(record.binding_state == "shadowed" for record in generic)
    signature_records = [record for record in records if record.context in {"annotation", "return"}]
    assert signature_records
    assert all(record.owner.kind == "unindexed" for record in signature_records)
    assert all(record.owner.start_byte != contract.byte_offset for record in signature_records)


def test_rust_associated_projections_and_macro_types_are_explicitly_unsupported(tmp_path):
    source = (
        "trait Bound {}\n"
        "type Projection<T> = T::Item;\n"
        "type Macro = generated_type!();\n"
        "type Object = impl Bound;\n"
    )
    _, records = _extract(tmp_path, source)

    projection = next(record for record in records if record.text == "T::Item")
    macro = next(record for record in records if record.text == "generated_type!()")
    abstract = next(record for record in records if record.text == "impl Bound")
    assert projection.binding_state == "unsupported"
    assert projection.unsupported_reason == "unsupported_associated_type_projection"
    assert macro.binding_state == "unsupported"
    assert macro.unsupported_reason == "unsupported_macro_invocation"
    assert abstract.binding_state == "unsupported"
    assert abstract.unsupported_reason == "unsupported_abstract_type"


def test_rust_local_type_scope_is_forward_visible_but_does_not_cross_inline_modules(tmp_path):
    source = (
        "use crate::schema::Imported;\n"
        "#[derive(Debug)]\n"
        "struct Item;\n"
        "fn forward() -> Item { loop {} }\n"
        "mod child {\n"
        "    struct Item;\n"
        "    fn own() -> Item { loop {} }\n"
        "    fn parent() -> Imported { loop {} }\n"
        "}\n"
    )
    symbols, records = _extract(tmp_path, source)
    outer = next(symbol for symbol in symbols if symbol.name == "Item" and symbol.byte_offset == source.index("struct Item"))
    forward = next(record for record in records if record.text == "Item" and record.line == 4)
    inner = next(record for record in records if record.text == "Item" and record.line == 7)
    parent = next(record for record in records if record.text == "Imported")

    assert forward.binding_state == "local"
    assert forward.local_bindings[0].declaration_start_byte == outer.byte_offset
    assert forward.local_bindings[0].declaration_end_byte == outer.byte_offset + outer.byte_length
    assert inner.binding_state == "local"
    assert inner.local_bindings[0].declaration_start_byte == source.index("    struct Item") + 4
    assert parent.binding_state == "unbound"
