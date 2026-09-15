from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from benchmarks.complete_work import controller
from benchmarks.complete_work.isolation import READ_PROFILE, WRITE_PROFILE
from benchmarks.complete_work.runtime import Journal, RuntimeFailure


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


class ScriptedClient:
    def __init__(self, events: list[dict], *, on_event=None) -> None:
        self.events = list(events)
        self.calls: list[tuple[str, dict, float]] = []
        self.closed = 0
        self.on_event = on_event

    def call(self, method: str, params: dict, *, timeout: float = 30) -> dict:
        self.calls.append((method, params, timeout))
        if method == "turn/start":
            return {"turn": {"id": f"turn-{sum(name == 'turn/start' for name, _, _ in self.calls)}"}}
        assert method == "turn/interrupt"
        return {"interrupted": True}

    def next_event(self, timeout: float) -> dict:
        if self.on_event is not None:
            self.on_event()
            self.on_event = None
        return self.events.pop(0)

    def close(self) -> None:
        self.closed += 1


def _stages() -> list[dict]:
    return [
        {"stage_id": "orient", "prompt": "first exact prompt", "cap_seconds": 120},
        {"stage_id": "implement", "prompt": "second exact prompt", "cap_seconds": 360},
        {"stage_id": "continue", "prompt": "third exact prompt", "cap_seconds": 240},
    ]


def _completed(turn_id: str) -> dict:
    return {"method": "turn/completed", "params": {
        "threadId": "thread-1", "turn": {"id": turn_id, "status": "completed", "error": None},
    }}


def _before(repo: Path, output: Path) -> None:
    output.mkdir()
    controller.write_json(output / "source-before.json", controller.source_snapshot(repo, output / "source-history"))


def _journal_messages(path: Path) -> list[dict]:
    return [json.loads(line)["message"] for line in path.read_text(encoding="utf-8").splitlines()]


def test_run_stages_reuses_one_thread_with_fixed_prompts_profiles_and_snapshots(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "source.py").write_text("value = 1\n", encoding="utf-8")
    output = tmp_path / "output"
    _before(repo, output)
    journal = Journal(output / "wire.jsonl")
    client = ScriptedClient([_completed("turn-1"), _completed("turn-2"), _completed("turn-3")])
    try:
        rows = controller.run_stages(client, journal, "thread-1", repo, _stages(), output, clock=Clock())
    finally:
        journal.close()

    starts = [params for method, params, _ in client.calls if method == "turn/start"]
    assert [item["threadId"] for item in starts] == ["thread-1", "thread-1", "thread-1"]
    assert [item["input"][0]["text"] for item in starts] == [stage["prompt"] for stage in _stages()]
    assert [item["permissions"] for item in starts] == [READ_PROFILE, WRITE_PROFILE, WRITE_PROFILE]
    assert [row["outcome"] for row in rows] == ["completed", "completed", "completed"]
    for stage in _stages():
        assert (output / f"source-after-{stage['stage_id']}.json").is_file()
    assert [message["event"] for message in _journal_messages(output / "wire.jsonl") if message.get("event")] == [
        "stage_submitted", "stage_turn_bound", "stage_finished",
        "stage_submitted", "stage_turn_bound", "stage_finished",
        "stage_submitted", "stage_turn_bound", "stage_finished",
    ]


def test_timeout_interrupts_once_then_retains_later_stages_as_not_reached(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "source.py").write_text("value = 1\n", encoding="utf-8")
    output = tmp_path / "output"
    _before(repo, output)
    clock = Clock()
    client = ScriptedClient([{"method": "thread/progress", "params": {}}], on_event=lambda: setattr(clock, "now", 121))
    journal = Journal(output / "wire.jsonl")
    try:
        rows = controller.run_stages(client, journal, "thread-1", repo, _stages(), output, clock=clock)
    finally:
        journal.close()

    assert [row["outcome"] for row in rows] == ["timed_out", "not_reached", "not_reached"]
    assert [name for name, _, _ in client.calls] == ["turn/start", "turn/interrupt"]
    assert client.closed == 1
    assert rows[0]["error"] == "stage deadline"
    assert rows[1]["turn_id"] is None and rows[1]["elapsed_ms"] is None


