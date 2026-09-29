# Handoff: Codex MCP startup failure reported from Workbench

Start the next session in `/Users/brummerv/phluxxed/workbench`.

## Objective

Diagnose the repeated 60-second Codex MCP startup failure reported from Workbench. Focus on the Codex host/runtime boundary and produce correlated evidence that identifies where the MCP handshake stops. Treat Loci as a known-fast server unless new evidence places the failure inside it.

Completion criterion: one failed reproduction is correlated across the Codex process UUID, thread/request identity, host lifecycle trace, and stdio handshake boundary, localizing the failure to one of host scheduling, request delivery, server response, response consumption, or host cancellation.

## Ground truth established so far

- The reported failure used `startup_timeout_sec = 60`, not 30 seconds.
- The earlier claim that ambient `python3` startup caused this incident was wrong and has been retracted.
- Current global registration is temporarily armed with
  `/Users/brummerv/loci/.scratch/loci-stdio-boundary-proxy.mjs`, which
  transparently launches `/Users/brummerv/.local/bin/loci-mcp`, with:
  - `LOCI_BASE_DIR=/Users/brummerv/.codex/loci-index`
  - `LOCI_STORE_NAMESPACE=codex`
  - `startup_timeout_sec = 60`
- No Workbench-local MCP override was found.
- Direct Loci handshakes are healthy: a prior 64-process concurrent test completed 64/64, with a maximum around 5.27 seconds.
- Recent Loci process traces show nine launches reaching `stdio_run_entered` in approximately 561–797 ms.
- The exact full Workbench app-server harness has shown host-level stalls while the matching Loci process reached `stdio_run_entered` in about 595 ms.

## 12:33 AEST diagnostic update (Codex 0.150.0)

- The full Workbench app-server feedback loop now wraps Loci at the stdio
  boundary and records only timestamps, process IDs, initialize request IDs,
  EOF, exit status, and signals. The bounded log is
  `/Users/brummerv/loci/.scratch/loci-stdio-boundary.jsonl`.
- One single run plus 16-, 32-, 48-, and 56-way concurrent runs completed
  154/154 app-server starts with Loci connected and 20 tools. The slowest
  host-visible status was 59.500 seconds in the 56-way run.
- The 64-way attempt is invalid evidence: the outer execution harness ended at
  about 68 seconds and closed every child. Eighteen connections had received
  initialize but had not responded before that cancellation. Do not present
  these as Codex MCP timeouts.
- Each app-server thread launch created two Loci connections. In the healthy
  armed smoke, both received initialize within 6 ms of proxy exec and emitted
  responses in 656.787 ms and 706.789 ms.
- The armed smoke is fully correlated:
  - marker: `wb-mcp-armed-smoke-20260827T1237AEST`
  - process UUID: `pid:73675:118a5df4-66f7-4729-adb4-b7ee8ad87e2e`
  - thread ID: `01a04110-97d4-78b2-9188-be3d601cbc5e`
  - app-server request ID: `2`
  - OTLP trace ID: `16912c424b1347c64064eb1856171413`
  - service version: `0.150.0`
- The actual 60-second failure remains unreproduced. Leave the proxy armed for
  an ordinary Workbench reproduction, then correlate the proxy's `host_pid`
  with the `pid:<host_pid>:<uuid>` value in `logs_2.sqlite` immediately.

## Telemetry findings

The local OTLP receiver stores raw data at:

`/Users/brummerv/Library/Application Support/codex-telemetry/telemetry.sqlite3`

The Codex host log database is:

`/Users/brummerv/.codex/logs_2.sqlite`

The Loci startup trace is:

`/Users/brummerv/.codex/loci-index/mcp-startup.jsonl`

Retention is approximately 30 days. Raw OTLP payloads and Codex log bodies may contain prompts, tool arguments, paths, and identifiers; use bounded queries and project only required fields.

### Captured 09:39 AEST run

- Codex service version: `0.149.1`
- Thread trace ID: `017a135b35c598b26c3700e1ea1e0079`
- Candidate thread ID from host evidence: `01a04071-ca85-7102-b1b7-4e574baace24`
- The entire `thread/start` trace lasted 5.376 seconds.
- Loci's host-side `initialize` span completed in 817.333 ms.
- Other local MCP initializations completed in roughly 275 ms to 1.399 seconds.
- The host then shut down and cancelled all local MCP services; six child processes exited via graceful SIGTERM.

