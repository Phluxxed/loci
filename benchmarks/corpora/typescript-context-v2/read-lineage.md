# V2 read lineage and complete output accounting

The original [causal classification](../typescript-context-v1/read-lineage.md)
and exact replay semantics remain in force. V2 changes the authored required
source spans and keeps invalid attempt accounting separate from that classifier.

Each adapter attempt has a monotonic `attempt_id`. A validated read also has the
existing `event_id`, which alone may be a later causal parent. A rejected
attempt retains its exact arguments and `because` value, a bounded structured
error, its costs and failure, but receives no valid causal event ID. Source
from a rejected read is withheld. Neither prose nor a search ID is converted
into an event ID.

The adapter persists a delivery ledger independently of valid trace events.
The runner reconciles it against every terminal Codex tool-call event, completed
or failed. This
includes schema errors and the empty MCP resource helpers, which can execute
outside the adapter's read function. Unexpected source-capable tools, unknown
payload forms, missing responses or changed delivery make accounting
inconclusive, never zero. Invalid attribution still disqualifies a run even
when all its output costs are known.

The complete output measure is the UTF-8 length of the model-visible result
payload: compact JSON for a structured result, or the exact delivered text
strings for a text result. Every field within structured JSON counts. For a
resource helper its text already contains the returned JSON. For host validation
errors the error text counts. The Codex timing prefix and message framing remain
included in provider-reported tokens, independently of this payload measure.
The raw content representation and per-response totals are retained. Offline
transport verification checks these representations against the actual next
Codex request, without authentication or a provider model call.

All actual source occurrences count each time delivered. V2's complete output
and call totals include rejected reads and helpers; the underlying validated
trace subtotal remains separately replayable. All frozen limits and retained
failure rules apply. Source is withheld after adapter budget exhaustion;
additional rejected calls and host responses retain their cost, and any total
overshoot fails the run. No runtime is claimed to impose a provider-side token
or host-helper generation cap.

Source-bearing signature strings are credited only when their exact bytes occur
inside the identified indexed declaration. Repeated source/signature occurrences
count separately. Transformed signatures stay metadata without source credit;
complete payload bytes still count. A signature can root a declared dependency
gap, but initially planned function hydration is not reclassified as avoidable.
