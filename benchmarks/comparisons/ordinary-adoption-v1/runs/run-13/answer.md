Primary functional check, known-answer condition; not a fresh task outcome.

`captureCommandResult` accepts `CaptureCommandResultOptions` at
`src/tool-results/service.ts:411`; that options type declares
`binding: WorkContextBinding` at lines 53–60. The imported public type comes
through `src/work-context/index.ts` (service line 23), whose lines 23–30
re-export both binding types from `binding.ts`.

The defining `WorkContextBinding` declaration is
`src/work-context/binding.ts:28–45`. It requires `session_id` and
`provenance.observed_cwd`. The separate view schema/type at lines 47–67 omits
those fields, so a bare `WorkContextBindingView` is not the declared capture
input contract. This establishes the declarations and required-field
difference, not any particular caller's runtime value or every possible
adaptation of a view.

The delivered type-dependency packet proved the options-to-binding edge and
returned the complete binding declaration. Its barrel support was only the
opening line of the multiline re-export; the separate exact file read supplied
the missing statement and the view comparison. Native IDs and exact
model-output matches are in `functional-check.json`.
