import hashlib
import time
from datetime import datetime, timezone

from . import event_bus
from .redact import sanitize_artifact


def _mock_score(battle_id: str, model_id: str) -> float:
    digest = hashlib.sha256(f"{battle_id}:{model_id}".encode()).hexdigest()
    return float(int(digest[:8], 16) % 101)


def _iter_phases(cfg: dict) -> list[tuple[str, list[str]]]:
    """Normalize a battle config to [(phase_name, [participant_model_ids]), ...].

    Legacy seed formats carry a top-level \`phases\` list with \`name\` +
    \`participants\`. Target-library battles carry a nested \`battle_plan.phases\`
    list with \`phase_id\` + \`actor\`. Fall back to \`roles\` when neither is present
    so the mock runner completes a single synthetic phase instead of crashing.
    """
    cfg = cfg or {}

    phases = cfg.get("phases") or []
    normalized: list[tuple[str, list[str]]] = []
    for phase in phases:
        if not isinstance(phase, dict):
            continue
        name = phase.get("name") or phase.get("phase_id") or ""
        participants = [
            str(p) for p in (phase.get("participants") or [phase.get("actor")]) if p
        ]
        participants = [p for p in participants if p != "judge"]
        if name and participants:
            normalized.append((str(name), participants))
    if normalized:
        return normalized

    plan_phases = (cfg.get("battle_plan") or {}).get("phases") or []
    for phase in plan_phases:
        if not isinstance(phase, dict):
            continue
        name = phase.get("phase_id") or phase.get("name") or ""
        actor = phase.get("actor")
        if name and actor and actor != "judge":
            normalized.append((str(name), [str(actor)]))
    if normalized:
        return normalized

    roles = [str(r) for r in (cfg.get("roles") or []) if r and r != "judge"]
    if roles:
        return [("race", roles)]

    return []


def _persist_rounds(battle_id: str, artifacts: list[dict]) -> None:
    from .persistence import service

    for art in artifacts:
        service.round_create(
            battle_id,
            art["phase"],
            art["model_id"],
            art["artifact"],
            meta=art.get("meta"),
        )


def _persist_scores(battle_id: str, scores: dict[str, float]) -> None:
    from .persistence import service

    for model_id, value in scores.items():
        service.score_upsert(
            battle_id,
            model_id,
            value,
            judge_model="mock",
            justification="Mock judge used by backend-core plan.",
        )


def persist_scores(battle_id: str) -> None:
    """Persist score docs for an unsaved battle when the user saves it later.

    The mock runner computes scores deterministically from (battle_id, model_id),
    so we can reproduce them after the fact. Idempotent: skips if scores for this
    battle already exist (e.g. battle was saved at create time).
    """
    from .persistence import service

    if service.scores_exist(battle_id):
        return
    battle = service.battle_get("", battle_id)
    if battle is None:
        return
    scores = {m: _mock_score(battle_id, m) for m in battle["model_ids"]}
    _persist_scores(battle_id, scores)


def run_battle(battle_id: str) -> None:
    from .persistence import service

    battle = service.battle_get("", battle_id)
    if battle is None:
        return
    event_bus.publish(
        battle_id, {"type": "battle_status", "data": {"status": "running", "authoritative": True}}
    )
    try:
        service.battle_update(battle_id, {"status": "running"})
        fmt = service.format_get(battle["format_id"])
        fmt_cfg = (fmt or {}).get("config") or {}
        from .custom_battles import is_ranked_battle, resolve_battle_config

        cfg = resolve_battle_config(battle, fmt_cfg)
        from .fighter_isolation import (
            FighterIsolationError,
            assert_isolated_fighter_execution,
            battle_target_id,
        )

        try:
            assert_isolated_fighter_execution(
                battle_target_id(battle, cfg), mode="mock"
            )
        except FighterIsolationError as exc:
            reason = str(exc)
            service.battle_update(
                battle_id, {"status": "failed", "failure_reason": reason}
            )
            event_bus.publish(battle_id, {"type": "error", "data": {"message": reason}})
            event_bus.publish(
                battle_id,
                {
                    "type": "battle_status",
                    "data": {"status": "failed", "reason": reason, "authoritative": True},
                },
            )
            return
        phases = _iter_phases(cfg)
        artifacts: list[dict] = []
        for phase_name, participants in phases:
            event_bus.publish(
                battle_id, {"type": "phase_start", "data": {"phase": phase_name}}
            )
            for participant in participants:
                battle = service.battle_get("", battle_id)
                if battle is None or battle["status"] == "cancelled":
                    event_bus.publish(
                        battle_id,
                        {"type": "battle_status", "data": {"status": "cancelled", "authoritative": True}},
                    )
                    return
                artifact_text = sanitize_artifact(
                    f"[mock:{battle_id}] {phase_name}/{participant}: executed plan"
                )
                artifacts.append(
                    {
                        "phase": phase_name,
                        "model_id": participant,
                        "artifact": artifact_text,
                        "meta": {"runner": "mock", "is_mock": True},
                    }
                )
                event_bus.publish(
                    battle_id,
                    {
                        "type": "artifact",
                        "data": {
                            "phase": phase_name,
                            "model_id": participant,
                            "artifact": artifact_text,
                        },
                    },
                )
                time.sleep(0.1)
        scores = {m: _mock_score(battle_id, m) for m in battle["model_ids"]}
        event_bus.publish(battle_id, {"type": "scores", "data": {"scores": scores}})
        # Persist rounds unconditionally so /save works even after a cold start
        # (in-memory state is lost when Modal scales to zero). /save only flips
        # the \`saved\` flag to expose them via GET /artifacts.
        _persist_rounds(battle_id, artifacts)
        if battle.get("saved"):
            _persist_scores(battle_id, scores)
        if is_ranked_battle(battle, cfg):
            service.leaderboard_apply_result(
                battle["format_id"], battle["model_ids"], scores
            )
        service.battle_update(
            battle_id,
            {"status": "completed", "completed_at": datetime.now(timezone.utc).isoformat()},
        )
        event_bus.publish(
            battle_id, {"type": "battle_status", "data": {"status": "completed", "authoritative": True}}
        )
    except Exception as exc:
        import traceback
        traceback.print_exc()
        try:
            service.battle_update(battle_id, {"status": "failed"})
        except Exception:
            pass
        event_bus.publish(
            battle_id, {"type": "battle_status", "data": {"status": "failed", "authoritative": True}}
        )
