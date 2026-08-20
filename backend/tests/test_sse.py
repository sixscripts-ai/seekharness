import importlib.util
import sys
from types import ModuleType

import pytest

from tests.conftest import make_user_id, playable_format_id, requires_appwrite


@pytest.fixture(autouse=True)
def _stub_leaderboard(monkeypatch):
    try:
        spec = importlib.util.find_spec("agent_arena.leaderboard")
    except ModuleNotFoundError:
        spec = None
    if spec is not None:
        return
    stub = ModuleType("agent_arena.leaderboard")
    stub.apply_result = lambda databases, database_id, format_id, model_ids, scores: None
    monkeypatch.setitem(sys.modules, "agent_arena.leaderboard", stub)


def _real_format_id() -> str:
    return playable_format_id()


@requires_appwrite
def test_stream_emits_ordered_events(client):
    from agent_arena.auth import get_current_user
    from agent_arena.main import app
    user_id = make_user_id()
    app.dependency_overrides[get_current_user] = lambda: user_id
    try:
        battle = client.post("/battles", json={
            "format_id": _real_format_id(),
            "model_ids": ["host:openrouter-free", "host:openrouter-free"],
            "arena_size": 2,
            "timeout_seconds": 600,
            "round_visibility": "isolated",
            "save": False,
        }).json()
        with client.stream("GET", f"/battles/{battle['id']}/stream") as resp:
            assert resp.status_code == 200
            text = "".join(resp.iter_text())
    finally:
        app.dependency_overrides.clear()

    assert "event: battle_status" in text
    assert "event: phase_start" in text
    assert "event: artifact" in text
    assert "event: scores" in text
    assert "event: done" in text
    assert '"status": "completed"' in text
    # phase_start must precede artifact within the stream text
    assert text.index("event: phase_start") < text.index("event: artifact")
