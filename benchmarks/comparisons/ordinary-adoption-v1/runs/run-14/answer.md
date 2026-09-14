Primary functional check, known-answer condition; not a fresh task outcome.

The browser feature is `runBrowserCli(args: string[], dependencies:
BrowserCliDependencies)` at `src/browser/cli.ts:554–588`. Its immediate
production caller is `bin/anvil.ts::main`: the browser branch at lines
1461–1470 passes `command.slice(1)`, `anvilCommand: currentFile`, and `anvilHome`
only when `ANVIL_HOME` is set. A nonzero result is assigned to
`process.exitCode`.

The entrypoint imports the feature through `src/browser/index.ts` at
`bin/anvil.ts:48`; the barrel re-exports it from `cli.ts` at lines 57–58.
The impact packet supplied the incoming import-resolved call, the exact caller
and callee source, and the complete import/re-export statements. Its partial,
non-exhaustive scope and alternative-path/hop-limit omissions do not establish
the only caller or any live browser invocation. Native IDs and exact
model-output matches are in `functional-check.json`.
