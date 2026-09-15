# Anvil evaluator receipt

Scope: `W1.8.4.4.10.2.2.3.1`, evaluator-only creation-evidence oracle.

- Retained export: `/tmp/anvil-source-tasks-20260914/t21`; the 638-file map in
  `ordinary-adoption-v1/cases.json` validated on 2026-09-15.
- Runtime prepared only in `/tmp/anvil-evaluator-reference.NRqvMN` with the
  retained `package-lock.json` and `npm ci --ignore-scripts`; Node `v26.5.0`.
- Unchanged source: after `npm ci --ignore-scripts` in
  `/tmp/anvil-evaluator-baseline.O1FCg4`, the original focused regressions
  passed (37 tests); evaluator status was `failed`, including
  `evidence_categories`, marker controls, history controls, recursive controls,
  and safe-public-output.
- Disposable reference patch: status `passed` on all eight hidden checks.
- Disposable bad patch that labels every source `Task details`: status `failed`
  on category, marker-control, and history-control checks.

The retained source, production Anvil, source manifest, and benchmark design
artifacts were not edited. The reference and bad patches exist only under
`/tmp`; they are never a measured run or a product fix.
