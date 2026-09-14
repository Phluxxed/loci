Production path:

- [`package.json`](/tmp/anvil-source-tasks-20260914/t20/package.json:9) maps the installed `anvil` executable to `./bin/anvil.ts`.
- [`bin/anvil.ts`](/tmp/anvil-source-tasks-20260914/t20/bin/anvil.ts:65) resolves its own physical path as `currentFile`; [line 66](/tmp/anvil-source-tasks-20260914/t20/bin/anvil.ts:66) derives `command` from `process.argv.slice(2)`. It invokes `main()` only when this file is the direct executable target ([lines 1479–1487](/tmp/anvil-source-tasks-20260914/t20/bin/anvil.ts:1479)).
- In `main`, the `browser` top-level command dispatches to `runBrowserCli(command.slice(1), …)` ([lines 1462–1468](/tmp/anvil-source-tasks-20260914/t20/bin/anvil.ts:1462)). Thus `anvil browser doctor --json` becomes `runBrowserCli(["doctor", "--json"], …)`.
- It passes exactly:
  - `anvilCommand: currentFile` ([line 1464](/tmp/anvil-source-tasks-20260914/t20/bin/anvil.ts:1464)), the resolved path to `bin/anvil.ts`;
  - `anvilHome: process.env.ANVIL_HOME` only if that variable is set ([line 1465](/tmp/anvil-source-tasks-20260914/t20/bin/anvil.ts:1465)).
- [`src/browser/index.ts`](/tmp/anvil-source-tasks-20260914/t20/src/browser/index.ts:57) re-exports `runBrowserCli` from [`src/browser/cli.ts`](/tmp/anvil-source-tasks-20260914/t20/src/browser/cli.ts:554). The CLI parses those args, defaults output to `process.stdout` and home to `~/.anvil` when not injected ([lines 554–558](/tmp/anvil-source-tasks-20260914/t20/src/browser/cli.ts:554)); other optional dependencies use production defaults where called.

No material uncertainty in this direct production dispatch path.