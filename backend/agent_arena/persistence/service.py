"""Persistence service: the single decision point for backend selection.

All durable reads/writes for the application domain flow through this module.
When PERSISTENCE_BACKEND=postgres, PostgreSQL is the primary store; optional
APPWRITE_DUAL_WRITE mirrors writes to Appwrite best-effort (never blocking),
and APPWRITE_READ_FALLBACK serves legacy records that are not in Postgres yet.

Fallback happens ONLY for legitimate record absence (404 / no rows), never for
arbitrary database errors. Appwrite Auth and the repository-backed Target
Library are untouched.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, text

from . import repositories
from .models import (
    Battle,
    BattleDraft,
    BattleEvent,
    Format,
    LeaderboardEntry,
    Memory,
    Provider,
    Round,
    Score,
    SkillRecord,
)
from .session import session_scope

log = logging.getLogger("agent_arena.persistence.service")


def using_postgres() -> bool:
    from agent_arena.config import settings

    return settings().get("PERSISTENCE_BACKEND", "appwrite") == "postgres"


def appwrite_read_fallback() -> bool:
    from agent_arena.config import settings

    value = settings().get("APPWRITE_READ_FALLBACK", "true")
    return value is True or str(value).lower() in ("true", "1")


def appwrite_dual_write() -> bool:
    from agent_arena.config import settings

    value = settings().get("APPWRITE_DUAL_WRITE", "true")
    return value is True or str(value).lower() in ("true", "1")


def _aw():
    """Return (databases, database_id) for direct Appwrite access."""
    from agent_arena import db

    return db.get_databases(), db.get_database_id()


def _sanitized_log(action: str, exc: Exception) -> None:
    """Log a persistence failure without any payload content or secrets."""
    log.warning("%s failed: %s", action, exc.__class__.__name__)


def _dual_write(action: str, fn) -> None:
    """Best-effort Appwrite mirror write; never raises, never blocks PG."""
    if not appwrite_dual_write():
        return
    try:
        fn()
    except Exception as exc:
        _sanitized_log(action, exc)


# ---------------------------------------------------------------------------
# Formats
# ---------------------------------------------------------------------------


def formats_list() -> list[dict]:
    """List playable formats, sorted by name (same shape as GET /formats)."""
    from agent_arena.seed_formats import is_playable_format

    if using_postgres():
        with session_scope() as session:
            rows = repositories.formats.format_list(session)
            out = []
            for row in rows:
                cfg = row.config if isinstance(row.config, dict) else {}
                if not is_playable_format(cfg):
                    continue
                out.append(
                    {
                        "id": row.id,
                        "name": cfg.get("name", row.name),
                        "engine": row.engine,
                        "description": cfg.get("description", ""),
                        "slug": cfg.get("id", row.id),
                        "roles": cfg.get("roles", []),
                        "config": cfg,
                    }
                )
            out.sort(key=lambda f: f["name"])
            return out
    # Appwrite path (unchanged behavior)
    from appwrite.query import Query

    databases, database_id = _aw()
    res = databases.list_documents(database_id, "formats", queries=[Query.limit(100)])
    out = []
    for doc in res.documents:
        cfg = json.loads(doc.data["config"])
        if not is_playable_format(cfg):
            continue
        out.append(
            {
                "id": doc.id,
                "name": cfg["name"],
                "engine": cfg["engine"],
                "description": cfg["description"],
                "slug": cfg["id"],
                "roles": cfg.get("roles", []),
                "config": cfg,
            }
        )
    out.sort(key=lambda f: f["name"])
    return out


def format_get(format_id: str) -> dict | None:
    """Return a format dict (including config) or None."""
    if using_postgres():
        with session_scope() as session:
            row = session.get(Format, format_id)
            if row is not None:
                cfg = row.config if isinstance(row.config, dict) else {}
                return {
                    "id": row.id,
                    "name": row.name,
                    "engine": row.engine,
                    "config": cfg,
                }
        if not appwrite_read_fallback():
            return None
        # fallthrough to Appwrite below
    try:
        databases, database_id = _aw()
        doc = databases.get_document(database_id, "formats", format_id)
        cfg = json.loads(doc.data["config"])
        record = {
            "id": doc.id,
            "name": doc.data["name"],
            "engine": doc.data["engine"],
            "config": cfg,
        }
        _format_read_through(record)
        return record
    except Exception as exc:
        if using_postgres() and not appwrite_read_fallback():
            return None
        if isinstance(exc, Exception) and _is_not_found(exc):
            return None
        if not using_postgres():
            return None
        raise


def _is_not_found(exc: Exception) -> bool:
    name = exc.__class__.__name__
    return name == "AppwriteException" and str(getattr(exc, "code", "") or "") in (
        "404",
    )


def _format_read_through(record: dict) -> None:
    try:
        with session_scope() as session:
            existing = session.get(Format, record["id"])
            if existing is None:
                repositories.formats.format_create(
                    session,
                    id=record["id"],
                    name=record["name"],
                    engine=record["engine"],
                    config=record["config"],
                )
    except Exception as exc:
        _sanitized_log("format read-through", exc)


# ---------------------------------------------------------------------------
# Providers
# ---------------------------------------------------------------------------


def _pg_provider_dict(row: Provider) -> dict:
    return {
        "id": row.id,
        "user_id": row.user_id,
        "name": row.name,
        "base_url": row.base_url,
        "masked_key": row.masked_key,
        "auth_style": row.auth_style,
        "model_name": row.model_name,
    }


def providers_list(user_id: str) -> list[dict]:
    """User-owned provider rows (host providers are layered on by the router)."""
    if using_postgres():
        with session_scope() as session:
            rows = repositories.providers.provider_list(session, user_id)
            return [_pg_provider_dict(r) for r in rows]
    databases, database_id = _aw()
    from appwrite.query import Query

    res = databases.list_documents(
        database_id,
        "providers",
        queries=[Query.equal("user_id", user_id), Query.limit(100)],
    )
    return [
        {
            "id": d.id,
            "user_id": d.data["user_id"],
            "name": d.data["name"],
            "base_url": d.data["base_url"],
            "masked_key": d.data["masked_key"],
            "auth_style": d.data["auth_style"],
            "model_name": d.data.get("model_name", ""),
        }
        for d in res.documents
    ]


def provider_upsert(
    user_id: str,
    name: str,
    base_url: str,
    encrypted_key: str,
    masked_key: str,
    auth_style: str,
    model_name: str,
) -> dict:
    """Create or replace a user provider (same-name upsert like Appwrite path)."""
    if using_postgres():
        with session_scope() as session:
            existing = None
            for row in repositories.providers.provider_list(session, user_id):
                if row.name == name:
                    existing = row
                    break
            if existing is not None:
                row = repositories.providers.provider_update(
                    session,
                    existing.id,
                    base_url=base_url,
                    encrypted_key=encrypted_key,
                    masked_key=masked_key,
                    auth_style=auth_style,
                    model_name=model_name,
                )
            else:
                row = repositories.providers.provider_create(
                    session,
                    user_id=user_id,
                    name=name,
                    base_url=base_url,
                    encrypted_key=encrypted_key,
                    masked_key=masked_key,
                    auth_style=auth_style,
                    model_name=model_name,
                )
            record = _pg_provider_dict(row)
        if using_postgres():
            _dual_write(
                "provider dual write",
                lambda: _aw_provider_upsert(
                    record["id"],
                    user_id,
                    name,
                    base_url,
                    encrypted_key,
                    masked_key,
                    auth_style,
                    model_name,
                ),
            )
        return record
    return _aw_provider_upsert(
        None, user_id, name, base_url, encrypted_key, masked_key, auth_style, model_name
    )


def _aw_provider_upsert(
    provider_id: str | None,
    user_id: str,
    name: str,
    base_url: str,
    encrypted_key: str,
    masked_key: str,
    auth_style: str,
    model_name: str,
) -> dict:
    from appwrite.query import Query

    databases, database_id = _aw()
    payload = {
        "user_id": user_id,
        "name": name,
        "base_url": base_url,
        "encrypted_key": encrypted_key,
        "masked_key": masked_key,
        "auth_style": auth_style,
        "model_name": model_name,
    }
    existing = provider_id
    if existing is None:
        res = databases.list_documents(
            database_id,
            "providers",
            queries=[
                Query.equal("user_id", user_id),
                Query.equal("name", name),
                Query.limit(1),
            ],
        )
        existing = res.documents[0].id if res.documents else None
    if existing:
        doc = databases.update_document(database_id, "providers", existing, payload)
    else:
        doc = databases.create_document(database_id, "providers", "unique()", payload)
    return {
        "id": doc.id,
        "user_id": user_id,
        "name": name,
        "base_url": base_url,
        "masked_key": masked_key,
        "auth_style": auth_style,
        "model_name": model_name,
    }


def provider_get(user_id: str, provider_id: str) -> dict | None:
    """Full provider doc including ciphertext (internal use: decrypt/health)."""
    if using_postgres():
        with session_scope() as session:
            row = session.get(Provider, provider_id)
            if row is not None:
                return {**_pg_provider_dict(row), "encrypted_key": row.encrypted_key}
        if not appwrite_read_fallback():
            return None
    try:
        databases, database_id = _aw()
        doc = databases.get_document(database_id, "providers", provider_id)
        record = {
            "id": doc.id,
            "user_id": doc.data.get("user_id", ""),
            "name": doc.data["name"],
            "base_url": doc.data["base_url"],
            "encrypted_key": doc.data["encrypted_key"],
            "masked_key": doc.data["masked_key"],
            "auth_style": doc.data["auth_style"],
            "model_name": doc.data.get("model_name", ""),
        }
        _provider_read_through(record)
        return record
    except Exception as exc:
        if not using_postgres():
            return None
        if _is_not_found(exc):
            return None
        raise


def _provider_read_through(record: dict) -> None:
    try:
        with session_scope() as session:
            if session.get(Provider, record["id"]) is None:
                repositories.providers.provider_create(
                    session,
                    id=record["id"],
                    user_id=record["user_id"],
                    name=record["name"],
                    base_url=record["base_url"],
                    encrypted_key=record["encrypted_key"],
                    masked_key=record["masked_key"],
                    auth_style=record["auth_style"],
                    model_name=record["model_name"],
                )
    except Exception as exc:
        _sanitized_log("provider read-through", exc)


def provider_delete(user_id: str, provider_id: str) -> tuple[bool, str | None]:
    """Delete a user provider. Returns (deleted, name)."""
    if using_postgres():
        with session_scope() as session:
            row = session.get(Provider, provider_id)
            if row is None:
                return False, None
            if row.user_id != user_id:
                return False, row.name
            name = row.name
            repositories.providers.provider_delete(session, provider_id)
        _dual_write(
            "provider delete dual write",
            lambda: _aw_provider_delete(provider_id),
        )
        return True, name
    return _aw_provider_delete_with_owner(provider_id, user_id)


def _aw_provider_delete(provider_id: str) -> None:
    databases, database_id = _aw()
    databases.delete_document(database_id, "providers", provider_id)


def _aw_provider_delete_with_owner(
    provider_id: str, user_id: str
) -> tuple[bool, str | None]:
    from appwrite.exception import AppwriteException

    databases, database_id = _aw()
    try:
        doc = databases.get_document(database_id, "providers", provider_id)
    except AppwriteException as exc:
        raise LookupError("Provider not found") from exc
    if doc.data.get("user_id") != user_id:
        return False, doc.data.get("name")
    databases.delete_document(database_id, "providers", provider_id)
    return True, doc.data.get("name")


# ---------------------------------------------------------------------------
# Battles
# ---------------------------------------------------------------------------


def _pg_battle_dict(battle: Battle, model_ids: list[str]) -> dict:
    return {
        "id": battle.id,
        "user_id": battle.user_id,
        "format_id": battle.format_id,
        "model_ids": model_ids,
        "arena_size": battle.arena_size,
        "status": battle.status,
        "timeout_seconds": battle.timeout_seconds,
        "round_visibility": battle.round_visibility,
        "saved": battle.saved,
        "sandbox_id": battle.sandbox_id,
        "judge_provider_id": battle.judge_provider_id,
        "preview_urls": battle.preview_urls,
        "failure_reason": battle.failure_reason,
        "started_at": battle.started_at,
        "completed_at": battle.completed_at,
        "difficulty": battle.difficulty,
        "draft_id": battle.draft_id,
        "battle_config": battle.battle_config,
        "spec_hash": battle.spec_hash,
        "custom_title": battle.custom_title,
        "ranked": battle.ranked,
        "target_id": battle.target_id,
        "target_version": battle.target_version,
        "target_manifest_hash": battle.target_manifest_hash,
        "created_at": battle.created_at,
        "updated_at": battle.updated_at,
    }


def _battle_model_ids_pg(session, battle_id: str) -> list[str]:
    return repositories.battles.battle_model_ids(session, battle_id)


def _authoritative_ranked_for_create(
    payload: dict, cfg: dict | None = None
) -> bool:
    """Create-time ranked boolean derived from frozen config + target gate.

    Always returns True or False. Does not treat stored null/missing as false;
    this helper is only for new writes. Callers cannot enable ranking when the
    frozen config or target gate disables it.
    """
    from agent_arena.custom_battles import is_ranked_battle

    if cfg is None:
        raw = payload.get("battle_config")
        if isinstance(raw, str) and raw.strip():
            try:
                raw = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                raw = {}
        cfg = raw if isinstance(raw, dict) else {}
    return is_ranked_battle(payload, cfg)


def battle_create(
    user_id: str,
    *,
    format_id: str,
    model_ids: list[str],
    arena_size: int,
    timeout_seconds: int,
    round_visibility: str,
    save: bool,
    judge_provider_id: str | None = None,
    difficulty: str | None = None,
    target_id: str | None = None,
    target_version: str | None = None,
) -> dict:
    """Create a battle with the full validation chain. Returns {id, status}."""
    from fastapi import HTTPException

    from agent_arena.providers import is_host_model
    from agent_arena.seed_formats import is_playable_format

    # --- validation (backend contract, unchanged) ---
    fmt = format_get(format_id)
    if fmt is None:
        raise HTTPException(status_code=404, detail="Unknown format")
    cfg = fmt["config"]
    if not is_playable_format(cfg):
        raise HTTPException(status_code=400, detail="Format is not available")
    if cfg.get("custom") or cfg.get("require_draft"):
        raise HTTPException(
            status_code=400,
            detail="Custom prompt battles launch from an approved draft",
        )
    target_bundle = None
    if target_id:
        from agent_arena.target_library import (
            compile_target_to_battle_config,
            get_target_library,
        )

        target_bundle = get_target_library().get_target(target_id)
        if target_bundle is None:
            raise HTTPException(
                status_code=404, detail=f"Target '{target_id}' not found"
            )
        if target_version and target_version != target_bundle.version:
            raise HTTPException(
                status_code=400,
                detail=f"Target version mismatch: requested '{target_version}', current is '{target_bundle.version}'",
            )
        cfg = compile_target_to_battle_config(target_bundle, arena_size=len(model_ids))

    playable = [r for r in cfg.get("roles", []) if r != "judge"]
    if len(model_ids) != len(playable):
        raise HTTPException(
            status_code=400,
            detail=f"model_ids must match non-judge roles ({len(playable)} required, got {len(model_ids)})",
        )
    if arena_size != len(model_ids):
        raise HTTPException(
            status_code=400, detail="arena_size must equal len(model_ids)"
        )
    for mid in model_ids:
        if is_host_model(mid):
            continue
        doc = provider_get(user_id, mid)
        if doc is None:
            raise HTTPException(status_code=400, detail=f"Unknown model_id: {mid}")
        if doc.get("user_id") != user_id:
            raise HTTPException(status_code=400, detail=f"model_id not owned: {mid}")
    if judge_provider_id and not is_host_model(judge_provider_id):
        doc = provider_get(user_id, judge_provider_id)
        if doc is None:
            raise HTTPException(
                status_code=400, detail=f"Unknown model_id: {judge_provider_id}"
            )
    active = battle_count_active(user_id)
    if active >= 5:
        raise HTTPException(
            status_code=429,
            detail=f"Concurrency limit reached: 5 active battles",
        )

    payload = {
        "user_id": user_id,
        "format_id": format_id,
        "model_ids": model_ids,
        "arena_size": arena_size,
        "status": "queued",
        "timeout_seconds": timeout_seconds,
        "round_visibility": round_visibility,
        "saved": save,
    }
    if target_bundle is not None:
        payload["target_id"] = target_bundle.id
        payload["target_version"] = target_bundle.version
        payload["spec_hash"] = target_bundle.manifest_hash
        payload["target_manifest_hash"] = target_bundle.manifest_hash
        payload["battle_config"] = cfg
        payload["custom_title"] = f"Target: {target_bundle.name}"
    if judge_provider_id:
        payload["judge_provider_id"] = judge_provider_id
    if difficulty:
        payload["difficulty"] = difficulty

    ranked = _authoritative_ranked_for_create(payload, cfg)
    payload["ranked"] = ranked

    if using_postgres():
        with session_scope() as session:
            battle = repositories.battles.battle_create(
                session,
                user_id=user_id,
                format_id=format_id,
                arena_size=arena_size,
                timeout_seconds=timeout_seconds,
                round_visibility=round_visibility,
                model_ids=model_ids,
                roles=[r if r != "judge" else None for r in cfg.get("roles", [])],
                saved=save,
                judge_provider_id=judge_provider_id,
                difficulty=difficulty,
                battle_config=payload.get("battle_config"),
                spec_hash=payload.get("spec_hash"),
                custom_title=payload.get("custom_title"),
                ranked=ranked,
                target_id=payload.get("target_id"),
                target_version=payload.get("target_version"),
                target_manifest_hash=payload.get("target_manifest_hash"),
            )
            battle_id = battle.id
        _dual_write("battle dual write", lambda: _aw_battle_create(payload))
        return {"id": battle_id, "status": "queued"}
    return _aw_battle_create(payload)


def _aw_battle_create(payload: dict) -> dict:
    import json as _json
    from agent_arena.schema import COLLECTIONS

    databases, database_id = _aw()
    allowed_keys = {attr[0] for attr in COLLECTIONS.get("battles", [])}
    aw_payload = {k: v for k, v in payload.items() if k in allowed_keys}
    if aw_payload.get("ranked") is not True and aw_payload.get("ranked") is not False:
        cfg = aw_payload.get("battle_config")
        if isinstance(cfg, str) and cfg.strip():
            try:
                cfg = _json.loads(cfg)
            except (_json.JSONDecodeError, TypeError):
                cfg = {}
        aw_payload["ranked"] = _authoritative_ranked_for_create(
            payload, cfg if isinstance(cfg, dict) else {}
        )
    if isinstance(aw_payload.get("battle_config"), dict):
        aw_payload["battle_config"] = _json.dumps(aw_payload["battle_config"])
    # The new tablesdb engine accepts real arrays for string attributes that
    # hold JSON (it auto-stringifies on the server); a pre-serialized JSON
    # string is rejected with "must be an array".
    if isinstance(aw_payload.get("model_ids"), list):
        aw_payload["model_ids"] = list(aw_payload["model_ids"])
    if isinstance(aw_payload.get("preview_urls"), dict):
        aw_payload["preview_urls"] = _json.dumps(aw_payload["preview_urls"])
    doc = databases.create_document(database_id, "battles", "unique()", aw_payload)
    return {"id": doc.id, "status": "queued"}


def _aw_battle_dict(doc) -> dict:
    data = dict(doc.data)
    data["id"] = doc.id
    for key in ("model_ids", "battle_config", "preview_urls"):
        value = data.get(key)
        if isinstance(value, str):
            try:
                data[key] = json.loads(value)
            except (json.JSONDecodeError, TypeError):
                pass
    if not data.get("target_id") and isinstance(data.get("battle_config"), dict):
        data["target_id"] = data["battle_config"].get("target_id")
        data["target_version"] = data["battle_config"].get("target_version")
        data["target_manifest_hash"] = data["battle_config"].get("manifest_hash")
    return data


def _battle_read_through(record: dict) -> None:
    try:
        model_ids = record.get("model_ids") or []

        def _ts(value):
            if value is None:
                return None
            if isinstance(value, datetime):
                return value
            try:
                return datetime.fromtimestamp(float(value), tz=timezone.utc)
            except (TypeError, ValueError):
                return None

        with session_scope() as session:
            if session.get(Battle, record["id"]) is not None:
                return
            repositories.battles.battle_create(
                session,
                id=record["id"],
                user_id=record.get("user_id", ""),
                format_id=record.get("format_id", ""),
                arena_size=int(record.get("arena_size") or len(model_ids)),
                timeout_seconds=int(record.get("timeout_seconds") or 600),
                round_visibility=record.get("round_visibility", "isolated"),
                model_ids=[str(m) for m in model_ids],
                saved=bool(record.get("saved")),
                status=record.get("status", "queued"),
                sandbox_id=record.get("sandbox_id"),
                judge_provider_id=record.get("judge_provider_id"),
                preview_urls=record.get("preview_urls"),
                failure_reason=record.get("failure_reason"),
                difficulty=record.get("difficulty"),
                started_at=_ts(record.get("started_at")),
                completed_at=_ts(record.get("completed_at")),
                draft_id=record.get("draft_id"),
                battle_config=record.get("battle_config"),
                spec_hash=record.get("spec_hash"),
                custom_title=record.get("custom_title"),
                ranked=record.get("ranked"),
                target_id=record.get("target_id"),
                target_version=record.get("target_version"),
                target_manifest_hash=record.get("target_manifest_hash")
                or (record.get("spec_hash") if record.get("target_id") else None),
            )
    except Exception as exc:
        _sanitized_log("battle read-through", exc)


def battle_get(user_id: str, battle_id: str) -> dict | None:
    if using_postgres():
        with session_scope() as session:
            battle = repositories.battles.battle_get(session, battle_id)
            if battle is not None:
                return _pg_battle_dict(battle, _battle_model_ids_pg(session, battle_id))
        if not appwrite_read_fallback():
            return None
    try:
        from appwrite.exception import AppwriteException

        databases, database_id = _aw()
        doc = databases.get_document(database_id, "battles", battle_id)
    except RuntimeError as exc:
        if "External Appwrite" in str(exc):
            return None
        raise
    except AppwriteException as exc:
        if not using_postgres() or _is_not_found(exc):
            return None
        raise
    record = _aw_battle_dict(doc)
    _battle_read_through(record)
    return record


def battle_list(user_id: str, *, saved: bool | None = None) -> list[dict]:
    if using_postgres():
        with session_scope() as session:
            rows = repositories.battles.battle_list(
                session, user_id=user_id, saved=saved
            )
            return [
                _pg_battle_dict(b, _battle_model_ids_pg(session, b.id)) for b in rows
            ]
    from appwrite.query import Query

    databases, database_id = _aw()
    queries = [Query.equal("user_id", user_id), Query.limit(100)]
    if saved is not None:
        queries.append(Query.equal("saved", saved))
    res = databases.list_documents(database_id, "battles", queries=queries)
    return [_aw_battle_dict(d) for d in res.documents]


def battle_count_active(user_id: str) -> int:
    if using_postgres():
        with session_scope() as session:
            rows = repositories.battles.battle_list(
                session, user_id=user_id, status=None
            )
            return sum(1 for b in rows if b.status in ("queued", "running"))
    from appwrite.query import Query

    databases, database_id = _aw()
    res = databases.list_documents(
        database_id,
        "battles",
        queries=[
            Query.equal("user_id", user_id),
            Query.equal("status", ["queued", "running"]),
            Query.limit(100),
        ],
    )
    return len(res.documents)


def battle_update(battle_id: str, fields: dict) -> None:
    """Internal field update (status, failure_reason, timestamps, previews...)."""
    if using_postgres():
        with session_scope() as session:
            repositories.battles.battle_update(session, battle_id, **fields)
        _dual_write(
            "battle update dual write",
            lambda: _aw_battle_update(battle_id, fields),
        )
        return
    _aw_battle_update(battle_id, fields)


def _aw_battle_update(battle_id: str, fields: dict) -> None:
    databases, database_id = _aw()
    payload = dict(fields)
    # completed_at is a Postgres-only column; Appwrite derives duration from
    # updatedAt, so drop it before writing to the Appwrite schema.
    payload.pop("completed_at", None)
    for key in ("preview_urls",):
        if isinstance(payload.get(key), dict):
            payload[key] = json.dumps(payload[key])
    databases.update_document(database_id, "battles", battle_id, payload)


def battle_save(user_id: str, battle_id: str) -> dict:
    battle = battle_get(user_id, battle_id)
    if battle is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Battle not found")
    if battle.get("user_id") != user_id:
        from fastapi import HTTPException

        raise HTTPException(status_code=403, detail="Forbidden")
    battle_update(battle_id, {"saved": True})
    return {"id": battle_id, "saved": True}


def battle_cancel(user_id: str, battle_id: str) -> dict:
    battle = battle_get(user_id, battle_id)
    if battle is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Battle not found")
    if battle.get("user_id") != user_id:
        from fastapi import HTTPException

        raise HTTPException(status_code=403, detail="Forbidden")
    battle_update(battle_id, {"status": "cancelled"})
    return {"id": battle_id, "status": "cancelled"}


# ---------------------------------------------------------------------------
# Events / rounds / scores
# ---------------------------------------------------------------------------


def events_append(
    battle_id: str,
    event_type: str,
    payload: dict,
    *,
    event_id: str = "",
    created_at: float | None = None,
) -> None:
    if using_postgres():
        with session_scope() as session:
            repositories.events.event_append(
                session,
                battle_id,
                event_type,
                payload,
                event_id=event_id or "",
            )
        return
    databases, database_id = _aw()
    databases.create_document(
        database_id,
        "battle_events",
        "unique()",
        {
            "battle_id": battle_id,
            "event_id": event_id or "",
            "payload": json.dumps({"type": event_type, "data": payload}),
            "created_at": created_at or time.time(),
        },
    )


def events_load(battle_id: str) -> list[dict]:
    """Durable events for SSE replay: [{type, data, event_id, created_at}]."""
    if using_postgres():
        with session_scope() as session:
            rows = repositories.events.event_list(session, battle_id)
            out = []
            for row in rows:
                created = (
                    row.created_at.timestamp() if row.created_at is not None else 0.0
                )
                out.append(
                    {
                        "type": row.event_type,
                        "data": row.payload or {},
                        "event_id": row.event_id,
                        "created_at": created,
                    }
                )
            out.sort(key=lambda e: (e["created_at"], e["event_id"]))
            return out
    from agent_arena.event_bus import load_durable

    events = load_durable(battle_id)
    if events and using_postgres() and appwrite_read_fallback():
        for event in events:
            try:
                with session_scope() as session:
                    repositories.events.event_append(
                        session,
                        battle_id,
                        event.get("type", "unknown"),
                        event.get("data", {}),
                        event_id=event.get("event_id", ""),
                    )
            except Exception as exc:
                _sanitized_log("event read-through", exc)
    return events


def round_create(
    battle_id: str,
    phase: str,
    model_id: str,
    artifact: str,
    *,
    tool_trace: dict | None = None,
    verification_log: str | None = None,
    meta: dict | None = None,
) -> None:
    if using_postgres():
        with session_scope() as session:
            session.add(
                Round(
                    battle_id=battle_id,
                    phase=phase,
                    model_id=model_id,
                    artifact=artifact,
                    tool_trace=tool_trace,
                    verification_log=verification_log,
                    meta=meta,
                )
            )
        return
    databases, database_id = _aw()
    payload: dict = {
        "battle_id": battle_id,
        "phase": phase,
        "model_id": model_id,
        "artifact": artifact,
    }
    databases.create_document(database_id, "rounds", "unique()", payload)


def rounds_list(battle_id: str) -> list[dict]:
    if using_postgres():
        with session_scope() as session:
            rows = session.scalars(
                select(Round)
                .where(Round.battle_id == battle_id)
                .order_by(Round.created_at)
            ).all()
            return [
                {
                    "battle_id": r.battle_id,
                    "phase": r.phase,
                    "model_id": r.model_id,
                    "artifact": r.artifact,
                    "tool_trace": r.tool_trace,
                    "verification_log": r.verification_log,
                    "meta": r.meta,
                }
                for r in rows
            ]
    databases, database_id = _aw()
    from appwrite.query import Query

    res = databases.list_documents(
        database_id,
        "rounds",
        queries=[Query.equal("battle_id", battle_id), Query.limit(500)],
    )
    return [dict(d.data) for d in res.documents]


def score_upsert(
    battle_id: str,
    model_id: str,
    score: float,
    judge_model: str | None = None,
    justification: str | None = None,
) -> None:
    if using_postgres():
        with session_scope() as session:
            repositories.scores.score_insert(
                session,
                battle_id=battle_id,
                model_id=model_id,
                score=score,
                judge_model=judge_model,
                justification=justification,
            )
        return
    databases, database_id = _aw()
    databases.create_document(
        database_id,
        "scores",
        "unique()",
        {
            "battle_id": battle_id,
            "model_id": model_id,
            "score": score,
            "judge_model": judge_model or "",
            "justification": justification or "",
        },
    )


def scores_list(battle_id: str) -> list[dict]:
    if using_postgres():
        with session_scope() as session:
            rows = repositories.scores.score_list(session, battle_id)
            return [
                {
                    "battle_id": r.battle_id,
                    "model_id": r.model_id,
                    "score": r.score,
                    "judge_model": r.judge_model,
                    "justification": r.justification,
                }
                for r in rows
            ]
    databases, database_id = _aw()
    from appwrite.query import Query

    res = databases.list_documents(
        database_id,
        "scores",
        queries=[Query.equal("battle_id", battle_id), Query.limit(100)],
    )
    return [dict(d.data) for d in res.documents]


def scores_exist(battle_id: str) -> bool:
    if using_postgres():
        with session_scope() as session:
            return bool(repositories.scores.score_list(session, battle_id))
    from appwrite.query import Query

    databases, database_id = _aw()
    res = databases.list_documents(
        database_id,
        "scores",
        queries=[Query.equal("battle_id", battle_id), Query.limit(1)],
    )
    return bool(res.documents)


def battle_result_upsert(
    battle_id: str,
    model_id: str,
    *,
    phase: str = "main",
    role: str = "fighter",
    status: str = "completed",
    passed: bool = False,
    score: float = 0.0,
    verification_status: str = "unverified",
    termination_reason: str | None = None,
    artifact_refs: list[str] | None = None,
    metrics: dict | None = None,
    result_version: int = 1,
) -> dict:
    if using_postgres():
        with session_scope() as session:
            row = repositories.results.result_upsert(
                session,
                battle_id=battle_id,
                phase=phase,
                role=role,
                model_id=model_id,
                status=status,
                passed=passed,
                score=score,
                verification_status=verification_status,
                termination_reason=termination_reason,
                artifact_refs=artifact_refs,
                metrics=metrics,
                result_version=result_version,
            )
            return {
                "id": row.id,
                "battle_id": row.battle_id,
                "phase": row.phase,
                "role": row.role,
                "model_id": row.model_id,
                "status": row.status,
                "passed": row.passed,
                "score": row.score,
                "verification_status": row.verification_status,
                "termination_reason": row.termination_reason,
                "artifact_refs": row.artifact_refs,
                "metrics": row.metrics,
                "result_version": row.result_version,
                "finalized_at": row.finalized_at.isoformat() if row.finalized_at else None,
            }
    return {
        "battle_id": battle_id,
        "phase": phase,
        "role": role,
        "model_id": model_id,
        "status": status,
        "passed": passed,
        "score": score,
        "verification_status": verification_status,
        "termination_reason": termination_reason,
        "artifact_refs": artifact_refs or [],
        "metrics": metrics or {},
        "result_version": result_version,
    }


def battle_results_list(battle_id: str) -> list[dict]:
    if using_postgres():
        with session_scope() as session:
            rows = repositories.results.results_list_by_battle(session, battle_id)
            return [
                {
                    "id": r.id,
                    "battle_id": r.battle_id,
                    "phase": r.phase,
                    "role": r.role,
                    "model_id": r.model_id,
                    "status": r.status,
                    "passed": r.passed,
                    "score": r.score,
                    "verification_status": r.verification_status,
                    "termination_reason": r.termination_reason,
                    "artifact_refs": r.artifact_refs,
                    "metrics": r.metrics,
                    "result_version": r.result_version,
                    "finalized_at": r.finalized_at.isoformat() if r.finalized_at else None,
                }
                for r in rows
            ]
    return []


# ---------------------------------------------------------------------------
# Stats (SQL aggregation in Postgres)
# ---------------------------------------------------------------------------



def stats_snapshot() -> dict:
    if using_postgres():
        with session_scope() as session:
            counts = session.execute(
                text(
                    "SELECT count(*) FILTER (WHERE status IN ('queued', 'running')) AS running, "
                    "count(*) AS total FROM battles"
                )
            ).one()
            median_row = session.execute(
                text(
                    "SELECT percentile_cont(0.5) WITHIN GROUP "
                    "(ORDER BY EXTRACT(EPOCH FROM (completed_at - created_at))) AS med "
                    "FROM battles WHERE status = 'completed' "
                    "AND completed_at IS NOT NULL AND created_at IS NOT NULL"
                )
            ).one()
            top_rows = session.execute(
                text(
                    "SELECT model_id, elo, games_played FROM leaderboard "
                    "WHERE scope = 'overall' ORDER BY elo DESC LIMIT 5"
                )
            ).all()
        median_s = float(median_row.med) if median_row.med is not None else None
        return {
            "battles_running": int(counts.running),
            "battles_total": int(counts.total),
            "median_duration_s": round(median_s, 1) if median_s is not None else None,
            "top_models": [
                {
                    "model_id": r.model_id,
                    "elo": round(float(r.elo), 1),
                    "games_played": int(r.games_played),
                }
                for r in top_rows
            ],
        }
    # Appwrite path: existing logic lives in the router; delegate here.
    from agent_arena import stats

    return stats.appwrite_snapshot()


# ---------------------------------------------------------------------------
# Memories / skills
# ---------------------------------------------------------------------------


def memory_create(
    user_id: str,
    insight: str,
    *,
    tokens: list[str] | None = None,
    battle_id: str | None = None,
    model_id: str | None = None,
    format: str | None = None,
    chosen_skills: list[str] | None = None,
    theory: str | None = None,
    outcome: str | None = None,
    target_id: str | None = None,
    role: str | None = None,
    visibility_class: str | None = None,
    authoritative_status: str | None = None,
    context_mode: str | None = None,
    source_result_id: str | None = None,
) -> dict:
    if using_postgres():
        embedding = None
        try:
            from agent_arena.mem0_pgvector import get_embedding

            embedding = get_embedding(f"{insight} {theory or ''}".strip())
        except Exception:
            pass
        with session_scope() as session:
            row = repositories.memories.memory_create(
                session,
                user_id=user_id,
                insight=insight,
                tokens=tokens,
                battle_id=battle_id,
                model_id=model_id,
                format=format,
                chosen_skills=chosen_skills,
                theory=theory,
                outcome=outcome,
                target_id=target_id,
                role=role,
                visibility_class=visibility_class,
                authoritative_status=authoritative_status,
                context_mode=context_mode,
                source_result_id=source_result_id,
                embedding=embedding,
            )
            return {"id": row.id}
    databases, database_id = _aw()
    payload = {
        "user_id": user_id,
        "insight": insight,
        "tokens": json.dumps(tokens or []),
        "battle_id": battle_id or "",
        "model_id": model_id or "",
        "format": format or "",
        "chosen_skills": json.dumps(chosen_skills or []),
        "theory": theory or "",
        "outcome": outcome or "",
    }
    doc = databases.create_document(database_id, "memories", "unique()", payload)
    return {"id": doc.id}


def memory_list(user_id: str, *, limit: int = 100) -> list[dict]:
    if using_postgres():
        with session_scope() as session:
            rows = repositories.memories.memory_list(session, user_id, limit=limit)
            return [
                {
                    "id": r.id,
                    "user_id": r.user_id,
                    "insight": r.insight,
                    "tokens": r.tokens or [],
                    "battle_id": r.battle_id,
                    "model_id": r.model_id,
                    "format": r.format,
                    "chosen_skills": r.chosen_skills or [],
                    "theory": r.theory,
                    "outcome": r.outcome,
                    "created_at": r.created_at,
                }
                for r in rows
            ]
    databases, database_id = _aw()
    from appwrite.query import Query

    res = databases.list_documents(
        database_id,
        "memories",
        queries=[Query.equal("user_id", user_id), Query.limit(limit)],
    )
    out = []
    for d in res.documents:
        data = dict(d.data)
        data["id"] = d.id
        for key in ("tokens", "chosen_skills"):
            value = data.get(key)
            if isinstance(value, str):
                try:
                    data[key] = json.loads(value)
                except (json.JSONDecodeError, TypeError):
                    data[key] = []
        out.append(data)
    return out


def skill_upsert(
    skill: str,
    *,
    elo: float | None = None,
    wins: int | None = None,
    losses: int | None = None,
    draws: int | None = None,
    uses: int | None = None,
    success_rate: float | None = None,
    tier: str | None = None,
    tags: list[str] | None = None,
    last_used=None,
) -> None:
    if using_postgres():
        with session_scope() as session:
            repositories.skills.skill_upsert(
                session,
                skill,
                elo=elo,
                wins=wins,
                losses=losses,
                draws=draws,
                uses=uses,
                success_rate=success_rate,
                tier=tier,
                tags=tags,
                last_used=last_used,
            )
        return
    from agent_arena.skills_registry import _upsert as aw_skill_upsert

    databases, database_id = _aw()
    payload = {
        "elo": elo,
        "wins": wins,
        "losses": losses,
        "draws": draws,
        "uses": uses,
        "success_rate": success_rate,
        "tier": tier,
        "tags": tags,
        "last_used": last_used,
    }
    aw_skill_upsert(
        databases,
        database_id,
        skill,
        {k: v for k, v in payload.items() if v is not None},
    )


def skill_get(skill: str) -> dict | None:
    if using_postgres():
        with session_scope() as session:
            row = repositories.skills.skill_get(session, skill)
            if row is None:
                return None
            return {
                "skill": row.skill,
                "elo": row.elo,
                "wins": row.wins,
                "losses": row.losses,
                "draws": row.draws,
                "uses": row.uses,
                "success_rate": row.success_rate,
                "tier": row.tier,
                "tags": row.tags or [],
                "last_used": row.last_used,
            }
    from agent_arena.skills_registry import _find as aw_skill_find

    databases, database_id = _aw()
    entry = aw_skill_find(databases, database_id, skill)
    return dict(entry.data) if entry is not None else None


# ---------------------------------------------------------------------------
# Draft-launched battles / leaderboard
# ---------------------------------------------------------------------------


def battle_create_raw(user_id: str, payload: dict) -> dict:
    """Create a battle from an already-validated raw payload (draft launch path).

    Used by /battle-drafts launch: the caller has compiled the frozen config,
    validated model ownership and the concurrency cap, and owns every field.
    """
    from fastapi import HTTPException

    cfg = payload.get("battle_config") or {}
    if isinstance(cfg, str) and cfg.strip():
        try:
            cfg = json.loads(cfg)
        except (json.JSONDecodeError, TypeError):
            cfg = {}
    if not isinstance(cfg, dict):
        cfg = {}
    ranked = _authoritative_ranked_for_create(payload, cfg)
    payload["ranked"] = ranked

    if using_postgres():
        with session_scope() as session:
            battle = repositories.battles.battle_create(
                session,
                user_id=user_id,
                format_id=payload["format_id"],
                arena_size=int(
                    payload.get("arena_size") or len(payload.get("model_ids") or [])
                ),
                timeout_seconds=int(payload.get("timeout_seconds") or 600),
                round_visibility=payload.get("round_visibility", "isolated"),
                model_ids=list(payload.get("model_ids") or []),
                saved=bool(payload.get("saved")),
                status="queued",
                judge_provider_id=payload.get("judge_provider_id"),
                difficulty=payload.get("difficulty"),
                draft_id=payload.get("draft_id"),
                battle_config=payload.get("battle_config"),
                spec_hash=payload.get("spec_hash"),
                custom_title=payload.get("custom_title"),
                ranked=ranked,
            )
            battle_id = battle.id
        _dual_write("battle raw dual write", lambda: _aw_battle_create(payload))
        return {"id": battle_id, "status": "queued"}
    return _aw_battle_create(payload)


def leaderboard_apply_result(
    format_id: str, model_ids: list[str], scores: dict
) -> None:
    """Apply one finished battle to Elo rankings (format scope + overall)."""
    scopes = [format_id]
    if format_id != "overall":
        scopes.append("overall")
    if using_postgres():
        from agent_arena import elo as elo_mod

        with session_scope() as session:
            for scope in scopes:
                for i in range(len(model_ids)):
                    for j in range(i + 1, len(model_ids)):
                        a, b = model_ids[i], model_ids[j]
                        sa = float(scores.get(a, 0))
                        sb = float(scores.get(b, 0))
                        row_a = repositories.leaderboard.leaderboard_get(
                            session, a, scope
                        )
                        row_b = repositories.leaderboard.leaderboard_get(
                            session, b, scope
                        )
                        ra = row_a.elo if row_a else elo_mod.INITIAL_RATING
                        rb = row_b.elo if row_b else elo_mod.INITIAL_RATING
                        outcome_a = 1.0 if sa > sb else (0.0 if sa < sb else 0.5)
                        new_a, new_b = elo_mod.update_ratings(ra, rb, outcome_a)
                        ga = (row_a.games_played if row_a else 0) + 1
                        gb = (row_b.games_played if row_b else 0) + 1
                        repositories.leaderboard.leaderboard_upsert(
                            session, a, scope, elo=new_a, games_played=ga
                        )
                        repositories.leaderboard.leaderboard_upsert(
                            session, b, scope, elo=new_b, games_played=gb
                        )
        return
    databases, database_id = _aw()
    from agent_arena import leaderboard as lb_mod

    lb_mod.apply_result(databases, database_id, format_id, model_ids, scores)


def leaderboard_rankings(format_id: str = "overall") -> list[dict]:
    if using_postgres():
        with session_scope() as session:
            rows = repositories.leaderboard.leaderboard_list(session, format_id)
            return [
                {
                    "model_id": r.model_id,
                    "elo": r.elo,
                    "games_played": r.games_played,
                    "rank": i + 1,
                }
                for i, r in enumerate(rows)
            ]
    databases, database_id = _aw()
    from agent_arena import leaderboard as lb_mod

    return lb_mod.get_rankings(databases, database_id, format_id)
