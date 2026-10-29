"""One production Loci call, pinned to a trial's trusted repository and store.

The Pi extension sends {tool, arguments} on stdin and receives the actual service
packet on stdout. Source handles persist in the trial store across subprocesses.
No model argument can select a repository, store or graph-enrichment policy.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys


def invoke(request):
    repo = Path(os.environ["LOCI_AGENT_REPO"])
    store = Path(os.environ["LOCI_AGENT_STORE"])
    mode = os.environ["LOCI_AGENT_GRAPH_ENRICHMENT"]
    if not repo.is_absolute() or not store.is_absolute():
        raise ValueError("trial repository and store must be absolute paths")
    repo, store = repo.resolve(strict=True), store.resolve()
    if not repo.is_dir() or repo != Path.cwd().resolve():
        raise ValueError("trial repository must equal the process working directory")
    if store == repo or store.is_relative_to(repo) or repo.is_relative_to(store):
        raise ValueError("trial store and repository must be separate directories")
    if mode not in {"true", "false"}:
        raise ValueError("LOCI_AGENT_GRAPH_ENRICHMENT must be true or false")
    if not isinstance(request, dict) or set(request) != {"tool", "arguments"}:
        raise ValueError("request requires exactly tool and arguments")
    arguments = request["arguments"]
    if not isinstance(arguments, dict):
        raise ValueError("arguments must be an object")

    # Import this checkout, never an installed checkout selected by PYTHONPATH.
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
    os.environ["LOCI_BASE_DIR"] = str(store)
    from loci import service

    if request["tool"] == "loci_retrieve":
        if set(arguments) - {"query", "seed_ids"}:
            raise ValueError("unknown retrieve argument")
        query, seeds = arguments.get("query", ""), arguments.get("seed_ids")
        if not isinstance(query, str) or len(query.encode("utf-8")) > 4096:
            raise ValueError("query must be a string of at most 4096 UTF-8 bytes")
        if seeds is not None and (
            not isinstance(seeds, list) or len(seeds) > 5
            or any(not isinstance(seed, str) or not seed for seed in seeds)
            or len(set(seeds)) != len(seeds)
        ):
            raise ValueError("seed_ids must contain at most five unique nonempty strings")
        if not query.strip() and not seeds:
            raise ValueError("provide a nonblank query or at least one seed ID")
        runtime = service.RetrievalRuntime(graph_enrichment=mode == "true")
        return runtime.retrieve(repo, query, seed_ids=seeds, ensure_fresh=True)
    if request["tool"] == "loci_read":
        if set(arguments) != {"source_ref"} or not isinstance(arguments["source_ref"], str) or not arguments["source_ref"]:
            raise ValueError("read requires exactly one nonempty source_ref string")
        return service.read(repo, arguments["source_ref"], ensure_fresh=True)
    raise ValueError("unknown tool")


def main():
    try:
        # Reserve stdout for one machine-readable packet, including failures.
        from contextlib import redirect_stdout
        with redirect_stdout(sys.stderr):
            result = invoke(json.load(sys.stdin))
    except Exception as exc:
        error = exc.to_dict() if hasattr(exc, "to_dict") else {
            "code": type(exc).__name__, "message": str(exc), "details": {},
        }
        result = {"error": error}
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
