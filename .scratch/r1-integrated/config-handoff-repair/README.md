# R1 configuration handoff evidence

The external command stopped before Codex launch because the runner compared the entire global configuration file byte-for-byte with its frozen hash. [Reported traceback](reported-failure.txt).

[Exact reconstruction](diagnosis.json) establishes the cause: only the root default model changed from `gpt-6-sol` to `gpt-6.1-sol`; changing that value back in RAM reproduces the original SHA256. The actual pilot CLI independently pins Terra 6.1/max. No broader configuration difference was inferred and no global setting was edited.

The repair binds all TOML semantics except those two explicitly overridden root defaults. Raw hashes are retained as observations, not discarded. Before launch and at qualification, all other values remain checked. Native contexts independently verify actual model, effort and protections. Existing unversioned R0/R1 records retain their full raw-hash behavior. R0's legacy pair checker is unchanged because the active R1 runner does not call it. JSON-compatible configuration values are supported; unrepresentable TOML values fail closed.

[CLI handoff evidence](cli-handoff-summary.json) uses the actual existing CLI entrypoint, frozen settings and current global config. The old command fails at the expected configuration guard; the new one reaches the Codex process boundary with correct Terra/max arguments and scrubbed API environment. The output directory is isolated and login/process creation intercepted. These are offline verification records, explicitly not real host attempts, authentication proof or successful availability gates. The deliberately intercepted failed-gate archives live only under `offline-cli-*`, never under the real pilot output root.

The focused [test log](tests.txt) covers legacy checks, preparation, qualification, gate evidence, first-turn catalogs, malformed configuration, protected setting changes and intercepted CLI execution. Tests are not substituted for native connectivity.

The [instruction update](instruction-update.json) separately records Vik's new AGENTS text. Its startup hash is re-frozen; instruction checking is not weakened. This repairs the existing native harness rather than introducing a new eval harness.

The next required evidence is the real native four-condition preflight in [pilot-availability-v2](../pilot-availability-v2/README.md), run externally under the existing Terminal constraint. Scored tasks remain blocked until all four probes pass. Any startup rejection now retains a unique traceback receipt and exits nonzero.
