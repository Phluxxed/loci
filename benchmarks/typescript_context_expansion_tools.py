"""Matched A/B adapter: identical v3 tools, with bounded context on B gets."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from loci import service

from benchmarks.typescript_context_observed import measure as observed_measure, reconcile_observed
from benchmarks.typescript_context_relationships import _unwrap_result, score_relationships
from benchmarks.typescript_context_tools_v3 import ObservedAdapter, create_server


class ExpansionAdapter(ObservedAdapter):
    def dispatch(self, operation: str, parameters: dict) -> dict:
        if operation != "get" or self.run["arm"] == "A":
            return super().dispatch(operation, parameters)
        if self.run["arm"] != "B":
            raise ValueError("existing-edge comparison supports only A and B")
        if parameters.keys() - {"symbol_ids", "context", "selected_from_search_id"}:
            raise ValueError("unknown operation or parameters outside the fixed tool contract")
        ids = parameters["symbol_ids"]
        if not isinstance(ids, list) or len(ids) > self.limits["max_nodes"]:
            raise ValueError("explicit IDs exceed the frozen node/anchor limit")
        if any(symbol_id not in self.symbols for symbol_id in ids):
            raise ValueError("IDs must belong to this snapshot index")
        if type(parameters.get("context", 0)) is not int or parameters.get("context", 0) < 0:
            raise ValueError("context must be a nonnegative line count")
        return service.get_symbols_result(self.repo, **parameters, include_type_context=True)

    def spans(self, operation: str, result: dict) -> list[dict]:
        spans = super().spans(operation, result)
        context = result.get("type_context")
        if operation == "get" and isinstance(context, dict):
            # The exact existing validator and signature provenance apply to
            # every added definition, including duplicate literal occurrences.
            spans.extend(super().spans("get", {"symbols": context["symbols"]}))
            spans.extend({"file": item["file"], "start_byte": item["byte_offset"], "text": item["content"]}
                         for item in context["evidence"])
        return spans


def relationship_payloads(delivered: list[dict]) -> list[dict]:
    """Expose actual added edge objects to the unchanged gold relationship scorer.

    Only the response-container shape changes. Edge source/target, evidence,
    resolution and selection ownership are never rewritten for scoring.
    """
    results = list(delivered)
    for result in delivered:
        payload = _unwrap_result(result)
        context = payload.get("type_context") if isinstance(payload, dict) else None
        if not isinstance(context, dict):
            continue
        steps = [{"edge": reference["edge"]} for reference in context["references"]]
        if steps:
            results.append({"paths": [{"steps": steps}]})
    return results


def measure(corpus, case, run, events, elapsed, exit_code, timed_out, index=None):
    result = observed_measure(corpus, case, run, events, elapsed, exit_code, timed_out, index)
    if index is not None:
        raw = json.loads(Path(run["trace_path"]).read_text())
        delivered = reconcile_observed(raw, events)["validated_results"]
        result["baseline"]["relationships"] = score_relationships(case, index, relationship_payloads(delivered))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path)
    args = parser.parse_args()
    create_server(ExpansionAdapter(json.loads(args.run.read_text()))).run(transport="stdio")


if __name__ == "__main__":
    main()
