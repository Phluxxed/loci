"""The frozen three-arm TypeScript context adapter.

The existing comparison adapter owns the v3 tool surface and the complete
delivery accounting.  A and B deliberately delegate to that adapter without
changing its dispatch.  C uses the same validation and delivery path for every
operation, and opts the exact ``get`` call into the type-context implementation
provided by the engine selected for the worker process.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from loci import service

from benchmarks.typescript_context_expansion_tools import (
    ExpansionAdapter,
    measure,
    relationship_payloads,
)
from benchmarks.typescript_context_observed import reconcile_observed
from benchmarks.typescript_context_tools_v3 import ObservedAdapter, create_server


class ThreeArmAdapter(ExpansionAdapter):
    """Run the frozen A, B, or C retrieval policy for one attempt.

    ``ExpansionAdapter`` is the source of truth for the A and B branches.  C
    repeats only its bounded ``get`` validation because the historical class
    intentionally rejects any arm other than A/B.  The selected engine owns
    the meaning of ``include_type_context``: A uses the exact-get path, B uses
    the existing-edge expansion path, and C uses the W2.3 type records from
    its pinned engine.
    """

    def dispatch(self, operation: str, parameters: dict) -> dict:
        arm = self.run["arm"]
        if arm in {"A", "B"}:
            # Preserve the inherited implementation byte-for-byte in behavior
            # and validation.  This is the matched comparator contract.
            return super().dispatch(operation, parameters)
        if arm != "C":
            raise ValueError("three-arm comparison supports only A, B, and C")

        if operation != "get":
            # ExpansionAdapter delegates non-get operations to ObservedAdapter
            # before it checks its own A/B arm restriction.  Keep that exact
            # inherited route for C as well.
            return ObservedAdapter.dispatch(self, operation, parameters)

        # Keep the existing expansion adapter's fixed get contract.  Only the
        # selected engine's proven relation records differ between B and C.
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


# A descriptive alias keeps callers that refer to the adapter as the ABC
# adapter independent of the implementation class name.
ABCAdapter = ThreeArmAdapter


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path)
    args = parser.parse_args()
    run = json.loads(args.run.read_text(encoding="utf-8"))
    create_server(ThreeArmAdapter(run)).run(transport="stdio")


__all__ = [
    "ABCAdapter",
    "ThreeArmAdapter",
    "create_server",
    "measure",
    "relationship_payloads",
    "reconcile_observed",
]


if __name__ == "__main__":
    main()
