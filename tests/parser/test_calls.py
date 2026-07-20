from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
from tree_sitter import Parser
from tree_sitter_language_pack import get_language

from loci.parser._binding_context import (
    ExecutableOwner,
    collect_syntax_context,
)
from loci.parser.call_models import (
    MAX_CALL_BINDING_CANDIDATES,
    MAX_CALL_PATH_SEGMENTS,
    LocalCallableBinding,
    RawCallSite,
)
from loci.parser.calls import extract_call_sites
from loci.parser.imports import ImportExtractionBatch, extract_import_batch


SOURCE_HASH = "a" * 64


def _owner(**overrides) -> ExecutableOwner:
    values = {
        "kind": "callable",
        "definition_start_byte": 20,
        "definition_end_byte": 100,
        "body_start_byte": 40,
        "body_end_byte": 100,
    }
    values.update(overrides)
    return ExecutableOwner(**values)


def _binding(**overrides) -> LocalCallableBinding:
    values = {
        "name": "helper",
        "callable_kind": "function",
        "definition_start_byte": 20,
        "definition_end_byte": 38,
        "definition_line": 2,
        "scope_start_byte": 0,
        "scope_end_byte": 200,
    }
    values.update(overrides)
    return LocalCallableBinding(**values)


def _call(**overrides) -> RawCallSite:
    values = {
        "source_file": "src/use.py",
        "language": "python",
        "line": 5,
        "column": 5,
        "start_byte": 60,
        "end_byte": 68,
        "callee_start_byte": 60,
        "callee_end_byte": 66,
        "callee_text": "helper",
        "callee_path": ("helper",),
        "callee_form": "identifier",
        "local_candidates": (_binding(),),
        "local_binding_state": "definite",
        "owner": _owner(),
        "source_hash": SOURCE_HASH,
    }
    values.update(overrides)
    return RawCallSite(**values)


@pytest.mark.parametrize(
    "record",
    [
        _owner(),
        _owner(kind="unindexed"),
        ExecutableOwner(
            kind="file",
            definition_start_byte=None,
            definition_end_byte=None,
            body_start_byte=None,
            body_end_byte=None,
        ),
        _binding(),
        _call(),
    ],
)
def test_call_parser_models_round_trip_strictly(record):
    serialized = record.to_dict()

    assert type(record).from_dict(serialized) == record

    missing = dict(serialized)
    missing.pop(next(iter(missing)))
    with pytest.raises(ValueError, match="fields"):
        type(record).from_dict(missing)

    unknown = dict(serialized)
    unknown["unknown"] = True
    with pytest.raises(ValueError, match="fields"):
        type(record).from_dict(unknown)


@pytest.mark.parametrize(
    "overrides",
    [
        {"kind": "guess"},
        {"definition_start_byte": None},
        {"definition_end_byte": 20},
        {"body_start_byte": 19},
        {"body_end_byte": 101},
    ],
)
def test_executable_owner_rejects_impossible_callable_ranges(overrides):
    with pytest.raises(ValueError):
        _owner(**overrides)


def test_file_owner_rejects_definition_ranges():
    with pytest.raises(ValueError):
        _owner(
            kind="file",
            definition_start_byte=None,
            definition_end_byte=None,
            body_start_byte=0,
            body_end_byte=None,
        )

    assert ExecutableOwner(
        kind="file",
        definition_start_byte=None,
        definition_end_byte=None,
        body_start_byte=None,
        body_end_byte=None,
    ).kind == "file"


@pytest.mark.parametrize(
    "overrides",
    [
        {"name": ""},
        {"callable_kind": "class"},
        {"definition_start_byte": -1},
        {"definition_end_byte": 20},
        {"definition_line": 0},
        {"scope_start_byte": 201},
        {"scope_end_byte": 0},
    ],
)
def test_local_callable_binding_rejects_malformed_values(overrides):
    with pytest.raises(ValueError):
        _binding(**overrides)


@pytest.mark.parametrize(
    "overrides",
    [
        {"source_file": "/tmp/use.py"},
        {"language": "ruby"},
        {"line": 0},
        {"column": 0},
        {"end_byte": 60},
        {"callee_start_byte": 59},
        {"callee_end_byte": 69},
        {"callee_text": ""},
        {"callee_path": ()},
        {"callee_form": "dynamic", "callee_path": ("helper",)},
        {"callee_form": "guess"},
        {"local_candidates": [_binding()]},
        {"local_binding_state": "guess"},
        {"local_binding_state": "definite", "local_candidates": ()},
        {
            "local_binding_state": "ambiguous",
            "local_candidates": (_binding(),),
        },
        {"local_binding_state": "absent", "local_candidates": (_binding(),)},
        {"owner": "callable"},
        {"source_hash": "A" * 64},
    ],
)
def test_raw_call_site_rejects_malformed_or_impossible_states(overrides):
    with pytest.raises(ValueError):
        _call(**overrides)


