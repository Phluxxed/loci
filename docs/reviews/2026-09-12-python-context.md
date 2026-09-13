# W4.2 — Python contract and dependency context

Task: `task_118c2cfa255b8d3fca0a4846bd0bec96`.

Python declarations now participate in the existing authored type family,
`loci_explore(intent="type_dependencies")`, optional `loci_get` type context,
and incoming static impact. The implementation remains in the isolated
`feat/evidence-backed-exploration` branch. This is language delivery against
the [W4.1 source contract](../design/2026-09-12-multilingual-context-cases.md),
not a provider benchmark or production promotion.

## Supported meaning

The Python adapter records parameter/return and variable/field annotations,
generic type arguments, unions, explicit module aliases and direct class
bases. It retains the exact authored occurrence and its indexed declaration
owner, including decorated declarations. Plain unescaped quoted bare or dotted
names are the supported string-forward subset; compound or escaped strings
are not evaluated.

Module `Alias: TypeAlias = Target` declarations become `kind="type"` symbols
with complete assignment spans. The marker must use a unique canonical import
from `typing` or `typing_extensions`, either bare `TypeAlias` or the corresponding
unaliased module-qualified name. Renamed markers, nested alias declarations,
PEP 695 alias declarations and uncertain marker bindings remain outside the
initial subset.

Lexical class/alias declarations and contained import/reexport routes resolve
through the existing Python export index. Module paths must name exactly one
exported member; `P.member` cannot resolve to an imported class `P`. Qualified
module imports and proven imported submodules retain their exact origin.
The same resolution validation is used when persisted records are reloaded.
Extractor version 26 invalidates earlier extraction caches.

Ordinary parameters do not shadow their own definition-time annotations.
Enclosing local values, PEP 695 parameter binders, conditional bindings and
wildcard imports cannot create trusted type edges. Scopes using global/nonlocal
rebinding, deletion or match patterns are conservatively unresolved. Builtin
and known typing markers do not become invented repository definitions.
`Literal` and `Annotated` expressions are conservatively unsupported because
their arguments can be values or metadata rather than types.

`extends` means an authored direct class base. No MRO, protocol/ABC conformance,
metaclass result, runtime dispatch, annotation evaluation or computed-base
inference is claimed. No repository code or dependency installer is executed
to determine a relationship.

## Frozen source cases

| Case | Delivered and checked |
| --- | --- |
| `python_alias_annotation` | Exact `decode`, `Alias`, `Payload` definitions and consumer/barrel origin proof; all three authored relations remain available in type diagnostics. |
| `python_base_and_literal_forward` | Exact direct base and literal-forward origins with authored spelling. |
| `python_known_call_impact` | Known incoming caller, exact definitions and import proof. |
| `python_unproven_contracts` | Missing, external, wildcard, shadowed, generic, computed and compound-string cases produce no fabricated type targets. |
| `python_loci_bundle_contract` | The frozen question selects `_validate_bundle`, `Bundle`, `Span` and `Relation`, preserving complete required definitions and the shared packet shape. |

Explore retains one proof path per delivered definition and reports alternative
paths as omissions. It is not a complete graph dump. Deeper field selection uses
the question; the Bundle test supplies the frozen question. Complete relation
diagnostics verify additional authored edges that do not need a second copy of
the same definition. Python alias markers bypass field-name selection because
their annotation colon does not make the alias a property branch.

Default 8 KiB source-evidence and 16 KiB complete-result budgets are retained.
Checks compare delivered bytes and hashes with the frozen source, validate
packet endpoint/path closure, exercise reduced and zero evidence limits, and
verify source, target and barrel refresh removes stale proof.

## Validation

The directly relevant acceptance set passes **204 tests**, including 24 new
Python parser, binding, delivery and actual stdio MCP checks. Existing extractor,
type-record, context, exploration and public-schema tests pass. The suite command:

```sh
.venv/bin/python -m pytest -q \
  tests/parser/test_python_type_observations.py \
  tests/test_python_type_relation_bindings.py \
  tests/test_python_context_delivery.py tests/test_python_context_mcp.py \
  tests/parser/test_extractor.py tests/parser/test_type_observations.py \
  tests/parser/test_type_models.py tests/graph/test_type_models.py \
  tests/test_type_relation_service.py tests/test_type_relation_queries.py \
  tests/test_type_relations_mcp.py tests/test_exploration.py \
  tests/test_exploration_mcp.py tests/test_type_context.py \
  tests/test_mcp_output_schemas.py
```

The multilingual corpus integrity check passes: 19 cases, 16 snapshots. Its
source files, expected facts and hashes are unchanged. The existing unsupported
language test now uses JavaScript, while Python is asserted supported. A stale
public-tool inventory expectation was updated to include the branch's existing
`loci_explore` tool; W4.2 adds no MCP tool.

Next: W4.3 JavaScript context,
`task_b280004a5bac7e5e92970ea053b51bf8`.
