"""Rust type contracts joined to exact lexical or proven item-reference evidence.

The imported seam consumes the existing visibility-checked Cargo/module result
at the same authored occurrence. Executable reference ownership is irrelevant:
the type record keeps its own declaration owner and does not alter references.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Mapping, Sequence

from loci.parser.symbols import Symbol
from loci.parser.type_models import RawTypeObservation, valid_type_import_path

from .references import SymbolReferenceRecord
from .imports import ImportRecord
from .type_models import TypeControl, TypeSupport


@dataclass(frozen=True)
class RustTypeIndex:
    symbols: Mapping[str, Symbol]
    references: Mapping[tuple, tuple[SymbolReferenceRecord, ...]]
    controls: tuple[TypeControl, ...]
    file_configurations: Mapping[str, str]
    module_support: Mapping[str, tuple[TypeSupport, ...]]


def build_rust_type_index(symbols: Sequence[Symbol], references: Sequence[SymbolReferenceRecord],
                          input_hashes: Mapping[str, str], imports: Sequence[ImportRecord]) -> RustTypeIndex:
    by_site = defaultdict(list)
    configurations = defaultdict(set)
    module_support = defaultdict(list)
    for record in imports:
        if (record.raw.language == "rust" and record.raw.rust is not None
                and record.raw.rust.kind == "module" and record.status == "resolved"
                and record.target_file is not None and record.resolution_configuration is not None):
            configurations[record.target_file].add(record.resolution_configuration)
            module_support[record.target_file].append(TypeSupport(
                "module_declaration", record.raw.source_file, record.raw.line,
                record.raw.source_hash, record.target_id,
            ))
    for symbol in symbols:
        if symbol.language == "rust" and symbol.kind == "crate":
            metadata = symbol.metadata.get("loci", {})
            root = metadata.get("crate_root")
            if isinstance(root, str):
                configurations[root].add("declared_possible" if metadata.get("required_features") else "unconditional")
    for record in references:
        raw = record.raw
        if raw.language == "rust":
            by_site[(raw.source_file, raw.source_hash, raw.start_byte,
                     raw.end_byte, raw.path)].append(record)
    return RustTypeIndex(
        {symbol.id: symbol for symbol in symbols},
        {key: tuple(value) for key, value in by_site.items()},
        tuple(TypeControl(file, content_hash) for file, content_hash in sorted(input_hashes.items())
              if PurePosixPath(file).name == "Cargo.toml"),
        {file: "declared_possible" if "declared_possible" in values else "unconditional"
         for file, values in configurations.items()},
        {file: tuple(values) for file, values in module_support.items()},
    )


def rust_type_configuration(symbol: Symbol, index: RustTypeIndex) -> str | None:
    if symbol.file_path not in index.file_configurations:
        # Indexing authored bytes does not declare a Cargo target or module.
        return None
    loci = symbol.metadata.get("loci", {})
    value = loci.get("rust_type_configuration")
    if value is None:
        value = loci.get("rust_item", {}).get("configuration")
    if value not in {"unconditional", "declared_possible"}:
        return None
    return "declared_possible" if "declared_possible" in {
        value, index.file_configurations.get(symbol.file_path),
    } else "unconditional"


def _compatible(raw: RawTypeObservation, target: Symbol) -> bool:
    if target.language != "rust":
        return False
    if raw.relation in {"supertrait", "impl_trait"} or raw.context == "constraint":
        return target.kind == "trait"
    if raw.relation == "impl_self_type":
        return target.kind in {"struct", "enum", "type"}
    return target.kind in {"struct", "enum", "type", "trait"}


def _module_proof(files: Sequence[str], index: RustTypeIndex) -> tuple[TypeSupport, ...]:
    pending = list(files)
    visited = set()
    proof = {}
    while pending:
        file = pending.pop()
        if file in visited:
            continue
        visited.add(file)
        for support in index.module_support.get(file, ()):
            proof[support] = None
            if len(proof) > 256:
                return tuple(proof)
            pending.append(support.file)
    return tuple(proof)


def resolve_rust_type(raw: RawTypeObservation, *, owner: Symbol, index: RustTypeIndex,
                      declarations: Mapping, finish):
    """Fail closed unless one exact occurrence establishes a compatible target."""
    controls = index.controls
    if len(controls) > 256:
        return finish("binding_limit")
    configuration = rust_type_configuration(owner, index)
    if configuration is None:
        return finish("unsupported_configuration", controls=controls)
    if raw.binding_state == "unbound":
        return finish("binding_not_found", controls=controls)
    if raw.binding_state == "local":
        if len(raw.local_bindings) != 1 or len(raw.path) != 1:
            return finish("unsupported_reference", controls=controls)
        binding = raw.local_bindings[0]
        targets = tuple(symbol for symbol in declarations.get(
            (raw.source_file, binding.declaration_start_byte, binding.declaration_end_byte), ()
        ) if symbol.name == binding.name and symbol.kind == binding.kind)
        if len(targets) != 1:
            return finish("ambiguous_target" if targets else "binding_unindexed", controls=controls)
        target = targets[0]
        file_node = index.symbols.get(f"{target.file_path}::__file__#file")
        if file_node is None:
            return finish("binding_unindexed", controls=controls)
        support = (TypeSupport("definition", target.file_path, target.line,
                               file_node.content_hash, target.id),
                   *_module_proof((owner.file_path, target.file_path), index))
        if len(support) + 2 > 256:
            return finish("binding_limit", controls=controls)
        args = dict(extra_support=support, controls=controls, candidate_ids=(target.id,),
                    candidate_universe="lexical_scope", candidate_scope_file=raw.source_file,
                    candidates_complete=True, candidates_truncated=0)
        target_configuration = rust_type_configuration(target, index)
        if target_configuration is None:
            return finish("unsupported_configuration", **args)
        if not _compatible(raw, target):
            return finish("unsupported_target", **args)
        if raw.relation != "uses_type" and owner.id == target.id:
            return finish("self_heritage", **args)
        return finish(None, target=target, basis="lexical_binding",
                      configuration="declared_possible" if "declared_possible" in
                      {configuration, target_configuration} else "unconditional", **args)
    if raw.binding_state != "imported" or len(raw.import_bindings) != 1:
        return finish("unsupported_reference", controls=controls)
    binding = raw.import_bindings[0]
    if not valid_type_import_path("rust", raw.path, binding):
        return finish("unsupported_reference", controls=controls)
    matches = tuple(record for record in index.references.get(
        (raw.source_file, raw.source_hash, raw.start_byte, raw.end_byte, raw.path), ()
    ) if record.binding == binding)
    if len(matches) != 1:
        return finish("binding_ambiguous" if matches else "import_unresolved", controls=controls)
    reference = matches[0]
    support = tuple(dict.fromkeys((
        *(TypeSupport(item.kind, item.file, item.line, item.content_hash,
                      item.endpoint_id) for item in reference.support),
        *_module_proof((owner.file_path, reference.target_file or owner.file_path,
                        *(item.file for item in reference.support)), index),
    )))
    if len(support) + 2 > 256:
        return finish("binding_limit", controls=controls)
    if reference.status != "resolved":
        reason = reference.unresolved_reason
        if reason not in {"target_inaccessible", "ambiguous_target", "target_not_indexed",
                          "unsupported_target", "unsupported_reference", "binding_shadowed"}:
            reason = "import_unresolved"
        return finish(reason, extra_support=support, controls=controls)
    target = index.symbols.get(reference.target_id)
    if target is None or reference.resolution_configuration is None:
        return finish("target_not_indexed", extra_support=support, controls=controls)
    args = dict(extra_support=support, controls=controls, candidate_ids=(target.id,),
                candidate_universe="import_surface", candidate_scope_file=target.file_path,
                candidates_complete=True, candidates_truncated=0)
    # Rust value references may prove only the containing type of an associated
    # path. Such a result cannot prove the named associated type itself.
    if len(raw.path) > 1 and target.name != raw.path[-1]:
        return finish("unsupported_reference", **args)
    if not _compatible(raw, target):
        return finish("unsupported_target", **args)
    if raw.relation != "uses_type" and owner.id == target.id:
        return finish("self_heritage", **args)
    return finish(None, target=target, basis=reference.resolution_basis,
                  configuration="declared_possible" if "declared_possible" in
                  {configuration, reference.resolution_configuration} else "unconditional", **args)
