from __future__ import annotations

import hashlib
from dataclasses import replace
from pathlib import Path

import pytest

from loci.graph.calls import (
    MAX_CALL_SUPPORT_RECORDS,
    CallRecord,
    CallSupport,
    resolve_calls,
)
from loci.graph.contracts import GraphContractError
from loci.graph.references import ReferenceSupport, SymbolReferenceRecord
from loci.parser._binding_context import ExecutableOwner
from loci.parser.call_models import LocalCallableBinding, RawCallSite
from loci.parser.extractor import parse_file
from loci.parser.imports import extract_import_batch
from loci.parser.symbols import Symbol, make_file_symbol, make_symbol_id


SOURCE_HASH = "a" * 64
TARGET_HASH = "b" * 64
SOURCE_FILE = "src/example.py"
FILE_ID = f"{SOURCE_FILE}::__file__#file"
CALLER_ID = f"{SOURCE_FILE}::caller#function"
TARGET_ID = f"{SOURCE_FILE}::target#function"


def _binding(**overrides) -> LocalCallableBinding:
    values = {
        "name": "target",
        "callable_kind": "function",
        "definition_start_byte": 0,
        "definition_end_byte": 20,
        "definition_line": 1,
        "scope_start_byte": 0,
        "scope_end_byte": 200,
    }
    values.update(overrides)
    return LocalCallableBinding(**values)


def _owner(**overrides) -> ExecutableOwner:
    values = {
        "kind": "callable",
        "definition_start_byte": 30,
        "definition_end_byte": 100,
        "body_start_byte": 45,
        "body_end_byte": 100,
    }
    values.update(overrides)
    return ExecutableOwner(**values)


def _raw_call(**overrides) -> RawCallSite:
    values = {
        "source_file": SOURCE_FILE,
        "language": "python",
        "line": 4,
        "column": 12,
        "start_byte": 60,
        "end_byte": 68,
        "callee_start_byte": 60,
        "callee_end_byte": 66,
        "callee_text": "target",
        "callee_path": ("target",),
        "callee_form": "identifier",
        "local_candidates": (_binding(),),
        "local_binding_state": "definite",
        "owner": _owner(),
        "source_hash": SOURCE_HASH,
    }
    values.update(overrides)
    return RawCallSite(**values)


def _support(**overrides) -> CallSupport:
    values = {
        "kind": "call_site",
        "file": SOURCE_FILE,
        "line": 4,
        "content_hash": SOURCE_HASH,
        "endpoint_id": CALLER_ID,
    }
    values.update(overrides)
    return CallSupport(**values)


def _resolved_record(**overrides) -> CallRecord:
    values = {
        "raw": _raw_call(),
        "caller_id": CALLER_ID,
        "caller_kind": "function",
        "target_file": SOURCE_FILE,
        "target_id": TARGET_ID,
        "target_kind": "function",
        "status": "resolved",
        "resolution": "exact",
        "unresolved_reason": None,
        "reference_unresolved_reason": None,
        "resolution_basis": "local_callable",
        "support": (
            _support(),
            _support(
                kind="caller_definition",
                line=3,
                content_hash=TARGET_HASH,
            ),
            _support(
                kind="local_definition",
                line=1,
                content_hash=TARGET_HASH,
                endpoint_id=TARGET_ID,
            ),
        ),
        "resolution_control_files": (),
        "resolution_configuration": None,
    }
    values.update(overrides)
    return CallRecord(**values)


def _symbol(
    *,
    symbol_id: str,
    name: str,
    kind: str,
    file_path: str = SOURCE_FILE,
    start: int,
    end: int,
    line: int,
    content_hash: str = TARGET_HASH,
) -> Symbol:
    return Symbol(
        id=symbol_id,
        name=name,
        qualified_name=name,
        kind=kind,
        language="python",
        file_path=file_path,
        byte_offset=start,
        byte_length=end - start,
        content_hash=content_hash,
        line=line,
        end_line=line,
    )


