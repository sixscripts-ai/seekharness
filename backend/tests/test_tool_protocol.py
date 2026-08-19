"""Slice C tests: JSON-first tool protocol, parse-failure events, exec identity."""

from __future__ import annotations

import json

from agent_arena.sandbox.executors.advanced_executor import parse_tool_calls
from tests.test_advanced_executor import _PASSING_TOOLS, _RACE_FORMAT, _run_fake_race


def test_json_shell_valid():
    calls = parse_tool_calls('{"tool": "shell", "arguments": {"cmd": "pytest -q"}}')
    assert calls == [{"tool": "shell", "cmd": "pytest -q", "content": ""}]


def test_json_write_and_test_valid():
    text = '{"tool": "write", "arguments": {"path": "solution.py", "content": "x = 1"}}'
    calls = parse_tool_calls(text)
    assert calls[0]["tool"] == "write"
    assert calls[0]["path"] == "solution.py"
    assert calls[0]["content"] == "x = 1"
    assert parse_tool_calls('{"tool": "test"}') == [{"tool": "test"}]


def test_json_fenced_array_with_prose():
    payload = json.dumps([{"tool": "read", "arguments": {"path": "TARGET.md"}}, {"tool": "test"}])
    text = "Let me inspect and fix.\n```json\n" + payload + "\n```\n"
    calls = parse_tool_calls(text)
    assert [c["tool"] for c in calls] == ["read", "test"]
    assert calls[0]["path"] == "TARGET.md"


def test_json_run_maps_args():
    calls = parse_tool_calls(
        '{"tool": "run", "arguments": {"path": "tests/test_target.py"}}'
    )
    assert calls[0]["tool"] == "run"
    assert calls[0]["path"] == "tests/test_target.py"


def test_invalid_json_falls_back_to_legacy():
    assert parse_tool_calls("{tool: shell}") == []
    legacy = parse_tool_calls("TOOL ls\nDONE")
    assert [c["tool"] for c in legacy] == ["ls", "done"]


def test_unknown_json_tool_yields_no_valid_calls():
    calls = parse_tool_calls('{"tool": "rmdir", "arguments": {}}')
    assert calls == []  # falls back to legacy -> empty -> parse-failure event


def test_wrong_argument_shape_invalid():
    calls = parse_tool_calls('{"tool": "shell", "arguments": "pytest"}')
    assert calls == []


def test_mixed_valid_and_invalid_json():
    text = '[{"tool": "ls"}, {"tool": "wat", "arguments": {}}]'
    calls = parse_tool_calls(text)
    assert calls[0]["tool"] == "ls"
    assert calls[1].get("error"), "invalid entry must carry an error marker"


def test_action_log_carries_execution_identity(monkeypatch):
    import os

    scores, transport = _run_fake_race(monkeypatch, _PASSING_TOOLS)
    assert scores
    identity = None
    for r in transport.rounds:
        if r.get("event_type") == "action_log":
            identity = json.loads(r["artifact"])
            break
    assert identity, "expected an action_log event"
    for key in ("battle_id", "fighter_id", "phase_id", "turn_id", "step_id", "exec_id"):
        assert key in identity, key
    # Backward-compatible payload shape for existing consumers.
    for key in ("action", "target", "state", "duration_ms", "result"):
        assert key in identity, key
    assert identity["battle_id"] == "race-1"
    assert identity["fighter_id"] in ("a", "b")
    assert identity["exec_id"].startswith("exec_")
    os.environ.pop("ARENA_IN_SANDBOX", None)


def test_parse_failure_emits_event(monkeypatch):
    import os

    from agent_arena.sandbox.client import FakeTransport, InternalClient
    from agent_arena.sandbox.executors.advanced_executor import AdvancedExecutor

    monkeypatch.setenv("ARENA_IN_SANDBOX", "1")
    monkeypatch.setenv("ARENA_PREVIEW", "0")
    transport = FakeTransport()
    transport.model_replies = {"a": "I have no tools to call today.", "b": _PASSING_TOOLS}
    transport.judge_result = {
        "scores": {"a": 1.0, "b": 9.0},
        "justifications": {},
        "judge_model": "mock",
    }
    AdvancedExecutor().run_battle(
        battle_id="pf-1",
        format_config={**_RACE_FORMAT, "max_tool_turns": 1, "max_tool_steps": 20},
        model_ids=["a", "b"],
        round_visibility="isolated",
        timeout_seconds=60,
        role_to_model={"player_a": "a", "player_b": "b"},
        client=InternalClient(transport),
    )
    failures = [
        json.loads(r["artifact"])
        for r in transport.rounds
        if r.get("event_type") == "action_log"
        and "tool_parse_failed" in (r.get("artifact") or "")
    ]
    assert failures, "malformed model output must emit tool_parse_failed"
    assert failures[0]["reason"]
    assert failures[0]["response_hash"]
    assert failures[0]["turn_id"] == 1
    os.environ.pop("ARENA_IN_SANDBOX", None)
