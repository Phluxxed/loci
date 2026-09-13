from __future__ import annotations

import hashlib

import pytest

from loci.parser.extractor import parse_file
from loci.parser.type_observations import (
    TypeExtractionError,
    extract_type_observations,
)


def _extract(tmp_path, source: str, *, name: str = "sample.ts"):
    path = tmp_path / name
    path.write_text(source, encoding="utf-8")
    source_file = f"src/{name}"
    symbols = parse_file(path)
    for symbol in symbols:
        symbol.file_path = source_file
    return extract_type_observations(
        path,
        source_file=source_file,
        language="typescript",
        source_hash=hashlib.sha256(source.encode()).hexdigest(),
        symbols=symbols,
    )


def test_extracts_type_sites_with_declaration_owners_and_heritage(tmp_path):
    observations = _extract(
        tmp_path,
        """
interface Payload { id: string }
interface Contract { value: Payload }
interface Derived extends Contract { payload: Payload }
class Base<T> { value!: T }
type Alias<T extends Base<Payload>> = Array<Payload | T>;
class Processor extends Base<Payload> implements Contract {
  payload: Payload;
  process(value: Payload): Alias { return {} as Alias; }
}
""".lstrip(),
    )

    named = {(item.text, item.relation, item.context) for item in observations}
    assert ("Base", "extends", "heritage") in named
    assert ("Contract", "implements", "heritage") in named
    assert ("Contract", "extends", "heritage") in named
    assert ("Payload", "uses_type", "property") in named
    assert ("Alias", "uses_type", "return") in named
    assert any(item.text == "Payload" and item.context == "type_argument" for item in observations)

    processor_payload = next(
        item for item in observations
        if item.text == "Payload" and item.context == "property" and item.owner.kind == "class"
    )
    assert processor_payload.path == ("Payload",)
    assert processor_payload.binding_state == "local"
    assert processor_payload.owner.start_byte < processor_payload.start_byte
    assert processor_payload.text.encode() == (
        b"Payload"
    )


def test_type_parameter_shadows_only_type_lookups_and_typeof_uses_value_space(tmp_path):
    observations = _extract(
        tmp_path,
        """
interface Payload { id: string }
const Payload = { id: "v" };
type Box<Payload> = { type: Payload; value: typeof Payload };
""".lstrip(),
    )

    type_use = next(item for item in observations if item.text == "Payload" and item.context == "property")
    query = next(item for item in observations if item.text == "Payload" and item.context == "type_query")
    assert type_use.lookup_space == "type"
    assert type_use.binding_state == "shadowed"
    assert type_use.local_bindings[0].kind == "type_parameter"
    assert query.lookup_space == "value"
    assert query.binding_state == "local"
    assert query.local_bindings[0].kind == "constant"


def test_import_binding_and_qualified_namespace_sites_are_retained(tmp_path):
    observations = _extract(
        tmp_path,
        """
import type { Payload } from "./payload";
import * as Models from "./models";
type View = Payload | Models.Result;
type Query = typeof Payload;
""".lstrip(),
    )

    payload = next(item for item in observations if item.text == "Payload" and item.context == "alias")
    qualified = next(item for item in observations if item.text == "Models.Result")
    query = next(item for item in observations if item.context == "type_query")
    assert payload.binding_state == "imported"
    assert payload.import_bindings[0].type_only is True
    assert qualified.path == ("Models", "Result")
    assert qualified.binding_state == "imported"
    assert query.lookup_space == "value"
    assert query.import_bindings[0].type_only is True


def test_qualified_local_and_unknown_namespaces_stay_explicitly_unsupported(tmp_path):
    observations = _extract(
        tmp_path,
        """
interface LocalNamespace { value: string }
type LocalUse = LocalNamespace.Member;
type UnknownUse = External.Member;
""".lstrip(),
    )

    local, unknown = [
        item for item in observations if item.text in {"LocalNamespace.Member", "External.Member"}
    ]
    assert local.binding_state == "unsupported"
    assert local.unsupported_reason == "qualified_local_namespace"
    assert local.path == ("LocalNamespace", "Member")
    assert local.import_bindings == ()
    assert unknown.binding_state == "unsupported"
    assert unknown.unsupported_reason == "qualified_unbound_namespace"
    assert unknown.path == ("External", "Member")


