Production path:

- [`package.json:9`](/tmp/anvil-source-tasks-20260914/t11/package.json:9) registers `anvil` as `./bin/anvil.ts`.
- [`bin/anvil.ts:65`](/tmp/anvil-source-tasks-20260914/t11/bin/anvil.ts:65) resolves its own real path; [`:66`](/tmp/anvil-source-tasks-20260914/t11/bin/anvil.ts:66) takes `process.argv.slice(2)`.
- [`bin/anvil.ts:1462`](/tmp/anvil-source-tasks-20260914/t11/bin/anvil.ts:1462) dispatches `anvil browser …` to `runBrowserCli(command.slice(1), …)`, imported through [`src/browser/index.ts:57`](/tmp/anvil-source-tasks-20260914/t11/src/browser/index.ts:57) from [`src/browser/cli.ts`](/tmp/anvil-source-tasks-20260914/t11/src/browser/cli.ts).
- It passes exactly:
  - `args`: everything after `browser` (`command.slice(1)`);
  - `dependencies.anvilCommand`: `currentFile`, the resolved path of `bin/anvil.ts`;
  - `dependencies.anvilHome`: only when `ANVIL_HOME` is set ([`bin/anvil.ts:1463`](/tmp/anvil-source-tasks-20260914/t11/bin/anvil.ts:1463)).
- No test doubles or explicit command runner are injected by production dispatch. `runBrowserCli` uses its imported production defaults for omitted dependencies and resolves its fallback home directory itself ([`src/browser/cli.ts:554`](/tmp/anvil-source-tasks-20260914/t11/src/browser/cli.ts:554)); its injectable dependency surface is declared at [`src/browser/cli.ts:60`](/tmp/anvil-source-tasks-20260914/t11/src/browser/cli.ts:60).

I first inspected the deferred tool surface; it exposes the `mcp__loci__*` retrieval tools, which I used for the source trace. No material uncertainty in this immediate route.