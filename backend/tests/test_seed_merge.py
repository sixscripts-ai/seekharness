"""Hermetic tests for the non-destructive seeder (merge-preserve + force)."""

import json

import pytest

from agent_arena import seed_formats as sf


class _Doc:
    def __init__(self, doc_id: str, data: dict):
        self.id = doc_id
        self.data = data


class _Res:
    def __init__(self, documents):
        self.documents = documents


class FakeDatabases:
    """Minimal Appwrite Databases stand-in keyed by format name."""

    def __init__(self, existing: dict[str, dict]):
        # name -> stored document data ({"name","engine","config"})
        self._store = {
            name: _Doc(f"id-{i}", data) for i, (name, data) in enumerate(existing.items())
        }
        self.updates: list[tuple[str, dict]] = []
        self.creates: list[dict] = []

    @staticmethod
    def _name_from_queries(queries) -> str | None:
        for q in queries:
            try:
                parsed = json.loads(q)
            except (TypeError, ValueError):
                continue
            if parsed.get("attribute") == "name" and parsed.get("values"):
                return parsed["values"][0]
        return None

    def list_documents(self, database_id, collection_id, queries=None):
        name = self._name_from_queries(queries or [])
        if name is None:
            return _Res(list(self._store.values()))
        doc = self._store.get(name)
        return _Res([doc] if doc else [])

    def update_document(self, database_id, collection_id, document_id, data):
        self.updates.append((document_id, data))
        for doc in self._store.values():
            if doc.id == document_id:
                doc.data = data
        return _Doc(document_id, data)

    def create_document(self, database_id, collection_id, document_id, data):
        self.creates.append(data)
        return _Doc("new", data)


@pytest.fixture
def one_format(monkeypatch):
    """Restrict ALL_FORMATS to a single deterministic format for isolation."""
    cfg = sf.build_format(
        "Debugging race",
        "same_target_race",
        "desc",
        extra=sf.FORMAT_EXTRA.get("Debugging race"),
    )
    monkeypatch.setattr(sf, "ALL_FORMATS", [cfg])
    return cfg


def _install(monkeypatch, fake: FakeDatabases):
    monkeypatch.setattr(sf.db, "get_databases", lambda: fake)
    monkeypatch.setattr(sf.db, "get_database_id", lambda: "db")


def test_merge_preserves_unknown_live_keys(monkeypatch, one_format):
    monkeypatch.delenv("ARENA_SEED_FORCE", raising=False)
    live_cfg = {
        "name": "Debugging race",
        "engine": "same_target_race",
        # live-only key that git does not know about
        "role_missions": {"player_a": "live mission"},
        # live value that differs from git — must NOT be overwritten
        "target_code": "LIVE TARGET",
    }
    fake = FakeDatabases(
        {"Debugging race": {"name": "Debugging race", "engine": "same_target_race", "config": json.dumps(live_cfg)}}
    )
    _install(monkeypatch, fake)

    sf.seed_formats()

    assert len(fake.updates) == 1
    written = json.loads(fake.updates[0][1]["config"])
    # live-only key survived
    assert written["role_missions"] == {"player_a": "live mission"}
    # existing live value was not clobbered by git
    assert written["target_code"] == "LIVE TARGET"
    # a key missing live was filled from git
    assert written["universal"] is True


def test_force_overwrites_wholesale(monkeypatch, one_format):
    monkeypatch.setenv("ARENA_SEED_FORCE", "1")
    live_cfg = {
        "name": "Debugging race",
        "engine": "same_target_race",
        "role_missions": {"player_a": "live mission"},
        "target_code": "LIVE TARGET",
    }
    fake = FakeDatabases(
        {"Debugging race": {"name": "Debugging race", "engine": "same_target_race", "config": json.dumps(live_cfg)}}
    )
    _install(monkeypatch, fake)

    sf.seed_formats()

    written = json.loads(fake.updates[0][1]["config"])
    # force replaces with git config, dropping live-only keys
    assert "role_missions" not in written
    assert written["target_code"] == one_format["target_code"]


def test_idempotent_no_write_when_unchanged(monkeypatch, one_format):
    monkeypatch.delenv("ARENA_SEED_FORCE", raising=False)
    # Live config already equals the git config -> merge is a no-op.
    fake = FakeDatabases(
        {
            "Debugging race": {
                "name": "Debugging race",
                "engine": "same_target_race",
                "config": json.dumps(one_format),
            }
        }
    )
    _install(monkeypatch, fake)

    sf.seed_formats()

    assert fake.updates == []
    assert fake.creates == []


def test_creates_missing_format(monkeypatch, one_format):
    monkeypatch.delenv("ARENA_SEED_FORCE", raising=False)
    fake = FakeDatabases({})
    _install(monkeypatch, fake)

    sf.seed_formats()

    assert len(fake.creates) == 1
    created = json.loads(fake.creates[0]["config"])
    assert created["name"] == "Debugging race"
    assert created["universal"] is True


def test_hides_catalog_leftovers(monkeypatch, one_format):
    monkeypatch.delenv("ARENA_SEED_FORCE", raising=False)
    stub_cfg = {
        "name": "WAF builder vs bypasser",
        "engine": "build_and_break",
        "target_code": "# TASK: Implement solution.py for this format's mission.",
    }
    fake = FakeDatabases(
        {
            "Debugging race": {
                "name": "Debugging race",
                "engine": "same_target_race",
                "config": json.dumps(one_format),
            },
            "WAF builder vs bypasser": {
                "name": "WAF builder vs bypasser",
                "engine": "build_and_break",
                "config": json.dumps(stub_cfg),
            },
        }
    )
    _install(monkeypatch, fake)

    sf.seed_formats()

    hidden_updates = [
        data
        for doc_id, data in fake.updates
        if json.loads(data["config"]).get("name") == "WAF builder vs bypasser"
    ]
    assert hidden_updates
    written = json.loads(hidden_updates[-1]["config"])
    assert written["hidden"] is True
    assert written["playable"] is False
