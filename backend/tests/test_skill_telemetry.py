from __future__ import annotations

import json
from types import SimpleNamespace

from agent_arena.sandbox.client import FakeTransport, InternalClient
from agent_arena.sandbox.executors.advanced_executor import AdvancedExecutor
from agent_arena.sandbox.executors.skill_pool import load_skill_pool
from agent_arena.skill_telemetry import (
    SKILL_EVENT_TYPES,
    public_skill_file_read,
    public_skill_tool_output,
    safe_skill_query,
    skill_event_for_call,
)


class _Resolver:
    def resolve(self, reference: str):
        if reference in {"auth-flow-debugger", "Auth Flow Debugger"}:
            return SimpleNamespace(id="auth-flow-debugger")
        if reference == "python-kata-fixer":
            return SimpleNamespace(id="python-kata-fixer")
        return None


def _skill_rounds(transport: FakeTransport) -> list[dict]:
    return [
        round_payload
        for round_payload in transport.rounds
        if round_payload["event_type"] in SKILL_EVENT_TYPES
    ]


def _run_tool_sequence(monkeypatch, replies: dict[str, str], roles: list[str]):
    monkeypatch.setenv("ARENA_IN_SANDBOX", "1")
    transport = FakeTransport()
    transport.model_replies = replies
    transport.judge_result = {"scores": {}, "justifications": {}, "judge_model": "mock"}
    client = InternalClient(transport)
    participants = [{"name": "race", "participants": roles}]
    role_to_model = {role: model for role, model in zip(roles, replies)}
    AdvancedExecutor().run_battle(
        battle_id="telemetry-test",
        format_config={
            "name": "Telemetry test",
            "engine": "agent_tool_race",
            "roles": [*roles, "judge"],
            "phases": participants,
            "target_code": "target",
            "max_tool_turns": 2,
            "max_tool_steps": 12,
        },
        model_ids=list(replies),
        round_visibility="isolated",
        timeout_seconds=60,
        role_to_model=role_to_model,
        client=client,
    )
    return transport


def test_skills_emits_index_browse_activity(monkeypatch):
    transport = _run_tool_sequence(
        monkeypatch,
        {"model-a": "TOOL skills\nTOOL done"},
        ["player_a"],
    )
    event = next(
        json.loads(item["artifact"])
        for item in _skill_rounds(transport)
        if item["event_type"] == "skill_index_browse"
    )
    assert event["type"] == "skill_index_browse"
    assert event["fighter_id"] == "model-a"
    assert "index" not in event


def test_skills_index_emits_index_browse_with_index(monkeypatch):
    transport = _run_tool_sequence(
        monkeypatch,
        {"model-a": "TOOL skills index=security\nTOOL done"},
        ["player_a"],
    )
    payload = next(
        json.loads(item["artifact"])
        for item in _skill_rounds(transport)
        if item["event_type"] == "skill_index_browse"
    )
    assert payload["index"] == "security"


def test_skills_search_emits_query_without_results(monkeypatch):
    transport = _run_tool_sequence(
        monkeypatch,
        {"model-a": 'TOOL skills search="session replay"\nTOOL done'},
        ["player_a"],
    )
    payload = next(
        json.loads(item["artifact"])
        for item in _skill_rounds(transport)
        if item["event_type"] == "skill_search"
    )
    assert payload["query"] == "session replay"
    assert "results" not in payload


def test_skills_card_view_emits_skill_id_only(monkeypatch):
    transport = _run_tool_sequence(
        monkeypatch,
        {"model-a": "TOOL skills skill=auth-flow-debugger\nTOOL done"},
        ["player_a"],
    )
    payload = next(
        json.loads(item["artifact"])
        for item in _skill_rounds(transport)
        if item["event_type"] == "skill_card_view"
    )
    assert payload["skill_id"] == "auth-flow-debugger"
    assert "body" not in payload