def test_runtime_error_and_orientation_edit_are_retained_as_terminal_failure(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    source = repo / "source.py"
    source.write_text("value = 1\n", encoding="utf-8")
    output = tmp_path / "output"
    _before(repo, output)
    journal = Journal(output / "wire.jsonl")
    client = ScriptedClient([{"method": "model/rerouted", "params": {}}])
    try:
        runtime_rows = controller.run_stages(client, journal, "thread-1", repo, _stages(), output, clock=Clock())
    finally:
        journal.close()
    assert [row["outcome"] for row in runtime_rows] == ["runtime_failed", "not_reached", "not_reached"]
    assert "model changed" in runtime_rows[0]["error"]

    edit_output = tmp_path / "edit-output"
    _before(repo, edit_output)
    edit_journal = Journal(edit_output / "wire.jsonl")
    editor = ScriptedClient([_completed("turn-1")], on_event=lambda: source.write_text("value = 2\n", encoding="utf-8"))
    try:
        edit_rows = controller.run_stages(editor, edit_journal, "thread-1", repo, _stages(), edit_output, clock=Clock())
    finally:
        edit_journal.close()
    assert [row["outcome"] for row in edit_rows] == ["protocol_violation", "not_reached", "not_reached"]
    assert edit_rows[0]["error"] == "source changed during read-only orientation"
    persisted = json.loads((edit_output / "stages.json").read_text(encoding="utf-8"))["stages"]
    assert persisted[0]["outcome"] == "protocol_violation"
    finished = [m for m in _journal_messages(edit_output / "wire.jsonl") if m.get("event") == "stage_finished"]
    assert finished[0]["outcome"] == "protocol_violation"
    assert finished[0]["error"] == "source changed during read-only orientation"


def test_execute_without_freeze_never_constructs_an_app_server(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    serving = tmp_path / "serving"
    serving.mkdir()
    output = tmp_path / "output"
    (repo / ".complete-work-isolation.json").write_text(json.dumps({"run_id": "run-1", "source_files": {}}), encoding="utf-8")
    prompts = ["one", "two", "three"]
    stages = [
        {"id": name, "prompt": prompt, "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(), "cap_seconds": cap}
        for name, prompt, cap in zip(("orient", "implement", "continue"), prompts, (120, 360, 240), strict=True)
    ]
    episodes = tmp_path / "episodes.json"
    episodes.write_text(json.dumps({"schema_version": 1, "common_initial_prompt_template": "", "episodes": [{"id": "case", "stages": stages}]}), encoding="utf-8")
    schedule = tmp_path / "schedule.json"
    schedule.write_text(json.dumps({"rows": [{"episode_run_id": "run-1", "episode_id": "case", "model": controller.MODEL,
                                                "effort": controller.EFFORT, "fork": "none", "graph_enrichment": "off"}]}), encoding="utf-8")
    config = tmp_path / "run.json"
    config.write_text(json.dumps({"schema_version": 1, "dependencies_status": "prepared", "preindex": {"status": "prepared"}, "run_id": "run-1", "repo": str(repo), "serving_root": str(serving),
                                  "output_dir": str(output), "episodes_path": str(episodes), "schedule_path": str(schedule),
                                  "arm": "off", "readonly_roots": [], "mcp_command": "unused", "mcp_args": [], "mcp_env": {},
                                  "user_config": str(tmp_path / "none.toml"), "mcp_config_path": str(tmp_path / "mcp.json"),
                                  "instruction_text_path": str(tmp_path / "instructions.md")}), encoding="utf-8")
    constructed = False

    def forbidden(*args, **kwargs):
        nonlocal constructed
        constructed = True
        raise AssertionError("AppServer must not be constructed before a freeze")

    monkeypatch.setattr(controller, "AppServer", forbidden)
    with pytest.raises(RuntimeFailure, match="published campaign freeze"):
        controller.execute(config)
    assert constructed is False
    assert not output.exists()


def test_late_completion_is_timed_out_instead_of_accepted(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "source.py").write_text("value = 1\n")
    output = tmp_path / "output"
    _before(repo, output)
    clock = Clock()
    client = ScriptedClient([_completed("turn-1")], on_event=lambda: setattr(clock, "now", 121))
    journal = Journal(output / "wire.jsonl")
    try:
        rows = controller.run_stages(client, journal, "thread-1", repo, _stages(), output, clock=clock)
    finally:
        journal.close()
    assert [x["outcome"] for x in rows] == ["timed_out", "not_reached", "not_reached"]
    assert rows[0]["deadline_overrun_ms"] == 1000
