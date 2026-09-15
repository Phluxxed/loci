"""Bounded stdio transport for the installed Codex App Server.

No model request is made by construction/initialize/model-list. Every wire
message is journaled before reduction. The episode controller owns generation.
"""
from __future__ import annotations

from collections import deque
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import queue
import signal
import subprocess
import threading
import time
from typing import Any


class RuntimeFailure(RuntimeError):
    pass


class Journal:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.stream = path.open("x", encoding="utf-8")
        os.chmod(path, 0o600)
        self.lock = threading.Lock()
        self.ordinal = 0

    def write(self, direction: str, message: dict) -> dict:
        with self.lock:
            self.ordinal += 1
            row = {"ordinal": self.ordinal, "monotonic": time.monotonic(),
                   "utc": datetime.now(timezone.utc).isoformat(),
                   "direction": direction, "message": message}
            self.stream.write(json.dumps(row, ensure_ascii=False) + "\n")
            self.stream.flush()
            return row

    def close(self) -> None:
        with self.lock:
            self.stream.close()


class AppServer:
    """One subprocess, one connection, and no implicit request retry."""
    def __init__(self, command: list[str], journal: Journal, stderr: Path,
                 *, cwd: Path, env: dict[str, str] | None = None):
        self.journal = journal
        self.sequence = 0
        self.cleanup_errors: list[str] = []
        self.closed = False
        self.events: deque[dict] = deque()
        self.incoming: queue.Queue[Any] = queue.Queue()
        self.stderr = stderr.open("xb")
        os.chmod(stderr, 0o600)
        self.process = subprocess.Popen(
            command, cwd=cwd, env=env, stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=self.stderr, text=True,
            encoding="utf-8", bufsize=1, start_new_session=True,
        )
        self.reader = threading.Thread(target=self._read, daemon=True)
        self.reader.start()

    def _read(self) -> None:
        assert self.process.stdout is not None
        try:
            for line in self.process.stdout:
                try:
                    value = json.loads(line)
                except ValueError:
                    self.journal.write("received_invalid", {"raw_line": line})
                    raise
                if not isinstance(value, dict):
                    raise RuntimeFailure("app-server emitted a non-object")
                self.journal.write("received", value)
                self.incoming.put(value)
        except (ValueError, OSError, RuntimeFailure) as exc:
            self.incoming.put(RuntimeFailure(str(exc)))
        finally:
            self.incoming.put(RuntimeFailure("app-server stream closed"))

    def send(self, method: str, params: dict, *, request: bool = True) -> int | None:
        value: dict = {"method": method, "params": params}
        if request:
            self.sequence += 1
            value["id"] = self.sequence
        self.journal.write("sent", value)
        try:
            assert self.process.stdin is not None
            self.process.stdin.write(json.dumps(value) + "\n")
            self.process.stdin.flush()
        except (BrokenPipeError, OSError) as exc:
            raise RuntimeFailure("app-server request could not be sent") from exc
        return value.get("id")

    def _receive(self, timeout: float) -> dict:
        try:
            value = self.incoming.get(timeout=max(0, timeout))
        except queue.Empty as exc:
            raise TimeoutError("app-server response deadline") from exc
        if isinstance(value, Exception):
            raise value
        if "method" in value and "id" in value:
            # No approval, elicitation or dynamic-tool decision is delegated to
            # the benchmark controller. Such a request invalidates this run.
            raise RuntimeFailure(f"unexpected server request: {value['method']}")
        return value

    def call(self, method: str, params: dict, *, timeout: float = 30) -> Any:
        ident = self.send(method, params)
        deadline = time.monotonic() + timeout
        while True:
            value = self._receive(deadline - time.monotonic())
            if value.get("id") == ident:
                if "error" in value:
                    raise RuntimeFailure(f"{method}: {json.dumps(value['error'])}")
                if "result" not in value:
                    raise RuntimeFailure(f"{method}: missing result")
                return value["result"]
            if "id" in value:
                raise RuntimeFailure("unexpected response identity")
            self.events.append(value)

    def next_event(self, timeout: float) -> dict:
        if self.events:
            return self.events.popleft()
        value = self._receive(timeout)
        if "id" in value:
            raise RuntimeFailure("unexpected response outside request")
        return value

    def initialize(self) -> dict:
        result = self.call("initialize", {
            "clientInfo": {"name": "loci-complete-work", "version": "1"},
            "capabilities": {"experimentalApi": True},
        })
        self.send("initialized", {}, request=False)
        return result

    def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        if self.process.poll() is None:
            try:
                os.killpg(self.process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            except OSError as exc:
                self.cleanup_errors.append(str(exc))
            try:
                self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(self.process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                except OSError as exc:
                    self.cleanup_errors.append(str(exc))
                try:
                    self.process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    self.cleanup_errors.append("owned app-server process did not terminate after SIGKILL")
        self.reader.join(timeout=2)
        if self.reader.is_alive():
            self.cleanup_errors.append("app-server reader remained alive after close")
        self.stderr.close()


def toml_value(value: Any) -> str:
    """Encode only configuration values used here; never shell interpolation."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return json.dumps(value)
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, list):
        return "[" + ",".join(toml_value(x) for x in value) + "]"
    if isinstance(value, dict):
        return "{" + ",".join(json.dumps(k) + "=" + toml_value(v)
                              for k, v in value.items()) + "}"
    raise ValueError("unsupported config value")


def command_with_config(codex: str, overrides: dict[str, Any]) -> list[str]:
    command = [codex, "app-server", "--stdio"]
    for name, value in sorted(overrides.items()):
        command.extend(["-c", name + "=" + toml_value(value)])
    return command
