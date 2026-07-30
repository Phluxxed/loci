from pathlib import PurePath

import pytest

from loci.indexability import (
    is_excluded_repository_path,
    is_indexable_source_path,
)


@pytest.mark.parametrize(
    "path",
    [
        "tests/test_widget.py",
        "__tests__/widget.test.ts",
        "src/widget_test.py",
        "pkg/widget_test.go",
        "tests/fixtures/sample.rs",
    ],
)
def test_maintained_test_and_fixture_source_is_indexable(path: str):
    assert is_indexable_source_path(PurePath(path))


@pytest.mark.parametrize(
    "path",
    [
        ".git/hooks/check.py",
        "src/__pycache__/module.py",
        "vendor/dependency.py",
        "dist/bundle.js",
        "target/debug/main.rs",
        "tmp/probe.py",
        "generated/client.py",
    ],
)
def test_disposable_repository_material_is_excluded(path: str):
    repository_path = PurePath(path)

    assert is_excluded_repository_path(repository_path)
    assert not is_indexable_source_path(repository_path)


@pytest.mark.parametrize(
    "path",
    [
        "src/data.json",
        "src/native.so",
        "src/credentials.json",
    ],
)
def test_non_source_or_sensitive_files_are_not_indexable(path: str):
    assert not is_indexable_source_path(PurePath(path))


@pytest.mark.parametrize(
    "path",
    [
        "/tmp/tests/repo/src/main.py",
        "../outside.py",
    ],
)
def test_indexability_policy_rejects_non_repository_relative_paths(path: str):
    with pytest.raises(ValueError, match="repository-relative"):
        is_indexable_source_path(PurePath(path))
