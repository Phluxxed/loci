from __future__ import annotations

import re
from bisect import bisect_right
from dataclasses import dataclass
from pathlib import PurePosixPath
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Literal, Mapping, Sequence, TypeAlias, cast

from loci.parser.imports import ImportUnresolvedReason
from loci.parser.reference_models import ImportBinding, RawLocalExport, RawSymbolReference
from loci.parser.symbols import Symbol

from .contracts import GraphContractError, JSONValue
from .go_modules import GoPackageIndex
from .imports import ImportRecord
from .rust_crates import RustCrateIndex, RustResolutionConfiguration

if TYPE_CHECKING:
    from ._go_references import GoReferenceIndex
    from ._javascript_references import JavaScriptReferenceIndex
    from ._python_references import PythonReferenceIndex


MAX_REFERENCE_REEXPORT_PASSES = 128
MAX_REFERENCE_SUPPORT_RECORDS = 256

ReferenceStatus: TypeAlias = Literal["resolved", "unresolved"]
ReferenceUnresolvedReason: TypeAlias = Literal[
    "import_unresolved",
    "binding_shadowed",
    "ambiguous_binding",
    "ambiguous_source",
    "target_not_indexed",
    "target_inaccessible",
    "ambiguous_target",
    "unsupported_reference",
    "configuration_divergent",
]
ReferenceResolutionBasis: TypeAlias = Literal[
    "direct_binding",
    "qualified_member",
    "reexport_chain",
]
ReferenceSupportKind: TypeAlias = Literal[
    "import_binding",
    "local_export",
    "reexport",
    "definition",
]

_REFERENCE_STATUSES = frozenset({"resolved", "unresolved"})
_REFERENCE_UNRESOLVED_REASONS = frozenset({
    "import_unresolved",
    "binding_shadowed",
    "ambiguous_binding",
    "ambiguous_source",
    "target_not_indexed",
    "target_inaccessible",
    "ambiguous_target",
    "unsupported_reference",
    "configuration_divergent",
})
_REFERENCE_RESOLUTION_BASES = frozenset({
    "direct_binding",
    "qualified_member",
    "reexport_chain",
})
_REFERENCE_SUPPORT_KINDS = frozenset({
    "import_binding",
    "local_export",
    "reexport",
    "definition",
})
_IMPORT_UNRESOLVED_REASONS = frozenset({
    "external",
    "not_indexed",
    "ambiguous",
    "unsupported_language",
    "invalid_specifier",
    "inaccessible",
    "unsupported_configuration",
})
_RUST_RESOLUTION_CONFIGURATIONS = frozenset({
    "unconditional",
    "declared_possible",
})
_REFERENCE_SUPPORT_FIELDS = {
    "kind",
    "file",
    "line",
    "content_hash",
    "endpoint_id",
}
_SYMBOL_REFERENCE_RECORD_FIELDS = {
    "raw",
    "binding",
    "source_id",
    "source_kind",
    "import_source_id",
    "import_target_id",
    "target_file",
    "target_id",
    "target_kind",
    "status",
    "unresolved_reason",
    "import_unresolved_reason",
    "resolution_basis",
    "support",
    "resolution_control_files",
    "resolution_configuration",
}
_SHA256_RE = re.compile(r"[0-9a-f]{64}")


