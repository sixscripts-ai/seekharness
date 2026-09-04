import time
from datetime import datetime, timedelta, timezone
import pytest
from fastapi import HTTPException

from agent_arena.internal_router import _rate_limit, _rate_counts, _rate_lock, _RATE_LIMIT
from agent_arena.persistence import service, repositories
from agent_arena.persistence.models import BattleEvent


def setup_function():
    with _rate_lock:
        _rate_counts.clear()


def test_local_fast_path_rate_limiting():
    battle_id = "test-battle-local-fast-path"

    # Up to _RATE_LIMIT calls should succeed
    for _ in range(_RATE_LIMIT):
        _rate_limit(battle_id)

    # 121st call should raise 429
    with pytest.raises(HTTPException) as exc_info:
        _rate_limit(battle_id)
    assert exc_info.value.status_code == 429
    assert "internal rate limit exceeded" in exc_info.value.detail


def test_durable_postgres_cross_replica_rate_limiting(monkeypatch):
    battle_id = "test-battle-postgres-cross-replica"

    # Clear local in-memory counts
    with _rate_lock:
        _rate_counts[battle_id] = []

    # Mock service.using_postgres to True
    monkeypatch.setattr(service, "using_postgres", lambda: True)

    # Simulate Postgres having recorded 120 calls from another replica
    monkeypatch.setattr(
        service,
        "event_count",
        lambda bid, event_type=None, since_seconds=None: 120,
    )

    # Call on this replica must raise 429 because cross-replica count >= 120
    with pytest.raises(HTTPException) as exc_info:
        _rate_limit(battle_id)
    assert exc_info.value.status_code == 429
    assert "internal rate limit exceeded" in exc_info.value.detail


def test_durable_postgres_sliding_window_allows_expired(monkeypatch):
    battle_id = "test-battle-sliding-window"

    with _rate_lock:
        _rate_counts[battle_id] = []

    monkeypatch.setattr(service, "using_postgres", lambda: True)

    # If events are older than 60s, event_count within last 60s returns 0
    monkeypatch.setattr(
        service,
        "event_count",
        lambda bid, event_type=None, since_seconds=None: 0,
    )

    appended_events = []
    monkeypatch.setattr(
        service,
        "events_append",
        lambda bid, etype, payload, event_id=None: appended_events.append((bid, etype, payload, event_id)),
    )

    # Call should succeed
    _rate_limit(battle_id)

    # An internal_call event should have been recorded
    assert len(appended_events) == 1
    assert appended_events[0][0] == battle_id
    assert appended_events[0][1] == "internal_call"
    assert "ts" in appended_events[0][2]
    assert appended_events[0][3].startswith("rate_")


def test_datastore_failure_falls_back_to_local_window(monkeypatch):
    battle_id = "test-battle-fallback-on-error"

    with _rate_lock:
        _rate_counts[battle_id] = []

    monkeypatch.setattr(service, "using_postgres", lambda: True)

    # Simulate database connection crash
    def crashing_event_count(*args, **kwargs):
        raise RuntimeError("database connection lost")

    monkeypatch.setattr(service, "event_count", crashing_event_count)

    # Should not raise 500/RuntimeError, falls back to local in-memory window
    _rate_limit(battle_id)

    with _rate_lock:
        assert len(_rate_counts[battle_id]) == 1


class MockSession:
    def __init__(self, count_value: int):
        self.count_value = count_value
        self.executed_stmt = None

    def scalar(self, stmt):
        self.executed_stmt = stmt
        return self.count_value


def test_repo_event_count():
    session = MockSession(count_value=42)
    count = repositories.events.event_count(
        session,
        "b-1",
        event_type="internal_call",
        since_created_at=100.0,
    )
    assert count == 42
    assert session.executed_stmt is not None
