from __future__ import annotations

import hashlib
from pathlib import Path

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
