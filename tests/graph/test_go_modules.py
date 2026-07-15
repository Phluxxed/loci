from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

import loci.graph.go_modules as go_modules
from loci.graph.contracts import GraphContractError
from loci.graph.go_modules import (
    GoExclusion,
    GoReplacement,
    GoRequirement,
    load_go_module_context,
)


def test_loader_parses_go_mod_directives_and_blocks(tmp_path: Path):
    go_mod = tmp_path / "go.mod"
    go_mod.write_text(
        """
module (
    "example.com/proj\\ect"
)

require (
    example.com/z v1.2.0 // indirect
    `example.com/a` `v1.0.0`
)
exclude example.com/z v1.1.0
replace (
    example.com/a => ./local/a
    example.com/z v1.2.0 => "example.com/fork/z" "v1.2.1"
)
toolchain go1.23.0
""".lstrip(),
        encoding="utf-8",
    )

    loaded = load_go_module_context(tmp_path, [go_mod])

    assert loaded.problems == ()
    assert loaded.input_hashes == {
        "go.mod": hashlib.sha256(go_mod.read_bytes()).hexdigest(),
    }
    assert len(loaded.context.modules) == 1
    module = loaded.context.modules[0]
    assert module.source == "go.mod"
    assert module.root == "."
    assert module.module_path == "example.com/project"
    assert module.requirements == (
        GoRequirement("example.com/a", "v1.0.0"),
        GoRequirement("example.com/z", "v1.2.0"),
    )
    assert module.exclusions == (GoExclusion("example.com/z", "v1.1.0"),)
    assert module.replacements == (
        GoReplacement(
            module_path="example.com/a",
            version=None,
            local_root="local/a",
            remote_path=None,
            remote_version=None,
        ),
        GoReplacement(
            module_path="example.com/z",
            version="v1.2.0",
            local_root=None,
            remote_path="example.com/fork/z",
            remote_version="v1.2.1",
        ),
    )


def test_loader_parses_go_work_use_and_replace_blocks(tmp_path: Path):
    go_work = tmp_path / "go.work"
    go_work.write_text(
        """
go 1.23.0
use (
    ./app // primary
    `./lib`
)
replace (
    example.com/old => ./local/old
    example.com/remote v1.0.0 => example.com/fork v1.1.0
)
godebug default=go1.21
""".lstrip(),
        encoding="utf-8",
    )

    loaded = load_go_module_context(tmp_path, [go_work])

    assert loaded.problems == ()
    assert loaded.context.modules == ()
    assert len(loaded.context.workspaces) == 1
    workspace = loaded.context.workspaces[0]
    assert workspace.source == "go.work"
    assert workspace.root == "."
    assert workspace.go_version == "1.23.0"
    assert workspace.use_roots == ("app", "lib")
    assert workspace.replacements == (
        GoReplacement(
            module_path="example.com/old",
            version=None,
            local_root="local/old",
            remote_path=None,
            remote_version=None,
        ),
        GoReplacement(
            module_path="example.com/remote",
            version="v1.0.0",
            local_root=None,
            remote_path="example.com/fork",
            remote_version="v1.1.0",
        ),
    )


@pytest.mark.parametrize(
    ("content", "reason"),
    [
        ("require example.com/a v1.0.0\n", "module_directive_count"),
        ("module example.com/a\nmodule example.com/b\n", "module_directive_count"),
        ("module example.com/a\nrequire example.com/b\n", "invalid_require"),
        ("module example.com/a\nrequire (\nexample.com/b v1.0.0\n", "unterminated_block"),
        ("module \"example.com/a\n", "unterminated_string"),
        ("module example.com/a /* bad */\n", "block_comments_not_allowed"),
        ("module example.com/a\n)\n", "unexpected_block_close"),
    ],
)
def test_loader_rejects_malformed_go_mod_as_one_problem(
    tmp_path: Path,
    content: str,
    reason: str,
):
    go_mod = tmp_path / "go.mod"
    go_mod.write_text(content, encoding="utf-8")

    loaded = load_go_module_context(tmp_path, [go_mod])

    assert loaded.context.modules == ()
    assert len(loaded.problems) == 1
    assert loaded.problems[0].code == "GRAPH_GO_MODULE_INVALID"
    assert loaded.problems[0].source == "go.mod"
    assert loaded.problems[0].details["reason"] == reason
    assert loaded.input_hashes["go.mod"] == hashlib.sha256(
        go_mod.read_bytes()
    ).hexdigest()