def _manual_symbols(*extra: Symbol) -> list[Symbol]:
    return [
        make_file_symbol(
            SOURCE_FILE,
            language="python",
            content_hash=SOURCE_HASH,
        ),
        _symbol(
            symbol_id=TARGET_ID,
            name="target",
            kind="function",
            start=0,
            end=20,
            line=1,
        ),
        _symbol(
            symbol_id=CALLER_ID,
            name="caller",
            kind="function",
            start=30,
            end=100,
            line=3,
        ),
        *extra,
    ]


def _resolve_source(
    tmp_path: Path,
    *,
    relative_path: str,
    language: str,
    source: str,
) -> tuple[list[CallRecord], list[Symbol]]:
    path = tmp_path / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")
    source_hash = hashlib.sha256(source.encode()).hexdigest()
    symbols = [
        make_file_symbol(
            relative_path,
            language=language,
            content_hash=source_hash,
        ),
        *(
            replace(
                symbol,
                id=make_symbol_id(
                    relative_path,
                    symbol.qualified_name,
                    symbol.kind,
                ),
                file_path=relative_path,
            )
            for symbol in parse_file(path)
        ),
    ]
    batch = extract_import_batch(
        path,
        source_file=relative_path,
        language=language,
        source_hash=source_hash,
    )
    return (
        resolve_calls(
            batch.calls,
            symbols=symbols,
            symbol_references=(),
            file_hashes={relative_path: source_hash},
        ),
        symbols,
    )


def _imported_call_fixture(
    tmp_path: Path,
    *,
    source_file: str,
    language: str,
    source: str,
    target_file: str,
    target_source: str,
    target_name: str,
    target_language: str | None = None,
    controls: tuple[str, ...] = (),
    configuration: str | None = None,
) -> tuple[RawCallSite, list[Symbol], SymbolReferenceRecord, dict[str, str]]:
    files = {
        source_file: (language, source),
        target_file: (target_language or language, target_source),
        f"decoy/{Path(target_file).name}": (
            target_language or language,
            target_source,
        ),
    }
    symbols: list[Symbol] = []
    hashes: dict[str, str] = {}
    source_batch = None
    for relative_path, (file_language, text) in files.items():
        path = tmp_path / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        source_hash = hashlib.sha256(text.encode()).hexdigest()
        hashes[relative_path] = source_hash
        symbols.append(
            make_file_symbol(
                relative_path,
                language=file_language,
                content_hash=source_hash,
            )
        )
        symbols.extend(
            replace(
                symbol,
                id=make_symbol_id(
                    relative_path,
                    symbol.qualified_name,
                    symbol.kind,
                ),
                file_path=relative_path,
            )
            for symbol in parse_file(path)
        )
        if relative_path == source_file:
            source_batch = extract_import_batch(
                path,
                source_file=relative_path,
                language=file_language,
                source_hash=source_hash,
            )

    assert source_batch is not None
    assert len(source_batch.calls) == 1
    call = source_batch.calls[0]
    reference = next(
        item
        for item in source_batch.references
        if (item.start_byte, item.end_byte)
        == (call.callee_start_byte, call.callee_end_byte)
    )
    target = next(
        symbol
        for symbol in symbols
        if symbol.file_path == target_file
        and symbol.name == target_name
        and symbol.kind == "function"
    )
    caller = next(
        symbol
        for symbol in symbols
        if symbol.file_path == source_file
        and symbol.kind == "function"
        and symbol.byte_offset == call.owner.definition_start_byte
    )
    binding = reference.candidate_bindings[0]
    record = SymbolReferenceRecord(
        raw=reference,
        binding=binding,
        source_id=caller.id,
        source_kind=caller.kind,
        import_source_id=f"{source_file}::__file__#file",
        import_target_id=f"{target_file}::__file__#file",
        target_file=target_file,
        target_id=target.id,
        target_kind=target.kind,
        status="resolved",
        unresolved_reason=None,
        import_unresolved_reason=None,
        resolution_basis=(
            "qualified_member" if len(reference.path) > 1 else "direct_binding"
        ),
        support=(
            ReferenceSupport(
                kind="import_binding",
                file=source_file,
                line=binding.import_line,
                content_hash=hashes[source_file],
                endpoint_id=f"{target_file}::__file__#file",
            ),
            ReferenceSupport(
                kind="definition",
                file=target_file,
                line=target.line,
                content_hash=hashes[target_file],
                endpoint_id=target.id,
            ),
        ),
        resolution_control_files=controls,
        resolution_configuration=configuration,
    )
    return call, symbols, record, hashes


