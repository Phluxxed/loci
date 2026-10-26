# R1 experimental agent interface

Run this branch's server with its own absolute store path:

```sh
PYTHONPATH=src LOCI_R1_STORE=/absolute/path/to/r1-store python -m loci.integrated_mcp
```

The production `loci-mcp` entrypoint is unchanged. This server exposes four tools:

| Tool | Use |
| --- | --- |
| `loci_retrieve(repo, query="", seed_ids=None)` | Find source by words or an exact relative path. Alternatively pass one previously returned identity in `seed_ids` to select its file. |
| `loci_read(repo, source_ref)` | Expand a returned exact, hash-bound extent. Follow `next_source_ref` until complete. |
| `loci_semantic(repo, query, anchor_file=None)` | Ask a static relationship question; optionally anchor to a located relative file. Supports JS/TS/Rust. |
| `loci_proof(repo, node_id)` | Get bounded incident relationship proof for an ID delivered by the latest semantic request or its proof followups. |

Start with retrieval. Inspect returned source and, when useful, retrieve a path
from `navigation.candidates`. These candidates come from delivered import,
export, Rust module/use and Cargo path text, intersected with the protected
inventory. They include alternatives and may reflect comments or inactive
configuration. They do not assert bindings. Incomplete source may hide paths;
read its remaining pages when needed. No path is followed automatically.

Request semantics when source relationships help answer the task. For example,
locate `entry.ts`, then ask `loci_semantic(repo, "entry", anchor_file="entry.ts")`.
Inspect its source proof and uncertainty. Request `loci_proof` for a returned
node ID if more focused evidence is needed. Proof does not expand the native
slice or rerun resolution, and is never dumped automatically. Another semantic
request replaces that slice; only its returned identities remain proof eligible.

Results are in `structuredContent`, with empty `content`. Save the raw result
before reducing it in Code Mode. Errors have `error.code`, `message` and
`details`. `SOURCE_STALE` requires fresh acquisition; old source references and
proof are never silently rebound to new bytes. Stores contain only inventories;
semantic packet/native caching stays in process, with freshness validation on
reuse. Restarting loses proof state and requires another semantic request.

Each emitted relationship must carry complete, independently checkable source
support. Coverage is bounded and non-exhaustive. Preserve unresolved, ambiguous,
external, inaccessible and configuration-dependent observations. Rust
`declared_possible` does not establish active configuration. Missing evidence,
empty selection and zero relationships do not establish absence. Python/Go
semantics, runtime dispatch, exhaustive reverse impact, package-alias source
navigation and macro expansion remain unsupported.

Set `LOCI_R1_SOURCE_ONLY=1` to expose only retrieval/read for the path-only pilot
condition. Source operations never request parsing, native resolution or graph
persistence. They retain the existing file/scan/output limits and protected
reads. The inventory is refreshed on retrieval and semantic/proof validation;
exact reads check current eligibility and content hashes. Navigation hints fit
within the existing output limit, with omitted candidates counted.

Compatibility: source fields, exact extents, continuations and semantic proof
formats reuse R0 mechanisms. Experimental source references remain opaque but
are longer than production handles. Source retrieval re-anchors one identity
at a time, at file granularity. Semantic IDs can also be re-anchored to source.
The production graph policy and diagnostics are not exposed by this server.
No planner, automatic semantic router, new graph or persistent proof store is
introduced.
