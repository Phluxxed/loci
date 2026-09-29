# Graph reference records are too heavy to consume

One ordinary `loci_graph_references` call returned **71 records in 153,195
characters**. The MCP host refused to inline that, wrote it to a file, and
returned a notice instructing the caller to read the file back in chunks before
summarising anything. The calling agent abandoned the graph, fell back to
`loci_grep`, and produced a wrong answer that the graph had the evidence to
prevent.

The cost is per record, not per page. Paging was already in effect and did not
help.

## Reproduction

The subject repository is private and is not named here; it is held locally and
the run can be repeated against it directly. Shape: TypeScript on Aurelia, 533
TypeScript files, 4,075 symbols, 8,756 symbol references indexed and 2,298
resolved, 14,141 calls indexed and 1,384 resolved.

```
loci_graph_references
  repo   = <private TypeScript repository>
  family = "type"
  file   = <one service module declaring a widely extended response interface>
```

Response: `counts {total: 71, resolved: 45, unresolved: 26, returned: 71}`,
`pagination {offset: 0, limit: 100, next_offset: null}`. A single complete page,
under the default limit, 153,195 characters — roughly 38,000 tokens for one
question about one file.

Any repository will reproduce it where a single file declares a type that is
extended or referenced a few dozen times; item count is not the variable.

## Where the weight is

161,890 characters of serialized JSON across 71 items, averaging **2,280
characters per record**. Two fields carry two thirds of it:

| Field | Total chars | Share | Per record |
| --- | ---: | ---: | ---: |
| `raw` | 57,258 | 35% | ~1,058 |
| `support` | 51,119 | 31% | ~1,054 |
| `source_id` | 4,853 | 2% | ~68 |
| `candidate_ids` | 3,465 | 2% | ~49 |
| `target_id` | 3,095 | 1% | ~44 |
| `resolution_controls` | 2,867 | 1% | ~40 |
| everything else | ~39,000 | 24% | — |

`raw` and `support` are the evidence and justification payloads: candidate
bindings, resolution basis, control files, byte offsets and matched source text.
They answer *why this reference resolved the way it did*. The caller's question
was *what references this*, which the identity fields alone answer.

At roughly 150 characters per record, the same 71 references would serialize to
about 11KB and consume normally.

## Why it matters

Three runs of one question against that repository — same task wording, same
model, differing only in tool availability and in whether the graph tools were
described to the agent. The question named a base response interface and asked
which files would have to change if it gained a required field. The repository
declares two further interfaces with that same name in unrelated modules, so a
text-only route has to separate them by hand.

| | Retrieval only | Graph available, not described | Graph described |
| --- | ---: | ---: | ---: |
| Tool calls | 12 | 16 | 11 |
| Graph calls | 0 | 0 | 1, abandoned |
| Tokens | 49,680 | 66,505 | 55,719 |
| Duration | 164s | 170s | 124s |
| Separated the same-named decoy | yes | yes | **no** |

The third run reached for `loci_graph_references` as its fourth call — the first
relationship question it hit. It received the spill notice, dropped the route,
ran six greps, and reported one of the unrelated same-named interfaces as
extending the target. Resolved references separate those declarations; text
search does not. The tool held the answer and could not deliver it in a
consumable size.

## Suggested direction

Not a prescription — the shape of the fix is yours to pick.

A lean default projection would likely be enough: identity and location per
record (`source_id`, `target_id`, `source_file`, `target_file`, line, `status`,
`unresolved_reason`), with `raw`, `support`, `candidate_*` and
`resolution_control*` returned only when explicitly requested. The chained call
after `loci_graph_references` is almost always `loci_get` on a target, so
identity fields are what the next step consumes; evidence is what a caller asks
for after a result looks wrong.

Worth checking whether `loci_graph_calls` and `loci_graph_retrieve` carry the
same record shape, since the same weight would apply.

## Not established

- Whether the same weight appears in other languages or smaller files; this is
  one call against one TypeScript file.
- Whether a lean projection would have changed the third run's answer. The run
  abandoned the route before reading any records, so the comparison was never
  made on content.
- Whether the decoy error was caused by the abandoned graph call. The two other
  runs got it right without the graph, so text search alone is capable of the
  correct answer here.
