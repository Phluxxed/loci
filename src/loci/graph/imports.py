from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any, Literal, Mapping, TypeAlias, cast

from loci.parser.imports import ImportUnresolvedReason, RawImport
from loci.parser.symbols import Symbol

from .contracts import (
    GraphContractError,
    GraphEdge,
    GraphEvidence,
    JSONValue,
)
from .go_modules import (
    GoModule,
    GoPackageBinding,
    GoPackageIndex,
    _valid_go_identifier,
)
from .javascript_modules import (
    JavaScriptResolutionBasis,
    JavaScriptResolutionIndex,
    JavaScriptModuleContext,
    build_javascript_resolution_index,
    resolve_javascript_import,
)


ImportStatus: TypeAlias = Literal["resolved", "unresolved"]
ImportTargetKind: TypeAlias = Literal["file", "package"]
_IMPORT_STATUSES = frozenset({"resolved", "unresolved"})
_IMPORT_TARGET_KINDS = frozenset({"file", "package"})
_UNRESOLVED_REASONS = frozenset({
    "external",
    "not_indexed",
    "ambiguous",
    "unsupported_language",
    "invalid_specifier",
    "inaccessible",
    "unsupported_configuration",
})
_RAW_IMPORT_FIELDS = {
    "source_file",
    "language",
    "line",
    "text",
    "specifier",
    "imported_name",
    "type_only",
    "is_reexport",
    "source_hash",
}
_IMPORT_RECORD_FIELDS = {
    "raw",
    "source_id",
    "target_file",
    "target_package",
    "target_kind",
    "target_id",
    "status",
    "unresolved_reason",
    "resolution_basis",
    "resolution_control_files",
}
_SHA256_RE = re.compile(r"[0-9a-f]{64}")
_JAVASCRIPT_LANGUAGES = frozenset({"javascript", "typescript"})
_JAVASCRIPT_EXTENSIONS = (
    ".ts", ".tsx", ".mts", ".cts", ".js", ".jsx", ".mjs", ".cjs",
)
_JAVASCRIPT_RESOLUTION_BASES = frozenset({
    "relative_path",
    "compiler_paths",
    "compiler_base_url",
    "compiler_root_dirs",
    "package_imports",
    "package_self_reference",
    "workspace_exports",
    "workspace_legacy_entry",
})


