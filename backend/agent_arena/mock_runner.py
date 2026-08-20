import hashlib
import json
import time

from . import db, event_bus
from .redact import sanitize_artifact


def _mock_score(battle_id: str, model_id: str) -> float:
    digest = hashlib.sha256(f"{battle_id}:{model_id}".encode()).hexdigest()
    return float(int(digest[:8], 16) % 101)


def _persist_rounds(databases, database_id: str, battle_id: str, artifacts: list[dict]) -> None:
    for art in artifacts:
        databases.create_document(database_id, "rounds", "unique()", {
            "battle_id": battle_id,
            "phase": art["phase"],
            "model_id": art["model_id"],
            "artifact": art["artifact"],
        })


def _persist_scores(databases, database_id: str, battle_id: str, scores: dict[str, float]) -> None:
    for model_id, value in scores.items():
        databases.create_document(database_id, "scores", "unique()", {
            "battle_id": battle_id,
            "model_id": model_id,
            "score": value,
            "judge_model": "mock",
            "justification": "Mock judge used by backend-core plan.",
        })


def persist_scores(battle_id: str) -> None:
    """Persist score docs for an unsaved battle when the user saves it later.

    The mock runner computes scores deterministically from (battle_id, model_id),
    so we can reproduce them after the fact. Idempotent: skips if scores for this
    battle already exist (e.g. battle was saved at create time).
    """
    from appwrite.query import Query

    databases = db.get_databases()
    database_id = db.get_database_id()
    existing = databases.list_documents(
        database_id, "scores", queries=[Query.equal("battle_id", battle_id), Query.limit(1)]
    )
    if existing.documents:
        return
    try:
        battle = databases.get_document(database_id, "battles", battle_id)
    except Exception:
        return
    scores = {m: _mock_score(battle_id, m) for m in battle.data["model_ids"]}
    _persist_scores(databases, database_id, battle_id, scores)


def run_battle(battle_id: str) -> None:
    databases = db.get_databases()
    database_id = db.get_database_id()
    try:
        battle = databases.get_document(database_id, "battles", battle_id)
    except Exception:
        return
    event_bus.publish(battle_id, {"type": "battle_status", "data": {"status": "running"}})
    try:
        databases.update_document(database_id, "battles", battle_id, {"status": "running"})
        format_doc = databases.get_document(database_id, "formats", battle.data["format_id"])
        from .custom_battles import is_ranked_battle, resolve_battle_config

        cfg = resolve_battle_config(battle.data, json.loads(format_doc.data["config"]))
        phases = cfg["phases"]
        artifacts: list[dict] = []
        for phase in phases:
            event_bus.publish(battle_id, {"type": "phase_start", "data": {"phase": phase["name"]}})
            for participant in phase["participants"]:
                battle = databases.get_document(database_id, "battles", battle_id)
                if battle.data["status"] == "cancelled":
                    event_bus.publish(battle_id, {"type": "battle_status", "data": {"status": "cancelled"}})
                    return
                artifact_text = sanitize_artifact(
                    f"[mock:{battle_id}] {phase['name']}/{participant}: executed plan"
                )
                artifacts.append({"phase": phase["name"], "model_id": participant, "artifact": artifact_text})
                event_bus.publish(battle_id, {
                    "type": "artifact",
                    "data": {"phase": phase["name"], "model_id": participant, "artifact": artifact_text},
                })
                time.sleep(0.1)
        scores = {m: _mock_score(battle_id, m) for m in battle.data["model_ids"]}
        event_bus.publish(battle_id, {"type": "scores", "data": {"scores": scores}})
        # Persist rounds unconditionally so /save works even after a cold start
        # (in-memory state is lost when Modal scales to zero). /save only flips
        # the `saved` flag to expose them via GET /artifacts.
        _persist_rounds(databases, database_id, battle_id, artifacts)
        if battle.data.get("saved"):
            _persist_scores(databases, database_id, battle_id, scores)
        from . import leaderboard
        from .custom_battles import is_ranked_battle

        if is_ranked_battle(battle.data, cfg):
            leaderboard.apply_result(databases, database_id, battle.data["format_id"], battle.data["model_ids"], scores)
        databases.update_document(database_id, "battles", battle_id, {"status": "completed"})
        event_bus.publish(battle_id, {"type": "battle_status", "data": {"status": "completed"}})
    except Exception:
        try:
            databases.update_document(database_id, "battles", battle_id, {"status": "failed"})
        except Exception:
            pass
        event_bus.publish(battle_id, {"type": "battle_status", "data": {"status": "failed"}})
