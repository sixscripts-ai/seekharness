"""Hermetic reaper policy: expire stuck queued/running without touching terminals."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from types import SimpleNamespace

from agent_arena.persistence.repositories import battles as battle_repo
from agent_arena.reaper import _is_expired, _reap_pg


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

    def fail_if_active(_session, battle_id, *, reason, completed_at):
        failed.append(battle_id)
        return SimpleNamespace(id=battle_id, status="failed")

    monkeypatch.setattr(
        "agent_arena.persistence.repositories.battles.battle_fail_if_active",
        fail_if_active,
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
    assert published == ["stale-1"]
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
        "agent_arena.persistence.repositories.battles.battle_fail_if_active",
        lambda *_a, **_k: None,
    )
    monkeypatch.setattr("agent_arena.reaper._stop_sandbox", lambda _sid: None)
    monkeypatch.setattr("agent_arena.reaper._publish_failed", lambda *_a: None)

    assert _reap_pg(NOW, GRACE) == []