def test_exported_named_arrow_uses_the_variable_declaration_owner(tmp_path):
    observations = _extract(
        tmp_path,
        """
interface Payload { id: string }
export const project = (value: Payload): Payload => value;
""".lstrip(),
    )

    sites = [item for item in observations if item.text == "Payload"]
    assert len(sites) == 2
    assert {item.owner.kind for item in sites} == {"function"}
    assert all(item.owner.start_byte < item.start_byte for item in sites)


def test_unicode_type_site_preserves_its_utf8_byte_interval(tmp_path):
    source = "interface Café { label: string }\ntype Menu = Café;\n"
    observations = _extract(tmp_path, source)
    cafe = next(item for item in observations if item.text == "Café")
    assert cafe.text.encode("utf-8") == source.encode("utf-8")[cafe.start_byte:cafe.end_byte]
    assert cafe.column == len("type Menu = ".encode("utf-8")) + 1


def test_alias_and_generic_binder_names_are_not_emitted_as_uses(tmp_path):
    observations = _extract(
        tmp_path,
        """
import type { Payload } from "./payload";
type Alias = Payload;
type Generic<Payload> = Payload;
""".lstrip(),
    )

    alias_use = [item for item in observations if item.text == "Alias"]
    payload = [item for item in observations if item.text == "Payload"]
    assert alias_use == []
    assert [item.binding_state for item in payload] == ["imported", "shadowed"]
    assert payload[1].import_bindings == ()
    assert payload[1].local_bindings[0].kind == "type_parameter"


def test_nearest_lexical_scope_hides_outer_import_and_parameter_scope_ends(tmp_path):
    observations = _extract(
        tmp_path,
        """
import { Payload } from "./payload";
function inner<Payload>(value: Payload): Payload {
  type Query = typeof Payload;
  return value;
}
function parameter(Payload: number) {
  type LocalQuery = typeof Payload;
}
function sibling(): typeof Payload { throw 0; }
""".lstrip(),
    )

    inner = [item for item in observations if item.owner.kind == "function" and item.owner.start_byte < 80]
    assert inner and all(item.binding_state == "shadowed" for item in inner)
    assert all(item.import_bindings == () for item in inner)
    parameter_query = next(
        item
        for item in observations
        if item.context == "type_query"
        and item.local_bindings
        and item.local_bindings[0].kind == "parameter"
    )
    assert parameter_query.binding_state == "shadowed"
    assert parameter_query.local_bindings[0].kind == "parameter"
    sibling = [
        item
        for item in observations
        if item.context == "type_query" and not item.local_bindings
    ]
    assert sibling and all(item.binding_state == "imported" for item in sibling)


def test_generic_binders_cover_arrow_expression_function_and_signature_forms(tmp_path):
    observations = _extract(
        tmp_path,
        """
import type { Payload } from "./payload";
const arrow = <Payload,>(value: Payload): Payload => value;
const expression = function<Payload>(value: Payload): Payload { return value; };
type Fn = <Payload>(value: Payload) => Payload;
type Ctor = new <Payload>(value: Payload) => Payload;
interface Shape { run<Payload>(value: Payload): Payload; }
""".lstrip(),
    )

    payload = [item for item in observations if item.text == "Payload"]
    assert len(payload) == 10
    assert all(item.binding_state == "shadowed" for item in payload)
    assert all(item.import_bindings == () for item in payload)
    assert all(item.local_bindings[0].kind == "type_parameter" for item in payload)


