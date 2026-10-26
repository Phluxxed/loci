"""Persistent, bounded aliases for exact source locators.

The store deliberately only keeps opaque locator payloads.  It does not make a
source locator valid or grant access to a source; :mod:`loci.retrieval_io`
continues to perform that validation when a resolved locator is used.
"""
from __future__ import annotations

import base64
from contextlib import closing
import hashlib
import json
from pathlib import Path
import re
import sqlite3
from typing import Any, Iterable, Mapping

from loci.graph.contracts import GraphContractError
from loci.storage.index_store import IndexStore


_HANDLE_RE = re.compile(r"sr1_[a-z2-7]{26}")
_DEFAULT_MAX_REFERENCES = 8192
_DEFAULT_MAX_PAYLOAD_BYTES = 8 * 1024 * 1024
_BUSY_TIMEOUT_MS = 5_000


def is_source_handle(reference: str) -> bool:
    """Whether *reference* has the syntactic form of a source-ref handle."""
    return isinstance(reference, str) and _HANDLE_RE.fullmatch(reference) is not None


def _handle_for(payload: bytes) -> str:
    digest = hashlib.sha256(payload).digest()[:16]
    encoded = base64.b32encode(digest).decode("ascii").rstrip("=").lower()
    return f"sr1_{encoded}"


def _invalid(message: str) -> GraphContractError:
    return GraphContractError(
        "INVALID_SOURCE_REF",
        f"{message} Retrieve fresh source context and use its current source reference.",
        {},
    )


def _unavailable(operation: str, exc: BaseException) -> GraphContractError:
    return GraphContractError(
        "SOURCE_REFERENCE_STORE_UNAVAILABLE",
        "Source reference storage is unavailable; retrieve fresh source context and retry.",
        {"operation": operation, "error": type(exc).__name__},
    )


