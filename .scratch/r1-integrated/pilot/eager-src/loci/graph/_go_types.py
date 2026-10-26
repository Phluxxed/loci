"""Go declared types in a contained package, without method-set inference.

Import records own module/workspace routing. This index supplies the separate
package declaration universe (including unexported names) and its source proof.
It is reconstructed from indexed symbols during graph validation and replay.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Callable, Mapping, Sequence
import unicodedata

from loci.parser.reference_models import ImportBinding
from loci.parser.symbols import Symbol
from loci.parser.type_models import RawTypeObservation

from .imports import ImportRecord
from .type_models import MAX_TYPE_CANDIDATES, MAX_TYPE_SUPPORT_RECORDS, TypeControl, TypeRelationRecord, TypeSupport


def _metadata(symbol: Symbol) -> Mapping:
    value = symbol.metadata.get("loci", {})
    return value if isinstance(value, Mapping) else {}


@dataclass(frozen=True)
class GoTypeIndex:
    files: Mapping[str, Symbol]
    packages: Mapping[str, Symbol]
    directory_files: Mapping[str, tuple[Symbol, ...]]
    declarations: Mapping[tuple[str, str], tuple[Symbol, ...]]
    controls: tuple[TypeControl, ...]


def build_go_type_index(symbols: Sequence[Symbol], input_hashes: Mapping[str, str]) -> GoTypeIndex:
    files = {s.file_path: s for s in symbols if s.language == "go" and s.kind == "file"}
    directories = defaultdict(list)
    declarations = defaultdict(list)
    for file, symbol in sorted(files.items()):
        path = PurePosixPath(file)
        if path.name.endswith("_test.go") or "vendor" in path.parts:
            continue
        directories[path.parent.as_posix()].append(symbol)
    for symbol in symbols:
        if symbol.language == "go" and _metadata(symbol).get("go_package_level") is True:
            path = PurePosixPath(symbol.file_path)
            if not path.name.endswith("_test.go") and "vendor" not in path.parts:
                declarations[(path.parent.as_posix(), symbol.name)].append(symbol)
    return GoTypeIndex(
        files=files,
        packages={s.id: s for s in symbols if s.language == "go" and s.kind == "package"},
        directory_files={key: tuple(value) for key, value in directories.items()},
        declarations={key: tuple(sorted(value, key=lambda s: s.id)) for key, value in declarations.items()},
        # Conservative complete resolver-input evidence. No ambient module cache
        # or Go toolchain participates, and every control is freshness checked.
        controls=tuple(TypeControl(file, digest) for file, digest in sorted(input_hashes.items())
                       if PurePosixPath(file).name in {"go.mod", "go.work"}),
    )


def _package_proof(directory: str, index: GoTypeIndex, expected_name: str | None = None) -> tuple[TypeSupport, ...] | None:
    files = index.directory_files.get(directory, ())
    names = set()
    support = []
    for file in files:
        clause = _metadata(file).get("go_package")
        if not isinstance(clause, Mapping) or not isinstance(clause.get("name"), str):
            return None
        line = clause.get("line")
        if type(line) is not int or line < 1:
            return None
        names.add(clause["name"])
        support.append(TypeSupport("package_clause", file.file_path, line, file.content_hash))
    if len(names) != 1 or (expected_name is not None and names != {expected_name}):
        return None
    return tuple(support)


def resolve_go_type(raw: RawTypeObservation, *, owner: Symbol, index: GoTypeIndex,
                    imports: Mapping[tuple[str, ImportBinding], tuple[ImportRecord, ...]],
                    finish: Callable[..., TypeRelationRecord]) -> TypeRelationRecord:
    """Return a shared record using the caller's validated owner/lexical seam."""
    if len(index.controls) > MAX_TYPE_SUPPORT_RECORDS:
        return finish("binding_limit")
    if _metadata(owner).get("go_type_configuration") != "unconditional":
        return finish("unsupported_configuration", controls=index.controls)
    source_directory = PurePosixPath(raw.source_file).parent.as_posix()
    source_proof = _package_proof(source_directory, index)
    if source_proof is None:
        return finish("binding_ambiguous", controls=index.controls)
    if len(source_proof) + 4 > MAX_TYPE_SUPPORT_RECORDS:
        return finish("binding_limit", controls=index.controls)
    extra = list(source_proof)
    if raw.binding_state == "package":
        directory = source_directory
        scope = raw.source_file
        universe, basis = "package_scope", "package_binding"
    elif raw.binding_state in {"imported", "deferred"}:
        if len(raw.path) != 2:
            return finish("unsupported_reference", controls=index.controls)
        candidates = []
        for binding in raw.import_bindings:
            records = imports.get((raw.source_file, binding), ())
            for record in records:
                package = index.packages.get(record.target_id)
                if binding.kind != "namespace":
                    continue
                if raw.binding_state == "deferred" and (
                    package is None or _metadata(package).get("package_name") != raw.path[0]
                ):
                    continue
                candidates.append((binding, record, package))
        if len(candidates) != 1:
            return finish("binding_ambiguous" if candidates else "import_unresolved",
                          extra_support=extra, controls=index.controls)
        binding, imported, package = candidates[0]
        extra.append(TypeSupport("import_binding", raw.source_file, binding.import_line,
                                 raw.source_hash, imported.target_id))
        if imported.status != "resolved" or imported.target_kind != "package" or package is None:
            return finish("import_unresolved", extra_support=extra, controls=index.controls)
        metadata = _metadata(package)
        directory = metadata.get("directory")
        # Replayed package metadata cannot redirect an otherwise valid import
        # endpoint into a different directory with the same package name.
        if directory != PurePosixPath(package.file_path).parent.as_posix():
            return finish("import_unresolved", extra_support=extra, controls=index.controls)
        proof = _package_proof(directory, index, metadata.get("package_name"))
        if proof is None:
            return finish("binding_ambiguous", extra_support=extra, controls=index.controls)
        if len(extra) + len(proof) + 4 > MAX_TYPE_SUPPORT_RECORDS:
            return finish("binding_limit", controls=index.controls)
        extra.extend(proof)
        scope = package.file_path
        universe, basis = "import_surface", "qualified_member"
        if not raw.path[-1] or unicodedata.category(raw.path[-1][0]) != "Lu":
            return finish("unsupported_target", extra_support=extra, controls=index.controls)
    else:
        return finish("unsupported_reference", controls=index.controls)
    targets = index.declarations.get((directory, raw.path[-1]), ())
    args = dict(extra_support=extra, controls=index.controls,
                candidate_ids=tuple(s.id for s in targets[:MAX_TYPE_CANDIDATES]),
                candidate_universe=universe, candidate_scope_file=scope,
                candidates_complete=len(targets) <= MAX_TYPE_CANDIDATES, candidates_truncated=max(0, len(targets) - MAX_TYPE_CANDIDATES))
    if any(_metadata(s).get("go_type_configuration") != "unconditional" for s in targets):
        return finish("unsupported_configuration", **args)
    if len(targets) != 1:
        return finish("ambiguous_target" if targets else "target_not_indexed", **args)
    target = targets[0]
    if target.kind != "type":
        return finish("unsupported_target", **args)
    if raw.relation == "embeds" and owner.id == target.id:
        return finish("self_heritage", **args)
    target_file = index.files.get(target.file_path)
    if target_file is None:
        return finish("target_not_indexed", **args)
    extra.append(TypeSupport("definition", target.file_path, target.line,
                             target_file.content_hash, target.id))
    return finish(None, target=target, basis=basis, **args)
