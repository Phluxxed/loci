Production path:

- [`package.json`](/tmp/anvil-source-tasks-20260914/t17/package.json:8) registers `anvil` as `./bin/anvil.ts`.
- [`bin/anvil.ts`](/tmp/anvil-source-tasks-20260914/t17/bin/anvil.ts:65) derives `currentFile`; line 66 parses `process.argv.slice(2)`. Its direct-execution guard calls `main()` at line 1479.
- `main()` routes `anvil browser …` when `command[0] === "browser"` at [`bin/anvil.ts:1462`](/tmp/anvil-source-tasks-20260914/t17/bin/anvil.ts:1462). It imports `runBrowserCli` through the browser barrel at line 48.
- The immediate invocation is [`bin/anvil.ts:1463`](/tmp/anvil-source-tasks-20260914/t17/bin/anvil.ts:1463): `runBrowserCli(command.slice(1), { anvilCommand: currentFile, ...(ANVIL_HOME ? { anvilHome: ANVIL_HOME } : {}) })`. It propagates a nonzero return value to `process.exitCode` at line 1467.
- [`src/browser/index.ts:57`](/tmp/anvil-source-tasks-20260914/t17/src/browser/index.ts:57) re-exports the implementation from `cli.ts`.
- [`src/browser/cli.ts:554`](/tmp/anvil-source-tasks-20260914/t17/src/browser/cli.ts:554) receives the sliced browser arguments and dependency object. The supplied production dependencies are only the canonical Anvil command path and optional `ANVIL_HOME`; its other dependencies default internally (including stdout, home directory, and browser command runner) at lines 555–557.

No material uncertainty: Loci’s static graph proves the `main → runBrowserCli` call at line 1463.