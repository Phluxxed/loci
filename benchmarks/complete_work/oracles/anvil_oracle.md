# Anvil creation-evidence oracle

`anvil.py` is evaluator-only support for `anvil-creation-evidence`. It verifies
the retained 638-file export before making a target copy, then runs its own
TypeScript fixture against a candidate checkout. The fixture never imports,
discovers, or relies on candidate-added tests.

Prepare an isolated target with the frozen source and its unchanged lockfile:

```sh
python -m benchmarks.complete_work.oracles.anvil \
  --prepare-target /tmp/anvil-target \
  --output /tmp/anvil-target-preparation.json
cd /tmp/anvil-target && npm ci
```

Evaluate a completed candidate with evaluator-owned scratch space:

```sh
python -m benchmarks.complete_work.oracles.anvil \
  --repo /path/to/candidate \
  --work-dir /path/to/evaluator-scratch \
  --output /path/to/report.json
```

The report always has this shape:

```json
{
  "schema_version": 1,
  "episode_id": "anvil-creation-evidence",
  "status": "passed | failed | unavailable",
  "checks": [{"id": "stable-check-id", "passed": true, "detail": "safe summary"}],
  "errors": ["safe evaluator error"],
  "runtime": {"node_binary": "node", "node_version": "v..."},
  "provenance": {"source_commit": "53bf29e..."}
}
```

`unavailable` means the candidate or its prepared pinned dependency environment
cannot be run. It is not a passing result. The fixture uses temporary Git
repositories and a loopback server. It verifies the exact public categories,
marker/history controls, recursive reparenting, unchanged derived graph state,
API/page parity, and safe output. A target may change to implement the episode;
the full file map is verified only before source copying, not against the
changed candidate.