def test_use_skill_emits_load_without_skill_body(monkeypatch):
    transport = _run_tool_sequence(
        monkeypatch,
        {"model-a": "TOOL use_skill name=python-kata-fixer\nTOOL done"},
        ["player_a"],
    )
    payload = next(
        json.loads(item["artifact"])
        for item in _skill_rounds(transport)
        if item["event_type"] == "skill_load"
    )
    assert payload["skill_id"] == "python-kata-fixer"
    assert payload["success"] is True
    public_rounds = "\n".join(item["artifact"] for item in transport.rounds)
    skill_body = next(
        skill["body"]
        for skill in load_skill_pool()
        if skill["name"] == "python-kata-fixer"
    )
    assert skill_body not in public_rounds


def test_browse_is_not_a_load_and_suggestions_are_not_loads():
    resolver = _Resolver()
    assert skill_event_for_call({"tool": "skills"}, resolver)[0] == "skill_index_browse"
    assert skill_event_for_call(
        {"tool": "skills", "index": "security"}, resolver
    )[0] == "skill_index_browse"
    assert skill_event_for_call(
        {"tool": "skills", "search": "session replay"}, resolver
    )[0] == "skill_search"
    assert skill_event_for_call(
        {"tool": "skills", "skill": "Auth Flow Debugger"}, resolver
    )[0] == "skill_card_view"
    assert skill_event_for_call(
        {"tool": "skills", "chosen": ["auth-flow-debugger"]}, resolver
    ) is None


def test_multiple_loads_are_observable_and_zero_skill_is_valid(monkeypatch):
    transport = _run_tool_sequence(
        monkeypatch,
        {
            "model-a": (
                "TOOL use_skill name=python-kata-fixer\n"
                "TOOL use_skill name=auth-flow-debugger\n"
                "TOOL done"
            )
        },
        ["player_a"],
    )
    loads = _skill_rounds(transport)
    assert [item["event_type"] for item in loads].count("skill_load") == 2
    assert skill_event_for_call({"tool": "done"}, _Resolver()) is None


def test_skill_events_are_attributed_to_the_correct_fighter(monkeypatch):
    transport = _run_tool_sequence(
        monkeypatch,
        {
            "model-a": "TOOL skills index=security\nTOOL done",
            "model-b": 'TOOL skills search="session replay"\nTOOL done',
        },
        ["player_a", "player_b"],
    )
    payloads = [
        json.loads(item["artifact"])
        for item in _skill_rounds(transport)
    ]
    by_fighter = {payload["fighter_id"]: payload for payload in payloads}
    assert by_fighter["model-a"]["fighter_slot"] == "player_a"
    assert by_fighter["model-a"]["index"] == "security"
    assert by_fighter["model-b"]["fighter_slot"] == "player_b"
    assert by_fighter["model-b"]["query"] == "session replay"


def test_public_skill_output_redacts_bodies_and_sensitive_queries():
    resolver = _Resolver()
    output = public_skill_tool_output(
        {"tool": "use_skill", "name": "auth-flow-debugger"},
        success=True,
        resolver=resolver,
    )
    assert output == "skill_load skill_id=auth-flow-debugger loaded=true"
    assert "Secure Code Execution" not in output
    assert safe_skill_query("reference_solution=/private/value") == "[redacted]"
    assert safe_skill_query("inspect hidden tests") == "[redacted]"
    assert safe_skill_query("find the flag") == "[redacted]"
    assert (
        public_skill_file_read(".agents/skills/auth-flow-debugger/SKILL.md")
        == "SKILL_FILE_READ auth-flow-debugger"
    )


def test_skill_activity_does_not_change_capabilities():
    resolver = _Resolver()
    activity = skill_event_for_call(
        {"tool": "use_skill", "name": "technical-web-researcher"},
        resolver,
    )
    assert activity == ("skill_load", {"skill_id": "technical-web-researcher"})
