from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any, Literal, Mapping, Sequence, TypeAlias, cast

from loci.parser.call_models import MAX_CALL_SITES_PER_FILE, RawCallSite
from loci.parser.symbols import Symbol

from .contracts import GraphContractError, GraphEdge, JSONValue
from .references import ReferenceUnresolvedReason, SymbolReferenceRecord
from .rust_crates import RustResolutionConfiguration


MAX_CALL_SUPPORT_RECORDS = 256

CallStatus: TypeAlias = Literal["resolved", "unresolved"]
CallResolution: TypeAlias = Literal["exact", "import-resolved"]
CallResolutionBasis: TypeAlias = Literal["local_callable", "imported_reference"]
CallUnresolvedReason: TypeAlias = Literal[
    "unsupported_callee",
    "caller_not_indexed",
    "caller_ambiguous",
    "local_binding_shadowed",
    "local_binding_ambiguous",
    "local_target_not_indexed",
    "callee_not_proven",
    "reference_unresolved",
    "target_not_callable",
    "conflicting_resolution",
]
CallSupportKind: TypeAlias = Literal[
    "call_site",
    "caller_definition",
    "local_definition",
    "symbol_reference",
]

_CALL_STATUSES = frozenset({"resolved", "unresolved"})
_CALL_RESOLUTIONS = frozenset({"exact", "import-resolved"})
_CALL_RESOLUTION_BASES = frozenset({"local_callable", "imported_reference"})
_CALL_UNRESOLVED_REASONS = frozenset({
    "unsupported_callee",
    "caller_not_indexed",
    "caller_ambiguous",
    "local_binding_shadowed",
    "local_binding_ambiguous",
    "local_target_not_indexed",
    "callee_not_proven",
    "reference_unresolved",
    "target_not_callable",
    "conflicting_resolution",
})
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
_CALL_SUPPORT_KINDS = frozenset({
    "call_site",
    "caller_definition",
    "local_definition",
    "symbol_reference",
})
_CALLABLE_KINDS = frozenset({"function", "method"})
_CALLER_KINDS = frozenset({"file", *_CALLABLE_KINDS})
_RUST_RESOLUTION_CONFIGURATIONS = frozenset({
    "unconditional",
    "declared_possible",
})
_SUPPORT_KIND_ORDER = {
    "call_site": 0,
    "caller_definition": 1,
    "local_definition": 2,
    "symbol_reference": 3,
}
_CALL_SUPPORT_FIELDS = {
    "kind",
    "file",
    "line",
    "content_hash",
    "endpoint_id",
}
_CALL_RECORD_FIELDS = {
    "raw",
    "caller_id",
    "caller_kind",
    "target_file",
    "target_id",
    "target_kind",
    "status",
    "resolution",
    "unresolved_reason",
    "reference_unresolved_reason",
    "resolution_basis",
    "support",
    "resolution_control_files",
    "resolution_configuration",
}
_SHA256_RE = re.compile(r"[0-9a-f]{64}")


@dataclass(frozen=True, slots=True)
class CallSupport:
    kind: CallSupportKind
    file: str
    line: int
    content_hash: str
    endpoint_id: str

    def __post_init__(self) -> None:
        _literal(self.kind, _CALL_SUPPORT_KINDS, "kind")
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
    def from_dict(cls, value: Mapping[str, Any]) -> CallSupport:
        _require_keys(value, _CALL_SUPPORT_FIELDS, "call support")
        return cls(
            kind=cast(
                CallSupportKind,
                _literal(value["kind"], _CALL_SUPPORT_KINDS, "kind"),
            ),
            file=_relative_path(value["file"], "file"),
            line=_positive_integer(value["line"], "line"),
            content_hash=_sha256(value["content_hash"], "content_hash"),
            endpoint_id=_nonempty_string(value["endpoint_id"], "endpoint_id"),
        )


