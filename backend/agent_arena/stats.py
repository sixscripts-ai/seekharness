from datetime import datetime
from statistics import median

from appwrite.query import Query
from fastapi import APIRouter

from . import db

router = APIRouter(prefix="/stats", tags=["stats"])


def _parse_ts(value) -> datetime | None:
    if not value:
        return None
    try:
        s = str(value)
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        return datetime.fromisoformat(s)
    except (ValueError, TypeError):
        return None


def _iter_battles(databases, database_id, cap: int = 2000):
    offset = 0
    total = 0
    while True:
        res = databases.list_documents(
            database_id,
            "battles",
            queries=[Query.limit(100), Query.offset(offset)],
        )
        docs = res.documents
        if not docs:
            break
        total += len(docs)
        for b in docs:
            yield b
        if total >= cap:
            break
        offset += len(docs)


def appwrite_snapshot() -> dict:
    """Legacy Appwrite-backed snapshot (kept for the Appwrite persistence branch)."""
    databases = db.get_databases()
    database_id = db.get_database_id()

    battles = list(_iter_battles(databases, database_id))
    running = sum(1 for b in battles if b.data.get("status") in ("queued", "running"))

    durations = []
    for b in battles:
        if b.data.get("status") != "completed":
            continue
        created = _parse_ts(getattr(b, "createdat", None) or b.data.get("created_at"))
        updated = _parse_ts(getattr(b, "updatedat", None) or b.data.get("updated_at"))
        if created and updated:
            durations.append((updated - created).total_seconds())

    lb = databases.list_documents(
        database_id,
        "leaderboard",
        queries=[Query.equal("format_id", "overall"), Query.limit(100)],
    ).documents
    top = sorted(lb, key=lambda e: e.data.get("elo", 0), reverse=True)[:5]

    return {
        "battles_running": running,
        "battles_total": len(battles),
        "median_duration_s": round(median(durations), 1) if durations else None,
        "top_models": [
            {
                "model_id": e.data["model_id"],
                "elo": round(e.data.get("elo", 0), 1),
                "games_played": e.data.get("games_played", 0),
            }
            for e in top
        ],
    }


@router.get("")
def get_stats():
    from .persistence import service

    return service.stats_snapshot()
