import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from agent_arena.persistence.models import Base, Battle, BattleParticipant
from agent_arena.persistence.repositories.battles import battle_cancel as repo_battle_cancel
from agent_arena.persistence import service


class MockBattleSession:
    def __init__(self, battle: Battle | None):
        self.battle = battle
        self.flushed = False

    def scalars(self, stmt):
        class Result:
            def __init__(self, item):
                self.item = item
            def first(self):
                return self.item
        return Result(self.battle)

    def flush(self):
        self.flushed = True


def test_repo_battle_cancel_transitions_active_battle():
    battle = Battle(
        id="b-active",
        user_id="user-1",
        status="running",
    )
    session = MockBattleSession(battle)

    updated_battle, err = repo_battle_cancel(session, "b-active", user_id="user-1")
    assert err is None
    assert updated_battle is not None
    assert updated_battle.status == "cancelled"
    assert session.flushed is True


def test_repo_battle_cancel_rejects_terminal_battle():
    for terminal_status in ("completed", "failed", "cancelled"):
        battle = Battle(
            id=f"b-{terminal_status}",
            user_id="user-1",
            status=terminal_status,
        )
        session = MockBattleSession(battle)
        updated_battle, err = repo_battle_cancel(session, battle.id, user_id="user-1")
        assert err == "already_terminal"
        assert updated_battle.status == terminal_status
        assert session.flushed is False


def test_repo_battle_cancel_checks_ownership():
    battle = Battle(
        id="b-owner-test",
        user_id="user-1",
        status="running",
    )
    session = MockBattleSession(battle)
    _, err = repo_battle_cancel(session, "b-owner-test", user_id="wrong-user")
    assert err == "forbidden"


def test_repo_battle_cancel_not_found():
    session = MockBattleSession(None)
    _, err = repo_battle_cancel(session, "b-nonexistent", user_id="user-1")
    assert err == "not_found"


def test_service_battle_cancel_raises_409_on_terminal(monkeypatch):
    """service.battle_cancel must raise 409 Conflict when battle is already completed."""
    monkeypatch.setattr(service, "using_postgres", lambda: False)
    monkeypatch.setattr(
        service,
        "battle_get",
        lambda uid, bid: {"id": bid, "user_id": uid, "status": "completed"},
    )

    with pytest.raises(HTTPException) as exc_info:
        service.battle_cancel("u1", "b-completed")
    assert exc_info.value.status_code == 409
    assert "terminal status" in str(exc_info.value.detail)


def test_service_battle_cancel_idempotent_on_cancelled(monkeypatch):
    """service.battle_cancel returns already_terminal when battle is already cancelled."""
    monkeypatch.setattr(service, "using_postgres", lambda: False)
    monkeypatch.setattr(
        service,
        "battle_get",
        lambda uid, bid: {"id": bid, "user_id": uid, "status": "cancelled"},
    )

    res = service.battle_cancel("u1", "b-already-cancelled")
    assert res["status"] == "cancelled"
    assert res.get("already_terminal") is True


def test_save_battle_never_calls_mock_persist_scores(monkeypatch):
    """Blocker 1 test: save_battle must only save the bookmark and never fabricate mock scores."""
    from agent_arena.battles import save_battle
    import agent_arena.mock_runner as mock_runner

    saved_calls = []
    monkeypatch.setattr(
        service,
        "battle_save",
        lambda uid, bid: saved_calls.append((uid, bid)),
    )
    monkeypatch.setattr(
        mock_runner,
        "persist_scores",
        lambda bid: pytest.fail("mock_runner.persist_scores must never be called by save_battle"),
    )

    res = save_battle("b-123", user_id="user-xyz")
    assert res == {"id": "b-123", "saved": True}
    assert saved_calls == [("user-xyz", "b-123")]
