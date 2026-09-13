"""Keep comparison identity separate from the shared exploration capability."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from benchmarks.typescript_context_explore_observed import ExploreObservedTrace
from benchmarks.typescript_context_explore_tools import ExploreAdapter, create_server


class RoutingAdapter(ExploreAdapter):
    """Both conditions use the old B capability with their own trace identity."""

    def __init__(self, run: dict):
        if run.get("arm") not in {"A", "B"}:
            raise ValueError("routing condition must be A or B")
        super().__init__({**run, "arm": "B"})
        self.trace = ExploreObservedTrace(
            self.corpus, run["case_id"], run["session_id"], run["arm"], run["repetition"],
        )
        self.persist()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path)
    args = parser.parse_args()
    run = json.loads(args.run.read_text(encoding="utf-8"))
    create_server(RoutingAdapter(run), "B").run()


if __name__ == "__main__":
    main()