@dataclass(frozen=True, slots=True)
class CallRecord:
    raw: RawCallSite
    caller_id: str | None
    caller_kind: str | None
    target_file: str | None
    target_id: str | None
    target_kind: str | None
    status: CallStatus
    resolution: CallResolution | None
    unresolved_reason: CallUnresolvedReason | None
    reference_unresolved_reason: ReferenceUnresolvedReason | None
    resolution_basis: CallResolutionBasis | None
    support: tuple[CallSupport, ...]
    resolution_control_files: tuple[str, ...]
    resolution_configuration: RustResolutionConfiguration | None

    def __post_init__(self) -> None:
        if not isinstance(self.raw, RawCallSite):
            raise _error("Call raw observation must be a RawCallSite")
        _optional_nonempty_string(self.caller_id, "caller_id")
        _optional_nonempty_string(self.caller_kind, "caller_kind")
        if (self.caller_id is None) != (self.caller_kind is None):
            raise _error("Call caller identity must be complete")
        if self.caller_kind is not None:
            _literal(self.caller_kind, _CALLER_KINDS, "caller_kind")
        self._validate_caller_identity()
        if self.target_file is not None:
            _relative_path(self.target_file, "target_file")
        _optional_nonempty_string(self.target_id, "target_id")
        _optional_nonempty_string(self.target_kind, "target_kind")
        _literal(self.status, _CALL_STATUSES, "status")
        _optional_literal(self.resolution, _CALL_RESOLUTIONS, "resolution")
        _optional_literal(
            self.unresolved_reason,
            _CALL_UNRESOLVED_REASONS,
            "unresolved_reason",
        )
        _optional_literal(
            self.reference_unresolved_reason,
            _REFERENCE_UNRESOLVED_REASONS,
            "reference_unresolved_reason",
        )
        _optional_literal(
            self.resolution_basis,
            _CALL_RESOLUTION_BASES,
            "resolution_basis",
        )
        _support_tuple(self.support)
        _control_files(self.resolution_control_files)
        _optional_literal(
            self.resolution_configuration,
            _RUST_RESOLUTION_CONFIGURATIONS,
            "resolution_configuration",
        )
        self._validate_outcome()

    def _validate_caller_identity(self) -> None:
        if self.caller_id is None:
            return
        assert self.caller_kind is not None
        if self.raw.owner.kind == "file":
            if (
                self.caller_kind != "file"
                or self.caller_id != f"{self.raw.source_file}::__file__#file"
            ):
                raise _error("Call caller does not match its file owner")
            return
        if self.raw.owner.kind == "callable":
            if self.caller_kind not in _CALLABLE_KINDS:
                raise _error("Call caller does not match its callable owner")
            return
        raise _error("Unindexed call owner cannot have an indexed caller")

    def _validate_outcome(self) -> None:
        if self.status == "unresolved":
            if any(
                value is not None
                for value in (
                    self.target_file,
                    self.target_id,
                    self.target_kind,
                    self.resolution,
                    self.resolution_basis,
                    self.resolution_configuration,
                )
            ):
                raise _error("Unresolved call cannot have a final target or basis")
            if self.unresolved_reason is None:
                raise _error("Unresolved call requires an unresolved reason")
            if self.resolution_control_files:
                raise _error("Unresolved call cannot carry resolution controls")
            if (
                self.reference_unresolved_reason is None
            ) != (self.unresolved_reason != "reference_unresolved"):
                raise _error(
                    "Reference failure is valid only for reference_unresolved calls"
                )
            if self.unresolved_reason in {
                "unsupported_callee",
                "caller_not_indexed",
                "caller_ambiguous",
            }:
                if self.caller_id is not None or self.support:
                    raise _error("Caller failure cannot carry caller evidence")
            elif self.caller_id is None:
                raise _error("Callee resolution failure requires an indexed caller")
            self._validate_unresolved_reason()
            return

        if any(
            value is None
            for value in (
                self.caller_id,
                self.caller_kind,
                self.target_file,
                self.target_id,
                self.target_kind,
                self.resolution,
                self.resolution_basis,
            )
        ):
            raise _error("Resolved call requires complete caller and target identity")
        if (
            self.unresolved_reason is not None
            or self.reference_unresolved_reason is not None
        ):
            raise _error("Resolved call cannot have an unresolved reason")
        if self.target_kind not in _CALLABLE_KINDS:
            raise _error("Resolved call target must be callable")
        if self.caller_kind not in _CALLER_KINDS:
            raise _error("Resolved call caller must be a file or callable")
        self._validate_resolved_support()
        if self.resolution == "exact":
            if self.resolution_basis != "local_callable":
                raise _error("Exact call requires local_callable resolution basis")
            if self.target_file != self.raw.source_file:
                raise _error("Exact call target must stay in the source file")
            if self.raw.local_binding_state != "definite":
                raise _error("Exact call requires one definite local binding")
            binding = self.raw.local_candidates[0]
            if self.target_kind != binding.callable_kind:
                raise _error("Exact call target kind does not match its binding")
            if (
                self.resolution_control_files
                or self.resolution_configuration is not None
            ):
                raise _error("Exact call cannot carry import resolution provenance")
            local_support = [
                item for item in self.support if item.kind == "local_definition"
            ]
            if len(local_support) != 1:
                raise _error("Exact call requires exactly one local definition support")
            if (
                local_support[0].file != self.target_file
                or local_support[0].line != binding.definition_line
            ):
                raise _error("Local definition support does not match its binding")
            if any(item.kind == "symbol_reference" for item in self.support):
                raise _error("Exact call cannot carry symbol reference support")
            return
        if self.resolution_basis != "imported_reference":
            raise _error("Import-resolved call requires imported_reference basis")
        if any(item.kind == "local_definition" for item in self.support):
            raise _error("Import-resolved call cannot carry local definition support")
        references = [
            item for item in self.support if item.kind == "symbol_reference"
        ]
        if len(references) != 1:
            raise _error(
                "Import-resolved call requires exactly one symbol reference support"
            )
        reference = references[0]
        if (
            reference.file != self.raw.source_file
            or reference.line != self.raw.line
            or reference.content_hash != self.raw.source_hash
            or reference.endpoint_id != self.target_id
        ):
            raise _error("Symbol reference support does not match the call target")
        if self.raw.language not in {"javascript", "typescript", "rust"} and (
            self.resolution_control_files
            or self.resolution_configuration is not None
        ):
            raise _error("Call language cannot carry import resolution provenance")
        if self.raw.language != "rust" and self.resolution_configuration is not None:
            raise _error("Only Rust calls may carry resolution configuration")
        if self.raw.language == "rust" and self.resolution_configuration is None:
            raise _error("Import-resolved Rust call requires configuration")

    def _validate_unresolved_reason(self) -> None:
        expected_state = (
            {
                "unsupported_callee": "unsupported",
                "local_binding_shadowed": "shadowed",
                "local_target_not_indexed": "definite",
            }.get(self.unresolved_reason)
            if self.unresolved_reason is not None
            else None
        )
        if expected_state is not None and self.raw.local_binding_state != expected_state:
            raise _error("Call failure does not match its local binding state")
        if (
            self.unresolved_reason == "local_binding_ambiguous"
            and self.raw.local_binding_state not in {"ambiguous", "definite"}
        ):
            raise _error("Ambiguous local call requires ambiguous binding evidence")
        if (
            self.unresolved_reason == "callee_not_proven"
            and self.raw.local_binding_state != "absent"
        ):
            raise _error("Unproven callee requires an absent local binding")

    def _validate_resolved_support(self) -> None:
        assert self.caller_id is not None
        assert self.caller_kind is not None
        assert self.target_id is not None
        call_sites = [item for item in self.support if item.kind == "call_site"]
        if len(call_sites) != 1:
            raise _error("Resolved call requires exactly one call-site support record")
        call_site = call_sites[0]
        if (
            call_site.file != self.raw.source_file
            or call_site.line != self.raw.line
            or call_site.content_hash != self.raw.source_hash
            or call_site.endpoint_id != self.caller_id
        ):
            raise _error("Call-site support does not match the raw call")
        caller_definitions = [
            item for item in self.support if item.kind == "caller_definition"
        ]
        if self.caller_kind == "file":
            if self.caller_id != f"{self.raw.source_file}::__file__#file":
                raise _error("File-owned call has an inconsistent caller identity")
            if caller_definitions:
                raise _error("File-owned call cannot carry caller definition support")
        elif len(caller_definitions) != 1:
            raise _error("Named call owner requires caller definition support")
        elif caller_definitions[0].endpoint_id != self.caller_id:
            raise _error("Caller definition support has the wrong endpoint")
        elif caller_definitions[0].file != self.raw.source_file:
            raise _error("Caller definition support must stay in the source file")
        local_definitions = [
            item for item in self.support if item.kind == "local_definition"
        ]
        if local_definitions and any(
            item.endpoint_id != self.target_id for item in local_definitions
        ):
            raise _error("Local definition support has the wrong endpoint")

    def to_dict(self) -> dict[str, JSONValue]:
        return cast(
            dict[str, JSONValue],
            {
                "raw": self.raw.to_dict(),
                "caller_id": self.caller_id,
                "caller_kind": self.caller_kind,
                "target_file": self.target_file,
                "target_id": self.target_id,
                "target_kind": self.target_kind,
                "status": self.status,
                "resolution": self.resolution,
                "unresolved_reason": self.unresolved_reason,
                "reference_unresolved_reason": self.reference_unresolved_reason,
                "resolution_basis": self.resolution_basis,
                "support": [item.to_dict() for item in self.support],
                "resolution_control_files": list(self.resolution_control_files),
                "resolution_configuration": self.resolution_configuration,
            },
        )

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> CallRecord:
        _require_keys(value, _CALL_RECORD_FIELDS, "call record")
        raw_value = value["raw"]
        if not isinstance(raw_value, Mapping):
            raise _error("Call raw observation must be an object", field="raw")
        support_value = value["support"]
        if not isinstance(support_value, list):
            raise _error("Call support must be a list", field="support")
        controls_value = value["resolution_control_files"]
        if not isinstance(controls_value, list):
            raise _error(
                "Call resolution control files must be a list",
                field="resolution_control_files",
            )
        return cls(
            raw=RawCallSite.from_dict(raw_value),
            caller_id=_optional_nonempty_string(value["caller_id"], "caller_id"),
            caller_kind=_optional_nonempty_string(value["caller_kind"], "caller_kind"),
            target_file=_optional_relative_path(value["target_file"], "target_file"),
            target_id=_optional_nonempty_string(value["target_id"], "target_id"),
            target_kind=_optional_nonempty_string(value["target_kind"], "target_kind"),
            status=cast(
                CallStatus,
                _literal(value["status"], _CALL_STATUSES, "status"),
            ),
            resolution=cast(
                CallResolution | None,
                _optional_literal(value["resolution"], _CALL_RESOLUTIONS, "resolution"),
            ),
            unresolved_reason=cast(
                CallUnresolvedReason | None,
                _optional_literal(
                    value["unresolved_reason"],
                    _CALL_UNRESOLVED_REASONS,
                    "unresolved_reason",
                ),
            ),
            reference_unresolved_reason=cast(
                ReferenceUnresolvedReason | None,
                _optional_literal(
                    value["reference_unresolved_reason"],
                    _REFERENCE_UNRESOLVED_REASONS,
                    "reference_unresolved_reason",
                ),
            ),
            resolution_basis=cast(
                CallResolutionBasis | None,
                _optional_literal(
                    value["resolution_basis"],
                    _CALL_RESOLUTION_BASES,
                    "resolution_basis",
                ),
            ),
            support=tuple(CallSupport.from_dict(item) for item in support_value),
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


def resolve_calls(
    observations: Sequence[RawCallSite],
    *,
    symbols: Sequence[Symbol],
    symbol_references: Sequence[SymbolReferenceRecord],
    file_hashes: Mapping[str, str],
) -> list[CallRecord]:
    """Resolve exact local calls and exact joins to accepted Stage 10 references."""
    _validate_observations(observations)
    _validate_file_hashes(file_hashes)

    file_nodes: dict[str, list[Symbol]] = defaultdict(list)
    callables: dict[tuple[str, int, int, str], list[Symbol]] = defaultdict(list)
    symbols_by_id: dict[str, list[Symbol]] = defaultdict(list)
    for symbol in symbols:
        if not isinstance(symbol, Symbol):
            raise _error("Call resolver symbol is not a Symbol")
        symbols_by_id[symbol.id].append(symbol)
        if symbol.kind == "file":
            _validate_indexed_symbol(symbol)
            file_nodes[symbol.file_path].append(symbol)
        elif symbol.kind in _CALLABLE_KINDS:
            _validate_indexed_symbol(symbol)
            callables[
                (
                    symbol.file_path,
                    symbol.byte_offset,
                    symbol.byte_offset + symbol.byte_length,
                    symbol.kind,
                )
            ].append(symbol)

    references: dict[
        tuple[str, str, int, int],
        list[SymbolReferenceRecord],
    ] = defaultdict(list)
    for reference in symbol_references:
        if not isinstance(reference, SymbolReferenceRecord):
            raise _error("Call resolver reference is not a SymbolReferenceRecord")
        if file_hashes.get(reference.raw.source_file) != reference.raw.source_hash:
            raise _error(
                "Call reference evidence is missing or stale",
                file=reference.raw.source_file,
            )
        references[
            (
                reference.raw.source_file,
                reference.raw.source_hash,
                reference.raw.start_byte,
                reference.raw.end_byte,
            )
        ].append(reference)

    return [
        _resolve_call(
            raw,
            file_nodes=file_nodes,
            callables=callables,
            symbols_by_id=symbols_by_id,
            references=references,
            file_hashes=file_hashes,
        )
        for raw in observations
    ]


def materialize_call_edges(records: Sequence[CallRecord]) -> list[GraphEdge]:
    """Build one deterministic edge per resolved caller/target relationship."""
    from ._call_validation import materialize_call_edges as materialize

    return materialize(records)


def validate_call_records(
    records: Sequence[CallRecord],
    *,
    symbol_references: Sequence[SymbolReferenceRecord],
    indexed_nodes: Mapping[str, Mapping[str, Any]],
    file_hashes: Mapping[str, str],
) -> None:
    """Cross-check call records against current indexed evidence."""
    from ._call_validation import validate_call_records as validate_records

    validate_records(
        records,
        symbol_references=symbol_references,
        indexed_nodes=indexed_nodes,
        file_hashes=file_hashes,
    )


def _resolve_call(
    raw: RawCallSite,
    *,
    file_nodes: Mapping[str, list[Symbol]],
    callables: Mapping[tuple[str, int, int, str], list[Symbol]],
    symbols_by_id: Mapping[str, list[Symbol]],
    references: Mapping[
        tuple[str, str, int, int],
        list[SymbolReferenceRecord],
    ],
    file_hashes: Mapping[str, str],
) -> CallRecord:
    current_hash = file_hashes.get(raw.source_file)
    if current_hash != raw.source_hash:
        raise _error("Call source evidence is missing or stale", file=raw.source_file)
    source_nodes = file_nodes.get(raw.source_file, [])
    if len(source_nodes) != 1:
        raise _error(
            "Call source file endpoint is missing or ambiguous",
            file=raw.source_file,
        )
    file_node = source_nodes[0]
    if file_node.language != raw.language or file_node.content_hash != raw.source_hash:
        raise _error("Call source evidence is stale", file=raw.source_file)

    if raw.callee_form == "dynamic" or raw.local_binding_state == "unsupported":
        return _unresolved(raw, reason="unsupported_callee")

    caller, caller_reason = _resolve_caller(
        raw,
        file_node=file_node,
        callables=callables,
    )
    if caller_reason is not None:
        return _unresolved(raw, reason=caller_reason)
    assert caller is not None

    binding_reason = {
        "shadowed": "local_binding_shadowed",
        "ambiguous": "local_binding_ambiguous",
    }.get(raw.local_binding_state)
    if binding_reason is not None:
        return _unresolved(
            raw,
            caller=caller,
            reason=cast(CallUnresolvedReason, binding_reason),
        )

    exact_references = references.get(
        (
            raw.source_file,
            raw.source_hash,
            raw.callee_start_byte,
            raw.callee_end_byte,
        ),
        [],
    )
    reference = exact_references[0] if len(exact_references) == 1 else None
    local_target, local_reason = _local_target(raw, callables=callables)
    imported_reference = (
        reference
        if reference is not None
        and reference.status == "resolved"
        and reference.binding is not None
        and not reference.binding.type_only
        and reference.target_kind in _CALLABLE_KINDS
        else None
    )

    if local_target is not None and imported_reference is not None:
        return _unresolved(raw, caller=caller, reason="conflicting_resolution")
    if local_target is not None:
        return _resolved_local(raw, caller=caller, target=local_target)
    if imported_reference is not None:
        return _resolved_import(
            raw,
            caller=caller,
            reference=imported_reference,
            symbols_by_id=symbols_by_id,
            file_hashes=file_hashes,
        )
    if reference is not None and reference.status == "unresolved":
        assert reference.unresolved_reason is not None
        return _unresolved(
            raw,
            caller=caller,
            reason="reference_unresolved",
            reference_reason=reference.unresolved_reason,
        )
    if (
        reference is not None
        and reference.status == "resolved"
        and reference.binding is not None
        and not reference.binding.type_only
        and reference.target_kind not in _CALLABLE_KINDS
    ):
        return _unresolved(raw, caller=caller, reason="target_not_callable")
    if local_reason is not None:
        return _unresolved(raw, caller=caller, reason=local_reason)
    return _unresolved(raw, caller=caller, reason="callee_not_proven")


def _local_target(
    raw: RawCallSite,
    *,
    callables: Mapping[tuple[str, int, int, str], list[Symbol]],
) -> tuple[Symbol | None, CallUnresolvedReason | None]:
    if raw.local_binding_state != "definite":
        return None, None
    binding = raw.local_candidates[0]
    candidates = [
        symbol
        for symbol in callables.get(
            (
                raw.source_file,
                binding.definition_start_byte,
                binding.definition_end_byte,
                binding.callable_kind,
            ),
            [],
        )
        if symbol.name == binding.name and symbol.language == raw.language
    ]
    if not candidates:
        return None, "local_target_not_indexed"
    if len(candidates) != 1:
        return None, "local_binding_ambiguous"
    return candidates[0], None


def _resolved_local(
    raw: RawCallSite,
    *,
    caller: Symbol,
    target: Symbol,
) -> CallRecord:
    support = _resolved_support(raw, caller=caller, target=target)
    return CallRecord(
        raw=raw,
        caller_id=caller.id,
        caller_kind=caller.kind,
        target_file=target.file_path,
        target_id=target.id,
        target_kind=target.kind,
        status="resolved",
        resolution="exact",
        unresolved_reason=None,
        reference_unresolved_reason=None,
        resolution_basis="local_callable",
        support=support,
        resolution_control_files=(),
        resolution_configuration=None,
    )


def _resolved_import(
    raw: RawCallSite,
    *,
    caller: Symbol,
    reference: SymbolReferenceRecord,
    symbols_by_id: Mapping[str, list[Symbol]],
    file_hashes: Mapping[str, str],
) -> CallRecord:
    assert reference.target_file is not None
    assert reference.target_id is not None
    assert reference.target_kind in _CALLABLE_KINDS
    targets = symbols_by_id.get(reference.target_id, [])
    if len(targets) != 1:
        raise _error(
            "Call reference target endpoint is missing or ambiguous",
            endpoint_id=reference.target_id,
        )
    target = targets[0]
    if (
        target.file_path != reference.target_file
        or target.kind != reference.target_kind
        or not _same_language_family(target.language, raw.language)
    ):
        raise _error(
            "Call reference target evidence is missing or stale",
            endpoint_id=reference.target_id,
        )
    current_target_hash = file_hashes.get(target.file_path)
    target_support = [
        item
        for item in reference.support
        if item.kind == "definition" and item.endpoint_id == target.id
    ]
    if (
        current_target_hash is None
        or len(target_support) != 1
        or target_support[0].file != target.file_path
        or target_support[0].content_hash != current_target_hash
    ):
        raise _error(
            "Call reference target support is missing or stale",
            endpoint_id=reference.target_id,
        )
    support = _resolved_support(raw, caller=caller, reference=reference)
    return CallRecord(
        raw=raw,
        caller_id=caller.id,
        caller_kind=caller.kind,
        target_file=reference.target_file,
        target_id=reference.target_id,
        target_kind=reference.target_kind,
        status="resolved",
        resolution="import-resolved",
        unresolved_reason=None,
        reference_unresolved_reason=None,
        resolution_basis="imported_reference",
        support=support,
        resolution_control_files=reference.resolution_control_files,
        resolution_configuration=reference.resolution_configuration,
    )


def _same_language_family(left: str, right: str) -> bool:
    if left == right:
        return True
    return {left, right} == {"javascript", "typescript"}


def _resolve_caller(
    raw: RawCallSite,
    *,
    file_node: Symbol,
    callables: Mapping[tuple[str, int, int, str], list[Symbol]],
) -> tuple[Symbol | None, CallUnresolvedReason | None]:
    if raw.owner.kind == "file":
        return file_node, None
    if raw.owner.kind == "unindexed":
        return None, "caller_not_indexed"
    assert raw.owner.definition_start_byte is not None
    assert raw.owner.definition_end_byte is not None
    candidates = [
        symbol
        for kind in _CALLABLE_KINDS
        for symbol in callables.get(
            (
                raw.source_file,
                raw.owner.definition_start_byte,
                raw.owner.definition_end_byte,
                kind,
            ),
            [],
        )
        if symbol.language == raw.language
    ]
    if not candidates:
        return None, "caller_not_indexed"
    if len(candidates) != 1:
        return None, "caller_ambiguous"
    return candidates[0], None


def _resolved_support(
    raw: RawCallSite,
    *,
    caller: Symbol,
    target: Symbol | None = None,
    reference: SymbolReferenceRecord | None = None,
) -> tuple[CallSupport, ...]:
    if (target is None) == (reference is None):
        raise _error("Call support requires exactly one target proof")
    support = [
        CallSupport(
            kind="call_site",
            file=raw.source_file,
            line=raw.line,
            content_hash=raw.source_hash,
            endpoint_id=caller.id,
        )
    ]
    if caller.kind != "file":
        support.append(
            CallSupport(
                kind="caller_definition",
                file=caller.file_path,
                line=caller.line,
                content_hash=caller.content_hash,
                endpoint_id=caller.id,
            )
        )
    if target is not None:
        support.append(
            CallSupport(
                kind="local_definition",
                file=target.file_path,
                line=target.line,
                content_hash=target.content_hash,
                endpoint_id=target.id,
            )
        )
    else:
        assert reference is not None
        assert reference.target_id is not None
        support.append(
            CallSupport(
                kind="symbol_reference",
                file=reference.raw.source_file,
                line=reference.raw.line,
                content_hash=reference.raw.source_hash,
                endpoint_id=reference.target_id,
            )
        )
    return tuple(support)


def _unresolved(
    raw: RawCallSite,
    *,
    reason: CallUnresolvedReason,
    caller: Symbol | None = None,
    reference_reason: ReferenceUnresolvedReason | None = None,
) -> CallRecord:
    return CallRecord(
        raw=raw,
        caller_id=caller.id if caller is not None else None,
        caller_kind=caller.kind if caller is not None else None,
        target_file=None,
        target_id=None,
        target_kind=None,
        status="unresolved",
        resolution=None,
        unresolved_reason=reason,
        reference_unresolved_reason=reference_reason,
        resolution_basis=None,
        support=(),
        resolution_control_files=(),
        resolution_configuration=None,
    )


def _validate_observations(observations: Sequence[RawCallSite]) -> None:
    counts: Counter[str] = Counter()
    for raw in observations:
        if not isinstance(raw, RawCallSite):
            raise _error("Call observation must be a RawCallSite")
        counts[raw.source_file] += 1
        if counts[raw.source_file] > MAX_CALL_SITES_PER_FILE:
            raise _error(
                "Call observations exceed the per-file limit",
                file=raw.source_file,
            )


def _validate_file_hashes(file_hashes: Mapping[str, str]) -> None:
    if not isinstance(file_hashes, Mapping):
        raise _error("Call file hashes must be a mapping")
    for path, content_hash in file_hashes.items():
        _relative_path(path, "file_hashes")
        _sha256(content_hash, "file_hashes")


def _validate_indexed_symbol(symbol: Symbol) -> None:
    _nonempty_string(symbol.id, "symbol.id")
    _nonempty_string(symbol.name, "symbol.name")
    _nonempty_string(symbol.language, "symbol.language")
    _relative_path(symbol.file_path, "symbol.file_path")
    if type(symbol.byte_offset) is not int or symbol.byte_offset < 0:
        raise _error("Invalid indexed symbol byte offset")
    if type(symbol.byte_length) is not int or symbol.byte_length < 0:
        raise _error("Invalid indexed symbol byte length")
    if symbol.kind != "file" and symbol.byte_length == 0:
        raise _error("Indexed callable span must be non-empty")
    _sha256(symbol.content_hash, "symbol.content_hash")
    _positive_integer(symbol.line, "symbol.line")


def _support_tuple(value: Any) -> None:
    if not isinstance(value, tuple) or any(
        not isinstance(item, CallSupport) for item in value
    ):
        raise _error("Call support must be an immutable tuple")
    if len(value) > MAX_CALL_SUPPORT_RECORDS:
        raise _error("Call support exceeds the record limit")
    if len(set(value)) != len(value):
        raise _error("Call support records must be unique")
    if tuple(sorted(value, key=_support_sort_key)) != value:
        raise _error("Call support records must be deterministically ordered")


def _support_sort_key(item: CallSupport) -> tuple[int, str, int, str, str]:
    return (
        _SUPPORT_KIND_ORDER[item.kind],
        item.file,
        item.line,
        item.endpoint_id,
        item.content_hash,
    )


def _control_files(value: Any) -> None:
    if not isinstance(value, tuple):
        raise _error("Call resolution control files must be an immutable tuple")
    validated = tuple(
        _relative_path(item, "resolution_control_files") for item in value
    )
    if len(set(validated)) != len(validated) or tuple(sorted(validated)) != validated:
        raise _error("Call resolution control files must be unique and ordered")


def _require_keys(value: Mapping[str, Any], expected: set[str], record: str) -> None:
    if not isinstance(value, Mapping) or set(value) != expected:
        raise _error(f"{record.title()} fields are missing or unknown")


def _relative_path(value: Any, field: str) -> str:
    text = _nonempty_string(value, field)
    path = PurePosixPath(text)
    if (
        path.is_absolute()
        or text != path.as_posix()
        or ".." in path.parts
        or "." in path.parts
    ):
        raise _error("Invalid repository-relative path", field=field)
    return text


def _optional_relative_path(value: Any, field: str) -> str | None:
    return None if value is None else _relative_path(value, field)


def _nonempty_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise _error("Expected a non-empty string", field=field)
    return value


def _optional_nonempty_string(value: Any, field: str) -> str | None:
    return None if value is None else _nonempty_string(value, field)


def _positive_integer(value: Any, field: str) -> int:
    if type(value) is not int or value < 1:
        raise _error("Expected a positive integer", field=field)
    return value


def _sha256(value: Any, field: str) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise _error("Expected a lowercase SHA-256 hash", field=field)
    return value


def _literal(value: Any, allowed: frozenset[str], field: str) -> str:
    if not isinstance(value, str) or value not in allowed:
        raise _error("Invalid literal value", field=field)
    return value


def _optional_literal(value: Any, allowed: frozenset[str], field: str) -> str | None:
    return None if value is None else _literal(value, allowed, field)


def _error(message: str, **details: Any) -> GraphContractError:
    return GraphContractError(
        "GRAPH_CALL_CONTRACT_INVALID",
        message,
        cast(dict[str, JSONValue], details),
    )
