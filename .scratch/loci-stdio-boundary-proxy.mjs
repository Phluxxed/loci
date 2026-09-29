#!/usr/bin/env node

import fs from "node:fs";
import { spawn } from "node:child_process";

const tracePath = "/Users/brummerv/loci/.scratch/loci-stdio-boundary.jsonl";
const marker = process.env.LOCI_DIAGNOSTIC_MARKER ?? "unmarked";
const started = process.hrtime.bigint();
const maxTraceBytes = 4 * 1024 * 1024;

function record(event, details = {}) {
  try {
    if (fs.statSync(tracePath).size >= maxTraceBytes) fs.truncateSync(tracePath, 0);
  } catch (error) {
    if (error.code !== "ENOENT") throw error;
  }
  const elapsedMs = Number(process.hrtime.bigint() - started) / 1e6;
  fs.appendFileSync(tracePath, `${JSON.stringify({
    timestamp: new Date().toISOString(),
    elapsed_ms: Math.round(elapsedMs * 1000) / 1000,
    marker,
    host_pid: process.ppid,
    proxy_pid: process.pid,
    event,
    ...details,
  })}\n`, { mode: 0o600 });
}

const child = spawn("/Users/brummerv/.local/bin/loci-mcp", [], {
  env: process.env,
  stdio: ["pipe", "pipe", "inherit"],
});
record("child_exec", { child_pid: child.pid });

let requestBuffer = "";
let responseBuffer = "";
const initializeIds = new Set();

function inspectLines(direction, chunk) {
  let buffer = direction === "request" ? requestBuffer : responseBuffer;
  buffer += chunk.toString("utf8");
  let newline;
  while ((newline = buffer.indexOf("\n")) >= 0) {
    const line = buffer.slice(0, newline);
    buffer = buffer.slice(newline + 1);
    try {
      const message = JSON.parse(line);
      if (direction === "request" && message.method === "initialize") {
        initializeIds.add(JSON.stringify(message.id));
        record("initialize_request_received", { request_id: message.id });
      } else if (
        direction === "response" &&
        Object.hasOwn(message, "id") &&
        initializeIds.has(JSON.stringify(message.id))
      ) {
        record("initialize_response_emitted", {
          request_id: message.id,
          outcome: Object.hasOwn(message, "result") ? "result" : "error",
        });
      }
    } catch {
      // Preserve protocol bytes unchanged; malformed lines are not logged.
    }
  }
  if (direction === "request") requestBuffer = buffer;
  else responseBuffer = buffer;
}

process.stdin.on("data", (chunk) => {
  inspectLines("request", chunk);
  if (!child.stdin.write(chunk)) process.stdin.pause();
});
child.stdin.on("drain", () => process.stdin.resume());
process.stdin.on("end", () => {
  record("host_stdin_eof");
  child.stdin.end();
});

child.stdout.on("data", (chunk) => {
  inspectLines("response", chunk);
  if (!process.stdout.write(chunk)) child.stdout.pause();
});
process.stdout.on("drain", () => child.stdout.resume());
child.stdout.on("end", () => record("child_stdout_eof"));

child.on("error", (error) => record("child_error", { code: error.code ?? "unknown" }));
child.on("exit", (code, signal) => {
  record("child_exit", { exit_status: code, signal });
  process.exitCode = code ?? (signal ? 1 : 0);
});

for (const signal of ["SIGINT", "SIGTERM", "SIGHUP"]) {
  process.on(signal, () => {
    record("proxy_signal", { signal });
    child.kill(signal);
  });
}
