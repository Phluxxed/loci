# Qualification preparation acceptance

Verified on 12 September 2026, before provider measurement.

- The declaration check preserves all 104 original corpus files, all 41
  historical frozen harness files, every effective A/B prompt, the unchanged
  numerical evaluator, and the original 102-attempt AB/BA schedule. The policy
  remains 1,154 bytes plus one newline. See
  [declaration-verification.json](declaration-verification.json).
- The pinned repaired engine, source tree and extractor identity passed runtime
  verification. Qualification adds version-owned runner, report and replay
  modules without modifying an earlier frozen harness or result.
- Preparation verified Codex CLI 0.154.0, the controlled Python/package
  environment, existing ChatGPT authentication and the fresh GPT-5.6 Luna model
  catalog. Corpus preflight covers all 17 cases. See
  [environment-verification.json](environment-verification.json) and
  [preflight.json](preflight.json).
- Both A/B offline probes passed through the actual `run_attempt` entrypoint,
  real Codex/MCP and a loopback Responses endpoint. Both expose the same 14
  repository tools plus three helpers and the published repaired schema. Both
  accepted explicit null byte limits and proved exact native payload delivery,
  requested source-anchor receipt, A/B identity and complete one-call
  accounting. The fixture retains `maintained_exposure: null`; this probe does
  not substitute for any of the nine maintained candidate attempts. See
  [measurement-transport-verification.json](measurement-transport-verification.json).
- Independent replay of both retained offline attempts passed against freshly
  indexed snapshots. The new report/replay checks passed six focused tests and
  17 related tests, including version mixing, provenance tampering, the full
  maintained denominator and unchanged numerical decisions. Pyright passed for
  all new qualification modules. The staged whitespace check reports only the
  final blank line preserved from the exact frozen selection-policy bytes;
  all other staged files pass.

Preparation used zero provider calls and establishes no model-adoption or
comparative-performance result. Qualification code and this evidence must be
published first; the separate committed freeze must then validate before the
first scheduled provider attempt.
