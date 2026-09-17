"""Saved custom challenges are owner-scoped Postgres records, not browser links."""

from contextlib import contextmanager
from types import SimpleNamespace

from sqlalchemy.dialects import postgresql

from agent_arena.auth import get_current_user
from agent_arena.main import app
from agent_arena.persistence import repositories, service
from agent_arena.persistence.models import BattleDraft
from agent_arena.persistence.repositories import drafts


def _row(draft_id: str, owner: str, saved: bool = False):
    return SimpleNamespace(
        id=draft_id,
        user_id=owner,
        mode="quick",
        transcript=[],
        spec={"title": "My challenge", "brief": "A task"},
        revision=3,
        status="ready",
        saved=saved,
        launched_battle_id=None,
        architect_error=None,
        created_at=None,
        updated_at=None,
    )


def test_saved_library_routes_are_account_owned_and_idempotent(client, monkeypatch):
    rows = {"mine": _row("mine", "owner"), "theirs": _row("theirs", "other")}

    @contextmanager
    def scope():
        yield SimpleNamespace()

    def list_saved(_session, owner):
        return [row for row in rows.values() if row.user_id == owner and row.saved]

    def set_saved(_session, draft_id, owner, saved):
        row = rows.get(draft_id)
        if not row or row.user_id != owner:
            return None
        row.saved = saved
        return row

    monkeypatch.setattr(service, "using_postgres", lambda: True)
    monkeypatch.setattr("agent_arena.persistence.session.session_scope", scope)
    monkeypatch.setattr(repositories.drafts, "saved_draft_list", list_saved)
    monkeypatch.setattr(repositories.drafts, "draft_set_saved", set_saved)
    app.dependency_overrides[get_current_user] = lambda: "owner"
    try:
        assert client.get("/battle-drafts").json() == []
        assert client.put("/battle-drafts/theirs/save").status_code == 404
        first = client.put("/battle-drafts/mine/save")
        assert first.status_code == 200
        assert first.json()["saved"] is True
        assert first.json()["revision"] == 3
        assert client.put("/battle-drafts/mine/save").json()["revision"] == 3
        assert [row["id"] for row in client.get("/battle-drafts").json()] == ["mine"]
        assert client.delete("/battle-drafts/mine/save").json()["saved"] is False
        assert client.get("/battle-drafts").json() == []
    finally:
        app.dependency_overrides.clear()


def test_saved_library_fails_closed_without_postgres(client, monkeypatch):
    monkeypatch.setattr(service, "using_postgres", lambda: False)
    app.dependency_overrides[get_current_user] = lambda: "owner"
    try:
        assert client.get("/battle-drafts").status_code == 503
        assert client.put("/battle-drafts/mine/save").status_code == 503
    finally:
        app.dependency_overrides.clear()


def test_repository_saved_selection_requires_owner_and_saved_flag():
    # Compile the real query; route mocks above are only for HTTP behavior.
    class Session:
        def scalars(self, statement):
            self.statement = statement
            return []

    session = Session()
    assert drafts.saved_draft_list(session, "owner") == []
    sql = str(session.statement.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))
    assert "battle_drafts.user_id = 'owner'" in sql
    assert "battle_drafts.saved IS true" in sql
    assert BattleDraft.saved is not None
