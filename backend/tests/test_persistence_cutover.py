"""Hermetic tests: Appwrite stays identity-only; Neon is the battle store."""

from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from agent_arena.config import settings
from agent_arena.persistence import service


@pytest.fixture(autouse=True)
def _clear_settings():
    settings.cache_clear()
    yield
    settings.cache_clear()


def test_postgres_auth_only_does_not_require_database_credentials(monkeypatch):
    monkeypatch.setenv("PERSISTENCE_BACKEND", "postgres")
    monkeypatch.delenv("APPWRITE_DUAL_WRITE", raising=False)
    monkeypatch.delenv("APPWRITE_READ_FALLBACK", raising=False)
    monkeypatch.setenv("APPWRITE_ENDPOINT", "https://example.test/v1")
    monkeypatch.setenv("APPWRITE_PROJECT_ID", "proj")
    monkeypatch.delenv("APPWRITE_API_KEY", raising=False)
    monkeypatch.delenv("APPWRITE_DATABASE_ID", raising=False)
    settings.cache_clear()
    s = settings()
    assert s["PERSISTENCE_BACKEND"] == "postgres"
    assert s["APPWRITE_DUAL_WRITE"] == "false"
    assert s["APPWRITE_READ_FALLBACK"] == "false"


def test_empty_persistence_backend_defaults_to_postgres(monkeypatch):
    monkeypatch.setenv("PERSISTENCE_BACKEND", "")
    monkeypatch.setenv("APPWRITE_ENDPOINT", "https://example.test/v1")
    monkeypatch.setenv("APPWRITE_PROJECT_ID", "proj")
    monkeypatch.delenv("APPWRITE_API_KEY", raising=False)
    monkeypatch.delenv("APPWRITE_DATABASE_ID", raising=False)
    settings.cache_clear()
    assert settings()["PERSISTENCE_BACKEND"] == "postgres"


def test_appwrite_primary_still_requires_database_credentials(monkeypatch):
    monkeypatch.setenv("PERSISTENCE_BACKEND", "appwrite")
    monkeypatch.setenv("APPWRITE_ENDPOINT", "https://example.test/v1")
    monkeypatch.setenv("APPWRITE_PROJECT_ID", "proj")
    monkeypatch.delenv("APPWRITE_API_KEY", raising=False)
    monkeypatch.delenv("APPWRITE_DATABASE_ID", raising=False)
    settings.cache_clear()
    with pytest.raises(RuntimeError, match="APPWRITE_API_KEY"):
        settings()


def test_dual_write_is_noop_when_disabled(monkeypatch):
    monkeypatch.setattr(service, "appwrite_dual_write", lambda: False)
    ran: list[int] = []
    service._dual_write("battle dual write", lambda: ran.append(1))
    assert ran == []


def test_battle_get_does_not_open_appwrite_when_fallback_disabled(monkeypatch):
    @contextmanager
    def fake_scope():
        yield SimpleNamespace()

    monkeypatch.setattr(service, "using_postgres", lambda: True)
    monkeypatch.setattr(service, "appwrite_read_fallback", lambda: False)
    monkeypatch.setattr(service, "session_scope", fake_scope)
    monkeypatch.setattr(service.repositories.battles, "battle_get", lambda *_a, **_k: None)

    def boom(*_a, **_k):
        raise AssertionError("must not open Appwrite")

    monkeypatch.setattr(service, "_aw", boom)
    assert service.battle_get("user-1", "missing-battle") is None


def test_stats_snapshot_uses_postgres_not_appwrite(monkeypatch):
    count_row = SimpleNamespace(running=3, total=9)
    median_row = SimpleNamespace(med=12.5)
    top_row = SimpleNamespace(model_id="host:x", elo=1200.04, games_played=4)
    sql_calls: list[str] = []

    class FakeSession:
        def execute(self, stmt):
            sql = str(stmt)
            sql_calls.append(sql)
            if "FILTER" in sql:
                return SimpleNamespace(one=lambda: count_row)
            if "percentile_cont" in sql:
                return SimpleNamespace(one=lambda: median_row)
            return SimpleNamespace(all=lambda: [top_row])

    @contextmanager
    def fake_scope():
        yield FakeSession()

    monkeypatch.setattr(service, "using_postgres", lambda: True)
    monkeypatch.setattr(service, "session_scope", fake_scope)

    def boom():
        raise AssertionError("stats must not scan Appwrite")

    monkeypatch.setattr("agent_arena.stats.appwrite_snapshot", boom)
    out = service.stats_snapshot()
    assert out == {
        "battles_running": 3,
        "battles_total": 9,
        "median_duration_s": 12.5,
        "top_models": [
            {"model_id": "host:x", "elo": 1200.0, "games_played": 4},
        ],
    }
    assert sql_calls
    assert all("appwrite" not in sql.lower() for sql in sql_calls)