def test_raw_call_site_enforces_path_and_candidate_limits():
    with pytest.raises(ValueError, match="path"):
        _call(
            callee_form="static_path",
            callee_path=tuple("part" for _ in range(MAX_CALL_PATH_SEGMENTS + 1)),
        )

    candidates = tuple(
        replace(_binding(), definition_start_byte=index, definition_end_byte=index + 1)
        for index in range(MAX_CALL_BINDING_CANDIDATES + 1)
    )
    with pytest.raises(ValueError, match="candidate"):
        _call(
            local_candidates=candidates,
            local_binding_state="ambiguous",
        )

    with pytest.raises(ValueError, match="unique"):
        _call(
            local_candidates=(_binding(), _binding()),
            local_binding_state="ambiguous",
        )


def _extract_calls(
    *,
    source: str,
    language: str,
    tree_sitter_language: str | None = None,
) -> tuple[RawCallSite, ...]:
    encoded = source.encode()
    root = Parser(get_language(tree_sitter_language or language)).parse(encoded).root_node
    context = collect_syntax_context(root, encoded, language)
    return extract_call_sites(
        root,
        encoded,
        source_file=f"src/example.{language}",
        language=language,
        source_hash=SOURCE_HASH,
        context=context,
    )


@pytest.mark.parametrize(
    ("language", "source", "expected"),
    [
        (
            "python",
            (
                "top()\n"
                "def helper(): pass\n"
                "def run(value=default()):\n"
                "    helper()\n"
                "    obj.work()\n"
                "    items[0]()\n"
                "    outer(inner())\n"
                "value = lambda: hidden()\n"
            ),
            [
                ("top", "identifier", "file", "absent"),
                ("default", "identifier", "file", "absent"),
                ("helper", "identifier", "callable", "definite"),
                ("obj.work", "static_path", "callable", "absent"),
                ("items[0]", "dynamic", "callable", "unsupported"),
                ("outer", "identifier", "callable", "absent"),
                ("inner", "identifier", "callable", "absent"),
                ("hidden", "identifier", "unindexed", "absent"),
            ],
        ),
        (
            "javascript",
            (
                "top();\n"
                "function helper() {}\n"
                "function run(value = defaultCall()) {\n"
                "  helper(); obj.work(); obj[key](); outer(inner());\n"
                "  obj?.optional(); callback?.(); obj.work?.();\n"
                "  const nested = () => hidden();\n"
                "}\n"
                "new Thing();\n"
            ),
            [
                ("top", "identifier", "file", "absent"),
                ("defaultCall", "identifier", "file", "absent"),
                ("helper", "identifier", "callable", "definite"),
                ("obj.work", "static_path", "callable", "absent"),
                ("obj[key]", "dynamic", "callable", "unsupported"),
                ("outer", "identifier", "callable", "absent"),
                ("inner", "identifier", "callable", "absent"),
                ("obj?.optional", "dynamic", "callable", "unsupported"),
                ("callback", "dynamic", "callable", "unsupported"),
                ("obj.work", "dynamic", "callable", "unsupported"),
                ("hidden", "identifier", "unindexed", "absent"),
            ],
        ),
        (
            "typescript",
            (
                "function helper(): void {}\n"
                "class Runner { run(): void { helper(); this.work(); } }\n"
                "const nested = (): void => hidden();\n"
                "top();\n"
            ),
            [
                ("helper", "identifier", "callable", "definite"),
                ("this.work", "static_path", "callable", "absent"),
                ("hidden", "identifier", "unindexed", "absent"),
                ("top", "identifier", "file", "absent"),
            ],
        ),
        (
            "go",
            (
                "package example\n"
                "func helper() {}\n"
                "func run() {\n"
                "  helper(); pkg.Work(); recv.Work(); outer(inner())\n"
                "  type Number int\n"
                "  Number(1)\n"
                "  nested := func() { hidden() }\n"
                "  _ = nested\n"
                "}\n"
                "var value = top()\n"
            ),
            [
                ("helper", "identifier", "callable", "definite"),
                ("pkg.Work", "static_path", "callable", "absent"),
                ("recv.Work", "static_path", "callable", "absent"),
                ("outer", "identifier", "callable", "absent"),
                ("inner", "identifier", "callable", "absent"),
                ("Number", "identifier", "callable", "shadowed"),
                ("hidden", "identifier", "unindexed", "absent"),
                ("top", "identifier", "file", "absent"),
            ],
        ),
        (
            "rust",
            (
                "struct Thing;\n"
                "fn helper() {}\n"
                "fn run() {\n"
                "  helper(); Thing(); crate::other(); value.work(); outer(inner());\n"
                "  let nested = || hidden();\n"
                "  println!(\"ignored\");\n"
                "}\n"
                "const VALUE: i32 = top();\n"
            ),
            [
                ("helper", "identifier", "callable", "definite"),
                ("Thing", "identifier", "callable", "shadowed"),
                ("crate::other", "static_path", "callable", "absent"),
                ("value.work", "dynamic", "callable", "unsupported"),
                ("outer", "identifier", "callable", "absent"),
                ("inner", "identifier", "callable", "absent"),
                ("hidden", "identifier", "unindexed", "absent"),
                ("top", "identifier", "file", "absent"),
            ],
        ),
    ],
)
def test_extracts_bounded_call_sites_with_exact_forms_and_owners(
    language: str,
    source: str,
    expected: list[tuple[str, str, str, str]],
):
    calls = _extract_calls(source=source, language=language)

    assert [
        (
            call.callee_text,
            call.callee_form,
            call.owner.kind,
            call.local_binding_state,
        )
        for call in calls
    ] == expected
    assert list(calls) == sorted(
        calls,
        key=lambda call: (
            call.source_file,
            call.start_byte,
            call.end_byte,
            call.callee_start_byte,
            call.callee_end_byte,
        ),
    )
    for call in calls:
        encoded = source.encode()
        assert encoded[call.start_byte : call.end_byte].endswith(b")")
        assert (
            encoded[call.callee_start_byte : call.callee_end_byte].decode()
            == call.callee_text
        )
        assert call.line == source.count("\n", 0, call.start_byte) + 1
        line_start = source.rfind("\n", 0, call.start_byte) + 1
        assert call.column == call.start_byte - line_start + 1


