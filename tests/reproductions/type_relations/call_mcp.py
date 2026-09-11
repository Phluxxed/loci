"""Run the six existing call-MCP assertions through this checkout's wrapper.

The installed-wrapper assertion is inapplicable to an intentionally isolated
branch. A temporary command symlink replaces only tests.test_call_mcp._server;
all call behavior, restart, boundary-error and refresh assertions are unchanged.
The globally installed command and server registration are never modified.
"""
from __future__ import annotations

import os
from pathlib import Path
import tempfile

from mcp import StdioServerParameters
import pytest


class IsolatedWrapper:
    def __init__(self, command: Path, repo: Path):
        self.command, self.repo = command, repo

    def pytest_collection_modifyitems(self, items):
        for item in items:
            if item.module.__name__ == "tests.test_call_mcp":
                item.module._server = self.server

    def server(self, cache_dir: Path) -> StdioServerParameters:
        return StdioServerParameters(
            command=str(self.command), args=[], cwd=self.repo,
            env={**os.environ, "LOCI_BASE_DIR": str(cache_dir), "LOCI_STORE_NAMESPACE": "test"},
        )


def main() -> None:
    repo = Path(__file__).resolve().parents[3]
    with tempfile.TemporaryDirectory(prefix="loci-w23-wrapper-") as directory:
        command = Path(directory) / "loci-mcp"
        wrapper = repo / ".shared/loci-mcp-wrapper.sh"
        command.symlink_to(wrapper)
        assert command.is_file() and command.resolve() == wrapper.resolve()
        raise SystemExit(pytest.main([
            "-q", str(repo / "tests/test_call_mcp.py"),
        ], plugins=[IsolatedWrapper(command, repo)]))


if __name__ == "__main__":
    main()