def test_call_record_round_trips_exact_fields():
    record = _resolved_record()

    assert CallRecord.from_dict(record.to_dict()) == record
    assert CallSupport.from_dict(record.support[0].to_dict()) == record.support[0]


@pytest.mark.parametrize(
    "overrides",
    [
        {"target_id": None},
        {"unresolved_reason": "callee_not_proven"},
        {"resolution_basis": "imported_reference"},
        {"target_kind": "class"},
        {"target_file": "src/other.py"},
        {"resolution_control_files": ("tsconfig.json",)},
        {"caller_kind": "file", "caller_id": FILE_ID},
        {
            "raw": _raw_call(
                local_candidates=(),
                local_binding_state="absent",
            )
        },
    ],
)
def test_exact_call_record_rejects_inconsistent_outcomes(overrides):
    with pytest.raises(GraphContractError):
        _resolved_record(**overrides)


def test_call_record_rejects_unknown_fields():
    value = _resolved_record().to_dict()
    value["surprise"] = True

    with pytest.raises(GraphContractError, match="fields"):
        CallRecord.from_dict(value)


def test_call_record_rejects_unbounded_support():
    support = tuple(
        _support(line=line)
        for line in range(1, MAX_CALL_SUPPORT_RECORDS + 2)
    )

    with pytest.raises(GraphContractError, match="limit"):
        _resolved_record(support=support)


@pytest.mark.parametrize(
    ("relative_path", "language", "source"),
    [
        (
            "src/example.py",
            "python",
            "def target():\n    pass\n\ndef caller():\n    target()\n",
        ),
        (
            "src/example.js",
            "javascript",
            "function target() {}\nfunction caller() { target(); }\n",
        ),
        (
            "src/example.ts",
            "typescript",
            "function target(): void {}\nfunction caller(): void { target(); }\n",
        ),
        (
            "src/example.go",
            "go",
            "package example\nfunc target() {}\nfunc caller() { target() }\n",
        ),
        (
            "src/example.rs",
            "rust",
            "fn target() {}\nfn caller() { target(); }\n",
        ),
    ],
)
def test_resolves_exact_same_file_calls_for_supported_languages(
    tmp_path: Path,
    relative_path: str,
    language: str,
    source: str,
):
    records, _ = _resolve_source(
        tmp_path,
        relative_path=relative_path,
        language=language,
        source=source,
    )

    assert len(records) == 1
    record = records[0]
    assert record.status == "resolved"
    assert record.resolution == "exact"
    assert record.resolution_basis == "local_callable"
    assert record.target_file == relative_path
    assert record.target_kind == "function"
    assert record.target_id is not None
    assert record.target_id.endswith("::target#function")
    assert [support.kind for support in record.support] == [
        "call_site",
        "caller_definition",
        "local_definition",
    ]


def test_resolves_forward_lexical_declaration(tmp_path: Path):
    records, _ = _resolve_source(
        tmp_path,
        relative_path="src/example.js",
        language="javascript",
        source=(
            "function caller() { return later(); }\n"
            "function later() { return 1; }\n"
        ),
    )

    assert [(record.raw.callee_text, record.status) for record in records] == [
        ("later", "resolved")
    ]