def test_python_owner_uses_indexed_definition_span_and_body_only():
    source = (
        "@decorate(factory())\n"
        "def run(value=default()):\n"
        "    body()\n"
        "nested = lambda: hidden()\n"
    )

    calls = _extract_calls(source=source, language="python")
    by_callee = {call.callee_text: call for call in calls}

    assert by_callee["decorate"].owner.kind == "file"
    assert by_callee["factory"].owner.kind == "file"
    assert by_callee["default"].owner.kind == "file"
    assert by_callee["body"].owner == ExecutableOwner(
        kind="callable",
        definition_start_byte=source.index("@decorate"),
        definition_end_byte=source.index("\nnested"),
        body_start_byte=source.index("body()"),
        body_end_byte=source.index("\nnested"),
    )
    assert by_callee["hidden"].owner.kind == "unindexed"


def test_call_site_limit_fails_atomically(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("loci.parser.calls.MAX_CALL_SITES_PER_FILE", 1)

    with pytest.raises(ValueError, match="per-file limit"):
        _extract_calls(source="one()\ntwo()\n", language="python")


def test_static_callee_path_limit_fails_atomically():
    path = ".".join(
        ["root", *(f"part{index}" for index in range(MAX_CALL_PATH_SEGMENTS))]
    )

    with pytest.raises(ValueError, match="path"):
        _extract_calls(source=f"{path}()\n", language="python")


def test_tsx_uses_the_typescript_call_contract(tmp_path: Path):
    source = "function App(): JSX.Element { return render(<Thing />); }\n"
    path = tmp_path / "app.tsx"
    path.write_text(source, encoding="utf-8")

    batch = extract_import_batch(
        path,
        source_file="src/app.tsx",
        language="typescript",
        source_hash=SOURCE_HASH,
    )

    assert [call.callee_text for call in batch.calls] == ["render"]
    assert batch.calls[0].owner.kind == "callable"


def test_import_batch_reuses_one_parse_and_returns_calls(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    import tree_sitter

    source = "from helper import work\ndef run():\n    work()\n"
    path = tmp_path / "use.py"
    path.write_text(source, encoding="utf-8")
    real_parser = tree_sitter.Parser
    parse_count = 0

    class CountingParser:
        def __init__(self, language):
            self._parser = real_parser(language)

        def parse(self, content):
            nonlocal parse_count
            parse_count += 1
            return self._parser.parse(content)

    monkeypatch.setattr(tree_sitter, "Parser", CountingParser)

    batch = extract_import_batch(
        path,
        source_file="src/use.py",
        language="python",
        source_hash=SOURCE_HASH,
    )

    assert parse_count == 1
    assert isinstance(batch, ImportExtractionBatch)
    assert [call.callee_text for call in batch.calls] == ["work"]
    assert batch.references[0].start_byte == batch.calls[0].callee_start_byte
    assert batch.references[0].end_byte == batch.calls[0].callee_end_byte