@pytest.mark.parametrize(
    ("content", "reason"),
    [
        ("use ./app\n", "go_directive_count"),
        ("go 1.22\ngo 1.23\nuse ./app\n", "go_directive_count"),
        ("go latest\nuse ./app\n", "invalid_go_version"),
        ("go 1.23\nuse ./app extra\n", "invalid_use"),
        ("go 1.23\nmodule example.com/a\n", "module_directive_in_go_work"),
    ],
)
def test_loader_rejects_malformed_go_work_as_one_problem(
    tmp_path: Path,
    content: str,
    reason: str,
):
    go_work = tmp_path / "go.work"
    go_work.write_text(content, encoding="utf-8")

    loaded = load_go_module_context(tmp_path, [go_work])

    assert loaded.context.workspaces == ()
    assert len(loaded.problems) == 1
    assert loaded.problems[0].code == "GRAPH_GO_WORKSPACE_INVALID"
    assert loaded.problems[0].source == "go.work"
    assert loaded.problems[0].details["reason"] == reason


def test_loader_rejects_control_symlink_outside_path_and_oversized_file_without_reading(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    outside = tmp_path.parent / f"{tmp_path.name}-outside"
    outside.mkdir()
    outside_go_mod = outside / "go.mod"
    outside_go_mod.write_text("module example.com/outside\n", encoding="utf-8")

    linked_dir = tmp_path / "linked"
    linked_dir.mkdir()
    linked_go_mod = linked_dir / "go.mod"
    linked_go_mod.symlink_to(outside_go_mod)

    large_dir = tmp_path / "large"
    large_dir.mkdir()
    large_go_work = large_dir / "go.work"
    large_go_work.write_bytes(b"x" * (go_modules.MAX_GO_CONTROL_BYTES + 1))

    def fail_if_read(*args: object, **kwargs: object) -> tuple[bytes, str]:
        raise AssertionError("invalid control candidate was read")

    monkeypatch.setattr(go_modules, "read_contained_file", fail_if_read)

    loaded = load_go_module_context(
        tmp_path,
        [outside_go_mod, linked_go_mod, large_go_work],
    )

    assert loaded.context == go_modules.GoModuleContext((), ())
    assert [(problem.source, problem.details["reason"]) for problem in loaded.problems] == [
        ("@outside/go.mod", "outside_repository"),
        ("large/go.work", "control_file_too_large"),
        ("linked/go.mod", "symlink"),
    ]
    assert loaded.problems[1].code == "GRAPH_GO_INDEX_LIMIT_EXCEEDED"
    assert all(len(value) == 64 for value in loaded.input_hashes.values())


def test_loader_rejects_invalid_utf8_and_preserves_content_hash(tmp_path: Path):
    go_mod = tmp_path / "go.mod"
    go_mod.write_bytes(b"module example.com/a\n\xff")

    loaded = load_go_module_context(tmp_path, [go_mod])

    assert loaded.context.modules == ()
    assert loaded.problems[0].details == {"reason": "invalid_utf8"}
    assert loaded.input_hashes["go.mod"] == hashlib.sha256(
        go_mod.read_bytes()
    ).hexdigest()


def test_loader_rejects_directive_limit_without_partial_context(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    go_mod = tmp_path / "go.mod"
    go_mod.write_text(
        """
module example.com/a
require (
    example.com/b v1.0.0
    example.com/c v1.0.0
)
""".lstrip(),
        encoding="utf-8",
    )
    monkeypatch.setattr(go_modules, "MAX_GO_DIRECTIVES_PER_FILE", 2)

    loaded = load_go_module_context(tmp_path, [go_mod])

    assert loaded.context.modules == ()
    assert loaded.problems[0].code == "GRAPH_GO_INDEX_LIMIT_EXCEEDED"
    assert loaded.problems[0].details["reason"] == "directive_limit_exceeded"
    assert loaded.problems[0].details["limit"] == 2


def test_loader_treats_explicit_outside_roots_as_non_local(tmp_path: Path):
    go_mod = tmp_path / "go.mod"
    go_mod.write_text(
        """
module example.com/a
replace example.com/b => ../outside
""".lstrip(),
        encoding="utf-8",
    )
    go_work = tmp_path / "go.work"
    go_work.write_text(
        """
go 1.23
use ../outside
""".lstrip(),
        encoding="utf-8",
    )

    loaded = load_go_module_context(tmp_path, [go_work, go_mod])

    assert loaded.problems == ()
    assert loaded.context.modules[0].replacements == (
        GoReplacement("example.com/b", None, None, None, None),
    )
    assert loaded.context.workspaces[0].use_roots == ()


def test_loader_rejects_lexically_contained_symlink_escape(tmp_path: Path):
    outside = tmp_path.parent / f"{tmp_path.name}-replacement"
    outside.mkdir()
    (tmp_path / "linked").symlink_to(outside, target_is_directory=True)
    go_mod = tmp_path / "go.mod"
    go_mod.write_text(
        """
module example.com/a
replace example.com/b => ./linked
""".lstrip(),
        encoding="utf-8",
    )

    loaded = load_go_module_context(tmp_path, [go_mod])

    assert loaded.context.modules == ()
    assert loaded.problems[0].details["reason"] == "local_path_symlink_escape"
    assert str(outside) not in str(loaded.problems[0].details)


def test_loader_orders_nested_controls_and_hashes_deterministically(tmp_path: Path):
    a_dir = tmp_path / "a"
    b_dir = tmp_path / "b"
    a_dir.mkdir()
    b_dir.mkdir()
    a_mod = a_dir / "go.mod"
    b_mod = b_dir / "go.mod"
    a_mod.write_text("module example.com/a\n", encoding="utf-8")
    b_mod.write_text("module example.com/b\n", encoding="utf-8")

    loaded = load_go_module_context(tmp_path, [b_mod, a_mod])

    assert [module.source for module in loaded.context.modules] == [
        "a/go.mod",
        "b/go.mod",
    ]
    assert [module.root for module in loaded.context.modules] == ["a", "b"]
    assert list(loaded.input_hashes) == ["a/go.mod", "b/go.mod"]


def test_loader_rejects_quoted_directive_keyword(tmp_path: Path):
    go_mod = tmp_path / "go.mod"
    go_mod.write_text('"module" example.com/a\n', encoding="utf-8")

    loaded = load_go_module_context(tmp_path, [go_mod])

    assert loaded.context.modules == ()
    assert loaded.problems[0].details["reason"] == "invalid_directive_keyword"


def test_loader_rejects_block_form_go_directive(tmp_path: Path):
    go_work = tmp_path / "go.work"
    go_work.write_text(
        """
go (
    1.23
)
use ./app
""".lstrip(),
        encoding="utf-8",
    )

    loaded = load_go_module_context(tmp_path, [go_work])

    assert loaded.context.workspaces == ()
    assert loaded.problems[0].details["reason"] == "invalid_go_version"


def test_loader_classifies_growth_past_size_limit_as_limit_problem(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    go_mod = tmp_path / "go.mod"
    go_mod.write_text("module example.com/a\n", encoding="utf-8")

    def report_growth(*args: object, **kwargs: object) -> tuple[bytes, str]:
        raise GraphContractError(
            "INVALID_GRAPH_PROFILE",
            "Graph Go control file exceeds the size limit",
            {"source": "go.mod", "limit": go_modules.MAX_GO_CONTROL_BYTES},
        )

    monkeypatch.setattr(go_modules, "read_contained_file", report_growth)

    loaded = load_go_module_context(tmp_path, [go_mod])

    assert loaded.context.modules == ()
    assert loaded.problems[0].code == "GRAPH_GO_INDEX_LIMIT_EXCEEDED"
    assert loaded.problems[0].details == {
        "reason": "control_file_too_large",
        "limit": go_modules.MAX_GO_CONTROL_BYTES,
    }


def test_outside_candidate_cannot_shadow_contained_control(tmp_path: Path):
    inside_go_mod = tmp_path / "go.mod"
    inside_go_mod.write_text("module example.com/inside\n", encoding="utf-8")
    outside = tmp_path.parent / f"{tmp_path.name}-shadow"
    outside.mkdir()
    outside_go_mod = outside / "go.mod"
    outside_go_mod.write_text("module example.com/outside\n", encoding="utf-8")

    loaded = load_go_module_context(tmp_path, [inside_go_mod, outside_go_mod])

    assert [module.module_path for module in loaded.context.modules] == [
        "example.com/inside",
    ]
    assert [(problem.source, problem.details["reason"]) for problem in loaded.problems] == [
        ("@outside/go.mod", "outside_repository"),
    ]
    assert list(loaded.input_hashes) == ["@outside/go.mod", "go.mod"]
