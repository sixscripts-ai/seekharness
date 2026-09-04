"""Reap battles stuck in queued/running past their timeout.

Run periodically via the Modal scheduled function (modal_entry.py) or on
demand through POST /internal/reap. Idempotent: only terminal-stale battles
are touched, and each reaped battle is failed exactly once.

Postgres scans queued/running rows (oldest first), not the newest 100 battles
of any status. Clock start is started_at, else created_at, so queued rows with
a null started_at still expire.
"""

from __future__ import annotations

import os
import time
from datetime import datetime, timezone

from appwrite.query import Query


def _started_at(battle: dict, created_meta: str | None = None) -> float:
    for key in ("started_at", "created_at", "$createdAt"):
        value = battle.get(key)
        if value is None:
            continue
        try:
            if isinstance(value, datetime):
                if value.tzinfo is None:
                    value = value.replace(tzinfo=timezone.utc)
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


def _is_expired(
    battle: dict,
    now: float,
    grace: float,
    *,
    created_meta: str | None = None,
) -> tuple[bool, int, str]:
    """Return (expired, age_seconds, reason)."""
    status = battle.get("status")
    if status not in ("queued", "running"):
        return False, 0, ""
    started = _started_at(battle, created_meta)
    if not started:
        return False, 0, ""
    timeout = int(battle.get("timeout_seconds") or 600)
    age = now - started
    if age <= timeout + grace:
        return False, int(age), ""
    reason = (
        f"Stuck in '{status}' for {int(age)}s "
        f"(timeout {timeout}s + grace {int(grace)}s)"
    )
    return True, int(age), reason


def _stop_sandbox(sandbox_id: str | None) -> None:
    if not sandbox_id:
        return
    try:
        from . import sandbox_launcher

        sandbox_launcher.stop_sandbox(sandbox_id)
    except Exception:
        pass


def _publish_failed(battle_id: str, reason: str) -> None:
    from . import event_bus

    event_bus.publish(battle_id, {"type": "error", "data": {"message": reason}})
    event_bus.publish(
        battle_id,
        {"type": "battle_status", "data": {"status": "failed", "reason": reason}},
    )


def _reap_pg(now: float, grace: float) -> list[str]:
    from .persistence import repositories
    from .persistence.session import session_scope

    with session_scope() as session:
        rows = repositories.battles.battle_list_active(session)
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
    completed_at = datetime.fromtimestamp(now, tz=timezone.utc)
    for battle in battles:
        expired, _age, reason = _is_expired(battle, now, grace)
        if not expired:
            continue
        try:
            with session_scope() as session:
                updated = repositories.battles.battle_fail_if_active(
                    session,
                    battle["id"],
                    reason=reason,
                    completed_at=completed_at,
                )
        except Exception:
            continue
        if updated is None:
            continue
        sandbox_id = battle.get("sandbox_id")
        if sandbox_id:
            _stop_sandbox(sandbox_id)
        _publish_failed(battle["id"], reason)
        reaped.append(battle["id"])
    return reaped


def reap_stale_battles(databases=None, database_id: str | None = None) -> list[str]:
    from . import db
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
        battle = dict(doc.data)
        battle.setdefault("id", doc.id)
        expired, _age, reason = _is_expired(
            battle, now, grace, created_meta=getattr(doc, "createdat", None)
        )
        if not expired:
            continue
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
            _stop_sandbox(sandbox_id)
        _publish_failed(doc.id, reason)
        reaped.append(doc.id)
    return reaped