def test_typeof_constant_keeps_the_exact_indexed_binding_span(tmp_path):
    source = "const FACTORY = 1;\ntype Factory = typeof FACTORY;\n"
    path = tmp_path / "factory.ts"
    path.write_text(source, encoding="utf-8")
    source_file = "src/factory.ts"
    symbols = parse_file(path)
    for symbol in symbols:
        symbol.file_path = source_file
    observation = next(
        item for item in extract_type_observations(
            path,
            source_file=source_file,
            language="typescript",
            source_hash=hashlib.sha256(source.encode()).hexdigest(),
            symbols=symbols,
        )
        if item.context == "type_query"
    )
    factory = next(symbol for symbol in symbols if symbol.name == "FACTORY")
    binding = observation.local_bindings[0]
    assert observation.binding_state == "local"
    assert (binding.declaration_start_byte, binding.declaration_end_byte) == (
        factory.byte_offset,
        factory.byte_offset + factory.byte_length,
    )


def test_heritage_uses_the_correct_type_and_value_lookup_spaces(tmp_path):
    observations = _extract(
        tmp_path,
        """
class Base<T> {}
interface Contract {}
class Child extends Base<Contract> implements Contract {}
interface Derived extends Contract {}
""".lstrip(),
    )

    extends = [item for item in observations if item.relation == "extends"]
    implements = next(item for item in observations if item.relation == "implements")
    assert any(item.text == "Base" and item.lookup_space == "value" for item in extends)
    assert any(item.text == "Contract" and item.lookup_space == "type" for item in extends)
    assert implements.lookup_space == "type"
    argument = next(item for item in observations if item.text == "Contract" and item.context == "type_argument")
    assert argument.relation == "uses_type"


def test_unsupported_constructs_and_anonymous_owners_remain_explicit(tmp_path):
    observations = _extract(
        tmp_path,
        """
type Conditional<T> = T extends string ? T : never;
const callback = wrap((value: External): External => value);
class Child extends mixin(Base) {}
""".lstrip(),
    )

    assert any(item.binding_state == "unsupported" and item.unsupported_reason for item in observations)
    anonymous = [item for item in observations if item.text == "External"]
    assert anonymous and all(item.owner.kind == "unindexed" for item in anonymous)
    heritage = next(item for item in observations if item.relation == "extends")
    assert heritage.binding_state == "unsupported"
    assert heritage.path == ()


def test_non_typescript_is_empty_and_invalid_typescript_is_diagnostic(tmp_path):
    path = tmp_path / "sample.py"
    path.write_text("x = 1\n", encoding="utf-8")
    assert extract_type_observations(
        path,
        source_file="src/sample.py",
        language="python",
        source_hash=hashlib.sha256(path.read_bytes()).hexdigest(),
        symbols=(),
    ) == ()

    broken = tmp_path / "broken.ts"
    broken.write_text("type Broken = {\n", encoding="utf-8")
    with pytest.raises(TypeExtractionError) as raised:
        extract_type_observations(
            broken,
            source_file="src/broken.ts",
            language="typescript",
            source_hash=hashlib.sha256(broken.read_bytes()).hexdigest(),
            symbols=(),
        )
    assert raised.value.code == "TYPE_PARSE_FAILED"


def test_changed_source_rejects_symbols_from_the_previous_hash(tmp_path):
    path = tmp_path / "changed.ts"
    original = "type Original = string;\n"
    path.write_text(original, encoding="utf-8")
    symbols = parse_file(path)
    for symbol in symbols:
        symbol.file_path = "src/changed.ts"
    path.write_text("type Changed = number;\n", encoding="utf-8")

    with pytest.raises(TypeExtractionError) as raised:
        extract_type_observations(
            path,
            source_file="src/changed.ts",
            language="typescript",
            source_hash=hashlib.sha256(original.encode()).hexdigest(),
            symbols=symbols,
        )
    assert raised.value.code == "TYPE_SOURCE_HASH_MISMATCH"
    assert raised.value.reason == "source_hash_mismatch"