class SourceRefStore:
    """Stage and selectively persist short aliases for one exact repository."""

    def __init__(
        self,
        repo: Path,
        store: IndexStore,
        *,
        max_references: int = _DEFAULT_MAX_REFERENCES,
        max_payload_bytes: int = _DEFAULT_MAX_PAYLOAD_BYTES,
    ) -> None:
        if type(max_references) is not int or max_references < 0:
            raise ValueError("max_references must be a non-negative integer")
        if type(max_payload_bytes) is not int or max_payload_bytes < 0:
            raise ValueError("max_payload_bytes must be a non-negative integer")
        self.repo = Path(repo)
        self.store = store
        self.max_references = max_references
        self.max_payload_bytes = max_payload_bytes
        self._repo_identity = str(self.repo.resolve())
        self._pending: dict[str, bytes] = {}

    @property
    def path(self) -> Path:
        """The lazily-created SQLite database for this repository."""
        return self.store.source_reference_path(self.repo)

    def stage(self, value: Mapping[str, Any]) -> str:
        """Buffer one exact canonical locator without opening the database."""
        if not isinstance(value, Mapping):
            raise _invalid("Source reference payload must be an object.")
        try:
            payload = json.dumps(
                dict(value), ensure_ascii=False, sort_keys=True,
                separators=(",", ":"), allow_nan=False,
            ).encode("utf-8")
        except (RecursionError, TypeError, ValueError, UnicodeError) as exc:
            raise _invalid("Source reference payload is not canonical JSON.") from exc
        if len(payload) > self.max_payload_bytes:
            raise _invalid("Source reference payload exceeds the configured storage bound.")
        try:
            canonical_value = json.loads(payload)
        except (RecursionError, UnicodeError, json.JSONDecodeError) as exc:
            raise _invalid("Source reference payload is not valid JSON.") from exc
        if (
            not isinstance(canonical_value, dict)
            or canonical_value.get("repo") != self._repo_identity
        ):
            raise _invalid("Source reference belongs to another repository.")
        handle = _handle_for(payload)
        prior = self._pending.get(handle)
        if prior is not None and prior != payload:
            raise _invalid("Source reference handle collision was detected.")
        self._pending[handle] = payload
        return handle

    def flush(self, references: Iterable[str]) -> None:
        """Atomically persist precisely the staged handles selected for output."""
        selected: dict[str, bytes] = {}
        try:
            for reference in references:
                if not is_source_handle(reference) or reference not in self._pending:
                    raise _invalid("Source reference was not staged for this response.")
                selected[reference] = self._pending[reference]
        except TypeError as exc:
            raise _invalid("Source reference selection must be iterable.") from exc

        selected_bytes = sum(len(payload) for payload in selected.values())
        if len(selected) > self.max_references or selected_bytes > self.max_payload_bytes:
            raise _invalid(
                "Selected source references exceed the configured storage bound."
            )
        if not selected:
            self._pending.clear()
            return

        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with closing(self._connect()) as connection:
                self._initialize(connection)
                try:
                    connection.execute("BEGIN IMMEDIATE")
                    self._persist_selected(connection, selected)
                    self._evict_unselected(connection, set(selected))
                    connection.commit()
                except BaseException:
                    connection.rollback()
                    raise
        except GraphContractError:
            raise
        except (OSError, sqlite3.Error) as exc:
            raise _unavailable("flush", exc) from exc
        self._pending.clear()

    def resolve(self, reference: str) -> dict[str, Any]:
        """Return an exact persisted locator, or fail closed."""
        if not is_source_handle(reference):
            raise _invalid("Source reference handle is malformed.")
        if not self.path.is_file():
            raise _invalid("Source reference is unknown or has expired.")
        try:
            with closing(self._connect_readonly()) as connection:
                row = connection.execute(
                    "SELECT payload FROM source_refs WHERE handle = ?", (reference,)
                ).fetchone()
        except (OSError, sqlite3.Error) as exc:
            raise _unavailable("resolve", exc) from exc
        if row is None:
            raise _invalid("Source reference is unknown or has expired.")
        payload = row[0]
        if not isinstance(payload, bytes) or len(payload) > self.max_payload_bytes:
            raise _invalid("Stored source reference is corrupt.")
        try:
            value = json.loads(payload)
            canonical = json.dumps(
                value, ensure_ascii=False, sort_keys=True,
                separators=(",", ":"), allow_nan=False,
            ).encode("utf-8")
        except (RecursionError, TypeError, ValueError, UnicodeError, json.JSONDecodeError) as exc:
            raise _invalid("Stored source reference is corrupt.") from exc
        if (
            not isinstance(value, dict)
            or canonical != payload
            or _handle_for(payload) != reference
            or value.get("repo") != self._repo_identity
        ):
            raise _invalid("Stored source reference is corrupt or belongs to another repository.")
        return value

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(str(self.path), timeout=_BUSY_TIMEOUT_MS / 1000)
        connection.execute(f"PRAGMA busy_timeout = {_BUSY_TIMEOUT_MS}")
        return connection

    def _connect_readonly(self) -> sqlite3.Connection:
        uri = f"{self.path.resolve().as_uri()}?mode=ro"
        connection = sqlite3.connect(
            uri, uri=True, timeout=_BUSY_TIMEOUT_MS / 1000
        )
        connection.execute(f"PRAGMA busy_timeout = {_BUSY_TIMEOUT_MS}")
        return connection

    @staticmethod
    def _initialize(connection: sqlite3.Connection) -> None:
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute(
            "CREATE TABLE IF NOT EXISTS source_refs ("
            "handle TEXT PRIMARY KEY, payload BLOB NOT NULL, stamp INTEGER NOT NULL)"
        )

    def _persist_selected(
        self, connection: sqlite3.Connection, selected: Mapping[str, bytes]
    ) -> None:
        next_stamp = int(
            connection.execute(
                "SELECT COALESCE(MAX(stamp), 0) FROM source_refs"
            ).fetchone()[0]
        )
        for handle in sorted(selected):
            payload = selected[handle]
            row = connection.execute(
                "SELECT payload FROM source_refs WHERE handle = ?", (handle,)
            ).fetchone()
            if row is not None and row[0] != payload:
                raise _invalid("Source reference handle collision was detected.")
            next_stamp += 1
            if row is None:
                connection.execute(
                    "INSERT INTO source_refs(handle, payload, stamp) VALUES (?, ?, ?)",
                    (handle, payload, next_stamp),
                )
            else:
                connection.execute(
                    "UPDATE source_refs SET stamp = ? WHERE handle = ?", (next_stamp, handle)
                )

    def _evict_unselected(self, connection: sqlite3.Connection, selected: set[str]) -> None:
        while True:
            count, total = connection.execute(
                "SELECT COUNT(*), COALESCE(SUM(length(payload)), 0) FROM source_refs"
            ).fetchone()
            if count <= self.max_references and total <= self.max_payload_bytes:
                return
            placeholders = ", ".join("?" for _ in selected)
            excluded = f"WHERE handle NOT IN ({placeholders})" if selected else ""
            row = connection.execute(
                "SELECT handle FROM source_refs "
                f"{excluded} ORDER BY stamp ASC, handle ASC LIMIT 1",
                tuple(sorted(selected)),
            ).fetchone()
            if row is None:
                raise _invalid(
                    "Selected source references cannot fit the configured storage bound."
                )
            connection.execute("DELETE FROM source_refs WHERE handle = ?", (row[0],))
