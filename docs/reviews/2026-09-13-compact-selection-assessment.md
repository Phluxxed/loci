# W5.2 compact-selection assessment

Task `task_ad3b550457fb0b586f7ec1474a867fe5` is complete with **no engine change**
and improved request guidance. The scoped omissions reproduce as documented
selection limits and task-agent request choices; no supported-contract defect
was demonstrated. Code and deterministic checks
stay in the isolated exploration checkout; the sole Manifest remains in
`/Users/brummerv/loci`.

## Acceptance boundary

The [selection contract](../design/2026-09-11-intent-evidence.md#selection-relevance)
requires one selected proof path per source item. A packet is a selection of
source and proof for an intent, not every graph relationship among its returned
declarations. `alternative_path` records another path to an already selected
declaration. Query relevance selects deeper type fields; structural alias and
heritage continuations do not require those query terms. Locate has no
relationship paths. Impact walks incoming known static relationships and
defaults to one hop. Outgoing call selection in dependencies is JavaScript-only.

Selection examines at most 64 nodes and 32 neighbors per expansion, with at most
three inferred or five explicit anchors. Packing admits at most 12 source items
and enforces independent complete-output and source-byte limits. Missing proof
ancestors prevent detached relationships. Increasing byte limits does not
override intent, direction, relevance or the one-path selection rule.

An engine defect would contradict that supported behavior or deliver incorrect,
detached, stale or falsely certain proof. An expected bounded omission obeys the
contract and is disclosed. A task-agent choice can fail to request available
proof—for example by using locate, the wrong traversal direction, disconnected
inferred anchors or multiple explicit endpoints. Those categories may coexist
in one retained packet and must not be treated as equivalent to a false edge.

## Deterministic dispositions

| Retained case | Reproduced omission and classification | Focused supported follow-up |
| --- | --- | --- |
| JavaScript value dependencies | `run` selects `make` and `add` directly, so the available `make -> add` path is counted as an alternate. Expected one-path omission. | Seed `make` alone with `dependencies`, one hop. |
| Python alias annotation | `decode` selects `Payload` directly, losing the alternate `Alias -> Payload`; another request makes both `decode` and `Alias` anchors, and a third uses locate. Expected alternate omission plus request choices. | Seed `Alias` alone with `type_dependencies`, one hop. |
| Maintained Python Bundle contract | An explicit entry seed with no query omits a deeper field as `not_selected`; inferred requests disclose anchor/hop/alternate omissions, while locate has no relationships. Expected relevance/one-path limits plus request choices. | Seed `_validate_bundle` with the original case prompt and two hops for its relevant Bundle fields; separately seed `Relation` with one hop for `Relation -> Span`. |
| Go alias/generic contract | `Build` selects `UserID` directly and counts `AliasID -> UserID` as an alternate. Expected one-path omission; unresolved records remain disclosed. | Seed `AliasID` alone with `type_dependencies`, one hop, retaining the original 12,000-byte output and 8,000-byte source bounds. |
| Go API impact | Incoming `impact` from `Handle` delivers `Serve -> Handle` and `Work -> Handle`; it does not then turn around to select each caller's parameter type. Request choice, with shared-target alternate omissions. | Separate `type_dependencies` calls from `Serve` and `Work`, one hop each, deliver their `Request` relations. |
| Rust trait/impl contract | The retained build and Receipt packets supply nine of eleven scoped meanings, including both separate impl sites. The missing `Envelope -> Render` and `Envelope -> UserId` paths compete with already selected targets. Expected one-path/anchor/hop omissions. | Seed `Envelope` alone with `type_dependencies`, one hop. |
| Rust known-call impact | Inferred `dependencies` anchors `caller` and selects its `Config` type; Rust dependencies does not select outgoing calls. Request choice. | Seed `parse` with `impact` for `caller -> parse`, then `type_dependencies` for `parse -> Config`, one hop each. |
| Rust optional workspace control | The retained exact authored path carries `declared_possible`; it does not prove an active feature. Uncertainty control, with no repair needed. | Original request retained unchanged. |

These are bounded case dispositions, not a claim that every selection is optimal
or that all requests can deliver all paths. The focused requests can be composed
to recover the identified missing proof. They do not turn a compact packet into
an exhaustive graph view or demonstrate lower aggregate workflow cost.

## Reproduction and acceptance

The two scripts materialize the frozen comparison's source snapshots in temporary
directories and use isolated index stores. They record the fixed requests,
effective hops/byte limits, source-file identities, graph hashes and packet/proof
hashes. The source baseline is isolated `a58e2e4`; no engine file changes here.

- [JavaScript/Python evidence](../evidence/2026-09-13-w52-js-python.json):
  all **14 retained requests** across three cases reproduce exactly after
  removing only `_evaluation` metadata. **70/70 checks pass**, including
  four focused requests recovering the identified missing edges.
- [Go/Rust evidence](../evidence/2026-09-13-w52-go-rust.json): **seven retained
  requests** across five cases match the recorded selected-source/proof
  projections, including scope, effective limits and omissions. Six focused
  requests recover all scoped available-but-unselected edges. The optional
  Rust workspace request preserves `declared_possible`.

Across both scripts, current selected edge objects match validated stored edges,
source bytes/line spans/full-file hashes agree with the pinned source, and paths
connect to their anchors in the recorded direction. Independent recomputation
of the source interval union and complete MCP-result JSON size matches declared
usage and stays within the requested limits. The new checks do not certify
unexamined historical responses or repair frozen evaluator accounting.

Run from the isolated checkout:

```text
.venv/bin/python -m tests.reproductions.exploration.selection_js_python --output /tmp/loci-w52-js-python-replay.json
.venv/bin/python -m tests.reproductions.exploration.selection_go_rust --output /tmp/loci-w52-go-rust-replay.json
```

The recorded checkout HEAD/tree is provenance and will change after later
commits; snapshot, graph and normalized proof identities are the relevant replay
comparison. Each script asserts its retained packet equality and proof checks.

The three existing directly relevant checks also pass:

```text
.venv/bin/python -m pytest \
  tests/test_exploration.py::test_cycle_neighbor_node_and_item_bounds_are_visible \
  tests/test_exploration.py::test_unicode_clipping_and_zero_evidence_are_explicit \
  tests/test_exploration.py::test_stale_cached_support_cannot_create_a_delivered_path -q
```

These retain explicit cycle/neighbor/item limits, UTF-8 clipping/zero-evidence
behavior and stale-source refusal. `git diff --check` passes. Retained packets
continue to report anchor/hop/alternate/unresolved omissions; the Rust control
establishes declared configuration uncertainty rather than active-feature proof.

## Delivery

README now explains how to choose a focused follow-up from each relevant
omission. Historical corpus, comparison inputs, engine/harness bundles and
all 114 outcomes remain frozen. This assessment produces no replacement
benchmark scores and runs no provider campaign.

Next is W5.3 deterministic evaluator/tool/answer contracts,
`task_63efbc92c3ec5ae63f25361a667950e3`. Integration and installed-runtime
promotion remain separate tasks requiring explicit release direction.
