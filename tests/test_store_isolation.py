import json
import os
import subprocess
import sys
from pathlib import Path

from loci.storage.store_resolver import resolve_store_base_dir


def _suite_store_root() -> Path:
    return Path(os.environ["LOCI_BASE_DIR"]).resolve()


def test_default_resolution_uses_suite_store_boundary() -> None:
    root = _suite_store_root()

    resolution = resolve_store_base_dir()

    assert resolution.source == "env"
    assert resolution.base_dir.resolve() == root
    assert os.environ["LOCI_STORE_NAMESPACE"] == "pytest"
    assert root.name.startswith("loci-pytest-store-")


def test_child_process_inherits_suite_store_boundary() -> None:
    root = _suite_store_root()
    script = (
        "import json, os; "
        "from loci.storage.store_resolver import resolve_store_base_dir; "
        "resolution = resolve_store_base_dir(); "
        "print(json.dumps({'base_dir': str(resolution.base_dir.resolve()), "
        "'namespace': os.environ.get('LOCI_STORE_NAMESPACE')}))"
    )

    result = subprocess.run(
        [sys.executable, "-c", script],
        check=True,
        capture_output=True,
        text=True,
        env=os.environ.copy(),
    )

    assert json.loads(result.stdout) == {
        "base_dir": str(root),
        "namespace": "pytest",
    }


def test_mcp_binding_uses_inherited_suite_store_boundary() -> None:
    root = _suite_store_root()
    script = (
        "import json; "
        "from loci.storage.store_identity import bind_mcp_store; "
        "print(json.dumps(bind_mcp_store().to_dict(), sort_keys=True))"
    )

    result = subprocess.run(
        [sys.executable, "-c", script],
        check=True,
        capture_output=True,
        text=True,
        env=os.environ.copy(),
    )

    binding = json.loads(result.stdout)
    assert binding["base_dir"] == str(root)
    assert binding["namespace"] == "pytest"
    assert (root / ".loci-store.json").exists()


def test_resolver_override_restores_suite_boundary(
    monkeypatch,
    tmp_path: Path,
) -> None:
    suite_root = _suite_store_root()
    override = tmp_path / "override"
    monkeypatch.setenv("LOCI_BASE_DIR", str(override))

    assert resolve_store_base_dir().base_dir == override

    monkeypatch.undo()

    assert resolve_store_base_dir().base_dir.resolve() == suite_root
    assert os.environ["LOCI_STORE_NAMESPACE"] == "pytest"
