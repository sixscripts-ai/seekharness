import json
import time

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sse_starlette.sse import EventSourceResponse

from . import event_bus, mock_runner, sandbox_launcher
from .auth import get_current_user, require_owner
from .providers import is_host_model
from .schemas import BattleCreate

router = APIRouter(prefix="/battles", tags=["battles"])

MAX_ACTIVE_BATTLES = 5


def _playable_roles(format_config: dict) -> list[str]:
    return [r for r in format_config.get("roles", []) if r != "judge"]


def _validate_model_ids(
    databases, database_id: str, user_id: str, model_ids: list[str]
) -> None:
    """Validate model ownership (Appwrite-era signature kept for importers)."""
    from .persistence import service

    for mid in model_ids:
        if is_host_model(mid):
            continue
        doc = service.provider_get(user_id, mid)
        if doc is None:
            raise HTTPException(status_code=400, detail=f"Unknown model_id: {mid}")
        if doc.get("user_id") != user_id:
            raise HTTPException(status_code=400, detail=f"model_id not owned: {mid}")


def active_battle_count(databases, database_id: str, user_id: str) -> int:
    from .persistence import service

    return service.battle_count_active(user_id)


def _get_owned(databases, database_id: str, battle_id: str, user_id: str):
    """Legacy Appwrite helper kept for external importers."""
    try:
        battle = databases.get_document(database_id, "battles", battle_id)
    except Exception as exc:
        raise HTTPException(status_code=404, detail="Battle not found") from exc
    require_owner(battle.data.get("user_id"), user_id, resource="battle")
    return battle


def _require_owned_battle(user_id: str, battle_id: str) -> dict:
    from .persistence import service

    battle = service.battle_get(user_id, battle_id)
    if battle is None:
        raise HTTPException(status_code=404, detail="Battle not found")
    require_owner(battle.get("user_id"), user_id, resource="battle")
    return battle


@router.post("", status_code=201)
def create_battle(
    body: BattleCreate,
    background: BackgroundTasks,
    user_id: str = Depends(get_current_user),
):
    import os

    from .fighter_isolation import (
        FighterIsolationError,
        assert_isolated_fighter_execution,
    )
    from .persistence import service

    use_mock = os.environ.get("ARENA_USE_MOCK") == "1"
    if use_mock:
        # Refuse before persisting: a target battle must not be queued onto a
        # same-host runner while evaluator material is mounted here.
        try:
            assert_isolated_fighter_execution(body.target_id or "", mode="mock")
        except FighterIsolationError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    battle = service.battle_create(
        user_id,
        format_id=body.format_id,
        model_ids=body.model_ids,
        arena_size=body.arena_size,
        timeout_seconds=body.timeout_seconds,
        round_visibility=body.round_visibility,
        save=body.save,
        judge_provider_id=body.judge_provider_id,
        difficulty=body.difficulty,
        target_id=body.target_id,
        target_version=body.target_version,
    )
    battle_id = battle["id"]
    # Prefer real sandbox runner; mock_runner remains for ARENA_USE_MOCK=1
    if use_mock:
        background.add_task(mock_runner.run_battle, battle_id)
    else:
        background.add_task(sandbox_launcher.start_battle, battle_id)
    return {"id": battle_id, "status": "queued"}


@router.get("")
def list_battles(saved: bool = False, user_id: str = Depends(get_current_user)):
    from .battle_public import public_battle_payload
    from .persistence import service

    rows = service.battle_list(user_id, saved=True if saved else None)
    return [public_battle_payload(row) for row in rows]


@router.get("/{battle_id}")
def get_battle(battle_id: str, user_id: str = Depends(get_current_user)):
    from .battle_public import public_battle_payload
    from .persistence import service

    data = _require_owned_battle(user_id, battle_id)
    results: list = []
    score_rows: list = []
    try:
        results = service.battle_results_list(battle_id)
        score_rows = service.scores_list(battle_id)
    except Exception:
        results, score_rows = [], []
    return public_battle_payload(
        data,
        results=results,
        score_rows=score_rows,
    )


@router.get("/{battle_id}/artifacts")
def get_artifacts(battle_id: str, user_id: str = Depends(get_current_user)):
    from .persistence import service

    battle = _require_owned_battle(user_id, battle_id)
    if not battle.get("saved"):
        raise HTTPException(
            status_code=404, detail="Battle was not saved; artifacts are gone"
        )
    return [
        {
            "phase": d["phase"],
            "model_id": d["model_id"],
            "artifact": d["artifact"],
        }
        for d in service.rounds_list(battle_id)
    ]


@router.get("/{battle_id}/stream")
def stream_battle(battle_id: str, user_id: str = Depends(get_current_user)):
    from .persistence import service

    _require_owned_battle(user_id, battle_id)

    def event_generator():
        from .battle_public import public_sse_payload

        seen_ids: set[str] = set()
        # Durable snapshot first (survives scale-to-zero / other replicas)
        for ev in service.events_load(battle_id):
            eid = ev.get("event_id")
            if eid and eid in seen_ids:
                continue
            if eid:
                seen_ids.add(eid)
            yield {
                "event": ev["type"],
                "data": json.dumps(public_sse_payload(ev)),
            }
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
                yield {
                    "event": ev["type"],
                    "data": json.dumps(public_sse_payload(ev)),
                }
            battle = service.battle_get(user_id, battle_id) or {}
            if battle.get("status") in ("completed", "failed", "cancelled"):
                yield {
                    "event": "done",
                    "data": json.dumps(
                        {"status": battle["status"], "authoritative": True}
                    ),
                }
                return
            yield {"event": "heartbeat", "data": "{}"}
            time.sleep(1)

    return EventSourceResponse(event_generator())


@router.post("/{battle_id}/cancel")
def cancel_battle(battle_id: str, user_id: str = Depends(get_current_user)):
    from .persistence import service

    battle = _require_owned_battle(user_id, battle_id)
    res = service.battle_cancel(user_id, battle_id)
    if not res.get("already_terminal"):
        sandbox_id = battle.get("sandbox_id")
        if sandbox_id:
            sandbox_launcher.stop_sandbox(sandbox_id)
        event_bus.publish(
            battle_id, {"type": "battle_status", "data": {"status": "cancelled", "authoritative": True}}
        )
    return {"id": battle_id, "status": "cancelled"}


@router.post("/{battle_id}/save")
def save_battle(battle_id: str, user_id: str = Depends(get_current_user)):
    from .persistence import service

    service.battle_save(user_id, battle_id)
    return {"id": battle_id, "saved": True}
