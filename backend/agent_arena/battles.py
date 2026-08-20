import json
import time

from appwrite.exception import AppwriteException
from appwrite.query import Query
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sse_starlette.sse import EventSourceResponse

from . import db, event_bus, mock_runner, sandbox_launcher
from .auth import get_current_user, require_owner
from .providers import is_host_model
from .schemas import BattleCreate
from .seed_formats import is_playable_format

router = APIRouter(prefix="/battles", tags=["battles"])

MAX_ACTIVE_BATTLES = 5


def _playable_roles(format_config: dict) -> list[str]:
    return [r for r in format_config.get("roles", []) if r != "judge"]


def _validate_model_ids(
    databases, database_id: str, user_id: str, model_ids: list[str]
) -> None:
    for mid in model_ids:
        if is_host_model(mid):
            continue
        try:
            doc = databases.get_document(database_id, "providers", mid)
        except AppwriteException as exc:
            raise HTTPException(
                status_code=400, detail=f"Unknown model_id: {mid}"
            ) from exc
        if doc.data.get("user_id") != user_id:
            raise HTTPException(status_code=400, detail=f"model_id not owned: {mid}")


def active_battle_count(databases, database_id: str, user_id: str) -> int:
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


def _get_owned(databases, database_id: str, battle_id: str, user_id: str):
    try:
        battle = databases.get_document(database_id, "battles", battle_id)
    except AppwriteException as exc:
        raise HTTPException(status_code=404, detail="Battle not found") from exc
    require_owner(battle.data.get("user_id"), user_id, resource="battle")
    return battle


@router.post("", status_code=201)
def create_battle(
    body: BattleCreate,
    background: BackgroundTasks,
    user_id: str = Depends(get_current_user),
):
    databases = db.get_databases()
    database_id = db.get_database_id()
    try:
        format_doc = databases.get_document(database_id, "formats", body.format_id)
    except AppwriteException as exc:
        raise HTTPException(status_code=404, detail="Unknown format") from exc
    cfg = json.loads(format_doc.data["config"])
    if not is_playable_format(cfg):
        raise HTTPException(status_code=400, detail="Format is not available")
    if cfg.get("custom") or cfg.get("require_draft"):
        raise HTTPException(
            status_code=400,
            detail="Custom prompt battles launch from an approved draft",
        )
    playable = _playable_roles(cfg)
    if len(body.model_ids) != len(playable):
        raise HTTPException(
            status_code=400,
            detail=f"model_ids must match non-judge roles ({len(playable)} required, got {len(body.model_ids)})",
        )
    if body.arena_size != len(body.model_ids):
        raise HTTPException(
            status_code=400, detail="arena_size must equal len(model_ids)"
        )
    _validate_model_ids(databases, database_id, user_id, body.model_ids)
    if body.judge_provider_id and not is_host_model(body.judge_provider_id):
        _validate_model_ids(databases, database_id, user_id, [body.judge_provider_id])
    if active_battle_count(databases, database_id, user_id) >= MAX_ACTIVE_BATTLES:
        raise HTTPException(
            status_code=429,
            detail=f"Concurrency limit reached: {MAX_ACTIVE_BATTLES} active battles",
        )
    payload = {
        "user_id": user_id,
        "format_id": body.format_id,
        "model_ids": body.model_ids,
        "arena_size": body.arena_size,
        "status": "queued",
        "timeout_seconds": body.timeout_seconds,
        "round_visibility": body.round_visibility,
        "saved": body.save,
    }
    if body.judge_provider_id:
        payload["judge_provider_id"] = body.judge_provider_id
    if body.difficulty:
        payload["difficulty"] = body.difficulty
    battle = databases.create_document(database_id, "battles", "unique()", payload)
    battle_id = battle.id
    # Prefer real sandbox runner; mock_runner remains for ARENA_USE_MOCK=1
    import os

    if os.environ.get("ARENA_USE_MOCK") == "1":
        background.add_task(mock_runner.run_battle, battle_id)
    else:
        background.add_task(sandbox_launcher.start_battle, battle_id)
    return {"id": battle_id, "status": "queued"}


@router.get("")
def list_battles(saved: bool = False, user_id: str = Depends(get_current_user)):
    databases = db.get_databases()
    database_id = db.get_database_id()
    queries = [Query.equal("user_id", user_id), Query.limit(100)]
    if saved:
        queries.append(Query.equal("saved", True))
    res = databases.list_documents(database_id, "battles", queries=queries)
    return [{**d.data, "id": d.id} for d in res.documents]