def test_resolves_nested_function_and_recursion(tmp_path: Path):
    records, _ = _resolve_source(
        tmp_path,
        relative_path=SOURCE_FILE,
        language="python",
        source=(
            "def recurse():\n"
            "    recurse()\n\n"
            "def outer():\n"
            "    def inner():\n"
            "        return 1\n"
            "    return inner()\n"
        ),
    )

    by_name = {record.raw.callee_text: record for record in records}
    assert by_name["recurse"].caller_id == by_name["recurse"].target_id
    assert by_name["inner"].status == "resolved"
    assert by_name["inner"].target_id is not None
    assert by_name["inner"].target_id.endswith("::outer.inner#function")


def test_resolves_file_level_initialization(tmp_path: Path):
    records, _ = _resolve_source(
        tmp_path,
        relative_path=SOURCE_FILE,
        language="python",
        source="def target():\n    return 1\n\nVALUE = target()\n",
    )

    assert records[0].status == "resolved"
    assert records[0].caller_id == FILE_ID
    assert records[0].caller_kind == "file"
    assert [support.kind for support in records[0].support] == [
        "call_site",
        "local_definition",
    ]


def test_resolves_method_only_from_an_exact_bare_binding():
    raw = _raw_call(
        local_candidates=(_binding(callable_kind="method"),),
    )
    target = _symbol(
        symbol_id=f"{SOURCE_FILE}::Runner.target#method",
        name="target",
        kind="method",
        start=0,
        end=20,
        line=1,
    )
    records = resolve_calls(
        (raw,),
        symbols=[_manual_symbols()[0], _manual_symbols()[2], target],
        symbol_references=(),
        file_hashes={SOURCE_FILE: SOURCE_HASH},
    )

    assert records[0].status == "resolved"
    assert records[0].target_kind == "method"


@pytest.mark.parametrize(
    ("source", "expected_reason"),
    [
        (
            "def target():\n    pass\n\ndef caller(target):\n    target()\n",
            "local_binding_shadowed",
        ),
        (
            "def target():\n    pass\ndef target():\n    pass\ntarget()\n",
            "local_binding_ambiguous",
        ),
        (
            (
                "def target():\n"
                "    pass\n"
                "def caller():\n"
                "    target = object()\n"
                "    target()\n"
            ),
            "local_binding_shadowed",
        ),
        (
            "from other import target\ndef caller():\n    target()\n",
            "callee_not_proven",
        ),
        (
            "def target():\n    pass\ncaller = lambda: target()\n",
            "caller_not_indexed",
        ),
    ],
)
def test_uncertain_python_calls_fail_closed(
    tmp_path: Path,
    source: str,
    expected_reason: str,
):
    records, _ = _resolve_source(
        tmp_path,
        relative_path=SOURCE_FILE,
        language="python",
        source=source,
    )

    record = next(record for record in records if record.raw.callee_text == "target")
    assert record.status == "unresolved"
    assert record.unresolved_reason == expected_reason
    assert record.target_id is None
    assert record.resolution is None


def test_go_type_conversion_does_not_become_a_call_edge(tmp_path: Path):
    records, _ = _resolve_source(
        tmp_path,
        relative_path="src/example.go",
        language="go",
        source=(
            "package example\n"
            "type Number int\n"
            "func caller() { _ = Number(1) }\n"
        ),
    )

    assert records[0].status == "unresolved"
    assert records[0].unresolved_reason == "local_binding_shadowed"


def test_repository_wide_same_name_decoy_cannot_resolve_local_target():
    decoy = _symbol(
        symbol_id="src/decoy.py::target#function",
        name="target",
        kind="function",
        file_path="src/decoy.py",
        start=0,
        end=20,
        line=1,
    )
    symbols = [
        symbol
        for symbol in _manual_symbols(decoy)
        if symbol.id != TARGET_ID
    ]

    records = resolve_calls(
        (_raw_call(),),
        symbols=symbols,
        symbol_references=(),
        file_hashes={SOURCE_FILE: SOURCE_HASH, "src/decoy.py": SOURCE_HASH},
    )

    assert records[0].status == "unresolved"
    assert records[0].unresolved_reason == "local_target_not_indexed"


