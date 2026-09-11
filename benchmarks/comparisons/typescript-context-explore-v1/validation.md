# Pre-measurement verification

Completed on 12 September 2026 before any provider model attempt in this trial.

- 48 focused tests pass across the new adapter, source/relationship scorer,
  observed accounting, request/runner boundary, independent replay and report.
- Pyright reports zero errors and warnings for all seven new harness modules
  and six new test files.
- The 23 existing v3 tool/observed tests pass. The old frozen harness and
  corpus files remain unchanged; their hashes are checked again by the freeze.
- Fresh extraction resolves every authored endpoint in the original 17 cases
  as indexed or explicitly source-only. No case is dropped or repaired by
  changing its gold.
- The new proof scorer passes the fourteen real source fixtures, including
  ambiguous and shadowed negatives. Additional direct native exploration
  checks on the three maintained Anvil snapshots report zero delivered-proof
  violations (2, 2 and 4 examined nodes respectively, within the common cap).
- Eight real Codex/MCP loopback probes verify exact get in both arms, actual
  exploration by seed and query, an empty evidence budget, unknown arguments,
  strict integer validation and source-free resource helpers. All eight
  reconcile exact host payloads and observed calls. No provider model is used.
- A exposes 13 evaluation tools plus three host helpers; B exposes the same
  13 tools plus `loci_explore` and the same helpers. Shared schemas are identical.
  Canonical schema hashes are retained in `transport-verification.json`.
- Replay tests construct genuine adapter source/proof deliveries and matching
  host events, then reject altered source, altered scores and missing
  relationship measurement. The runner cannot report qualification before
  replay. Missing or malformed host evidence remains unavailable.

The real transport probe discovered one missing verifier import during
preparation; its incomplete loopback evidence is retained separately and the
successful canonical proof follows the correction. Review also found and
fixed missing-relationship replay acceptance, completion before replay and
malformed host-event usage reporting. The declared hard-interruption boundary
remains fail-closed: an incomplete attempt is not retried or overwritten.

These checks establish the new measurement boundary. They are not evidence
that the candidate improves agent outcomes; the separately frozen 102-attempt
comparison must establish that result.