@dataclass(frozen=True, slots=True)
class ImportRecord:
    raw: RawImport
    source_id: str
    target_file: str | None
    target_package: str | None
    target_kind: ImportTargetKind | None
    target_id: str | None
    status: ImportStatus
    unresolved_reason: ImportUnresolvedReason | None
    resolution_basis: JavaScriptResolutionBasis | None = None
    resolution_control_files: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _validate_raw_import(self.raw)
        _nonempty_string(self.source_id, "source_id")
        if self.target_file is not None:
            _relative_path(self.target_file, "target_file")
        if self.target_package is not None:
            _nonempty_string(self.target_package, "target_package")
        if (
            self.target_kind is not None
            and (
                not isinstance(self.target_kind, str)
                or self.target_kind not in _IMPORT_TARGET_KINDS
            )
        ):
            raise _error("Invalid import target kind", field="target_kind")
        if self.target_id is not None:
            _nonempty_string(self.target_id, "target_id")
        if not isinstance(self.status, str) or self.status not in _IMPORT_STATUSES:
            raise _error("Invalid import status", field="status")
        if (
            self.unresolved_reason is not None
            and (
                not isinstance(self.unresolved_reason, str)
                or self.unresolved_reason not in _UNRESOLVED_REASONS
            )
        ):
            raise _error(
                "Invalid import unresolved reason",
                field="unresolved_reason",
            )
        if self.resolution_basis is not None and (
            not isinstance(self.resolution_basis, str)
            or self.resolution_basis not in _JAVASCRIPT_RESOLUTION_BASES
        ):
            raise _error(
                "Invalid JavaScript resolution basis",
                field="resolution_basis",
            )
        _validate_resolution_controls(self.resolution_control_files)
        is_javascript = self.raw.language in _JAVASCRIPT_LANGUAGES
        if not is_javascript and (
            self.resolution_basis is not None or self.resolution_control_files
        ):
            raise _error(
                "Only JavaScript imports may carry resolution provenance"
            )
        if self.status == "resolved":
            if self.target_kind is None:
                raise _error("Resolved import requires a target kind")
            if self.target_kind == "file":
                if self.target_file is None or self.target_id is None:
                    raise _error("Resolved file import requires a target file and ID")
                if self.target_package is not None:
                    raise _error("Resolved file import cannot have a target package")
                if self.raw.language == "go":
                    raise _error("Go imports must target packages")
            else:
                if self.target_file is not None:
                    raise _error("Resolved package import cannot have a target file")
                if self.target_package is None or self.target_id is None:
                    raise _error(
                        "Resolved package import requires a target package and ID"
                    )
                if self.raw.language != "go":
                    raise _error("Only Go imports may target packages")
            if self.raw.language == "rust":
                raise _error("Rust imports cannot be resolved")
            if self.unresolved_reason is not None:
                raise _error("Resolved import cannot have an unresolved reason")
            if is_javascript and self.resolution_basis is None:
                raise _error("Resolved JavaScript import requires a resolution basis")
        else:
            if any((
                self.target_file is not None,
                self.target_package is not None,
                self.target_kind is not None,
                self.target_id is not None,
            )):
                raise _error("Unresolved import cannot have a target")
            if self.unresolved_reason is None:
                raise _error("Unresolved import requires an unresolved reason")
            if self.resolution_basis is not None:
                raise _error("Unresolved import cannot have a resolution basis")

    def to_dict(self) -> dict[str, JSONValue]:
        return {
            "raw": _raw_import_to_dict(self.raw),
            "source_id": self.source_id,
            "target_file": self.target_file,
            "target_package": self.target_package,
            "target_kind": self.target_kind,
            "target_id": self.target_id,
            "status": self.status,
            "unresolved_reason": self.unresolved_reason,
            "resolution_basis": self.resolution_basis,
            "resolution_control_files": list(self.resolution_control_files),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> ImportRecord:
        _require_keys(value, _IMPORT_RECORD_FIELDS, "import record")
        raw_value = value["raw"]
        if not isinstance(raw_value, Mapping):
            raise _error("Import raw observation must be an object", field="raw")
        target_file = _optional_relative_path(value["target_file"], "target_file")
        target_package = _optional_nonempty_string(
            value["target_package"],
            "target_package",
        )
        target_kind = value["target_kind"]
        if target_kind is not None and (
            not isinstance(target_kind, str)
            or target_kind not in _IMPORT_TARGET_KINDS
        ):
            raise _error("Invalid import target kind", field="target_kind")
        target_id = _optional_nonempty_string(value["target_id"], "target_id")
        status = value["status"]
        if not isinstance(status, str) or status not in _IMPORT_STATUSES:
            raise _error("Invalid import status", field="status")
        unresolved_reason = value["unresolved_reason"]
        if unresolved_reason is not None and (
            not isinstance(unresolved_reason, str)
            or unresolved_reason not in _UNRESOLVED_REASONS
        ):
            raise _error(
                "Invalid import unresolved reason",
                field="unresolved_reason",
            )
        resolution_basis = value["resolution_basis"]
        if resolution_basis is not None and (
            not isinstance(resolution_basis, str)
            or resolution_basis not in _JAVASCRIPT_RESOLUTION_BASES
        ):
            raise _error(
                "Invalid JavaScript resolution basis",
                field="resolution_basis",
            )
        resolution_control_files = _resolution_controls(
            value["resolution_control_files"]
        )
        return cls(
            raw=_raw_import_from_dict(raw_value),
            source_id=_nonempty_string(value["source_id"], "source_id"),
            target_file=target_file,
            target_package=target_package,
            target_kind=cast(ImportTargetKind | None, target_kind),
            target_id=target_id,
            status=cast(ImportStatus, status),
            unresolved_reason=cast(ImportUnresolvedReason | None, unresolved_reason),
            resolution_basis=cast(
                JavaScriptResolutionBasis | None,
                resolution_basis,
            ),
            resolution_control_files=resolution_control_files,
        )


@dataclass(frozen=True, slots=True)
class _GoResolverIndex:
    packages: GoPackageIndex
    modules_by_root: Mapping[str, tuple[GoModule, ...]]
    modules_by_path: Mapping[str, tuple[GoModule, ...]]
    bindings_by_source_module: Mapping[
        str,
        Mapping[str, tuple[GoPackageBinding, ...]],
    ]


def resolve_import(
    raw: RawImport,
    *,
    file_nodes: Mapping[str, Symbol],
    go_packages: GoPackageIndex | None = None,
    javascript_modules: JavaScriptResolutionIndex | None = None,
) -> ImportRecord:
    """Resolve one raw import against deterministic indexed file/package targets."""
    return resolve_imports(
        (raw,),
        file_nodes=file_nodes,
        go_packages=go_packages,
        javascript_modules=javascript_modules,
    )[0]


def resolve_imports(
    raw_imports: Sequence[RawImport],
    *,
    file_nodes: Mapping[str, Symbol],
    go_packages: GoPackageIndex | None = None,
    javascript_modules: JavaScriptResolutionIndex | None = None,
) -> list[ImportRecord]:
    """Resolve a batch while deriving indexed language layouts only once."""
    indexed_python_files = _indexed_python_files(file_nodes)
    python_package_roots = _python_package_roots(indexed_python_files)
    javascript_resolver = javascript_modules or build_javascript_resolution_index(
        JavaScriptModuleContext((), (), ()),
        file_nodes=file_nodes,
    ).index
    go_resolver = (
        _build_go_resolver_index(go_packages)
        if go_packages is not None
        else None
    )
    return [
        _resolve_import(
            raw,
            file_nodes=file_nodes,
            indexed_python_files=indexed_python_files,
            python_package_roots=python_package_roots,
            javascript_modules=javascript_resolver,
            go_resolver=go_resolver,
        )
        for raw in raw_imports
    ]


def _resolve_import(
    raw: RawImport,
    *,
    file_nodes: Mapping[str, Symbol],
    indexed_python_files: frozenset[str],
    python_package_roots: tuple[PurePosixPath, ...],
    javascript_modules: JavaScriptResolutionIndex,
    go_resolver: _GoResolverIndex | None,
) -> ImportRecord:
    _validate_raw_import(raw)
    source = _require_file_node(file_nodes, raw.source_file, field="source_file")
    if raw.language == "python":
        target_file, unresolved_reason = _resolve_python_target(
            raw,
            indexed_python_files,
            python_package_roots,
        )
    elif raw.language in _JAVASCRIPT_LANGUAGES:
        resolution = resolve_javascript_import(raw, javascript_modules)
        if resolution.target_file is None:
            assert resolution.unresolved_reason is not None
            return _unresolved(
                raw,
                source.id,
                resolution.unresolved_reason,
                resolution_control_files=resolution.control_files,
            )
        target = _require_file_node(
            file_nodes,
            resolution.target_file,
            field="target_file",
        )
        return ImportRecord(
            raw=raw,
            source_id=source.id,
            target_file=resolution.target_file,
            target_package=None,
            target_kind="file",
            target_id=target.id,
            status="resolved",
            unresolved_reason=None,
            resolution_basis=resolution.basis,
            resolution_control_files=resolution.control_files,
        )
    elif raw.language == "go":
        if go_resolver is None:
            return _unresolved(raw, source.id, "unsupported_language")
        target_package, unresolved_reason = _resolve_go_target(
            raw,
            go_resolver,
        )
        if target_package is None:
            return _unresolved(raw, source.id, unresolved_reason)
        return ImportRecord(
            raw=raw,
            source_id=source.id,
            target_file=None,
            target_package=target_package.qualified_name,
            target_kind="package",
            target_id=target_package.id,
            status="resolved",
            unresolved_reason=None,
        )
    else:
        return _unresolved(raw, source.id, "unsupported_language")
    if target_file is None:
        return _unresolved(raw, source.id, unresolved_reason)

    target = _require_file_node(file_nodes, target_file, field="target_file")
    return ImportRecord(
        raw=raw,
        source_id=source.id,
        target_file=target_file,
        target_package=None,
        target_kind="file",
        target_id=target.id,
        status="resolved",
        unresolved_reason=None,
    )


def materialize_import_edges(
    records: Sequence[ImportRecord],
    *,
    file_nodes: Mapping[str, Symbol],
    go_packages: GoPackageIndex | None = None,
) -> list[GraphEdge]:
    """Build one deterministic evidence-backed edge per resolved dependency."""
    edges: dict[tuple[str, str, str, str], GraphEdge] = {}
    evidence_ranks: dict[tuple[str, str, str, str], tuple[int, str, str, str]] = {}
    package_nodes = {
        node.id: node
        for node in (go_packages.package_nodes if go_packages is not None else ())
    }

    for record in records:
        source = _require_file_node(
            file_nodes,
            record.raw.source_file,
            field="source_file",
        )
        if source.id != record.source_id:
            raise _error(
                "Import record source does not match its file node",
                field="source_id",
                source_id=record.source_id,
            )
        if record.status != "resolved":
            continue
        if record.target_id is None:
            raise _error("Resolved import requires a target ID")
        if record.target_kind == "file":
            if record.target_file is None:
                raise _error("Resolved file import requires a target file")
            target = _require_file_node(
                file_nodes,
                record.target_file,
                field="target_file",
            )
            if target.id != record.target_id:
                raise _error(
                    "Import record target does not match its file node",
                    field="target_id",
                    target_id=record.target_id,
                )
        elif record.target_kind == "package":
            if record.raw.type_only:
                raise _error(
                    "Go package imports cannot be type-only",
                    field="target_id",
                    target_id=record.target_id,
                )
            if record.target_package is None:
                raise _error("Resolved package import requires a target package")
            target = package_nodes.get(record.target_id)
            if target is None:
                raise _error(
                    "Import record target is not present in the Go package index",
                    field="target_id",
                    target_id=record.target_id,
                )
            _validate_go_package_target(target, record.target_package)
        else:
            raise _error("Resolved import requires a supported target kind")
        if source.id == target.id:
            continue

        edge_type = "imports_type" if record.raw.type_only else "imports"
        edge = GraphEdge(
            from_id=source.id,
            to_id=target.id,
            type=edge_type,
            directed=True,
            namespace="loci",
            resolution="import-resolved",
            evidence=GraphEvidence(
                file=record.raw.source_file,
                line=record.raw.line,
                content_hash=record.raw.source_hash,
            ),
        )
        key = (edge.namespace, edge.type, edge.from_id, edge.to_id)
        rank = (
            record.raw.line,
            record.raw.text,
            record.raw.specifier,
            record.raw.imported_name or "",
        )
        if key not in evidence_ranks or rank < evidence_ranks[key]:
            edges[key] = edge
            evidence_ranks[key] = rank

    return [edges[key] for key in sorted(edges)]


def _resolve_python_target(
    raw: RawImport,
    indexed_files: frozenset[str],
    package_roots: tuple[PurePosixPath, ...],
) -> tuple[str | None, ImportUnresolvedReason]:
    imported_name = raw.imported_name
    if imported_name is not None and not imported_name.isidentifier():
        return None, "invalid_specifier"

    specifier = raw.specifier
    if specifier.startswith("."):
        base = _relative_python_base(raw.source_file, specifier)
        if base is None:
            return None, "invalid_specifier"
        bases = (base,)
    else:
        parts = _dotted_parts(specifier)
        if parts is None:
            return None, "invalid_specifier"
        bases = tuple(
            root.joinpath(*parts)
            for root in package_roots
        )

    targets = {
        target
        for base in bases
        if (target := _resolve_python_base(base, imported_name, indexed_files))
        is not None
    }
    if not targets:
        return None, "not_indexed"
    if len(targets) > 1:
        return None, "ambiguous"
    return targets.pop(), "not_indexed"


def _indexed_python_files(file_nodes: Mapping[str, Symbol]) -> frozenset[str]:
    return frozenset(
        path
        for path, node in file_nodes.items()
        if (
            path == node.file_path
            and node.kind == "file"
            and node.language == "python"
            and path.endswith(".py")
        )
    )


def _indexed_javascript_files(file_nodes: Mapping[str, Symbol]) -> frozenset[str]:
    return frozenset(
        path
        for path, node in file_nodes.items()
        if (
            path == node.file_path
            and node.kind == "file"
            and node.language in _JAVASCRIPT_LANGUAGES
            and path.endswith(_JAVASCRIPT_EXTENSIONS)
        )
    )


def _resolve_javascript_target(
    raw: RawImport,
    indexed_files: frozenset[str],
) -> tuple[str | None, ImportUnresolvedReason]:
    specifier = raw.specifier
    if not specifier or "\\" in specifier or specifier.startswith("/"):
        return None, "invalid_specifier"
    if not specifier.startswith(("./", "../")):
        return None, "external"

    base = _relative_javascript_base(raw.source_file, specifier)
    if base is None:
        return None, "invalid_specifier"

    base_path = base.as_posix()
    candidates = (
        f"{base_path}.ts",
        f"{base_path}.tsx",
        f"{base_path}.js",
        (base / "index.ts").as_posix(),
        (base / "index.tsx").as_posix(),
        (base / "index.js").as_posix(),
    )
    target = next(
        (candidate for candidate in candidates if candidate in indexed_files),
        None,
    )
    if target is None:
        return None, "not_indexed"
    return target, "not_indexed"


def _resolve_go_target(
    raw: RawImport,
    resolver: _GoResolverIndex,
) -> tuple[Symbol | None, ImportUnresolvedReason]:
    specifier = raw.specifier
    if not _valid_go_import_specifier(specifier):
        return None, "invalid_specifier"
    if specifier == "C":
        return None, "external"

    source_module = _go_source_module(raw.source_file, resolver.modules_by_root)
    if source_module is None:
        return None, "external"
    # Go package paths are a module prefix joined with the package subdirectory.
    # Source: https://go.dev/ref/mod
    bindings_by_prefix = resolver.bindings_by_source_module.get(
        source_module.root,
        {},
    )
    longest = next(
        (
            bindings_by_prefix[prefix]
            for prefix in _go_import_prefixes(specifier)
            if prefix in bindings_by_prefix
        ),
        (),
    )
    if not longest:
        return None, "external"

    if _more_specific_go_module_is_ineligible(
        specifier,
        longest,
        resolver.modules_by_path,
    ):
        return None, "external"
    candidates = tuple(
        (
            binding,
            _go_binding_directory(binding, specifier),
            resolver.packages.packages_by_binding.get(
                (binding.module_root, specifier)
            ),
        )
        for binding in longest
    )
    if len({directory for _, directory, _ in candidates}) > 1:
        return None, "ambiguous"
    target_ids = {target.id for _, _, target in candidates if target is not None}
    if len(target_ids) > 1:
        return None, "ambiguous"

    binding, _, target = candidates[0]
    key = (binding.module_root, specifier)
    if key in resolver.packages.command_packages:
        return None, "inaccessible"
    if target is None:
        return None, "not_indexed"
    _validate_go_package_target(target, specifier)
    if not _go_internal_import_allowed(raw.source_file, source_module, specifier):
        return None, "inaccessible"
    return target, "not_indexed"


def _valid_go_import_specifier(specifier: str) -> bool:
    if (
        not specifier
        or "\\" in specifier
        or specifier.startswith(("./", "../"))
        or any(
            ord(character) < 32 or ord(character) == 127
            for character in specifier
        )
    ):
        return False
    path = PurePosixPath(specifier)
    parts = specifier.split("/")
    return (
        not path.is_absolute()
        and path.as_posix() == specifier
        and all(part not in {"", ".", ".."} for part in parts)
    )


def _go_source_module(
    source_file: str,
    modules_by_root: Mapping[str, tuple[GoModule, ...]],
) -> GoModule | None:
    directory = PurePosixPath(source_file).parent.as_posix()
    while True:
        owners = modules_by_root.get(directory, ())
        if owners:
            if len({module.module_path for module in owners}) != 1:
                return None
            return min(owners, key=lambda module: module.source)
        if directory == ".":
            return None
        directory = PurePosixPath(directory).parent.as_posix()


def _more_specific_go_module_is_ineligible(
    specifier: str,
    eligible_bindings: Sequence[GoPackageBinding],
    modules_by_path: Mapping[str, tuple[GoModule, ...]],
) -> bool:
    eligible_prefix_length = len(eligible_bindings[0].import_prefix)
    for prefix in _go_import_prefixes(specifier):
        if len(prefix) <= eligible_prefix_length:
            return False
        for module in modules_by_path.get(prefix, ()):
            for binding in eligible_bindings:
                relative = _relative_directory(module.root, binding.module_root)
                if relative not in {None, ""}:
                    return True
    return False


def _go_binding_directory(binding: GoPackageBinding, specifier: str) -> str:
    suffix = specifier[len(binding.import_prefix):].removeprefix("/")
    if not suffix:
        return binding.module_root
    return (PurePosixPath(binding.module_root) / suffix).as_posix()


def _go_import_prefixes(specifier: str) -> tuple[str, ...]:
    parts = specifier.split("/")
    return tuple(
        "/".join(parts[:end])
        for end in range(len(parts), 0, -1)
    )


def _build_go_resolver_index(go_packages: GoPackageIndex) -> _GoResolverIndex:
    modules_by_root: dict[str, list[GoModule]] = {}
    modules_by_path: dict[str, list[GoModule]] = {}
    for module in go_packages.modules:
        modules_by_root.setdefault(module.root, []).append(module)
        modules_by_path.setdefault(module.module_path, []).append(module)

    bindings_by_source: dict[
        str,
        dict[str, tuple[GoPackageBinding, ...]],
    ] = {}
    for source_root, bindings in go_packages.bindings_by_source_module.items():
        grouped: dict[str, list[GoPackageBinding]] = {}
        for binding in bindings:
            grouped.setdefault(binding.import_prefix, []).append(binding)
        bindings_by_source[source_root] = {
            prefix: tuple(matches)
            for prefix, matches in grouped.items()
        }

    return _GoResolverIndex(
        packages=go_packages,
        modules_by_root={
            root: tuple(modules)
            for root, modules in modules_by_root.items()
        },
        modules_by_path={
            path: tuple(modules)
            for path, modules in modules_by_path.items()
        },
        bindings_by_source_module=bindings_by_source,
    )


def _go_internal_import_allowed(
    source_file: str,
    source_module: GoModule,
    target_import_path: str,
) -> bool:
    target_parts = target_import_path.split("/")
    internal_positions = [
        index for index, part in enumerate(target_parts) if part == "internal"
    ]
    if not internal_positions:
        return True

    # Go limits internal packages to importers beneath the parent import path.
    # Source: https://go.dev/cmd/go/#hdr-Internal_Directories
    parent_prefix = "/".join(target_parts[:internal_positions[-1]])
    importer_directory = PurePosixPath(source_file).parent.as_posix()
    relative = _relative_directory(importer_directory, source_module.root)
    if relative is None:
        return False
    importer_path = source_module.module_path
    if relative:
        importer_path = f"{importer_path}/{relative}"
    return (
        not parent_prefix
        or importer_path == parent_prefix
        or importer_path.startswith(f"{parent_prefix}/")
    )


def _validate_go_package_target(target: Symbol, import_path: str) -> None:
    loci = target.metadata.get("loci")
    package_name = loci.get("package_name") if isinstance(loci, Mapping) else None
    if (
        target.kind != "package"
        or target.language != "go"
        or target.qualified_name != import_path
        or not isinstance(loci, Mapping)
        or loci.get("go_package_node") is not True
        or loci.get("import_path") != import_path
        or not isinstance(package_name, str)
        or target.name != package_name
        or package_name == "main"
        or not _valid_go_identifier(package_name)
    ):
        raise _error(
            "Go package index target is invalid",
            field="target_id",
            target_id=target.id,
        )


def _relative_directory(directory: str, root: str) -> str | None:
    if root == ".":
        return "" if directory == "." else directory
    try:
        relative = PurePosixPath(directory).relative_to(PurePosixPath(root))
    except ValueError:
        return None
    return "" if relative == PurePosixPath(".") else relative.as_posix()


def _relative_javascript_base(
    source_file: str,
    specifier: str,
) -> PurePosixPath | None:
    parts = [*PurePosixPath(source_file).parent.parts]
    for part in specifier.split("/"):
        if part in {"", "."}:
            continue
        if part == "..":
            if not parts:
                return None
            parts.pop()
        else:
            parts.append(part)
    if not parts:
        return None
    return PurePosixPath(*parts)


def _python_package_roots(indexed_files: frozenset[str]) -> tuple[PurePosixPath, ...]:
    package_dirs = {
        PurePosixPath(path).parent
        for path in indexed_files
        if PurePosixPath(path).name == "__init__.py"
    }
    roots = {PurePosixPath(".")}
    roots.update(
        directory.parent
        for directory in package_dirs
        if directory.parent not in package_dirs
    )
    return tuple(sorted(roots, key=lambda path: path.as_posix()))


def _relative_python_base(
    source_file: str,
    specifier: str,
) -> PurePosixPath | None:
    dot_count = len(specifier) - len(specifier.lstrip("."))
    remainder = specifier[dot_count:]
    parts = _dotted_parts(remainder, allow_empty=True)
    if parts is None:
        return None

    base = PurePosixPath(source_file).parent
    for _ in range(dot_count - 1):
        if base == PurePosixPath("."):
            return None
        base = base.parent
    return base.joinpath(*parts)


def _dotted_parts(
    value: str,
    *,
    allow_empty: bool = False,
) -> tuple[str, ...] | None:
    if not value:
        return () if allow_empty else None
    parts = tuple(value.split("."))
    if any(not part or not part.isidentifier() for part in parts):
        return None
    return parts


def _resolve_python_base(
    base: PurePosixPath,
    imported_name: str | None,
    indexed_files: frozenset[str],
) -> str | None:
    if imported_name is not None:
        submodule = _indexed_python_module(base / imported_name, indexed_files)
        if submodule is not None:
            return submodule
    return _indexed_python_module(base, indexed_files)


def _indexed_python_module(
    base: PurePosixPath,
    indexed_files: frozenset[str],
) -> str | None:
    candidates: list[str] = []
    if base != PurePosixPath("."):
        candidates.append(f"{base.as_posix()}.py")
    candidates.append((base / "__init__.py").as_posix())
    return next(
        (candidate for candidate in candidates if candidate in indexed_files),
        None,
    )


def _unresolved(
    raw: RawImport,
    source_id: str,
    reason: ImportUnresolvedReason,
    *,
    resolution_control_files: tuple[str, ...] = (),
) -> ImportRecord:
    return ImportRecord(
        raw=raw,
        source_id=source_id,
        target_file=None,
        target_package=None,
        target_kind=None,
        target_id=None,
        status="unresolved",
        unresolved_reason=reason,
        resolution_control_files=resolution_control_files,
    )


def _resolution_controls(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise _error(
            "JavaScript resolution control files must be an array",
            field="resolution_control_files",
        )
    controls = tuple(
        _relative_path(item, "resolution_control_files") for item in value
    )
    _validate_resolution_controls(controls)
    return controls


def _validate_resolution_controls(controls: tuple[str, ...]) -> None:
    if not isinstance(controls, tuple):
        raise _error(
            "JavaScript resolution control files must be a tuple",
            field="resolution_control_files",
        )
    for control in controls:
        _relative_path(control, "resolution_control_files")
    if controls != tuple(sorted(set(controls))):
        raise _error(
            "JavaScript resolution control files must be unique and sorted",
            field="resolution_control_files",
        )


def _require_file_node(
    file_nodes: Mapping[str, Symbol],
    path: str,
    *,
    field: str,
) -> Symbol:
    node = file_nodes.get(path)
    if node is None or node.kind != "file" or node.file_path != path:
        raise _error(
            "Import path does not identify an indexed file node",
            field=field,
            path=path,
        )
    return node


def _raw_import_to_dict(raw: RawImport) -> dict[str, JSONValue]:
    return {
        "source_file": raw.source_file,
        "language": raw.language,
        "line": raw.line,
        "text": raw.text,
        "specifier": raw.specifier,
        "imported_name": raw.imported_name,
        "type_only": raw.type_only,
        "is_reexport": raw.is_reexport,
        "source_hash": raw.source_hash,
    }


def _raw_import_from_dict(value: Mapping[str, Any]) -> RawImport:
    _require_keys(value, _RAW_IMPORT_FIELDS, "raw import")
    imported_name = value["imported_name"]
    if imported_name is not None:
        imported_name = _nonempty_string(imported_name, "imported_name")
    type_only = _boolean(value["type_only"], "type_only")
    is_reexport = _boolean(value["is_reexport"], "is_reexport")
    line = value["line"]
    if isinstance(line, bool) or not isinstance(line, int) or line < 1:
        raise _error("Import line must be a positive integer", field="line")
    raw = RawImport(
        source_file=_relative_path(value["source_file"], "source_file"),
        language=_nonempty_string(value["language"], "language"),
        line=line,
        text=_nonempty_string(value["text"], "text"),
        specifier=_string(value["specifier"], "specifier"),
        imported_name=imported_name,
        type_only=type_only,
        is_reexport=is_reexport,
        source_hash=_sha256(value["source_hash"], "source_hash"),
    )
    _validate_raw_import(raw)
    return raw


def _validate_raw_import(raw: RawImport) -> None:
    if not isinstance(raw, RawImport):
        raise _error("Import raw observation must be a RawImport", field="raw")
    _relative_path(raw.source_file, "source_file")
    _nonempty_string(raw.language, "language")
    if isinstance(raw.line, bool) or not isinstance(raw.line, int) or raw.line < 1:
        raise _error("Import line must be a positive integer", field="line")
    _nonempty_string(raw.text, "text")
    _string(raw.specifier, "specifier")
    if raw.imported_name is not None:
        _nonempty_string(raw.imported_name, "imported_name")
    _boolean(raw.type_only, "type_only")
    _boolean(raw.is_reexport, "is_reexport")
    _sha256(raw.source_hash, "source_hash")


def _require_keys(value: Mapping[str, Any], expected: set[str], record: str) -> None:
    actual = set(value)
    if actual != expected:
        raise _error(
            f"Invalid graph {record} fields",
            record=record,
            missing=sorted(expected - actual),
            unknown=sorted(actual - expected),
        )


def _relative_path(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value or "\\" in value:
        raise _error(f"Import {field} must be a relative path", field=field)
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or path.as_posix() != value:
        raise _error(f"Import {field} must be a relative path", field=field)
    return value


def _optional_relative_path(value: Any, field: str) -> str | None:
    return None if value is None else _relative_path(value, field)


def _nonempty_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise _error(f"Import {field} must be a non-empty string", field=field)
    return value


def _optional_nonempty_string(value: Any, field: str) -> str | None:
    return None if value is None else _nonempty_string(value, field)


def _string(value: Any, field: str) -> str:
    if not isinstance(value, str):
        raise _error(f"Import {field} must be a string", field=field)
    return value


def _boolean(value: Any, field: str) -> bool:
    if not isinstance(value, bool):
        raise _error(f"Import {field} must be a boolean", field=field)
    return value


def _sha256(value: Any, field: str) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise _error(f"Import {field} must be a SHA-256 hash", field=field)
    return value


def _error(message: str, **details: Any) -> GraphContractError:
    return GraphContractError(
        "INVALID_GRAPH_SCHEMA",
        message,
        cast(dict[str, JSONValue], details),
    )