def test_same_span_non_callable_cannot_resolve_local_target():
    non_callable = _symbol(
        symbol_id=f"{SOURCE_FILE}::target#class",
        name="target",
        kind="class",
        start=0,
        end=20,
        line=1,
    )
    symbols = [
        symbol
        for symbol in _manual_symbols(non_callable)
        if symbol.id != TARGET_ID
    ]

    records = resolve_calls(
        (_raw_call(),),
        symbols=symbols,
        symbol_references=(),
        file_hashes={SOURCE_FILE: SOURCE_HASH},
    )

    assert records[0].status == "unresolved"
    assert records[0].unresolved_reason == "local_target_not_indexed"


def test_duplicate_indexed_call_owner_is_ambiguous():
    duplicate_owner = _symbol(
        symbol_id=f"{SOURCE_FILE}::Runner.caller#method",
        name="caller",
        kind="method",
        start=30,
        end=100,
        line=3,
    )

    records = resolve_calls(
        (_raw_call(),),
        symbols=_manual_symbols(duplicate_owner),
        symbol_references=(),
        file_hashes={SOURCE_FILE: SOURCE_HASH},
    )

    assert records[0].status == "unresolved"
    assert records[0].unresolved_reason == "caller_ambiguous"


def test_duplicate_indexed_local_target_is_ambiguous():
    duplicate_target = _symbol(
        symbol_id=f"{SOURCE_FILE}::other.target#function",
        name="target",
        kind="function",
        start=0,
        end=20,
        line=1,
    )

    records = resolve_calls(
        (_raw_call(),),
        symbols=_manual_symbols(duplicate_target),
        symbol_references=(),
        file_hashes={SOURCE_FILE: SOURCE_HASH},
    )

    assert records[0].status == "unresolved"
    assert records[0].unresolved_reason == "local_binding_ambiguous"


def test_dynamic_and_unproven_import_like_calls_remain_unresolved():
    dynamic = _raw_call(
        callee_text="items[0]",
        callee_path=(),
        callee_form="dynamic",
        local_candidates=(),
        local_binding_state="unsupported",
    )
    imported = _raw_call(
        local_candidates=(),
        local_binding_state="absent",
    )

    records = resolve_calls(
        (dynamic, imported),
        symbols=_manual_symbols(),
        symbol_references=(),
        file_hashes={SOURCE_FILE: SOURCE_HASH},
    )

    assert [record.unresolved_reason for record in records] == [
        "unsupported_callee",
        "callee_not_proven",
    ]


def test_missing_or_stale_file_hash_is_a_contract_error():
    with pytest.raises(GraphContractError, match="source evidence"):
        resolve_calls(
            (_raw_call(),),
            symbols=_manual_symbols(),
            symbol_references=(),
            file_hashes={SOURCE_FILE: "c" * 64},
        )


