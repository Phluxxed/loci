# Passive observer preflight

W1.2.5 validates capture before any scored ordinary case. The adapter reads
native terminal events after a task; it does not change the task prompt or
installed MCP server. The rubric helper validates explicit reviewer annotations
and evidence references; semantic judgment remains with the reviewer.

## Actual retained host checks

| Interval | Independently counted native evidence | Required interpretation |
| --- | --- | --- |
| Initial adoption diagnostic, session `01a09e1d-d62a-7e40-8243-d7a5add917a2`, first task only | 0 MCP, 13 shell; final shell completion at line 103, task completion at 112. | Last request at 101 does not end collection. Later catalog discovery is a separate turn and excluded. |
| Retained partial exploration, session `01a09d82-8731-73b2-8c07-58b872b7feac` | 35 MCP and 20 shell; three partial exploration packets; eleven looped outline calls include one completion after the first Code Mode yield. | This interval is aborted and has no final answer. Capture evidence is valid; a completed task outcome or ordinary adoption rate is not established. |
| Dynamic fixture, session `01a09e65-0e26-7a32-abae-9f5537052c88`, turn `01a09e66-d7e8-72b3-bfcd-58cdfd7cdf10` | 12 MCP, 1 shell, 4 failed native statuses; explicit task completion at line 93. Successful type-context get delivers one semantic reference; dependency/locate packets are empty with the stated omissions. | All failures and recovery calls remain. The agent's receipt described four final fixture results, which is not the full executed-call count. Validation failures without structured content are valid source-free results, not missing records. |
| Primary compact reference fixture | One resolved compact type-reference record, 832 server-reported response bytes, default 16,384-byte limit. | Count its semantic relationship even though the compact record has `relation`/endpoint fields rather than a wrapped `edge`. This is current host delivery, not an ordinary outcome. |

The dynamic fixture uses a separate two-file TypeScript repository with a
`Payload` interface imported by `Envelope`. It deliberately requests type
context, zero-budget dependency selection, an absent anchor and a nonexistent
symbol. It is a directed capability check. No selected Anvil case was answered
by this fixture agent.

The complete original local sessions are the source of truth for native item,
turn and outer-output identities. Only bounded purpose-specific normalization
and receipts are retained with the audit. Unrelated history and private raw
sessions are not published.

## Answer/source check

The frozen Anvil corpus validates 638 file hashes and all 18 required-fact source
spans. A known prose answer to the direct renderer case passes explicit review
with zero relationship annotations. That confirms a sufficient non-graph route
is valid. The result is retained in
[annotation-preflight.json](runtime/annotation-preflight.json); it is a synthetic
known-answer check, not a scored provider result.

Supported relationship annotations require an actual native item, a positive
semantic relationship count and an unambiguous matching model-output reference
from that same observed item. Invented IDs, wrong pairings and zero-proof
records cannot satisfy that check. Identical competing packets remain ambiguous;
different packets in one batch wrapper remain independently matched. A reviewer
can record a material unsupported extra claim even when all required facts
appear in the answer.

## Acceptance boundary

The deterministic suites must pass on the final adapter/review source before
`freeze.json` is created. Their receipt records the exact command, test result
and source identities. Required negatives include malformed/missing/duplicate
records, ordinal gaps, altered retained hashes, missing outer outputs,
interrupted/no-final tasks, false answer quotes, changed source, and unsupported
relationship attribution. Native payload bytes use a declared canonical JSON
encoding; model-visible text bytes and server-reported bytes remain separate.

Structural validity is relative to the retained host stream. Upstream silent
logging omissions, opaque shell internals, transformed/unemitted proof and
per-tool causal token attribution remain unknown. No new production telemetry
platform is selected by this preflight.

Final acceptance passed **37 tests** with:

```sh
.venv/bin/python -m pytest tests/test_ordinary_adoption_observed.py tests/test_ordinary_adoption_review.py -q
```

The primary then replayed all three retained native intervals above through the
final observer and matched their independently counted operations and terminal
states. [native-observer-preflight.json](runtime/native-observer-preflight.json)
records interval hashes, counts, outcome/completeness boundaries and final
adapter/test source hashes. The completed dynamic fixture has one unambiguous
model-visible type relationship; the aborted historical interval retains its
three visible partial packets without becoming a completed task.
