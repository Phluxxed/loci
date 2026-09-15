# Workflow repair active in the restarted host

The restarted Codex host now runs the W1.8.4.4 repair published at `b2f2664`.
The function-only `captureCommandResult` request returns the complete
function-to-options-to-binding path and 30-character source references. Its
exact source read completes successfully, as does the two-page binding file.
The restart blocker is resolved. This is activation evidence; token savings
still require a new measurement.

## Actual-host requests

The primary called the installed `loci_retrieve` and `loci_read` tools against
the original `/tmp/anvil-source-tasks-20260914/t16` source snapshot. The first
request named only the function. No options name, graph mode or hop parameter
was supplied to obtain its input path.

| Request | Returned relationship records | Reported complete MCP result bytes |
| --- | ---: | ---: |
| Function-only | 6 | 16,268 |
| Richer question | 4 | 14,846 |
| Explicit options/binding pair | 5 | 16,161 |
| Binding file | 11 | 16,162 |
| Browser function | 5 | 16,245 |
| Renderer function | 6 | 15,523 |

The function result includes `captureCommandResult → CaptureCommandResultOptions`
and `CaptureCommandResultOptions → WorkContextBinding`. Its proof includes the
parameter declaration, options field, import, public re-export, target declaration
and resolution controls. Browser and renderer requests retain their required
forward body calls and reverse callers.

Passing returned references unchanged to the installed read tool reconstructs
the full 4,468-byte function in one page and the 14,082-byte binding file in two
contiguous pages, covering offsets 0–8,192 and 8,192–14,082. All item, source and
continuation references use the 30-character form. The three read result sizes
are 5,108, 9,078 and 6,575 bytes.

## Evidence boundary

The nine original tool result objects and their requests are retained under
[workflow-host-activation-20260915](../../.scratch/deterministic-graph-retrieval/workflow-host-activation-20260915/).
The independent Sol/high validator records exact local-envelope comparison,
source identity, linked proof, paging and byte-limit checks in
[validation.json](../../.scratch/deterministic-graph-retrieval/workflow-host-activation-20260915/validation.json).
All nine full result objects match the retained local expectations. Source hashes
and spans, complete linked proof, reference lengths and paging pass; all 638
files match before and after validation, without extras or symlinks.
The earlier 66 passing product tests remain the local implementation evidence;
this turn verifies actual-host activation without changing product code.

Retrieval packets retain partial coverage, explicit omissions and supported
static semantics. Complete selected proof does not establish exhaustive runtime
relationships, internal model reliance or population-level agent adoption.
Recorded raw MCP responses establish what the host returned; reduced Code Mode
summaries do not establish full outer model-visible delivery or a completed
provider interval.

Evidence-byte accounting counts the union of overlapping source spans. Saving
the results through JavaScript also normalizes integral float anchor scores
from `0.0` to `0`: the explicit-pair/file records reencode 4/2 bytes shorter than
their declared sizes while preserving full object equality. Declared sizes
match the retained local serialization; original live-wire byte equality was
not independently observed. See
[primary accounting](../../.scratch/deterministic-graph-retrieval/workflow-host-activation-20260915/primary-accounting.json).
The validator's initial sum-of-spans and reencoded-byte assumptions were
corrected to this contract; its initial receipt is retained separately.

## Next

W1.8.4.4's selected repair and activation check are finished. The broader value
gate remains open: the last two-binding measurement used a median 479,060 input
tokens, 1.9216 times the original baseline. That result and its strict-answer and
historical-review qualifications are unchanged.

The recommended next step is a separately selected, freshly frozen two-binding
comparison using fresh Terra/high agents, the original prompts/source, and the
unchanged 1.25-times per-case cost limits. Measure complete workflow input,
answer completeness and graph delivery together. No new provider trial was
selected or launched by this restart verification.