@pytest.mark.parametrize(
    (
        "source_file",
        "language",
        "source",
        "target_file",
        "target_source",
        "target_name",
        "controls",
        "configuration",
    ),
    [
        (
            "app.py",
            "python",
            "from lib import target as alias\n\ndef caller():\n    return alias()\n",
            "lib.py",
            "def target():\n    return 1\n",
            "target",
            (),
            None,
        ),
        (
            "src/app.ts",
            "typescript",
            (
                'import * as lib from "./lib.js";\n'
                "export function caller(): number { return lib.target(); }\n"
            ),
            "src/lib.ts",
            "export function target(): number { return 1; }\n",
            "target",
            ("tsconfig.json",),
            None,
        ),
        (
            "cmd/app/main.go",
            "go",
            (
                "package main\n"
                'import api "example.com/project/api"\n'
                "func caller() { api.Target() }\n"
            ),
            "api/api.go",
            "package api\nfunc Target() {}\n",
            "Target",
            (),
            None,
        ),
        (
            "src/lib.rs",
            "rust",
            "use crate::api;\npub fn caller() { api::target(); }\n",
            "src/api.rs",
            "pub fn target() {}\n",
            "target",
            ("Cargo.toml",),
            "declared_possible",
        ),
    ],
)
def test_resolves_imported_calls_only_through_exact_stage_10_reference(
    tmp_path: Path,
    source_file: str,
    language: str,
    source: str,
    target_file: str,
    target_source: str,
    target_name: str,
    controls: tuple[str, ...],
    configuration: str | None,
):
    call, symbols, reference, hashes = _imported_call_fixture(
        tmp_path,
        source_file=source_file,
        language=language,
        source=source,
        target_file=target_file,
        target_source=target_source,
        target_name=target_name,
        controls=controls,
        configuration=configuration,
    )

    records = resolve_calls(
        (call,),
        symbols=symbols,
        symbol_references=(reference,),
        file_hashes=hashes,
    )

    assert len(records) == 1
    record = records[0]
    assert record.status == "resolved"
    assert record.resolution == "import-resolved"
    assert record.resolution_basis == "imported_reference"
    assert record.target_file == reference.target_file
    assert record.target_id == reference.target_id
    assert record.target_kind == "function"
    assert record.resolution_control_files == reference.resolution_control_files
    assert record.resolution_configuration == reference.resolution_configuration
    assert [item.kind for item in record.support] == [
        "call_site",
        "caller_definition",
        "symbol_reference",
    ]
    assert record.support[-1] == CallSupport(
        kind="symbol_reference",
        file=reference.raw.source_file,
        line=reference.raw.line,
        content_hash=reference.raw.source_hash,
        endpoint_id=reference.target_id,
    )
    assert CallRecord.from_dict(record.to_dict()) == record


@pytest.mark.parametrize(
    "reference_reason",
    [
        "import_unresolved",
        "binding_shadowed",
        "ambiguous_binding",
        "ambiguous_source",
        "target_not_indexed",
        "target_inaccessible",
        "ambiguous_target",
        "unsupported_reference",
        "configuration_divergent",
    ],
)
def test_unresolved_stage_10_reason_is_preserved_separately(
    tmp_path: Path,
    reference_reason: str,
):
    call, symbols, reference, hashes = _imported_call_fixture(
        tmp_path,
        source_file="app.py",
        language="python",
        source="from lib import target\n\ndef caller():\n    target()\n",
        target_file="lib.py",
        target_source="def target():\n    pass\n",
        target_name="target",
    )
    unresolved_reference = replace(
        reference,
        target_file=None,
        target_id=None,
        target_kind=None,
        status="unresolved",
        unresolved_reason=reference_reason,
        resolution_basis=None,
        resolution_control_files=(),
        resolution_configuration=None,
    )

    record = resolve_calls(
        (call,),
        symbols=symbols,
        symbol_references=(unresolved_reference,),
        file_hashes=hashes,
    )[0]

    assert record.status == "unresolved"
    assert record.unresolved_reason == "reference_unresolved"
    assert record.reference_unresolved_reason == reference_reason


def test_typescript_call_accepts_stage_10_javascript_target(tmp_path: Path):
    call, symbols, reference, hashes = _imported_call_fixture(
        tmp_path,
        source_file="src/app.ts",
        language="typescript",
        source=(
            'import {target} from "./lib.js";\n'
            "export function caller(): number { return target(); }\n"
        ),
        target_file="src/lib.js",
        target_language="javascript",
        target_source="export function target() { return 1; }\n",
        target_name="target",
    )

    record = resolve_calls(
        (call,),
        symbols=symbols,
        symbol_references=(reference,),
        file_hashes=hashes,
    )[0]

    assert record.status == "resolved"
    assert record.target_file == "src/lib.js"