This was not a 60-second Loci startup timeout. It is useful evidence about host-wide cancellation, but it must not be presented as the user's reported failure.

### Captured 10:09 AEST session

- Thread trace ID: `fa2316e8dcd845fbc272a1c7ec941795`
- Loci's host-side `initialize` span completed in 860.726 ms.
- Its `serve_inner` span remained alive for about 30 minutes.

This session was healthy and appears to be the diagnostic/reporting session, not the failed Workbench startup.

### Missing evidence

The actual reported 60-second Workbench failure has no correlated failed `thread/start` trace, explicit timeout event, cancellation owner, or failed Loci handshake span in the retained data. Existing metrics for the relevant window do not provide historical CPU, memory pressure, scheduler delay, file-descriptor pressure, or disk I/O.

Therefore the current evidence supports this boundary only:

> Loci starts and handshakes in under a second when Codex drives the connection. The reported failure is not attributable to Loci startup, but its exact Codex-side mechanism remains unobserved.

## Existing Loci changes

- `f69ea24`: removed the wrapper's ambient-Python dependency and set the configured startup timeout to 60 seconds. This is valid cleanup but unrelated to the reported 60-second failure.
- `eeab33f`: added bounded, opt-in startup tracing and deferred the Loci service import until the first tool call.
- Startup phases are `wrapper_exec`, `module_entered`, `tool_schemas_ready`, `store_bind_started`, `store_bound`, and `stdio_run_entered`.
- `stdio_run_entered` means only that the MCP SDK stdio loop was entered; it does not prove an initialize request arrived or a response was consumed.
- Focused Loci tests passed after these changes.

Keep this instrumentation. Additional production changes in Loci require new evidence that places the fault there.

## Recommended next diagnostic loop

1. Launch one full Workbench Codex app-server reproduction with a unique wall-clock marker and capture its process UUID, thread ID, request ID, Codex version, and effective MCP configuration.
2. Put a diagnostic stdio boundary around `loci-mcp` for the reproduction. Record timestamps only for child exec, initialize request received, initialize response emitted, EOF, exit status, and signal. Keep protocol bodies and environment values out of the log.
3. On failure, immediately correlate that marker with:
   - `/Users/brummerv/.codex/logs_2.sqlite`
   - raw OTLP rows in `/Users/brummerv/Library/Application Support/codex-telemetry/telemetry.sqlite3`
   - the diagnostic stdio boundary log
   - `/Users/brummerv/.codex/loci-index/mcp-startup.jsonl`
4. Identify the first missing transition:
   - no initialize request: Codex did not drive the child;
   - request arrived, no response: server/SDK boundary;
   - response emitted, host remained pending: Codex response consumption/state transition;
   - all transitions completed, then cancellation: host lifecycle/deadline ownership.
5. Fix the layer shown by that transition and rerun the same reproduction as the acceptance check.

## Useful safe queries

Raw signal counts for a chosen nanosecond window:

```sql
SELECT signal,
       count(*) AS requests,
       sum(body_size) AS body_bytes,
       min(received_at_unix_nano) AS first_ns,
       max(received_at_unix_nano) AS last_ns,
       sum(validation_status='valid') AS valid
FROM ingest_requests
WHERE received_at_unix_nano >= :start_ns
  AND received_at_unix_nano <  :end_ns
GROUP BY signal
ORDER BY signal;
```

Host lifecycle rows for a chosen second window:

```sql
SELECT id,
       datetime(ts,'unixepoch','localtime') || printf('.%09d',ts_nanos) AS local_time,
       level,
       target,
       thread_id,
       process_uuid,
       length(feedback_log_body) AS body_chars
FROM logs
WHERE ts >= :start_s AND ts < :end_s
ORDER BY ts,ts_nanos,id;
```

## Guardrails

- Preserve the distinction between the captured 09:39 cancellation and the user's unobserved 60-second Workbench failure.
- Treat raw telemetry bodies as sensitive.
- Use the exact Workbench host path; direct `loci-mcp` tests do not reproduce the failing layer.
- Require correlated evidence before changing timeout values or Loci startup code.
