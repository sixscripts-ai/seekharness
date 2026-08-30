"""Appwrite-backed skill registry: Elo, wins/losses/draws, uses, success_rate,
tier, tags, last_used, and time-based decay. Mirrors leaderboard.py patterns.

Collection: `skills`. Document id = unique per skill name (slugified).
Outcome is judged as win/loss/draw against an expected score derived from
Elo and battle difficulty; success_rate tracks recent correctness.
"""

from __future__ import annotations

import time

from appwrite.query import Query

from . import elo

INITIAL_RATING = elo.INITIAL_RATING
DECAY_RATE = 0.02  # fraction of (INITIAL_RATING - elo) recovered per day unused
DECAY_PERIOD_SECONDS = 86400.0

_DIFFICULTY_OFFSET = {
    "novice": 0.0,
    "general": 0.0,
    "advanced": -100.0,  # harder targets: expected win rate lower for same elo
    "expert": -200.0,
}


from .skills.canonical import slugify


def _find(databases, database_id, skill_name):
    clean = slugify(skill_name)
    res = databases.list_documents(
        database_id,
        "skills",
        queries=[Query.equal("skill", clean), Query.limit(1)],
    )
    docs = res.documents
    if docs:
        return docs[0]
    if clean != skill_name:
        res2 = databases.list_documents(
            database_id,
            "skills",
            queries=[Query.equal("skill", skill_name), Query.limit(1)],
        )
        if res2.documents:
            return res2.documents[0]
    return None


def _defaults(skill_name: str) -> dict:
    clean = slugify(skill_name)
    return {
        "skill": clean,
        "elo": INITIAL_RATING,
        "wins": 0,
        "losses": 0,
        "draws": 0,
        "uses": 0,
        "success_rate": 1.0,
        "tier": "general",
        "tags": [],
        "last_used": time.time(),
    }



def _with_decay(entry: dict, now: float | None = None) -> dict:
    """Time decay toward INITIAL_RATING while unused; deterministic per update."""
    if entry.get("uses", 0) <= 0:
        return entry
    now = now or time.time()
    last = float(entry.get("last_used") or now)
    days = max(0.0, (now - last) / DECAY_PERIOD_SECONDS)
    factor = max(0.0, 1.0 - DECAY_RATE * days)
    current = float(entry.get("elo") or INITIAL_RATING)
    entry["elo"] = round(INITIAL_RATING + (current - INITIAL_RATING) * factor, 2)
    return entry


def get_skill(databases, database_id, skill_name) -> dict:
    entry = _find(databases, database_id, skill_name)
    if not entry:
        return _defaults(skill_name)
    data = dict(entry.data)
    return _with_decay(data)


def _upsert(databases, database_id, skill_name: str, payload: dict) -> None:
    entry = _find(databases, database_id, skill_name)
    if entry:
        databases.update_document(database_id, "skills", entry.id, payload)
    else:
        databases.create_document(database_id, "skills", "unique()", payload)


def record_outcome(
    databases,
    database_id,
    skill_name: str,
    *,
    outcome: str,
    tier: str = "general",
    tags: list[str] | None = None,
) -> dict:
    """Apply one outcome: win|loss|draw (agent used the skill successfully or not).

    Elo moves toward the expected score implied by current elo + difficulty.
    Keeps wins/losses/draws/uses/success_rate/last_used. Returns updated doc.
    """
    cur = get_skill(databases, database_id, skill_name)
    offset = _DIFFICULTY_OFFSET.get(tier, 0.0)
    expected = elo.expected_score(cur["elo"] + offset, INITIAL_RATING)
    score = {"win": 1.0, "draw": 0.5, "loss": 0.0}[outcome]

    if outcome == "win":
        cur["wins"] = int(cur.get("wins") or 0) + 1
    elif outcome == "loss":
        cur["losses"] = int(cur.get("losses") or 0) + 1
    else:
        cur["draws"] = int(cur.get("draws") or 0) + 1
    cur["uses"] = int(cur.get("uses") or 0) + 1
    cur["success_rate"] = round(
        (float(cur.get("wins") or 0) + 0.5 * float(cur.get("draws") or 0))
        / max(1, int(cur.get("uses") or 1)),
        3,
    )
    cur["elo"] = round(float(cur["elo"]) + elo.K_FACTOR * (score - expected), 2)
    cur["tier"] = tier
    cur["tags"] = tags or []
    cur["last_used"] = time.time()

    payload = {k: v for k, v in cur.items()}
    _upsert(databases, database_id, skill_name, payload)
    return payload


def apply_result(
    databases, database_id, used_skills: list[str], won: bool
) -> list[dict]:
    """Batch record: mark each used skill with the battle outcome."""
    out: list[dict] = []
    for skill in used_skills or []:
        out.append(
            record_outcome(
                databases,
                database_id,
                skill,
                outcome="win" if won else "loss",
            )
        )
    return out


def get_rankings(databases, database_id, limit: int = 100) -> list[dict]:
    res = databases.list_documents(
        database_id,
        "skills",
        queries=[Query.limit(limit)],
    )
    entries = sorted(
        (_with_decay(dict(e.data)) for e in res.documents),
        key=lambda e: e["elo"],
        reverse=True,
    )
    return [
        {
            "skill": e["skill"],
            "elo": e["elo"],
            "wins": e["wins"],
            "losses": e["losses"],
            "draws": e["draws"],
            "uses": e["uses"],
            "success_rate": e["success_rate"],
            "tier": e["tier"],
            "tags": e["tags"],
            "last_used": e["last_used"],
        }
        for e in entries
    ]
