# Observed calls and exact delivery

Each unique host-observed tool-call ID counts once. Count the attempt when it
starts, including failures and calls unfinished at timeout. Repeated starts,
missing terminal events, changed arguments, duplicate results or an unmatched
adapter attempt invalidate complete accounting; never treat missing output as
zero. Retain raw host events, every adapter attempt, exact responses and source.

Every typed evaluation response binds to its internal attempt ID, exact forwarded
arguments (including declared defaults), compact UTF-8 JSON, validated source
spans and latency. Every source occurrence is verified against the exact frozen
file and indexed declaration provenance. Repeated source/signature strings count
again. V2 source coverage rules are unchanged; names or transformed metadata do
not count as delivered source. Gold stays outside the agent workspace.

Argument validation can reject a call before the adapter body executes. Count its
exact host/MCP error payload and call, with zero source only when the audited tool
surface and error representation establish that. Resource helpers expose no
resources in this isolated profile. Their exact empty results and host errors,
including a nonexistent server argument, count as source-free costs. The server
label on a helper event is its requested server, not a newly configured source.
An unexpected tool, nonempty resource result or unknown payload stays inconclusive.

The complete output measure is the UTF-8 length of all model-visible result
payload strings: compact JSON for structured output, exact text for errors and
helpers. Provider tokens independently include host timing/framing. Gross input
is primary; cached input is a subset, output includes reasoning, byte-derived
source token estimates are separate, and missing usage is unavailable.

No reason, detail, because, causal classification, proven subtotal or avoidable
read count is an observed measurement in v3. Source-validation events have no
such fields. Actual search-selection identifiers remain supported for deliberately
selected gets. Invalid selection returns no source and its attempt cost remains
recorded. Task answers, full run validity, recoverable errors, source coverage and
all-call totals are distinct facts. Source/cost replay never assumes task success.

All frozen byte/span/call/time/token caps remain in force. The adapter withholds
oversized source before delivery and retains a failed-budget outcome. Host errors
and helper outputs count toward run totals; actual overshoots invalidate a run.
Provider token checks occur at reported usage boundaries and are not generation
caps. Inner expansion work must be charged to its outer operation, never omitted.
