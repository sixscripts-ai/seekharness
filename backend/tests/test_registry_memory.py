"""C9 skill Elo registry + D13 memory + E14 difficulty + E15 novelty (hermetic)."""

import types
import time

from agent_arena.seed_formats import DIFFICULTY_PRESETS, apply_difficulty


class _Doc:
    def __init__(self, id_, data):
        self.id = id_
        self.data = data


class FakeDB:
    """Minimal Appwrite Databases stub (create/list/update/delete on one coll)."""

    def __init__(self):
        self.store = {}
        self.n = 0

    def create_document(self, database_id, collection, id_, payload):
        self.n += 1
        key = f"d{self.n}"
        self.store[key] = dict(payload)
        return _Doc(key, self.store[key])

    def list_documents(self, database_id, collection, queries=None):
        import json

        docs = [_Doc(k, v) for k, v in self.store.items()]
        for q in queries or []:
            try:
                spec = json.loads(q)
            except (TypeError, ValueError):
                continue
            attr = spec.get("attribute")
            values = spec.get("values") or []
            if attr and values:
                docs = [d for d in docs if d.data.get(attr) in values]

        class R:
            documents = docs

        return R()

    def update_document(self, database_id, collection, id_, payload):
        self.store[id_] = dict(payload)
        return _Doc(id_, self.store[id_])

    def delete_document(self, database_id, collection, id_):
        self.store.pop(id_, None)


# ---- C9 skills_registry ----


def test_record_outcome_and_decay():
    from agent_arena.skills_registry import get_skill, get_rankings, record_outcome

    db = FakeDB()
    r = record_outcome(db, "d", "waf-bypass", outcome="win", tier="novice")
    assert r["wins"] == 1 and r["uses"] == 1 and r["elo"] > 1200
    r2 = record_outcome(db, "d", "waf-bypass", outcome="loss", tier="expert")
    assert r2["losses"] == 1 and r2["uses"] == 2
    assert r2["success_rate"] == 0.5
    assert get_skill(db, "d", "missing")["elo"] == 1200
    assert get_rankings(db, "d")


def test_difficulty_presets():
    base = {"limits": {"max_tool_steps": 14}, "scoring": {"weights": {"tests": 0.6}}}
    novice = apply_difficulty(base, "novice")
    assert novice["limits"]["max_tool_steps"] == 8
    assert novice["difficulty"] == "novice"
    expert = apply_difficulty(base, "expert")
    assert expert["limits"]["max_tool_steps"] == 30
    assert apply_difficulty(base, None) is base


# ---- D13 memory + E15 novelty ----


def test_memory_remember_retrieve_and_novelty():
    from agent_arena.memory import maybe_remember, novelty_score, retrieve

    db = FakeDB()
    insight = "WAF bypass wins when payload is encoded as unicode escapes"
    r = maybe_remember(
        db,
        "d",
        insight=insight,
        battle_id="b1",
        chosen_skills=["waf-bypass"],
        theory="unicode",
        outcome="win",
        format_name="WAF",
    )
    assert r is not None
    hits = retrieve(db, "d", "how to bypass waf unicode", context_mode="adaptive")
    assert hits and hits[0]["battle_id"] == "b1"
    # duplicate is blocked by novelty gate
    dup = maybe_remember(
        db,
        "d",
        insight=insight,
        battle_id="b2",
        chosen_skills=["waf-bypass"],
        theory="unicode",
        outcome="win",
    )
    assert dup is None
    assert novelty_score(db, "d", insight="totally different topic") > 0


def test_memory_forget():
    from agent_arena.memory import forget

    db = FakeDB()
    db.create_document(
        "d",
        "memories",
        "unique()",
        {
            "created_at": time.time() - 400 * 86400,
            "tokens": ["old"],
            "insight": "stale",
        },
    )
    db.create_document(
        "d",
        "memories",
        "unique()",
        {
            "created_at": time.time(),
            "tokens": ["fresh"],
            "insight": "new",
        },
    )
    assert forget(db, "d", older_than_days=180) == 1
    assert len(db.store) == 1
