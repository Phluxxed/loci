# Aborted exploration measurement v1

This batch is **inconclusive because its measurement layer is invalid**. It
was stopped after 17 complete result files and 1 partial attempt; the remaining
84 planned attempts were not started. Existing raw artifacts and scores are
preserved without rescoring, replacement or retry.

The first A attempt made valid `graph_anchors` and `graph_neighbors` calls.
Their host arguments match the delivery ledger exactly. The ledger records
those specific public operation names; the source trace categorizes both as
`graph`. The new v1 reconciler incorrectly required the ledger to use the
trace category, producing `delivery_trace_mismatch` and an incomplete
measurement. This failure is unrelated to product correctness or efficiency.

Preparation tested the new exploration route and exact reads, but omitted a
real legacy graph call through the new reconciler. The replacement protocol
must add that coverage and distinguish ledger operation names from trace
categories. It will retain the same product source, tools, tasks, prompt,
model, numerical limits and gates, and use a separately published freeze for
a new full 102-attempt matched block. No task outcome motivates a product or
threshold change.

The partial attempt has no complete host outcome or result file; absent costs
are unavailable. `abort.json` inventories every retained artifact. The v1
harness and its original freeze remain immutable.
