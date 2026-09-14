Production path:

- [`package.json:9`](/tmp/anvil-source-tasks-20260914/t03/package.json:9) exposes `anvil` as `./bin/anvil.ts`.
- [`bin/anvil.ts:1479`](/tmp/anvil-source-tasks-20260914/t03/bin/anvil.ts:1479) invokes `main()` when run directly.
- [`bin/anvil.ts:1462`](/tmp/anvil-source-tasks-20260914/t03/bin/anvil.ts:1462) handles `anvil browser …` by calling `runBrowserCli(command.slice(1), …)`.
- It passes:
  - `anvilCommand: currentFile`, the canonical real path computed at [`bin/anvil.ts:65`](#/tmp/anvil-source-tasks-20260914/t03/bin/anvil.ts:65)
  - `anvilHome` only when `ANVIL_HOME` is set ([`bin/anvil.ts:1463`](#/tmp/anvil-source-tasks-20260914/t03/bin/anvil.ts:1463)).
- [`src/browser/index.ts:57`](/tmp/anvil-source-tasks-20260914/t03/src/browser/index.ts:57) re-exports the implementation from `cli.ts`. [`src/browser/cli.ts:554`](/tmp/anvil-source-tasks-20260914/t03/src/browser/cli.ts:554) parses those arguments and resolves `anvilHome` from the injected value, then `homeDir`/OS home plus `.anvil`.

Static source search found no other in-repo non-test/non-doc caller of `runBrowserCli`; external consumers remain possible.