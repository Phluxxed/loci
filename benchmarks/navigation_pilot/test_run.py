"""Focused checks for pilot isolation and native-event accounting."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

from benchmarks.navigation_pilot import run
from benchmarks.navigation_pilot.run import arm_overrides, canary, run_turn, summarize_wire, target_guard


class PilotRunTests(unittest.TestCase):
    def test_graph_pair_freezes_production_and_preserves_default_run(self) -> None:
        case, digest = run.load_case()

        def archived(repo, commit, destination):
            destination.mkdir(parents=True)
            if destination.parent.name == "serving":
                (destination / "skills/loci").mkdir(parents=True)
                (destination / "skills/loci/SKILL.md").write_text("same pinned skill")
            return {"commit": commit, "path": str(destination)}

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / "config.toml"
            config.write_text("")
            for paired in (False, True):
                with self.subTest(paired=paired), patch.object(run, "archive", side_effect=archived) as archive, \
                        patch.object(run, "AppServer") as server, \
                        patch.object(run, "preflight", return_value={"status": "passed", "thread_id": "t"}), \
                        patch.object(run, "run_turn") as turn:
                    server.return_value.cleanup_errors = []
                    receipt = run.execute(root / str(paired), preflight_only=True, graph_toggle=paired)
                self.assertEqual(receipt["status"], "preflight_passed_no_generation")
                self.assertEqual(receipt["case_sha256"], digest)
                turn.assert_not_called()
                expected = ("graph_on", "graph_off") if paired else run.ARMS
                self.assertEqual(tuple(receipt["arms"]), expected)
                if paired:
                    experiment = receipt["experiment"]
                    self.assertEqual(experiment["order"], list(expected))
                    self.assertEqual(experiment["conditions"], dict.fromkeys(expected, run.PRODUCTION_COMMIT))
                    self.assertEqual(experiment["case_sha256"], digest)
                    self.assertEqual(experiment["time_cap_seconds"], 300)
                    self.assertTrue(experiment["cold_stores"])
                    serving_calls = [call for call in archive.call_args_list
                                     if call.args[2].parent.name == "serving"]
                    self.assertEqual(len(serving_calls), 2)
                    self.assertTrue(all(call.args[:2] == (run.ORIGINAL, case["conditions"]["production"])
                                        for call in serving_calls))
                    configs = [receipt["arms"][arm]["configuration"] for arm in expected]
                    self.assertEqual(configs[0]["instructions"]["sha256"], configs[1]["instructions"]["sha256"])
                else:
                    self.assertNotIn("experiment", receipt)
                for arm in expected:
                    workspace = root / str(paired) / "arms" / arm / "workspace"
                    serving = None if arm == "vanilla" else root / str(paired) / "serving" / arm
                    overrides = arm_overrides(workspace, arm, serving, "test", user_config=config)
                    if arm == "vanilla":
                        continue
                    args = overrides["mcp_servers.loci"]["args"]
                    self.assertEqual("--graph-enrichment" in args, paired)
                    if paired:
                        self.assertEqual(args[-2:], ["--graph-enrichment", "on" if arm == "graph_on" else "off"])
                        self.assertEqual(receipt["arms"][arm]["configuration"]["graph_enrichment"], arm == "graph_on")

        with patch.object(run, "load_case", return_value=(
                {**case, "conditions": {**case["conditions"], "production": "other"}}, digest)):
            with self.assertRaisesRegex(ValueError, "frozen production commit"):
                run.execute(Path("unused"), graph_toggle=True)

    def test_server_binds_only_trusted_runtime_and_keeps_normal_descriptors(self) -> None:
        from loci import mcp_server, service
        from mcp.server.mcpserver.exceptions import ToolError

        normal = mcp_server.create_server("normal")
        descriptors = [tool.model_dump() for tool in asyncio.run(normal.list_tools())]
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            for enabled in (None, True, False):
                with self.subTest(enabled=enabled), \
                        patch.dict("os.environ", {"LOCI_MCP_SURFACE": "normal"}), \
                        patch.object(mcp_server, "mcp", mcp_server.create_server("normal")), \
                        patch.object(mcp_server, "_service_module", service), \
                        patch.object(mcp_server, "main"), \
                        patch.object(service, "RetrievalRuntime", create=True) as factory:
                    # The branch under test differs from the production archive;
                    # exercise the binding seam without replacing service.retrieve.
                    runtime = Mock()
                    factory.return_value = runtime
                    run.serve_target(target, graph_enrichment=enabled)
                    self.assertEqual([tool.model_dump() for tool in asyncio.run(mcp_server.mcp.list_tools())], descriptors)
                    bound = mcp_server._service()
                    if enabled is None:
                        factory.assert_not_called()
                        self.assertIs(bound, service)
                    else:
                        factory.assert_called_once_with(graph_enrichment=enabled)
                        self.assertIs(bound.retrieve, runtime.retrieve)
                        self.assertIs(bound.read, service.read)
                        self.assertIs(bound.LociError, service.LociError)
                    with self.assertRaises(ToolError):
                        asyncio.run(mcp_server.mcp.call_tool("loci_retrieve", {
                            "repo": str(target / "outside"), "query": "root"}))

    def test_graph_setting_is_server_only_and_cli_selects_pair(self) -> None:
        with patch.object(run.sys, "argv", ["run", "--graph-enrichment", "off"]):
            with self.assertRaises(SystemExit) as failure:
                run.main()
            self.assertEqual(failure.exception.code, 2)
        with patch.object(run.sys, "argv", ["run", "--graph-toggle"]), \
                patch.object(run, "execute", return_value={"status": "completed"}) as execute, \
                patch.object(run.os, "umask"), patch("builtins.print"):
            run.main()
        args, kwargs = execute.call_args
        self.assertTrue(args[0].name.startswith("loci-graph-toggle-"))
        self.assertEqual(args[0].parent, Path.home() / "phluxxed/tmp")
        self.assertEqual(kwargs, {"preflight_only": False, "graph_toggle": True})

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