def test_non_callable_and_type_only_stage_10_targets_do_not_resolve(
    tmp_path: Path,
):
    call, symbols, reference, hashes = _imported_call_fixture(
        tmp_path,
        source_file="src/app.ts",
        language="typescript",
        source=(
            'import {target} from "./lib.js";\n'
            "export function caller(): void { target(); }\n"
        ),
        target_file="src/lib.ts",
        target_source=(
            "export class Builder {}\n"
            "export function target(): void {}\n"
        ),
        target_name="target",
    )
    assert reference.binding is not None
    type_binding = replace(reference.binding, type_only=True)
    type_raw = replace(reference.raw, candidate_bindings=(type_binding,))
    type_reference = replace(reference, raw=type_raw, binding=type_binding)
    non_callable_target = next(
        symbol
        for symbol in symbols
        if symbol.file_path == "src/lib.ts" and symbol.name == "Builder"
    )
    non_callable_reference = replace(
        reference,
        target_id=non_callable_target.id,
        target_kind=non_callable_target.kind,
        support=tuple(
            replace(item, endpoint_id=non_callable_target.id)
            if item.kind == "definition"
            else item
            for item in reference.support
        ),
    )

    type_only = resolve_calls(
        (call,),
        symbols=symbols,
        symbol_references=(type_reference,),
        file_hashes=hashes,
    )[0]
    non_callable = resolve_calls(
        (call,),
        symbols=symbols,
        symbol_references=(non_callable_reference,),
        file_hashes=hashes,
    )[0]

    assert type_only.unresolved_reason == "callee_not_proven"
    assert non_callable.unresolved_reason == "target_not_callable"


def test_reference_join_rejects_span_mismatch_and_multiple_exact_records(
    tmp_path: Path,
):
    call, symbols, reference, hashes = _imported_call_fixture(
        tmp_path,
        source_file="app.py",
        language="python",
        source="from lib import target\n\ndef caller():\n    target()\n",
        target_file="lib.py",
        target_source="def target():\n    pass\n",
        target_name="target",
    )
    mismatched = replace(
        reference,
        raw=replace(
            reference.raw,
            start_byte=reference.raw.start_byte + 1,
        ),
    )

    no_match = resolve_calls(
        (call,),
        symbols=symbols,
        symbol_references=(mismatched,),
        file_hashes=hashes,
    )[0]
    conflicting = resolve_calls(
        (call,),
        symbols=symbols,
        symbol_references=(reference, reference),
        file_hashes=hashes,
    )[0]

    assert no_match.unresolved_reason == "callee_not_proven"
    assert conflicting.unresolved_reason == "callee_not_proven"

    stale = replace(
        reference,
        raw=replace(reference.raw, source_hash="c" * 64),
    )
    with pytest.raises(GraphContractError, match="reference evidence"):
        resolve_calls(
            (call,),
            symbols=symbols,
            symbol_references=(stale,),
            file_hashes=hashes,
        )


def test_local_and_imported_proof_conflict_fails_closed(tmp_path: Path):
    call, symbols, reference, hashes = _imported_call_fixture(
        tmp_path,
        source_file="app.py",
        language="python",
        source="from lib import target\n\ndef caller():\n    target()\n",
        target_file="lib.py",
        target_source="def target():\n    pass\n",
        target_name="target",
    )
    local = _symbol(
        symbol_id="app.py::target#function",
        name="target",
        kind="function",
        file_path="app.py",
        start=0,
        end=20,
        line=1,
        content_hash=hashes["app.py"],
    )
    local_binding = _binding(
        name="target",
        definition_start_byte=local.byte_offset,
        definition_end_byte=local.byte_offset + local.byte_length,
        definition_line=local.line,
    )
    conflicting_call = replace(
        call,
        local_candidates=(local_binding,),
        local_binding_state="definite",
    )

    record = resolve_calls(
        (conflicting_call,),
        symbols=(*symbols, local),
        symbol_references=(reference,),
        file_hashes=hashes,
    )[0]

    assert record.status == "unresolved"
    assert record.unresolved_reason == "conflicting_resolution"
