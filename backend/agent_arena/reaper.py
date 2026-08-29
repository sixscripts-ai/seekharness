"""Reap battles stuck in queued/running past their timeout.

Run periodically via the Modal scheduled function (modal_entry.py) or on
demand through POST /internal/reap. Idempotent: only terminal-stale battles
are touched, and each reaped battle is failed exactly once.
"""

from __future__ import annotations

import os
import time
from datetime import datetime

from appwrite.query import Query


def _started_at(battle: dict, created_meta: str | None = None) -> float:
    for key in ("started_at", "created_at", "$createdAt"):
        value = battle.get(key)
        if value is None:
            continue
        try:
            if isinstance(value, datetime):
                return value.timestamp()
            return float(value)
        except (TypeError, ValueError):
            continue
    if created_meta:
        s = str(created_meta)
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        try:
            return datetime.fromisoformat(s).timestamp()
        except (ValueError, TypeError):
            pass
    return 0.0


def _reap_pg(now: float, grace: float) -> list[str]:
    from . import event_bus
    from .persistence import repositories, service
    from .persistence.session import session_scope

    with session_scope() as session:
        rows = repositories.battles.battle_list(session, user_id=None, status=None)
        battles = [
            {
                "id": b.id,
                "status": b.status,
                "started_at": b.started_at,
                "created_at": b.created_at,
                "timeout_seconds": b.timeout_seconds,
                "sandbox_id": b.sandbox_id,
            }
            for b in rows
        ]
    reaped: list[str] = []
    for battle in battles:
        if battle.get("status") not in ("queued", "running"):
            continue
        started = _started_at(battle)
        if not started:
            continue
        timeout = int(battle.get("timeout_seconds") or 600)
        age = now - started
        if age <= timeout + grace:
            continue
        reason = f"Stuck in '{battle.get('status')}' for {int(age)}s (timeout {timeout}s + grace {int(grace)}s)"
        try:
            service.battle_update(
                battle["id"], {"status": "failed", "failure_reason": reason}
            )
        except Exception:
            continue
        sandbox_id = battle.get("sandbox_id")
        if sandbox_id:
            try:
                from . import sandbox_launcher

                sandbox_launcher.stop_sandbox(sandbox_id)
            except Exception:
                pass
        event_bus.publish(battle["id"], {"type": "error", "data": {"message": reason}})
        event_bus.publish(
            battle["id"],
            {"type": "battle_status", "data": {"status": "failed", "reason": reason}},
        )
        reaped.append(battle["id"])
    return reaped


def reap_stale_battles(databases=None, database_id: str | None = None) -> list[str]:
    from . import db, event_bus
    from .persistence import service

    now = time.time()
    grace = float(os.environ.get("REAPER_GRACE_SECONDS", "300"))
    if service.using_postgres():
        return _reap_pg(now, grace)
    databases = databases or db.get_databases()
    database_id = database_id or db.get_database_id()
    res = databases.list_documents(
        database_id,
        "battles",
        queries=[
            Query.equal("status", ["queued", "running"]),
            Query.limit(100),
        ],
    )
    reaped: list[str] = []
    for doc in res.documents:
        battle = doc.data
        started = _started_at(battle, getattr(doc, "createdat", None))
        if not started:
            continue
        timeout = int(battle.get("timeout_seconds") or 600)
        age = now - started
        if age <= timeout + grace:
            continue
        reason = f"Stuck in '{battle.get('status')}' for {int(age)}s (timeout {timeout}s + grace {int(grace)}s)"
        try:
            databases.update_document(
                database_id,
                "battles",
                doc.id,
                {"status": "failed", "failure_reason": reason},
            )
        except Exception:
            continue
        sandbox_id = battle.get("sandbox_id")
        if sandbox_id:
            try:
                from . import sandbox_launcher

                sandbox_launcher.stop_sandbox(sandbox_id)
            except Exception:
                pass
        event_bus.publish(doc.id, {"type": "error", "data": {"message": reason}})
        event_bus.publish(
            doc.id,
            {"type": "battle_status", "data": {"status": "failed", "reason": reason}},
        )
        reaped.append(doc.id)
    return reaped
