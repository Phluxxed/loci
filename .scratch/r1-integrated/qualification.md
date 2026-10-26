# R1 deterministic combined qualification

The experimental integrated interface passed deterministic integrity qualification.
Twelve focused tests passed; independent replay verified all 288 case executions.
The binding gate is `qualification-gate.json`. This establishes bounded source and
proof delivery behavior under the recorded policy, not agent benefit or adoption.

The combined policy returned fewer authored source spans than source-only and
proved 24 of 84 historical gold dependencies. Those misses are retained results,
not repaired away or treated as proof that missing relationships do not exist.

## Method and boundaries

`benchmarks.architecture_integrated` reuses the unchanged `architecture.acquire`,
`acquisition_scores`, `score_acquisition`, native proof and structural validators.
The two conditions use the same `IntegratedSource` and path scheduler. Source-only
omits semantic/proof operations. The integrated condition asks semantics in slot
two using the path scheduler's next query, consuming one of five base calls, then
asks up to four proofs using identities actually delivered to the consumer.
The scheduler receives inventory and delivered source, never corpus gold or the
native observer index. This is a fixed deterministic qualification policy; native
agents may choose whether, when, and how to request optional semantics.

The original 17-case TypeScript v3 and 19-case multilingual corpora are archived
with their immutable source archives. Two repetitions alternate arm order. Each
arm/suite/repetition starts a separate Python process and isolated source store.
Each case runs its complete acquisition sequence followed immediately by the
same warm sequence. Runtime setup, inventory, query selection, retrieval,
continuations, semantic work, proof freshness, and complete sequences have actual
wall/CPU/resource observations. Source and full MCP envelope bytes remain exact.
First sequences are not uniformly cold: 2/36 semantic questions reused a previous
matching case slice. All 36/36 repeat semantic requests hit cache and parsed zero
new bytes; freshness work remained in their measured sequence cost.

Independent replay checks the artifact manifest and recorded evaluator hashes,
rematerializes frozen source archives in a new temporary root, and recomputes the
same scores from original packets, inventories, traces and native indexes without
calling the candidate. No scorer, corpus, threshold or production entrypoint was
changed.

## Recorded results

Values below are means across two repetitions, combining all 36 cases.

| Condition | First complete sequence | Repeat complete sequence | Authored source spans | Packet/session dependency links | Entry source |
| --- | ---: | ---: | ---: | ---: | ---: |
| Source-only | 6.577 s | 6.578 s | 185/187 | 0/84, 0/84 | 36/36 |
| Integrated | 17.973 s | 12.679 s | 180/187 | 24/84, 24/84 | 36/36 |

Complete sequence time includes query selection, all current-source checks,
source pages, optional semantics, all focused proof calls and proof freshness.
It excludes separate one-time runtime setup and initial inventory. Including
worker startup, inventory, both first/repeat sequences and artifact writes,
worker process wall totals averaged 14.097 s source-only and 34.214 s integrated
per repetition. Initial inventory averaged 0.727 s and 0.691 s respectively.
These descriptive timings are for fixed local fixtures and two repetitions.

The integrated condition delivered 488,459 source bytes and 1,621,584 full-envelope
bytes per repetition; source-only delivered 399,790 and 951,584 respectively.
Both retained source-store footprints averaged 35,372 bytes across the two suites.
Integrated first sequences parsed 6,582,987 bytes; repeats parsed zero. Native
slice and serialized-cache proxy sizes, retained raw bytes, phase resources,
process peak RSS and operation details remain in each `worker.json`.

All 288 executions passed source/envelope/acquisition integrity. Forbidden proven
claims were zero. Source-only performed zero semantic/proof operations and
delivered zero relationships. Python/Go questions delivered zero relationships.
All semantic and focused proof packets remained under their original budgets.

The focused tests verify actual stdio catalogs (four integrated tools, two
source-only tools), source/read/semantic/proof calls, delivered-ID reanchoring,
cold/warm cache behavior, source and control mutation invalidation, stale ordinary
and semantic references, native Rust uncertainty counts, declared-possible
configuration, unsupported languages, corrupted source, unsupported gold-only
proof queries, missing linked proof source, manifest tampering, and continuation
wire compatibility. Ten actual concurrent stdio requests (eight retrieval, two
semantic) observed a maximum of one active service operation, without an elapsed
time assertion.

## Coverage limits and retained failures

Integrated source misses were `barrel.py` reexport spans in
`python_alias_annotation` and `python_base_and_literal_forward`, `go.mod` in
`go_alias_generic_contract`, `go_known_api_impact`, and `go_unproven_package_uses`,
and `Cargo.toml` in `rust_authored_trait_contract` and `rust_known_call_impact`.
All seven are required authored evidence in those historical cases. Source-only
missed one span each in `rust_contained_optional_reexport` and
`rust_unproven_contracts`. The optional semantic slot consumes source acquisition
capacity even when a language is unsupported. Missing coverage remains explicit;
there was no gold-directed retry or corpus-specific policy adjustment.

The 24/84 gold-link result includes unsupported Python/Go dependencies in its
unchanged denominator. It also has supported JS/TS/Rust misses; it does not imply
full supported-language recall. Detailed endpoint, record, proof and missing-link
results remain in each capability file. Native uncertainty is bounded to the
computed slice, and neither empty output nor zero omissions establishes absence.
No final consumer answer was observed in this deterministic qualification.

The first full attempt is retained under `qualification/` with
`qualification-run.txt`. It failed because adding navigation to exact read
packets violated the unchanged strict legacy read schema. The smallest correction
keeps read packets in their original format and exposes navigation on retrieval.
The corrected run is `qualification-final/`; no schema projection or relaxed
scorer was retained.

## Reproduce

```sh
PYTHONPATH=src /Users/brummerv/phluxxed/loci/.venv/bin/python -m pytest -q tests/test_r1_integrated.py
PYTHONPATH=src /Users/brummerv/phluxxed/loci/.venv/bin/python -m benchmarks.architecture_integrated --output NEW_DIRECTORY --repetitions 2
PYTHONPATH=src /Users/brummerv/phluxxed/loci/.venv/bin/python -m benchmarks.architecture_integrated --verify .scratch/r1-integrated/qualification-final
```

The final artifact set is about 42 MB, including isolated fixture/store material;
the retained failed attempt is about 5.6 MB. The gate binds the current six
runtime source files and final artifact manifest. It authorizes no production
configuration or integration change. Native agent-pilot acceptance is separate.
