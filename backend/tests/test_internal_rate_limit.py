import pytest
from fastapi import HTTPException

from agent_arena.internal_router import _RATE_LIMIT, _rate_counts, _rate_limit, _rate_lock
from agent_arena.persistence import repositories, service
from agent_arena.persistence.repositories.rate_limits import decide_admission


def setup_function():
    with _rate_lock:
        _rate_counts.clear()


def test_decide_admission_first_call():
    admitted, window = decide_admission([], 1000.0, limit=3, window_seconds=60.0)
    assert admitted is True
    assert window == [1000.0]


def test_decide_admission_rejects_at_limit_without_recording():
    existing = [941.0, 950.0, 990.0]
    admitted, window = decide_admission(existing, 1000.0, limit=3, window_seconds=60.0)
    assert admitted is False
    assert window == existing


def test_decide_admission_prunes_expired_then_admits():
    existing = [930.0, 941.0, 990.0]
    admitted, window = decide_admission(existing, 1000.0, limit=3, window_seconds=60.0)
    assert admitted is True
    assert window == [941.0, 990.0, 1000.0]


def test_decide_admission_prunes_expired_on_reject_without_append():
    existing = [900.0, 950.0, 960.0, 970.0]
    admitted, window = decide_admission(existing, 1000.0, limit=3, window_seconds=60.0)
    assert admitted is False
    assert window == [950.0, 960.0, 970.0]


def test_local_fast_path_rate_limiting():
    battle_id = "test-battle-local-fast-path"

    for _ in range(_RATE_LIMIT):
        _rate_limit(battle_id)

    with pytest.raises(HTTPException) as exc_info:
        _rate_limit(battle_id)
    assert exc_info.value.status_code == 429
    assert "internal rate limit exceeded" in exc_info.value.detail


def test_durable_postgres_cross_replica_rate_limiting(monkeypatch):
    battle_id = "test-battle-postgres-cross-replica"

    with _rate_lock:
        _rate_counts[battle_id] = []

    monkeypatch.setattr(service, "using_postgres", lambda: True)
    monkeypatch.setattr(service, "rate_limit_admit", lambda *a, **k: False)

    with pytest.raises(HTTPException) as exc_info:
        _rate_limit(battle_id)
    assert exc_info.value.status_code == 429
    assert "internal rate limit exceeded" in exc_info.value.detail


def test_durable_postgres_admission_does_not_append_events(monkeypatch):
    battle_id = "test-battle-sliding-window"

    with _rate_lock:
        _rate_counts[battle_id] = []

    monkeypatch.setattr(service, "using_postgres", lambda: True)
    monkeypatch.setattr(service, "rate_limit_admit", lambda *a, **k: True)
    appended_events = []
    monkeypatch.setattr(
        service,
        "events_append",
        lambda *a, **k: appended_events.append((a, k)),
    )

    _rate_limit(battle_id)

    assert appended_events == []
    with _rate_lock:
        assert len(_rate_counts[battle_id]) == 1


def test_rejected_admission_does_not_record_local_call(monkeypatch):
    battle_id = "test-battle-reject-no-local"

    with _rate_lock:
        _rate_counts[battle_id] = []

    monkeypatch.setattr(service, "using_postgres", lambda: True)
    monkeypatch.setattr(service, "rate_limit_admit", lambda *a, **k: False)

    with pytest.raises(HTTPException):
        _rate_limit(battle_id)

    with _rate_lock:
        assert _rate_counts[battle_id] == []


def test_datastore_failure_falls_back_to_local_window(monkeypatch):
    battle_id = "test-battle-fallback-on-error"

    with _rate_lock:
        _rate_counts[battle_id] = []

    monkeypatch.setattr(service, "using_postgres", lambda: True)

    def crashing_admit(*args, **kwargs):
        raise RuntimeError("database connection lost")

    monkeypatch.setattr(service, "rate_limit_admit", crashing_admit)
    logged: list[tuple[str, str]] = []
    monkeypatch.setattr(
        service,
        "_sanitized_log",
        lambda action, exc: logged.append((action, exc.__class__.__name__)),
    )

    _rate_limit(battle_id)

    with _rate_lock:
        assert len(_rate_counts[battle_id]) == 1
    assert logged == [("rate-limit datastore fallback", "RuntimeError")]


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
