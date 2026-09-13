# W5.4 canonical source integration

Vik authorized integration on 13 September 2026 in response to the proposal to
merge the accepted exploration branch into canonical source. The target is
`master` in `/Users/brummerv/loci`. W5.4 is
`task_ac21c3c2d3153e5a4e28879935240777`.

## Integrated scope

The accepted source is `feat/evidence-backed-exploration` at
`ffd9b4806352825d70916b012fe2f8f23a40bb66`, including the implemented multilingual
type/dependency context and bounded exploration core, W5.1 exact Go/Cargo control
retrieval, W5.2 selection dispositions/guidance and W5.3 versioned evaluator
contracts. Canonical `ebbd0937abf7713854876433b1d6637f79e1abcd` was followed by
`6f01269`, which records this integration authorization in Manifest.

The native merge preserves both histories. Its only conflict was the branch's
stale `.manifest/objectives/obj_0110c8712b21bdd2c12532f189d84a74.json`. Resolution
retained the authorized canonical graph byte for byte. No source conflict or
product behavior adjustment was required.

Before adding this report, the complete merged index was compared with the
accepted branch. Its only differences were the canonical Manifest and four
canonical W3 decision reports. Every product, test, harness, corpus, comparison
bundle and result therefore retains exact Git blob identity from the accepted
branch. Unrelated `.scratch` work remains outside the merge.

The pinned reference to this report in W5.4's Manifest completion identifies the
exact resulting integration commit. Its source tree is the accepted source
above; source integration does not itself establish new efficiency results.

## Integrated acceptance

The following bounded command passed **168 tests** on the merged canonical
checkout:

```sh
.venv/bin/python -m pytest \
  tests/test_multilingual_context_mcp.py \
  tests/test_exploration.py \
  tests/test_exploration_output.py \
  tests/test_type_relation_service.py \
  tests/test_resolver_control_source.py \
  tests/test_resolver_control_mcp.py \
  tests/test_resolver_control_adapter.py \
  tests/test_multilingual_context_answers_v2.py \
  tests/test_multilingual_context_observed_v2.py \
  tests/test_multilingual_context_tools_v2.py -q
```

This covers real multilingual stdio packets, schema and cross-root identity,
source/config freshness, intent and traversal bounds, exact output packing,
type-record validation, W5.1 source/MCP/adapter control access and W5.3 future
evaluator contracts. Combined with exact tree identity and the absence of source
conflicts, this is the integrated acceptance boundary. No provider run or broad
historical replay was needed.

The non-frozen staged diff passes `git diff --cached --check`. The whole staged
diff reports two pre-existing trailing blank lines in frozen routing v1/v2
`selection-policy.md` files. Those evidence files remain byte-identical to the
accepted branch; they were not reformatted during integration.

## Runtime boundary

Checks use the canonical checkout's virtual environment and import its source.
No installation, package upgrade, MCP host reconfiguration or shared process
restart is performed by W5.4. Existing processes are not claimed to have adopted
the merged code; any editable consumer of canonical source must be verified as
part of runtime promotion.

Next is W5.5, `task_7b37dbd0d2e578949b7d38bc5160f305`: activate and verify the
integrated shared Loci runtime under Vik's separate explicit direction. The
canonical Manifest remains the sole work/status authority. Future repository
work should begin from the integrated canonical revision; the exploration branch
is retained as historical source provenance. No provider campaign or historical
rescore is part of this integration.
