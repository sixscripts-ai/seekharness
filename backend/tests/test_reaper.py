"""Hermetic reaper policy: expire stuck queued/running without touching terminals."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from types import SimpleNamespace

from agent_arena.persistence.repositories import battles as battle_repo
from agent_arena.reaper import _is_expired, _reap_pg, _reap_reason
from agent_arena.first_token import FAILURE_REASON


NOW = 1_800_000_000.0  # 2027-01-14ish; far after the Aug 2026 leftovers
GRACE = 300.0


def _dt(age_s: float) -> datetime:
    return datetime.fromtimestamp(NOW - age_s, tz=timezone.utc)


def test_queued_without_started_at_expires_from_created_at():
    expired, age, reason = _is_expired(
        {
            "status": "queued",
            "started_at": None,
            "created_at": _dt(10_000),
            "timeout_seconds": 600,
        },
        NOW,
        GRACE,
    )
    assert expired is True
    assert age >= 9000
    assert "queued" in reason


def test_fresh_running_is_not_expired():
    expired, _, _ = _is_expired(
        {
            "status": "running",
            "started_at": _dt(60),
            "created_at": _dt(90),
            "timeout_seconds": 600,
        },
        NOW,
        GRACE,
    )
    assert expired is False


def test_running_past_timeout_plus_grace_expires():
    expired, _, reason = _is_expired(
        {
            "status": "running",
            "started_at": _dt(901),
            "timeout_seconds": 600,
        },
        NOW,
        GRACE,
    )
    assert expired is True
    assert "running" in reason


def test_completed_is_not_expired():
    expired, _, _ = _is_expired(
        {
            "status": "completed",
            "started_at": _dt(10_000),
            "created_at": _dt(10_000),
            "timeout_seconds": 600,
        },
        NOW,
        GRACE,
    )
    assert expired is False


def test_fail_if_active_leaves_completed_alone():
    battle = SimpleNamespace(status="completed", failure_reason=None, completed_at=None)
    session = SimpleNamespace(scalar=lambda _stmt: battle, flush=lambda: None)
    out = battle_repo.battle_fail_if_active(
        session,
        "done-1",
        reason="should not apply",
        completed_at=_dt(0),
    )
    assert out is None
    assert battle.status == "completed"
    assert battle.failure_reason is None


def test_fail_if_active_fails_queued():
    battle = SimpleNamespace(status="queued", failure_reason=None, completed_at=None)
    session = SimpleNamespace(scalar=lambda _stmt: battle, flush=lambda: None)
    done = _dt(0)
    out = battle_repo.battle_fail_if_active(
        session, "q-1", reason="stuck", completed_at=done
    )
    assert out is battle
    assert battle.status == "failed"
    assert battle.failure_reason == "stuck"
    assert battle.completed_at == done


def test_reap_pg_fails_only_stale_active(monkeypatch):
    stale = SimpleNamespace(
        id="stale-1",
        status="queued",
        started_at=None,
        created_at=_dt(50_000),
        timeout_seconds=600,
        sandbox_id=None,
    )
    fresh = SimpleNamespace(
        id="fresh-1",
        status="running",
        started_at=_dt(30),
        created_at=_dt(40),
        timeout_seconds=600,
        sandbox_id="sbx-live",
    )
    failed: list[str] = []
    stopped: list[str] = []
    published: list[str] = []

    @contextmanager
    def fake_scope():
        yield SimpleNamespace()

    monkeypatch.setattr(
        "agent_arena.persistence.session.session_scope", fake_scope
    )
    monkeypatch.setattr(
        "agent_arena.persistence.repositories.battles.battle_list_active",
        lambda _session, **_k: [stale, fresh],
    )

    def fail_closed(battle_id, *, reason):
        failed.append(battle_id)
        return {"ok": True, "status": "failed", "already_finalized": False}

    monkeypatch.setattr(
        "agent_arena.finalization.fail_closed_incomplete", fail_closed
    )
    monkeypatch.setattr(
        "agent_arena.reaper._stop_sandbox", lambda sid: stopped.append(sid)
    )
    monkeypatch.setattr(
        "agent_arena.reaper._publish_failed",
        lambda bid, _reason: published.append(bid),
    )

    reaped = _reap_pg(NOW, GRACE)
    assert reaped == ["stale-1"]
    assert failed == ["stale-1"]
    assert published == []
    assert stopped == []


def test_reap_pg_skips_when_row_already_terminal(monkeypatch):
    stale = SimpleNamespace(
        id="race-1",
        status="running",
        started_at=_dt(50_000),
        created_at=_dt(50_000),
        timeout_seconds=600,
        sandbox_id="sbx-1",
    )

    @contextmanager
    def fake_scope():
        yield SimpleNamespace()

    monkeypatch.setattr(
        "agent_arena.persistence.session.session_scope", fake_scope
    )
    monkeypatch.setattr(
        "agent_arena.persistence.repositories.battles.battle_list_active",
        lambda _session, **_k: [stale],
    )
    monkeypatch.setattr(
        "agent_arena.finalization.fail_closed_incomplete",
        lambda *_a, **_k: {
            "ok": True,
            "status": "failed",
            "already_finalized": True,
        },
    )
    monkeypatch.setattr("agent_arena.reaper._stop_sandbox", lambda _sid: None)
    monkeypatch.setattr("agent_arena.reaper._publish_failed", lambda *_a: None)

    assert _reap_pg(NOW, GRACE) == []


def test_reap_reason_silence_after_budget(monkeypatch):
    monkeypatch.setattr(
        "agent_arena.reaper._battle_has_first_token", lambda _bid: False
    )
    reason = _reap_reason(
        {
            "id": "silent-1",
            "status": "running",
            "started_at": _dt(200),
            "timeout_seconds": 600,
        },
        NOW,
        GRACE,
    )
    assert FAILURE_REASON in reason
    assert "budget" in reason


def test_reap_reason_keeps_battle_with_first_token(monkeypatch):
    monkeypatch.setattr(
        "agent_arena.reaper._battle_has_first_token", lambda _bid: True
    )
    reason = _reap_reason(
        {
            "id": "3d50f4d83a6d4d808ba81d1b4b40137d",
            "status": "running",
            "started_at": _dt(200),
            "timeout_seconds": 600,
        },
        NOW,
        GRACE,
    )
    assert reason == ""


def test_reap_reason_queued_without_started_at_skips_first_token():
    reason = _reap_reason(
        {
            "id": "queued-1",
            "status": "queued",
            "started_at": None,
            "created_at": _dt(200),
            "timeout_seconds": 600,
        },
        NOW,
        GRACE,
    )
    assert reason == ""


def test_reap_pg_fails_silent_running(monkeypatch):
    silent = SimpleNamespace(
        id="silent-1",
        status="running",
        started_at=_dt(200),
        created_at=_dt(210),
        timeout_seconds=600,
        sandbox_id="sbx-silent",
    )
    failed: list[str] = []
    stopped: list[str] = []
    published: list[str] = []

    @contextmanager
    def fake_scope():
        yield SimpleNamespace()

    monkeypatch.setattr("agent_arena.persistence.session.session_scope", fake_scope)
    monkeypatch.setattr(
        "agent_arena.persistence.repositories.battles.battle_list_active",
        lambda _session, **_k: [silent],
    )
    monkeypatch.setattr(
        "agent_arena.reaper._battle_has_first_token", lambda _bid: False
    )

    def fail_closed(battle_id, *, reason):
        assert FAILURE_REASON in reason
        failed.append(battle_id)
        return {"ok": True, "status": "failed", "already_finalized": False}

    monkeypatch.setattr(
        "agent_arena.finalization.fail_closed_incomplete", fail_closed
    )
    monkeypatch.setattr(
        "agent_arena.reaper._stop_sandbox", lambda sid: stopped.append(sid)
    )
    monkeypatch.setattr(
        "agent_arena.reaper._publish_failed",
        lambda bid, _reason: published.append(bid),
    )

    reaped = _reap_pg(NOW, GRACE)
    assert reaped == ["silent-1"]
    assert failed == ["silent-1"]
    assert published == []
    assert stopped == ["sbx-silent"]
