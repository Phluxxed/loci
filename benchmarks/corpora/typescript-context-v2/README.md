# TypeScript context protocol v2

V2 corrects the evaluation defects identified in the 10 September 2026 A-only
baseline. It is declared before new measurements. The v1 corpus, controls,
snapshots, raw attempts and strict scores remain historical evidence. No v1
answer is relabelled as a v2 result, and no candidate improvement is claimed.

## Changes and retained controls

- All four endpoint controls now ask for `declared_parameter_type`: the written
  annotation on the resolved callee's parameter, independently of the argument
  expression at the call site. The source-authored value remains `unknown`.
  The prompt does not disclose the origin file that the agent must discover.
- The retrieval-limits task asks for `emitted_message_keys`, explicitly the
  branches selected for the supplied input. Its four expected values and order
  are unchanged; unused message constants are not part of the answer.
- Required declaration spans omit surrounding whitespace and declaration-leading
  export modifiers. The body must still match the exact original file and byte
  range, including every internal token, member, alias and heritage clause.
  Variable bindings use the complete declarator without the surrounding
  `const`/`let`/`var` keyword or statement semicolon; their names, values, type
  annotations and `as const` assertions remain required.
- Import and re-export statements retain all their tokens. Direct-export call
  controls have separate exact export headers, including the declaration name,
  so a body can count independently while missing origin evidence stays visible.
  The default-identifier case retains the full `export default num;` statement.
- The retrieval-limits task no longer requires the members of
  `BrainCompiledEvidence`: the input supplies `evidence=[]`, and no evidence
  member affects a requested fact. Its corresponding semantic dependency is
  removed from this task's gold. Full outer input declarations and alias linkage
  remain conservative source requirements; v2 does not claim minimal evidence.
- The common prompt explains exact causal event IDs, their difference from
  search-selection IDs, and the meanings of hydration and verification. It
  contains no expected answer, gold span, task-specific path or oracle feedback.
- V2 records rejected attempts independently of validated read chains. Invalid
  attribution remains a failure and cannot become a successful causal recovery.
  Complete output accounting includes helper and error responses.
- Source-bearing signatures in search, get and outline results also count when
  their exact bytes can be located inside the identified indexed declaration.
  A transformed signature receives no source credit. A repeated signature and
  body are separate delivered occurrences, and all metadata retains its output
  cost. This lets actual signature evidence root a later type-context gap.

The 17 tasks, 14/3 group split, source archives, production baseline, requested
model, repetition counts, budgets and numerical acceptance thresholds are
unchanged. There are 71 required source spans and 34 task-relevant semantic
relationships. The files and archives are byte-identical to v1; `span-changes.json`
records the exact source-range changes. The corpus and controls are separately
hashed and identify their v1 predecessors.

## Source coverage and interpretation

Coverage uses the existing exact-interval scorer against the new authored spans.
It does not strip or normalize returned source. A declaration body retrieved
without `export` or a final newline can satisfy its body requirement. Constant
declarators need no surrounding declaration keyword or statement semicolon. Missing a
member, supplying a same-named declaration from another file, or omitting required
import/export evidence cannot satisfy those respective requirements. Adjacent
exact fragments may combine to cover a requirement.

Causal attribution still requires an explicitly linked missing-context chain
rooted in delivered task source that completes new required source. An unproven
claim stays inconclusive. Completing v2 does not guarantee a positive baseline
opportunity; zero or inconclusive results must be reported unchanged.

New A-only measurements are descriptive. Future A/B or A/B/C comparisons rerun
all their arms in a new matched batch. V1 and v2 measurements are never paired.
The three maintained tasks remain a small, single-repository experiment.

## Verification

`load_corpus(Path('benchmarks/corpora/typescript-context-v2'))` and
`load_controls(corpus)` verify the complete package. Focused protocol checks
verify source integrity, corrected answer fields, real body retrieval, missing
members, origin evidence and unchanged v1 artifacts. Preflight identifies source
endpoints independently of any model attempt.

See [comparison controls](comparison-controls.md), the original
[corpus method](../typescript-context-v1/README.md), and the retained
[historical results](../../results/typescript-context-baseline-v1/README.md).
