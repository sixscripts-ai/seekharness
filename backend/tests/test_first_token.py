"""First-token classification: preview/phase_start are not tokens; parse/result are."""

from __future__ import annotations

import json

import httpx

from agent_arena.first_token import (
    FAILURE_REASON,
    emit_status,
    first_token_budget_seconds,
    first_token_expired,
    has_first_token,
    is_first_token_event,
    is_transport_timeout,
    silence_reason,
)


def _action_log(action: str, **extra) -> dict:
    payload = {"action": action, **extra}
    return {"phase": "build", "model_id": "host:modal-kimi", "artifact": json.dumps(payload)}


def test_preview_and_phase_start_are_not_first_token():
    events = [
        ("preview", {"artifact": "work listing"}),
        ("phase_start", {"artifact": json.dumps({"role": "builder"})}),
        ("action_log", _action_log("preview", state="starting")),
        ("battle_status", {"status": "running"}),
        ("skill_search", {"query": "auth"}),
    ]
    assert has_first_token(events) is False
    assert is_first_token_event("phase_start", events[1][1]) is False


def test_tool_parse_success_is_first_token():
    payload = _action_log("tool_parse_success", state="done")
    assert is_first_token_event("action_log", payload) is True
    assert has_first_token([("action_log", payload)]) is True


def test_tool_parse_failed_is_first_token_model_returned():
    payload = _action_log("tool_parse_failed", state="failed")
    assert is_first_token_event("action_log", payload) is True


def test_executor_result_event_is_first_token():
    assert is_first_token_event("result", {"artifact": "EXECUTOR_RESULT: {}"}) is True
    assert is_first_token_event(
        "action_log",
        {"artifact": "EXECUTOR_RESULT: {\"passed\": true}"},
    ) is True


def test_specimen_3d50_would_not_trip_watchdog():
    """Battle 3d50f4d83a6d4d808ba81d1b4b40137d produced a parsed tool call."""
    events = [
        ("phase_start", {"artifact": "{}"}),
        ("action_log", _action_log("preview", state="starting")),
        (
            "action_log",
            _action_log(
                "tool_parse_success",
                state="done",
                result="parsed 1 calls (dialect: native, status: ok)",
            ),
        ),
        ("result", {"artifact": "EXECUTOR_RESULT: {}"}),
        ("judge", {"scores": {"host:modal-kimi": 88}}),
    ]
    assert has_first_token(events) is True
    reason = first_token_expired(
        started_at=1_800_000_000.0 - 914,
        now=1_800_000_000.0,
        timeout_seconds=600,
        has_first_token=True,
    )
    assert reason == ""


def test_preview_only_silence_expires_after_budget():
    reason = first_token_expired(
        started_at=1_800_000_000.0 - 200,
        now=1_800_000_000.0,
        timeout_seconds=600,
        has_first_token=False,
    )
    assert FAILURE_REASON in reason
    assert "200" in reason
    assert first_token_expired(
        started_at=1_800_000_000.0 - 30,
        now=1_800_000_000.0,
        timeout_seconds=600,
        has_first_token=False,
    ) == ""


def test_queued_without_started_at_is_not_first_token_expired():
    assert (
        first_token_expired(
            started_at=None,
            now=1_800_000_000.0,
            timeout_seconds=600,
            has_first_token=False,
        )
        == ""
    )


def test_budget_is_capped_by_battle_timeout(monkeypatch):
    monkeypatch.delenv("ARENA_FIRST_TOKEN_SECONDS", raising=False)
    assert first_token_budget_seconds(30) == 30
    monkeypatch.setenv("ARENA_FIRST_TOKEN_SECONDS", "15")
    assert first_token_budget_seconds(600) == 15


def test_transport_timeout_classification():
    assert is_transport_timeout(TimeoutError("hung")) is True
    assert is_transport_timeout(httpx.ReadTimeout("timed out")) is True
    assert is_transport_timeout(RuntimeError("server 502")) is False
    assert (
        is_transport_timeout(
            RuntimeError("internal /internal/model exhausted retries: server 502")
        )
        is False
    )


def test_emit_status_passes_reason_when_supported():
    seen: list[tuple] = []

    def on_status(status, reason=None):
        seen.append((status, reason))

    emit_status(on_status, "failed", FAILURE_REASON)
    assert seen == [("failed", FAILURE_REASON)]


def test_emit_status_falls_back_for_single_arg_callbacks():
    seen: list[str] = []
    emit_status(seen.append, "failed", FAILURE_REASON)
    assert seen == ["failed"]


def test_silence_reason_stable_token():
    assert silence_reason(200, 120).startswith(FAILURE_REASON)
