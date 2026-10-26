"""Experimental agent workflow: source first, semantics and proof on request."""
from __future__ import annotations

from pathlib import Path

from .focused_proof import FocusedDemandSource
from .graph_free import GraphFreeError, MAX_OUTPUT_BYTES, _account, _repo
from .path_navigation import candidate_paths


class IntegratedSource(FocusedDemandSource):
    """Reuse protected source reads and one bounded, optional native slice."""

    def __init__(self, store: Path):
        super().__init__(store)
        self._delivered: dict[tuple[Path, str], str] = {}

    def _navigation(self, root: Path, packet: dict) -> dict:
        hashes = self.inventory(root)["file_hashes"]
        sources = packet["sources"]
        candidates = []
        seen = set()
        for source in sources:
            for candidate in candidate_paths(source["file"], source["content"], hashes):
                if candidate["path"] not in seen:
                    candidates.append(candidate)
                    seen.add(candidate["path"])
        packet["navigation"] = {
            "meaning": "source path candidates; not resolved relationships",
            "exhaustive": False,
            "candidates": candidates[:8],
            "omitted_candidates": max(0, len(candidates) - 8),
        }
        evidence = packet["usage"]["evidence_bytes"]
        _account(packet, evidence)
        while packet["usage"]["output_bytes"] > MAX_OUTPUT_BYTES:
            if not packet["navigation"]["candidates"]:
                # Keep the original bounded source packet if no hints fit.
                del packet["navigation"]
                return _account(packet, evidence)
            packet["navigation"]["candidates"].pop()
            packet["navigation"]["omitted_candidates"] += 1
            _account(packet, evidence)
        return packet

    def retrieve(self, repo, query: str = "", *, seed_ids: list[str] | None = None, **ignored):
        root = _repo(repo)
        if seed_ids:
            if len(seed_ids) != 1:
                raise GraphFreeError("INVALID_QUERY", "Re-anchor one delivered identity at a time")
            file = self._delivered.get((root, seed_ids[0]))
            if file is None:
                raise GraphFreeError("UNKNOWN_SOURCE_ID", "Re-anchor requires a previously delivered identity")
            # Explicit identity selects its source file, as an exact path does.
            query = file
        packet = super().retrieve(root, query, **ignored)
        for item in packet["items"]:
            self._delivered[root, item["node_id"]] = item["extent"]["file"]
        return self._navigation(root, packet)

    def semantic_context(self, repo, query: str, *, anchor_file: str | None = None):
        root = _repo(repo)
        packet = super().semantic_context(root, query, anchor_file=anchor_file)
        for node in packet["nodes"]:
            if node.get("file"):
                self._delivered[root, node["id"]] = node["file"]
        return packet

    def proof_context(self, repo, node_id: str):
        root = _repo(repo)
        packet = super().proof_context(root, node_id)
        for node in packet["nodes"]:
            if node.get("file"):
                self._delivered[root, node["id"]] = node["file"]
        return packet