@dataclass(frozen=True, slots=True)
class ReferenceSupport:
    kind: ReferenceSupportKind
    file: str
    line: int
    content_hash: str
    endpoint_id: str

    def __post_init__(self) -> None:
        if not isinstance(self.kind, str) or self.kind not in _REFERENCE_SUPPORT_KINDS:
            raise _error("Invalid reference support kind", field="kind")
        _relative_path(self.file, "file")
        _positive_integer(self.line, "line")
        _sha256(self.content_hash, "content_hash")
        _nonempty_string(self.endpoint_id, "endpoint_id")

    def to_dict(self) -> dict[str, JSONValue]:
        return {
            "kind": self.kind,
            "file": self.file,
            "line": self.line,
            "content_hash": self.content_hash,
            "endpoint_id": self.endpoint_id,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> ReferenceSupport:
        _require_keys(value, _REFERENCE_SUPPORT_FIELDS, "reference support")
        kind = value["kind"]
        if not isinstance(kind, str) or kind not in _REFERENCE_SUPPORT_KINDS:
            raise _error("Invalid reference support kind", field="kind")
        return cls(
            kind=cast(ReferenceSupportKind, kind),
            file=_relative_path(value["file"], "file"),
            line=_positive_integer(value["line"], "line"),
            content_hash=_sha256(value["content_hash"], "content_hash"),
            endpoint_id=_nonempty_string(value["endpoint_id"], "endpoint_id"),
        )


@dataclass(frozen=True, slots=True)
class SymbolReferenceRecord:
    raw: RawSymbolReference
    binding: ImportBinding | None
    source_id: str
    source_kind: str
    import_source_id: str
    import_target_id: str | None
    target_file: str | None
    target_id: str | None
    target_kind: str | None
    status: ReferenceStatus
    unresolved_reason: ReferenceUnresolvedReason | None
    import_unresolved_reason: ImportUnresolvedReason | None
    resolution_basis: ReferenceResolutionBasis | None
    support: tuple[ReferenceSupport, ...]
    resolution_control_files: tuple[str, ...]
    resolution_configuration: RustResolutionConfiguration | None

    def __post_init__(self) -> None:
        if not isinstance(self.raw, RawSymbolReference):
            raise _error("Reference raw observation must be a RawSymbolReference")
        if self.binding is not None:
            if not isinstance(self.binding, ImportBinding):
                raise _error("Reference binding must be an ImportBinding")
            if self.binding not in self.raw.candidate_bindings:
                raise _error("Reference binding is not a raw candidate", field="binding")
        _nonempty_string(self.source_id, "source_id")
        _nonempty_string(self.source_kind, "source_kind")
        expected_import_source = f"{self.raw.source_file}::__file__#file"
        if self.import_source_id != expected_import_source:
            raise _error(
                "Reference import source must be the source file node",
                field="import_source_id",
            )
        if self.source_kind == "file" and self.source_id != self.import_source_id:
            raise _error("File-owned reference source identity is inconsistent")
        _optional_nonempty_string(self.import_target_id, "import_target_id")
        if self.target_file is not None:
            _relative_path(self.target_file, "target_file")
        _optional_nonempty_string(self.target_id, "target_id")
        _optional_nonempty_string(self.target_kind, "target_kind")
        if not isinstance(self.status, str) or self.status not in _REFERENCE_STATUSES:
            raise _error("Invalid reference status", field="status")
        if self.unresolved_reason is not None and (
            not isinstance(self.unresolved_reason, str)
            or self.unresolved_reason not in _REFERENCE_UNRESOLVED_REASONS
        ):
            raise _error("Invalid reference unresolved reason", field="unresolved_reason")
        if self.import_unresolved_reason is not None and (
            not isinstance(self.import_unresolved_reason, str)
            or self.import_unresolved_reason not in _IMPORT_UNRESOLVED_REASONS
        ):
            raise _error(
                "Invalid underlying import unresolved reason",
                field="import_unresolved_reason",
            )
        if self.resolution_basis is not None and (
            not isinstance(self.resolution_basis, str)
            or self.resolution_basis not in _REFERENCE_RESOLUTION_BASES
        ):
            raise _error("Invalid reference resolution basis", field="resolution_basis")
        _support_tuple(self.support)
        _control_files(self.resolution_control_files)
        if self.resolution_configuration is not None and (
            not isinstance(self.resolution_configuration, str)
            or self.resolution_configuration not in _RUST_RESOLUTION_CONFIGURATIONS
        ):
            raise _error(
                "Invalid reference resolution configuration",
                field="resolution_configuration",
            )
        self._validate_language_provenance()
        self._validate_outcome()

    def _validate_language_provenance(self) -> None:
        language = self.raw.language
        if language not in {"javascript", "typescript", "rust"} and (
            self.resolution_control_files or self.resolution_configuration is not None
        ):
            raise _error("Reference language cannot carry resolution provenance")
        if language != "rust" and self.resolution_configuration is not None:
            raise _error("Only Rust references may carry resolution configuration")

    def _validate_outcome(self) -> None:
        if self.status == "resolved":
            if self.binding is None:
                raise _error("Resolved reference requires one selected binding")
            if self.raw.binding_state not in {"definite", "deferred"}:
                raise _error("Resolved reference requires a resolvable binding state")
            if any(
                value is None
                for value in (
                    self.import_target_id,
                    self.target_file,
                    self.target_id,
                    self.target_kind,
                    self.resolution_basis,
                )
            ):
                raise _error("Resolved reference requires complete target identity")
            if self.unresolved_reason is not None:
                raise _error("Resolved reference cannot have an unresolved reason")
            if self.import_unresolved_reason is not None:
                raise _error("Resolved reference cannot have an import failure")
            if not self.support:
                raise _error("Resolved reference requires support")
            if self.raw.language == "rust" and self.resolution_configuration is None:
                raise _error("Resolved Rust reference requires configuration")
            return

        if any(
            value is not None
            for value in (
                self.target_file,
                self.target_id,
                self.target_kind,
                self.resolution_basis,
                self.resolution_configuration,
            )
        ):
            raise _error("Unresolved reference cannot have a final target or basis")
        if self.unresolved_reason is None:
            raise _error("Unresolved reference requires an unresolved reason")
        if (
            self.import_unresolved_reason is not None
            and self.unresolved_reason != "import_unresolved"
        ):
            raise _error("Import failure requires import_unresolved reference outcome")
        expected_by_state = {
            "shadowed": "binding_shadowed",
            "ambiguous": "ambiguous_binding",
            "unsupported": "unsupported_reference",
        }
        expected = expected_by_state.get(self.raw.binding_state)
        if expected is not None and self.unresolved_reason != expected:
            raise _error("Reference outcome does not match its binding state")

    def to_dict(self) -> dict[str, JSONValue]:
        return cast(
            dict[str, JSONValue],
            {
                "raw": self.raw.to_dict(),
                "binding": self.binding.to_dict() if self.binding is not None else None,
                "source_id": self.source_id,
                "source_kind": self.source_kind,
                "import_source_id": self.import_source_id,
                "import_target_id": self.import_target_id,
                "target_file": self.target_file,
                "target_id": self.target_id,
                "target_kind": self.target_kind,
                "status": self.status,
                "unresolved_reason": self.unresolved_reason,
                "import_unresolved_reason": self.import_unresolved_reason,
                "resolution_basis": self.resolution_basis,
                "support": [item.to_dict() for item in self.support],
                "resolution_control_files": list(self.resolution_control_files),
                "resolution_configuration": self.resolution_configuration,
            },
        )

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> SymbolReferenceRecord:
        _require_keys(value, _SYMBOL_REFERENCE_RECORD_FIELDS, "symbol reference record")
        raw_value = value["raw"]
        if not isinstance(raw_value, Mapping):
            raise _error("Reference raw observation must be an object", field="raw")
        binding_value = value["binding"]
        if binding_value is not None and not isinstance(binding_value, Mapping):
            raise _error("Reference binding must be an object", field="binding")
        support_value = value["support"]
        if not isinstance(support_value, list):
            raise _error("Reference support must be a list", field="support")
        controls_value = value["resolution_control_files"]
        if not isinstance(controls_value, list):
            raise _error(
                "Reference resolution control files must be a list",
                field="resolution_control_files",
            )
        return cls(
            raw=RawSymbolReference.from_dict(raw_value),
            binding=(
                ImportBinding.from_dict(binding_value)
                if binding_value is not None
                else None
            ),
            source_id=_nonempty_string(value["source_id"], "source_id"),
            source_kind=_nonempty_string(value["source_kind"], "source_kind"),
            import_source_id=_nonempty_string(
                value["import_source_id"],
                "import_source_id",
            ),
            import_target_id=_optional_nonempty_string(
                value["import_target_id"],
                "import_target_id",
            ),
            target_file=_optional_relative_path(value["target_file"], "target_file"),
            target_id=_optional_nonempty_string(value["target_id"], "target_id"),
            target_kind=_optional_nonempty_string(value["target_kind"], "target_kind"),
            status=cast(
                ReferenceStatus,
                _literal(value["status"], _REFERENCE_STATUSES, "status"),
            ),
            unresolved_reason=cast(
                ReferenceUnresolvedReason | None,
                _optional_literal(
                    value["unresolved_reason"],
                    _REFERENCE_UNRESOLVED_REASONS,
                    "unresolved_reason",
                ),
            ),
            import_unresolved_reason=cast(
                ImportUnresolvedReason | None,
                _optional_literal(
                    value["import_unresolved_reason"],
                    _IMPORT_UNRESOLVED_REASONS,
                    "import_unresolved_reason",
                ),
            ),
            resolution_basis=cast(
                ReferenceResolutionBasis | None,
                _optional_literal(
                    value["resolution_basis"],
                    _REFERENCE_RESOLUTION_BASES,
                    "resolution_basis",
                ),
            ),
            support=tuple(ReferenceSupport.from_dict(item) for item in support_value),
            resolution_control_files=tuple(
                _relative_path(item, "resolution_control_files")
                for item in controls_value
            ),
            resolution_configuration=cast(
                RustResolutionConfiguration | None,
                _optional_literal(
                    value["resolution_configuration"],
                    _RUST_RESOLUTION_CONFIGURATIONS,
                    "resolution_configuration",
                ),
            ),
        )


@dataclass(frozen=True, slots=True)
class ReferenceResolverIndex:
    """Frozen exact-endpoint lookups shared by language reference resolvers."""

    _symbols_by_id: Mapping[str, Symbol]
    _file_nodes: Mapping[str, Symbol]
    _source_spans: Mapping[str, _SourceSpanIndex]
    _imports: tuple[ImportRecord, ...]
    _imports_by_binding: Mapping[
        tuple[str, ImportBinding],
        tuple[ImportRecord, ...],
    ]
    _python: PythonReferenceIndex
    _javascript: JavaScriptReferenceIndex
    _go: GoReferenceIndex


@dataclass(frozen=True, slots=True)
class _SourceOwner:
    symbol: Symbol
    ambiguous: bool


@dataclass(frozen=True, slots=True)
class _SourceSpanIndex:
    symbols: tuple[Symbol, ...]
    starts: tuple[int, ...]
    tree_size: int
    max_ends: tuple[int, ...]

    @classmethod
    def build(cls, symbols: Sequence[Symbol]) -> _SourceSpanIndex:
        ordered = tuple(sorted(symbols, key=lambda item: (item.byte_offset, item.id)))
        tree_size = 1
        while tree_size < len(ordered):
            tree_size *= 2
        max_ends = [-1] * (tree_size * 2)
        for index, symbol in enumerate(ordered):
            max_ends[tree_size + index] = symbol.byte_offset + symbol.byte_length
        for index in range(tree_size - 1, 0, -1):
            max_ends[index] = max(max_ends[index * 2], max_ends[index * 2 + 1])
        return cls(
            symbols=ordered,
            starts=tuple(symbol.byte_offset for symbol in ordered),
            tree_size=tree_size,
            max_ends=tuple(max_ends),
        )

    def containing(self, start_byte: int, end_byte: int) -> list[Symbol]:
        upper = bisect_right(self.starts, start_byte)
        if upper == 0:
            return []
        matches: list[Symbol] = []
        pending = [(1, 0, self.tree_size)]
        while pending:
            node, left, right = pending.pop()
            if left >= upper or self.max_ends[node] < end_byte:
                continue
            if right - left == 1:
                if left < len(self.symbols):
                    matches.append(self.symbols[left])
                continue
            middle = (left + right) // 2
            pending.append((node * 2 + 1, middle, right))
            pending.append((node * 2, left, middle))
        return matches


def build_reference_resolver_index(
    symbols: Sequence[Symbol],
    imports: Sequence[ImportRecord],
    exports: Sequence[RawLocalExport],
    *,
    go_packages: GoPackageIndex | None = None,
    rust_crates: RustCrateIndex | None = None,
) -> ReferenceResolverIndex:
    """Build bounded immutable reference lookups without repository I/O."""
    del rust_crates  # Reserved by the frozen four-language API.
    symbols_by_id: dict[str, Symbol] = {}
    file_nodes: dict[str, Symbol] = {}
    source_symbols: dict[str, list[Symbol]] = {}
    for symbol in symbols:
        _validate_symbol(symbol)
        if symbol.id in symbols_by_id:
            raise _error(
                "Reference index contains duplicate symbol IDs",
                symbol_id=symbol.id,
            )
        symbols_by_id[symbol.id] = symbol
        if _is_file_node(symbol):
            if symbol.file_path in file_nodes:
                raise _error(
                    "Reference index contains duplicate file nodes",
                    file=symbol.file_path,
                )
            file_nodes[symbol.file_path] = symbol
        elif not _is_synthetic_symbol(symbol):
            source_symbols.setdefault(symbol.file_path, []).append(symbol)

    frozen_imports = tuple(imports)
    imports_by_binding: dict[
        tuple[str, ImportBinding],
        list[ImportRecord],
    ] = {}
    for record in frozen_imports:
        if not isinstance(record, ImportRecord):
            raise _error("Reference index import is not an ImportRecord")
        source = file_nodes.get(record.raw.source_file)
        if source is None or source.id != record.source_id:
            raise _error(
                "Reference import source does not match an indexed file node",
                file=record.raw.source_file,
            )
        if source.content_hash != record.raw.source_hash:
            raise _error(
                "Reference import source hash is stale",
                file=record.raw.source_file,
            )
        for binding in record.raw.bindings:
            imports_by_binding.setdefault(
                (record.raw.source_file, binding),
                [],
            ).append(record)

    for file, values in source_symbols.items():
        file_node = file_nodes.get(file)
        if file_node is None:
            raise _error(
                "Reference symbol has no indexed file node",
                file=file,
            )
        for symbol in values:
            if symbol.language != file_node.language:
                raise _error(
                    "Reference symbol language does not match its file node",
                    symbol_id=symbol.id,
                )

    frozen_spans = {
        file: _SourceSpanIndex.build(values)
        for file, values in source_symbols.items()
    }
    frozen_import_map = {
        key: tuple(value) for key, value in imports_by_binding.items()
    }
    from ._python_references import build_python_reference_index

    python_index = build_python_reference_index(
        tuple(symbols_by_id.values()),
        frozen_imports,
        tuple(exports),
        file_nodes=file_nodes,
    )
    from ._javascript_references import build_javascript_reference_index

    javascript_index = build_javascript_reference_index(
        tuple(symbols_by_id.values()),
        frozen_imports,
        tuple(exports),
        file_nodes=file_nodes,
    )
    from ._go_references import build_go_reference_index

    go_index = build_go_reference_index(
        tuple(symbols_by_id.values()),
        tuple(exports),
        file_nodes=file_nodes,
        go_packages=go_packages,
    )
    return ReferenceResolverIndex(
        _symbols_by_id=MappingProxyType(symbols_by_id),
        _file_nodes=MappingProxyType(file_nodes),
        _source_spans=MappingProxyType(frozen_spans),
        _imports=frozen_imports,
        _imports_by_binding=MappingProxyType(frozen_import_map),
        _python=python_index,
        _javascript=javascript_index,
        _go=go_index,
    )


def resolve_symbol_references(
    observations: Sequence[RawSymbolReference],
    *,
    imports: Sequence[ImportRecord],
    index: ReferenceResolverIndex,
) -> list[SymbolReferenceRecord]:
    """Resolve raw observations against only their proven import endpoints."""
    if not isinstance(index, ReferenceResolverIndex):
        raise _error("Reference resolver index has an invalid type")
    if tuple(imports) != index._imports:
        raise _error("Reference resolver imports do not match its frozen index")
    return [_resolve_symbol_reference(raw, index) for raw in observations]


def _resolve_symbol_reference(
    raw: RawSymbolReference,
    index: ReferenceResolverIndex,
) -> SymbolReferenceRecord:
    if not isinstance(raw, RawSymbolReference):
        raise _error("Reference observation must be a RawSymbolReference")
    owner = _source_owner(raw, index)
    binding, import_record, import_is_ambiguous = _select_reference_import(raw, index)

    binding_reason = {
        "shadowed": "binding_shadowed",
        "ambiguous": "ambiguous_binding",
        "unsupported": "unsupported_reference",
    }.get(raw.binding_state)
    if binding_reason is not None:
        return _unresolved_record(
            raw,
            binding=binding,
            owner=owner,
            import_record=import_record,
            reason=cast(ReferenceUnresolvedReason, binding_reason),
        )
    if binding is None or import_is_ambiguous:
        return _unresolved_record(
            raw,
            binding=None,
            owner=owner,
            import_record=None,
            reason="ambiguous_binding",
        )
    if import_record is None:
        return _unresolved_record(
            raw,
            binding=binding,
            owner=owner,
            import_record=None,
            reason="import_unresolved",
        )
    if import_record.status == "unresolved":
        return _unresolved_record(
            raw,
            binding=binding,
            owner=owner,
            import_record=import_record,
            reason="import_unresolved",
            import_reason=import_record.unresolved_reason,
        )
    if owner.ambiguous:
        return _unresolved_record(
            raw,
            binding=binding,
            owner=owner,
            import_record=import_record,
            reason="ambiguous_source",
        )
    if raw.language not in {"python", "javascript", "typescript", "go"}:
        return _unresolved_record(
            raw,
            binding=binding,
            owner=owner,
            import_record=import_record,
            reason="unsupported_reference",
        )

    if raw.language == "python":
        from ._python_references import resolve_python_reference

        outcome = resolve_python_reference(
            raw,
            binding=binding,
            import_record=import_record,
            index=index._python,
        )
    elif raw.language in {"javascript", "typescript"}:
        from ._javascript_references import resolve_javascript_reference

        outcome = resolve_javascript_reference(
            raw,
            binding=binding,
            import_record=import_record,
            index=index._javascript,
        )
    else:
        from ._go_references import resolve_go_reference

        outcome = resolve_go_reference(
            raw,
            binding=binding,
            import_record=import_record,
            index=index._go,
        )
    import_support = _import_binding_support(raw, import_record)
    if outcome.target is None:
        return _unresolved_record(
            raw,
            binding=binding,
            owner=owner,
            import_record=import_record,
            reason=outcome.reason or "target_not_indexed",
            import_reason=outcome.import_unresolved_reason,
            support=(import_support, *outcome.support),
        )
    return SymbolReferenceRecord(
        raw=raw,
        binding=binding,
        source_id=owner.symbol.id,
        source_kind=owner.symbol.kind,
        import_source_id=import_record.source_id,
        import_target_id=import_record.target_id,
        target_file=outcome.target.file_path,
        target_id=outcome.target.id,
        target_kind=outcome.target.kind,
        status="resolved",
        unresolved_reason=None,
        import_unresolved_reason=None,
        resolution_basis=outcome.basis,
        support=(import_support, *outcome.support),
        resolution_control_files=outcome.resolution_control_files,
        resolution_configuration=None,
    )


def _select_reference_import(
    raw: RawSymbolReference,
    index: ReferenceResolverIndex,
) -> tuple[ImportBinding | None, ImportRecord | None, bool]:
    if raw.language == "go" and raw.binding_state == "deferred":
        from ._go_references import select_go_reference_binding

        binding, record = select_go_reference_binding(
            raw,
            imports_by_binding=index._imports_by_binding,
            index=index._go,
        )
        return binding, record, False

    binding = raw.candidate_bindings[0] if len(raw.candidate_bindings) == 1 else None
    matched = (
        index._imports_by_binding.get((raw.source_file, binding), ())
        if binding is not None
        else ()
    )
    return (
        binding,
        matched[0] if len(matched) == 1 else None,
        len(matched) > 1,
    )


def _source_owner(
    raw: RawSymbolReference,
    index: ReferenceResolverIndex,
) -> _SourceOwner:
    file_node = index._file_nodes.get(raw.source_file)
    if file_node is None:
        raise _error("Reference source file node is not indexed", file=raw.source_file)
    if file_node.language != raw.language or file_node.content_hash != raw.source_hash:
        raise _error("Reference source evidence is stale", file=raw.source_file)
    spans = index._source_spans.get(raw.source_file)
    candidates = (
        spans.containing(raw.start_byte, raw.end_byte)
        if spans is not None
        else []
    )
    if not candidates:
        return _SourceOwner(file_node, False)
    smallest_length = min(symbol.byte_length for symbol in candidates)
    smallest = [
        symbol for symbol in candidates if symbol.byte_length == smallest_length
    ]
    if len(smallest) != 1:
        return _SourceOwner(file_node, True)
    return _SourceOwner(smallest[0], False)


def _unresolved_record(
    raw: RawSymbolReference,
    *,
    binding: ImportBinding | None,
    owner: _SourceOwner,
    import_record: ImportRecord | None,
    reason: ReferenceUnresolvedReason,
    import_reason: ImportUnresolvedReason | None = None,
    support: tuple[ReferenceSupport, ...] = (),
) -> SymbolReferenceRecord:
    file_node_id = f"{raw.source_file}::__file__#file"
    return SymbolReferenceRecord(
        raw=raw,
        binding=binding,
        source_id=owner.symbol.id,
        source_kind=owner.symbol.kind,
        import_source_id=(
            import_record.source_id if import_record is not None else file_node_id
        ),
        import_target_id=(
            import_record.target_id if import_record is not None else None
        ),
        target_file=None,
        target_id=None,
        target_kind=None,
        status="unresolved",
        unresolved_reason=reason,
        import_unresolved_reason=import_reason,
        resolution_basis=None,
        support=support,
        resolution_control_files=(
            import_record.resolution_control_files
            if import_record is not None
            else ()
        ),
        resolution_configuration=None,
    )


def _import_binding_support(
    raw: RawSymbolReference,
    import_record: ImportRecord,
) -> ReferenceSupport:
    if import_record.target_id is None:
        raise _error("Resolved reference import has no target endpoint")
    return ReferenceSupport(
        kind="import_binding",
        file=raw.source_file,
        line=import_record.raw.line,
        content_hash=raw.source_hash,
        endpoint_id=import_record.target_id,
    )


def _validate_symbol(symbol: Any) -> None:
    if not isinstance(symbol, Symbol):
        raise _error("Reference index symbol is not a Symbol")
    _nonempty_string(symbol.id, "symbol.id")
    _relative_path(symbol.file_path, "symbol.file_path")
    _nonempty_string(symbol.kind, "symbol.kind")
    _nonempty_string(symbol.language, "symbol.language")
    if (
        isinstance(symbol.byte_offset, bool)
        or not isinstance(symbol.byte_offset, int)
        or symbol.byte_offset < 0
        or isinstance(symbol.byte_length, bool)
        or not isinstance(symbol.byte_length, int)
        or symbol.byte_length < 0
    ):
        raise _error("Reference symbol has an invalid byte range", symbol_id=symbol.id)


def _is_file_node(symbol: Symbol) -> bool:
    loci = symbol.metadata.get("loci")
    return (
        symbol.kind == "file"
        and isinstance(loci, Mapping)
        and loci.get("file_node") is True
    )


def _is_synthetic_symbol(symbol: Symbol) -> bool:
    if symbol.kind in {"file", "package", "crate"} or symbol.language == "markdown":
        return True
    loci = symbol.metadata.get("loci")
    return isinstance(loci, Mapping) and any(
        loci.get(key) is True
        for key in ("file_node", "go_package", "rust_crate")
    )


def _support_tuple(value: Any) -> None:
    if not isinstance(value, tuple):
        raise _error("Reference support must be an immutable tuple", field="support")
    if len(value) > MAX_REFERENCE_SUPPORT_RECORDS:
        raise _error("Reference support exceeds the support limit", field="support")
    if any(not isinstance(item, ReferenceSupport) for item in value):
        raise _error("Reference support contains an invalid item", field="support")


def _control_files(value: Any) -> None:
    if not isinstance(value, tuple):
        raise _error(
            "Reference resolution control files must be an immutable tuple",
            field="resolution_control_files",
        )
    for item in value:
        _relative_path(item, "resolution_control_files")
    if value != tuple(sorted(set(value))):
        raise _error(
            "Reference resolution control files must be unique and sorted",
            field="resolution_control_files",
        )


def _require_keys(value: Mapping[str, Any], expected: set[str], record: str) -> None:
    if not isinstance(value, Mapping) or set(value) != expected:
        raise _error(
            f"Invalid {record} fields",
            missing=sorted(expected - set(value)),
            unknown=sorted(set(value) - expected),
        )


def _relative_path(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value or "\\" in value:
        raise _error(f"Reference {field} must be a relative path", field=field)
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or path.as_posix() != value:
        raise _error(f"Reference {field} must be a relative path", field=field)
    return value


def _optional_relative_path(value: Any, field: str) -> str | None:
    return None if value is None else _relative_path(value, field)


def _nonempty_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise _error(f"Reference {field} must be a non-empty string", field=field)
    return value


def _optional_nonempty_string(value: Any, field: str) -> str | None:
    return None if value is None else _nonempty_string(value, field)


def _positive_integer(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise _error(f"Reference {field} must be a positive integer", field=field)
    return value


def _sha256(value: Any, field: str) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise _error(f"Reference {field} must be a SHA-256 hash", field=field)
    return value


def _literal(value: Any, allowed: frozenset[str], field: str) -> str:
    if not isinstance(value, str) or value not in allowed:
        raise _error(f"Invalid reference {field}", field=field)
    return value


def _optional_literal(
    value: Any,
    allowed: frozenset[str],
    field: str,
) -> str | None:
    return None if value is None else _literal(value, allowed, field)


def _error(message: str, **details: Any) -> GraphContractError:
    return GraphContractError(
        "GRAPH_CONTRACT_INVALID",
        message,
        cast(dict[str, JSONValue], details),
    )
