`captureCommandResult` accepts the full `WorkContextBinding`, not the public view.

- Its options declare `binding: WorkContextBinding` at `src/tool-results/service.ts:53-60`; the function validates it before capture at `:411-414`.
- That type is imported from the public barrel at `src/tool-results/service.ts:23`, re-exported by `src/work-context/index.ts:23-30`, and defined in `src/work-context/binding.ts:28-45`.
- `WorkContextBindingView` is also exported (`index.ts:28`) but is not accepted. Its schema omits `session_id` and `provenance.observed_cwd` (`binding.ts:47-67`), and `workContextBindingView` deliberately removes both (`:130-139`).
- Consequently it fails both static compatibility and runtime authorization: capture calls `assertActiveWorkContextBinding` through `validateBinding` (`service.ts:124-132`), whose guard requires `session_id` and `provenance.observed_cwd` (`binding.ts:217-235`).

No material uncertainty: the import/re-export chain and runtime guard directly establish the contract.