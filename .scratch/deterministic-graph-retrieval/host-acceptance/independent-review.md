# Independent review — W1.8.1 normal graph retrieval

Review target: `master` at `90068fa`, the frozen
`.scratch/deterministic-graph-retrieval/contract.md` and companion schema, the
requested normal retrieval/source/MCP/output/adapter files, and the retained
primary-host catalog/retrieve/read receipts. This was one read-only source and
evidence pass. I used the actual primary `loci_retrieve` operation for source
discovery; its packet reported `normal-graph-v1`, partial indexed coverage, and
bounded omissions. I did not change product source or frozen artifacts.

## Required finding

### Required — the normal rollout adapter accepts false byte accounting as complete and can validate it as actual-host proof

The product contract says `usage` reports evidence bytes and complete MCP-result
bytes as observed execution counts
(`contract.md:210-219`). Product serialization does calculate a fixed point over
the complete `{content:[], structuredContent:..., isError:false}` result
(`src/loci/retrieval_io.py:48-64`). The rollout adapter does not independently
check those claims:

- `_usage` labels every nonnegative integer `complete`
  (`benchmarks/ordinary_adoption_normal.py:239-243`).
- `_retrieve_readout` does not read or expose `evidence_bytes` or `output_bytes`
  at all (`benchmarks/ordinary_adoption_normal.py:270-308`).
- `_read_readout` exposes both declared numbers but never compares evidence
  bytes with returned source content or output bytes with the captured result
  envelope (`benchmarks/ordinary_adoption_normal.py:311-347`).
- `_set_host_proof` ignores read usage/accounting status when promoting a
  `full_exact` call to `actual_host_proof_status="validated"`
  (`benchmarks/ordinary_adoption_normal.py:368-386`).

A deterministic in-memory reproducer loaded the retained primary receipts,
changed both `usage.evidence_bytes` and `usage.output_bytes` to zero, called the
adapter readout helpers, and supplied a `full_exact` delivery marker. The
retrieve call still became `validated` with no usage readout; the read call
reported both zero fields as `complete` and also became `validated`:

```json
{"read_host_status":"validated","read_usage":{"reported_evidence_bytes":0,"reported_evidence_bytes_status":"complete","reported_output_bytes":0,"reported_output_bytes_status":"complete"},"retrieve_has_usage":false,"retrieve_host_status":"validated"}
```

This permits a malformed or truncated retained result to pass the accounting
gate and contaminates W1.8 cost/proof evidence, even though the current primary
receipts happen to be correct. The adapter should independently compute compact
UTF-8 bytes for the captured complete `result`, compare them to declared
`output_bytes`, compute read evidence bytes from the returned source and
retrieve evidence bytes from the union of source spans, retain explicit
`complete`/`mismatch`/`unknown` statuses for both operations, and require those
statuses to be complete before actual-host proof becomes `validated`. Add
negative tests that mutate each declared count while leaving source/proof and
`full_exact` delivery intact.

## Primary-host receipt assessment

The retained catalog contains exactly `mcp__loci__loci_retrieve` and
`mcp__loci__loci_read`, with no request-time intent, family, direction, hop, or
budget controls. Both saved results use the structured-only successful MCP
shape: `content=[]`, populated `structuredContent`, and `isError=false`. Empty
`content` is therefore not missing evidence; the full source and proof live in
`structuredContent` as declared by the tool output schema.

The actual saved values are internally exact. Compact UTF-8 serialization of
the complete `result` object is 16,224 bytes for
`primary-retrieve-001.json`, matching declared `output_bytes=16224`, and 8,962
bytes for `primary-read-001.json`, matching declared `output_bytes=8962`.
The read returns exactly 7,979 source bytes, matching its declared
`evidence_bytes=7979`. Both structured payloads validate with the published
Pydantic output models. I did not infer or create transport IDs, model-visible
delivery references, or provider usage; reconciliation of those fields remains
outside this artifact as requested.

## Overall judgment and limits

One required gap remains in actual-host accounting, so W1.8.1 should not treat
the adapter's `validated` status as an accounting-integrity check until the
finding above is corrected. I found no additional required correctness,
readability, architecture, security, or performance defect in the reviewed
normal retrieval, proof hydration, exact-source paging, MCP surface, or output
models. This conclusion retains the intentional supported-subset limits:
relationships are static and non-exhaustive, Swift proof may be unavailable,
and a `source_ref` is an exact hash-bound locator rather than an issuance claim.

Verification performed for this review was bounded to: actual normal Loci
retrieval, source/schema inspection, Pydantic validation of both primary
structured payloads, exact compact-envelope byte recomputation, and the
accounting-corruption reproducer above. I did not rerun focused or full suites;
the delivery report's prior test results and six baseline failures remain
reported evidence rather than checks independently rerun here.

## Finding disposition — corrected

The required adapter finding was adopted and corrected after this review.
`benchmarks/ordinary_adoption_normal.py` is now
`ordinary-adoption-normal-v2`: it merges selected source extents by
`(file, content_hash)`, recomputes the compact UTF-8 size of the complete
captured MCP `result`, exposes reported/actual byte values with
`complete`/`mismatch`/`unknown` status per call and in aggregate, and requires
complete byte accounting before a `full_exact` delivery becomes validated.
Source-free error calls retain unknown byte-accounting status because they do
not carry successful usage declarations.

Regression coverage in `tests/test_ordinary_adoption_normal.py` proves that
overlapping source spans use their unique extent union and that corrupt
evidence/output declarations remain mismatches, cannot validate host proof,
and cannot enter the model-output evidence registry. The focused normal adapter
plus frozen observer/review check passed **51/51** in 0.27 seconds with the
repository virtual environment. After retaining the known zero-byte extent for
source-free errors while keeping their declaration status unknown, the targeted
error-accounting regression passed **1/1** in 0.03 seconds. An exact readback
of the retained primary receipts also passed: retrieve recomputed 3,339 unique
evidence bytes from 3,345 raw source-record bytes and 16,224 result bytes; read
recomputed 7,979 evidence bytes and 8,962 result bytes. Both matched their
declarations and qualified as validated when independently supplied the existing
`full_exact` condition. No native IDs, delivery references, or provider usage
were added.