@router.get("/{battle_id}")
def get_battle(battle_id: str, user_id: str = Depends(get_current_user)):
    databases = db.get_databases()
    battle = _get_owned(databases, db.get_database_id(), battle_id, user_id)
    data = {k: v for k, v in battle.data.items() if k not in ("encrypted_key",)}
    raw_previews = data.get("preview_urls")
    if isinstance(raw_previews, str) and raw_previews.strip():
        try:
            data["preview_urls"] = json.loads(raw_previews)
        except Exception:
            data["preview_urls"] = {}
    elif not isinstance(raw_previews, dict):
        data["preview_urls"] = {}
    raw_cfg = data.get("battle_config")
    if isinstance(raw_cfg, str) and raw_cfg.strip():
        try:
            data["battle_config"] = json.loads(raw_cfg)
        except Exception:
            data["battle_config"] = {}
    return {**data, "id": battle.id}


@router.get("/{battle_id}/artifacts")
def get_artifacts(battle_id: str, user_id: str = Depends(get_current_user)):
    databases = db.get_databases()
    database_id = db.get_database_id()
    battle = _get_owned(databases, database_id, battle_id, user_id)
    if not battle.data.get("saved"):
        raise HTTPException(
            status_code=404, detail="Battle was not saved; artifacts are gone"
        )
    res = databases.list_documents(
        database_id,
        "rounds",
        queries=[Query.equal("battle_id", battle_id), Query.limit(100)],
    )
    return [
        {
            "phase": d.data["phase"],
            "model_id": d.data["model_id"],
            "artifact": d.data["artifact"],
        }
        for d in res.documents
    ]


@router.get("/{battle_id}/stream")
def stream_battle(battle_id: str, user_id: str = Depends(get_current_user)):
    databases = db.get_databases()
    database_id = db.get_database_id()
    _get_owned(databases, database_id, battle_id, user_id)

    def event_generator():
        seen_ids: set[str] = set()
        # Durable snapshot first (survives scale-to-zero / other replicas)
        for ev in event_bus.load_durable(battle_id):
            eid = ev.get("event_id")
            if eid and eid in seen_ids:
                continue
            if eid:
                seen_ids.add(eid)
            yield {"event": ev["type"], "data": json.dumps(ev.get("data", {}))}
        while True:
            events = event_bus.subscribe(battle_id)
            # sort by created_at then event_id for stable multi-writer merge
            ordered = sorted(
                events,
                key=lambda e: (
                    e.get("created_at", e.get("ts", 0)),
                    e.get("event_id", ""),
                ),
            )
            for ev in ordered:
                eid = ev.get("event_id")
                if eid and eid in seen_ids:
                    continue
                if eid:
                    seen_ids.add(eid)
                yield {"event": ev["type"], "data": json.dumps(ev.get("data", {}))}
            battle = databases.get_document(database_id, "battles", battle_id)
            if battle.data["status"] in ("completed", "failed", "cancelled"):
                yield {
                    "event": "done",
                    "data": json.dumps({"status": battle.data["status"]}),
                }
                return
            yield {"event": "heartbeat", "data": "{}"}
            time.sleep(1)

    return EventSourceResponse(event_generator())


@router.post("/{battle_id}/cancel")
def cancel_battle(battle_id: str, user_id: str = Depends(get_current_user)):
    databases = db.get_databases()
    database_id = db.get_database_id()
    battle = _get_owned(databases, database_id, battle_id, user_id)
    databases.update_document(
        database_id, "battles", battle_id, {"status": "cancelled"}
    )
    sandbox_id = battle.data.get("sandbox_id")
    if sandbox_id:
        sandbox_launcher.stop_sandbox(sandbox_id)
    event_bus.publish(
        battle_id, {"type": "battle_status", "data": {"status": "cancelled"}}
    )
    return {"id": battle_id, "status": "cancelled"}


@router.post("/{battle_id}/save")
def save_battle(battle_id: str, user_id: str = Depends(get_current_user)):
    databases = db.get_databases()
    database_id = db.get_database_id()
    _get_owned(databases, database_id, battle_id, user_id)
    databases.update_document(database_id, "battles", battle_id, {"saved": True})
    mock_runner.persist_scores(battle_id)
    return {"id": battle_id, "saved": True}
