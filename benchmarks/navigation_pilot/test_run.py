"""Focused checks for pilot isolation and native-event accounting."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from benchmarks.navigation_pilot.run import arm_overrides, canary, run_turn, summarize_wire, target_guard


class PilotRunTests(unittest.TestCase):
    def test_turn_waits_for_requested_completion_and_rejects_delegation(self) -> None:
        class Client:
            def __init__(self, events):
                self.events = iter(events)

            def call(self, method, params, *, timeout):
                return {"turn": {"id": "root-turn"}}

            def next_event(self, timeout):
                return next(self.events)

        completed = {"method": "turn/completed", "params": {
            "threadId": "root", "turn": {"id": "root-turn", "status": "completed"}}}
        foreign = {"method": "turn/completed", "params": {
            "threadId": "child", "turn": {"id": "child-turn", "status": "completed"}}}
        other_turn = {"method": "turn/completed", "params": {
            "threadId": "root", "turn": {"id": "other-turn", "status": "completed"}}}
        row = run_turn(Client([foreign, other_turn, completed]), {
            "time_cap_seconds": 300, "prompt": "question", "model": "model",
            "reasoning_effort": "high"}, Path.cwd(), "root")
        self.assertEqual(row["status"], "completed")
        activity = {"method": "item/started", "params": {
            "threadId": "root", "turnId": "root-turn", "item": {
                "type": "subAgentActivity", "kind": "started", "id": "spawn"}}}
        row = run_turn(Client([activity, completed]), {
            "time_cap_seconds": 300, "prompt": "question", "model": "model",
            "reasoning_effort": "high"}, Path.cwd(), "root")
        self.assertTrue(row["isolation_failure"])
        self.assertEqual(row["status"], "runtime_failed")

    def test_canary_uses_native_shell_and_rejects_unrestricted_access(self) -> None:
        class LocalClient:
            def call(self, method, params, *, timeout):
                self.command = params["command"]
                completed = subprocess.run(
                    self.command, cwd=params["cwd"], capture_output=True,
                    text=True, timeout=timeout,
                )
                return {"exitCode": completed.returncode, "stdout": completed.stdout,
                        "stderr": completed.stderr}

        base = Path.home() / "phluxxed/tmp"
        base.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=base) as directory:
            root = Path(directory)
            workspace = root / "workspace with 'quotes'"
            (workspace / ".episode-tmp").mkdir(parents=True)
            client = LocalClient()
            result = canary(client, workspace, root / "outside")
            self.assertEqual(client.command[:2], ["/bin/sh", "-c"])
            self.assertEqual(result["command_result"]["exitCode"], 0)
            self.assertEqual(result["observed"], {
                "visible": "visible", "hidden": "allowed", "source_write": "allowed",
            })
            self.assertEqual(result["status"], "failed")
            self.assertFalse((workspace / ".pilot-write-canary").exists())

    def test_wire_deduplicates_and_preserves_completion_order(self) -> None:
        def event(ordinal: int, method: str, params: dict) -> str:
            return json.dumps({"ordinal": ordinal, "monotonic": float(ordinal),
                               "utc": f"2026-09-30T00:00:{ordinal:02d}+00:00",
                               "direction": "received", "message": {"method": method, "params": {
                                   "threadId": "thread", "turnId": "turn", **params}}})

        usage = {"inputTokens": 10, "cachedInputTokens": 2, "outputTokens": 3,
                 "reasoningOutputTokens": 1, "totalTokens": 13}
        more_usage = {"inputTokens": 15, "cachedInputTokens": 4, "outputTokens": 5,
                      "reasoningOutputTokens": 2, "totalTokens": 20}
        mcp = {"id": "m1", "type": "mcpToolCall", "server": "loci", "tool": "loci_read",
               "arguments": {"repo": "/target", "source_ref": "ref"}, "status": "completed",
               "result": {"structuredContent": {"source": {"content": "x"}}}}
        shell = {"id": "s1", "type": "commandExecution", "command": "rg foo",
                 "status": "completed", "exitCode": 0, "aggregatedOutput": "one\ntwo"}
        rows = [
            event(1, "thread/tokenUsage/updated", {"tokenUsage": {"total": usage}}),
            event(2, "thread/tokenUsage/updated", {"tokenUsage": {"total": usage}}),
            event(3, "item/completed", {"item": shell}),
            event(4, "item/completed", {"item": mcp}),
            event(5, "item/completed", {"item": shell}),
            event(6, "thread/tokenUsage/updated", {"tokenUsage": {"total": more_usage}}),
            event(7, "item/completed", {"item": {"id": "a1", "type": "agentMessage",
                                                "phase": "commentary", "text": "thinking"}}),
            event(8, "item/completed", {"item": {"id": "a2", "type": "agentMessage",
                                                "phase": "final_answer", "text": "answer"}}),
            event(9, "rawResponse/completed", {"responseId": "r1"}),
            event(10, "rawResponse/completed", {"responseId": "r1"}),
            event(11, "item/completed", {"item": {**shell, "aggregatedOutput": "conflict"}}),
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "wire.jsonl"
            path.write_text("\n".join(rows) + "\n")
            report = summarize_wire(path, "thread", "turn")
            interrupted = summarize_wire(path, "thread", "turn", completed=False)
        self.assertEqual([x["id"] for x in report["navigation_trace"]], ["s1", "m1", "a1", "a2"])
        self.assertEqual(report["mcp_calls"], 1)
        self.assertEqual(report["shell_calls"], 1)
        self.assertEqual(report["captured_tool_output_bytes"]["shell_aggregated"], 7)
        self.assertEqual(report["usage_updates"], 2)
        self.assertEqual(report["usage"]["uncachedInputTokens"], 11)
        self.assertIsNone(report["usage"]["cacheWriteInputTokens"])
        self.assertEqual(report["completed_response_count_lower_bound"], 1)
        self.assertEqual(report["capture_errors"], ["conflicting completed item s1"])
        self.assertEqual(report["final_answer"], "answer")
        self.assertEqual(interrupted["usage_status"], "unknown")
        self.assertIsNone(interrupted["usage"])
        self.assertEqual(interrupted["observed_usage_lower_bound"]["inputTokens"], 15)

    def test_vanilla_removes_loci_and_disables_ambient_mcp(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = root / "workspace"
            workspace.mkdir()
            config = root / "config.toml"
            config.write_text('[mcp_servers.loci]\nenabled = true\n'
                              '[mcp_servers.other]\nenabled = true\n')
            vanilla = arm_overrides(workspace, "vanilla", None, "test", user_config=config)
            loci = arm_overrides(workspace, "production", root / "serving", "test", user_config=config)
        self.assertNotIn("mcp_servers.loci", vanilla)
        self.assertFalse(vanilla["mcp_servers.loci.enabled"])
        self.assertFalse(vanilla["mcp_servers.other.enabled"])
        self.assertFalse(vanilla["agents.enabled"])
        self.assertFalse(vanilla["features.multi_agent_v2"])
        self.assertFalse(loci["agents.enabled"])
        self.assertEqual(vanilla["project_doc_max_bytes"], 0)
        self.assertTrue(loci["mcp_servers.loci"]["enabled"])
        self.assertEqual(loci["mcp_servers.loci"]["env"]["LOCI_STORE_NAMESPACE"], "test")
        self.assertEqual(Path(loci["mcp_servers.loci"]["env"]["LOCI_BASE_DIR"]), root / "loci-store")
        self.assertNotIn("LOCI_BASE_DIR", vanilla["shell_environment_policy.set"])
        self.assertNotIn(".episode-store", vanilla["permissions.loci_episode_read"]["filesystem"][":workspace_roots"])

    def test_guard_rejects_other_repo_before_dispatch_and_keeps_same_target(self) -> None:
        class Denied(Exception):
            pass

        calls = []

        async def delegate(name: str, arguments: dict, context=None) -> str:
            calls.append((name, arguments))
            return "unchanged"

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "target"
            target.mkdir()
            other = root / "other"
            other.mkdir()
            guarded = target_guard(delegate, target, Denied)
            with self.assertRaises(Denied):
                asyncio.run(guarded("loci_read", {"repo": str(other), "source_ref": "r"}))
            with self.assertRaises(Denied):
                asyncio.run(guarded("loci_graph_health", {"repo": str(target)}))
            self.assertEqual(calls, [])
            self.assertEqual(asyncio.run(guarded("loci_read", {
                "repo": str(target), "source_ref": "r"})), "unchanged")
            self.assertEqual(len(calls), 1)

            # Exercise the actual normal MCP server dispatch entrypoint too.
            from loci.mcp_server import create_server
            from mcp.server.mcpserver.exceptions import ToolError

            server = create_server("normal")
            server.call_tool = target_guard(server.call_tool, target, ToolError)
            with self.assertRaises(ToolError):
                asyncio.run(server.call_tool("loci_read", {"repo": str(other), "source_ref": "r"}))


if __name__ == "__main__":
    unittest.main()
