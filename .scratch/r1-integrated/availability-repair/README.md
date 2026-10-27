# R1 native-host availability repair

The earlier 16 Terra executions have valid retained native accounting and frozen grades, but tool availability in the measured host was never established. They are **availability-unverified**, and the architectural recommendation derived from their condition scores is withdrawn. [Correction and preserved archive hashes](validity-correction.json). Neither non-use nor a deferred catalog omitted from top-level logging proves absence.

The repair extends the existing R0.1/R1 native execution, accounting, snapshot, archive and replay components. It introduces no new host, launcher, sandbox, permission profile, global setting or API credential.

## What must pass

1. Before scored source copies are prepared, four **unscored native Codex sessions** run under the same pinned condition/model/effort/native settings. Their independent TypeScript probe repositories and stores contain no scored task material.
2. Each session's first tool action executes a frozen Code Mode program that reads `ALL_TOOLS`. Acceptance joins that exact program (allowing only outer whitespace) to its actual native output by `call_id`; model-written assertions and files do not count. The complete Loci set must be exactly 0 / 2 / 4 / 2 for native / path-only / integrated / eager. Unrelated MCP tools remain permitted.
3. Positive probes must successfully invoke every enabled operation through Codex. Native `McpToolCall` events, arguments and results are retained and reconciled with native accounting. Retrieve → read must use a returned reference. Integrated semantic → proof must follow a returned identity and provide the fixture's supported entry-to-Public type relationship with exact source/hash evidence. Missing calls, errors, filtered tools, stale bytes or invented identities fail the gate.
4. All four probe receipts must bind the same freeze and deterministic qualification gate. Shared `r1.prepare` and `r1.execute` revalidate native traces, operation receipts, current configuration/implementation hashes and gate identity. A `status: passed` field alone cannot authorize a run. Probe failure is archived and stops; it is never automatically retried or counted as a scored task.
5. Positive measured servers use command-local `mcp_servers.loci.required=true`. Every fresh measured session also records its exact live catalog as its first tool action. The actual native user message must match the submitted frozen prompt. Missing or mismatched evidence writes `treatment.json` as invalid and stops before the correctness oracle. Resume reaudits native evidence; it cannot promote an old unchecked run.

The `required` startup setting fails an enabled server's startup when initialization fails; allowlists and deferred discovery have distinct roles. See the [official MCP documentation](https://learn.chatgpt.com/docs/extend/mcp?surface=cli) and [configuration reference](https://learn.chatgpt.com/docs/config-file/config-reference). Startup success alone is never treated as callable-tool proof.

## Measurement boundary

This is a **new, discovery-primed protocol**. Mandatory catalog discovery changes agent information. Its full tokens and elapsed time remain in measured task accounting. Original engineering task text, source snapshots, graders, model (`gpt-6.1-terra`), effort (`max`), four tool conditions and task order are preserved. No answer-schema, allowlist or candidate tuning was performed. Earlier scores are known; a repair replication is not an untouched prospective trial and must not be pooled with the original runs.

Probe transcripts, source, caches and stores are separate; none is copied into scored context. Tool use for the engineering task remains voluntary after discovery. The assurance is bounded: probes establish operational usability under pinned host settings, and measured catalogs establish discovery in each measured session. Continued operational success of every tool cannot be claimed without actual measured calls.

Native error/usage evidence, failed/incomplete probes and all immutable receipts are retained. Complete billing and invisible retries remain unknown. The ordinary existing ChatGPT login is checked, and API-key/base-URL environment overrides are removed as before. No tool or native host availability is claimed from unit tests.

## External execution

The new freeze and exact normal-Terminal command are in [pilot-availability-v1/README.md](../pilot-availability-v1/README.md). Start with **preflight-only**: four unscored condition checks and zero scored assignments. This Codex development session must not launch another Codex process. A failure retains its error and stops. No sandbox/profile/global configuration troubleshooting is part of this repair.

`tests.txt` contains the focused no-native-launch acceptance result. The tests combine real service source/proof packets with native-event fixtures, plus actual previously retained native traces as negative availability controls. They do not substitute for the external probes.
