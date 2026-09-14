The production path is:

- [`package.json`](/tmp/anvil-source-tasks-20260914/t06/package.json:9) publishes `anvil` as `./bin/anvil.ts`.
- [`bin/anvil.ts`](/tmp/anvil-source-tasks-20260914/t06/bin/anvil.ts:65) derives `command` from `process.argv.slice(2)` and imports `runBrowserCli` at [line 48](/tmp/anvil-source-tasks-20260914/t06/bin/anvil.ts:48).
- Its `browser` branch calls `runBrowserCli(command.slice(1), …)` at [lines 1462–1466](/tmp/anvil-source-tasks-20260914/t06/bin/anvil.ts:1462), passing:
  - remaining CLI arguments after `browser`;
  - `anvilCommand: currentFile`, the resolved absolute path of `bin/anvil.ts`;
  - `anvilHome` only when `ANVIL_HOME` is set.
  It propagates a nonzero returned code to `process.exitCode` at [line 1467](/tmp/anvil-source-tasks-20260914/t06/bin/anvil.ts:1467).

`runBrowserCli` is re-exported through [`src/browser/index.ts`](/tmp/anvil-source-tasks-20260914/t06/src/browser/index.ts:57), then parses and dispatches those arguments in [`src/browser/cli.ts`](/tmp/anvil-source-tasks-20260914/t06/src/browser/cli.ts:554). Unprovided dependencies use production defaults: stdout, `~/.anvil`, `runBrowserCommand`, renderer/Codex-registration functions, and `serveBrowserMcp` ([lines 554–578](/tmp/anvil-source-tasks-20260914/t06/src/browser/cli.ts:554)).

For the persistent Codex MCP route, registrations launch that same absolute `anvilCommand` with `["browser", "mcp", "serve", "--network-mode", "local"|"corporate"]` in [`src/browser/codex.ts`](/tmp/anvil-source-tasks-20260914/t06/src/browser/codex.ts:38). No material uncertainty: this is the direct production caller found in source.