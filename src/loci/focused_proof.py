"""R0.6 only: optional exact-identity proof packing from one retained slice."""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
from pathlib import Path
from typing import Any

from .demand_semantics import DemandSource, _MemorySourceStore, _phase
from .graph_free import GraphFreeError, _canonical, _repo


def uncertainty_summary(state: Any) -> dict:
    """Describe native observations, without promoting them to relationships."""
    counts = Counter()
    examples = []
    possible = 0
    for family, records in (("imports", state.imports), ("references", state.symbol_references),
                            ("calls", state.calls), ("types", state.type_relations)):
        for record in records:
            possible += getattr(record, "resolution_configuration", None) == "declared_possible"
            if getattr(record, "status", None) != "unresolved":
                continue
            reason = getattr(record, "unresolved_reason", None) or "unknown"
            category = ("ambiguous_relation" if reason.startswith("ambiguous") else
                        "inaccessible_relation" if reason == "target_inaccessible" else
                        "configuration_dependent_relation" if reason == "configuration_divergent" else
                        "external_relation" if reason == "external" else "unresolved_relation")
            counts[family, reason, category] += 1
            if len(examples) < 8:
                raw = record.raw
                example = {"family": family, "file": raw.source_file, "line": raw.line,
                           "status": "unresolved", "reason": reason}
                import_reason = getattr(record, "import_unresolved_reason", None)
                if import_reason is not None:
                    example["import_unresolved_reason"] = import_reason
                examples.append(example)
    return {"scope": "native_records_in_computed_slice", "exhaustive": False,
            "counts": [{"family": family, "status": "unresolved", "reason": reason,
                        "consumer_reason": category, "count": count}
                       for (family, reason, category), count in sorted(counts.items())],
            "configuration_possible_count": possible,
            "configuration_meaning": "declared_possible does not establish active configuration",
            "examples": examples, "examples_omitted": sum(counts.values()) - len(examples)}


class FocusedDemandSource(DemandSource):
    """Retain one computed slice; followups never expand or resolve its graph."""

    def __init__(self, store: Path, *, wide: bool = False):
        super().__init__(store)
        self.wide = wide
        self._retained = None
        self._visible_ids: set[str] = set()
        self._focused_work: list[dict] = []

    def _pack_semantics(self, root, query, query_terms, hashes, raw, seeds, symbols,
                        source, state, import_edges, reference_edges, call_edges,
                        type_edges, work, rust_controls, rust_module_support):
        # Capture pre-packing omissions and the native objects already computed
        # by R0.5. The temporary snapshot/source object is not retained.
        self._retained = {
            "root": root, "query": query, "query_terms": query_terms, "hashes": hashes,
            "raw": raw, "seeds": seeds, "symbols": symbols, "state": state,
            "import_edges": import_edges, "reference_edges": reference_edges,
            "call_edges": call_edges, "type_edges": type_edges, "work": deepcopy(work),
            "rust_controls": rust_controls, "rust_module_support": rust_module_support,
        }
        self._packet_uncertainty = uncertainty_summary(state)
        initial = {**self._retained, "work": work}
        return super()._pack_semantics(source=source, **initial)

    def semantic_context(self, *args, **kwargs):
        self._focused_work = []
        packet = super().semantic_context(*args, **kwargs)
        self._visible_ids = {node["id"] for node in packet["nodes"]}
        return packet

    def semantic_observer(self):
        observer = super().semantic_observer()
        if self._retained is not None:
            raw = self._retained["raw"]
            observer["work"]["retained_raw_bytes"] = sum(len(data) for data in raw.values())
            observer["work"]["retained_native_index_proxy_bytes"] = len(_canonical(observer["index"]))
        observer["work"]["focused_requests"] = deepcopy(self._focused_work)
        return observer

    def proof_observer(self):
        return deepcopy(self._focused_work[-1])

    def proof_context(self, repo: str | Path, node_id: str) -> dict:
        root = _repo(repo)
        if self._retained is None or node_id not in self._visible_ids:
            raise GraphFreeError("UNKNOWN_PROOF_ID", "Proof requires a previously delivered node identity")
        args = dict(self._retained)
        if root != args["root"]:
            raise GraphFreeError("UNKNOWN_PROOF_ID", "Proof slice belongs to another repository")
        work = deepcopy(args["work"])
        work.update(semantic_calls=0, focused_node_id=node_id, phases=[], cache_hit=True,
                    cache_kind="native_slice_reuse", native_resolution_calls=0,
                    parsed_paths=[], bytes_parsed=0, bytes_discovered=0, discovered_paths=[],
                    bytes_controls=0, bytes_rust_snapshot=0, bytes_snapshot_parsed=0,
                    rust_snapshot_paths=[], snapshot_parsed_paths=[])
        expected = self._observer["index"]["snapshot"]
        with _phase(work, "proof_freshness"):
            inventory = self.index_repo(root)
            if inventory["snapshot"] != expected:
                raise GraphFreeError("SOURCE_STALE", "Repository changed since semantic preparation")
        from .exploration import _Source
        symbols = args["symbols"]
        args["source"] = _Source(root, _MemorySourceStore(args["raw"]),
                          {symbol.id: symbol.to_dict() for symbol in symbols})
        args["work"] = work
        self._proof_focus_id = node_id
        self._proof_evidence_limit = 32768 if self.wide else 8192
        self._proof_output_limit = 65536 if self.wide else 16384
        self._proof_packet_policy = "focused-semantic-wide-v1" if self.wide else "focused-semantic-v1"
        try:
            # Call the same packer directly, bypassing extraction and resolution.
            packet = DemandSource._pack_semantics(self, **args)
        finally:
            for name in ("_proof_focus_id", "_proof_evidence_limit", "_proof_output_limit",
                         "_proof_packet_policy"):
                delattr(self, name)
        with _phase(work, "proof_final_freshness"):
            if self.index_repo(root)["snapshot"] != expected:
                raise GraphFreeError("SOURCE_STALE", "Repository changed during proof delivery")
        work["retained_raw_bytes"] = sum(len(data) for data in args["raw"].values())
        self._visible_ids.update(node["id"] for node in packet["nodes"])
        self._focused_work.append(work)
        return packet
