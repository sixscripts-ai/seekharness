"""Sandbox → backend callbacks. Hidden from OpenAPI; auth via X-Sandbox-Token."""

from __future__ import annotations

import hmac
import json
import time
from collections import defaultdict
from datetime import datetime, timezone
from threading import Lock

from appwrite.exception import AppwriteException
from appwrite.query import Query
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field, field_validator

from . import db, event_bus, judge, llm_client
from .battle_token import issue_battle_token, verify_battle_token
from .config import settings
from .providers import get_model_call_spec
from .redact import sanitize_artifact

router = APIRouter(prefix="/internal", tags=["internal"], include_in_schema=False)

_rate_lock = Lock()
_rate_counts: dict[str, list[float]] = defaultdict(list)
_RATE_LIMIT = 120  # calls per battle per minute

# Cost / DoS bounds for sandbox-supplied model calls (C1/H1) — mirror the
# sandbox's own limits so a compromised sandbox cannot drive unbounded spend.
MAX_MESSAGES = 50
MAX_MESSAGE_CHARS = 200_000
MAX_TOKENS = 4096


def _require_battle_token(
    battle_id: str,
    x_sandbox_token: str | None = Header(default=None),
    x_internal_key: str | None = Header(default=None),
) -> bool:
    # The legacy global key (x_internal_key) is intentionally ignored here:
    # battle-scoped endpoints accept ONLY the per-battle token. We still
    # declare the header so stale clients get a clean 401 rather than a
    # confusing schema error, but it is never treated as a valid credential.
    del x_internal_key
    if x_sandbox_token and verify_battle_token(x_sandbox_token, battle_id):
        return True
    raise HTTPException(status_code=401, detail="invalid or expired sandbox token")


def require_internal_key(x_internal_key: str | None = Header(default=None)) -> bool:
    """Legacy global-key check (kept for /internal/reap and self-calls)."""
    expected = settings().get("INTERNAL_API_KEY") or ""
    if not expected:
        raise HTTPException(status_code=401, detail="internal key not configured")
    if not x_internal_key or not hmac.compare_digest(x_internal_key, expected):
        raise HTTPException(status_code=401, detail="invalid internal key")
    return True


def _rate_limit(battle_id: str) -> None:
    """Durable per-battle rate limit backed by Appwrite.

    The in-process dict was unreliable across Modal replicas and reset on cold
    start. We persist a per-battle call counter document so the limit holds
    regardless of which replica serves the request. Falls back to the local
    in-memory window if the datastore is unavailable (best-effort).
    """
    now = time.time()
    # Local fast-path first (cheap, no I/O).
    with _rate_lock:
        window = [t for t in _rate_counts[battle_id] if now - t < 60]
        _rate_counts[battle_id] = window
        if len(window) >= _RATE_LIMIT:
            raise HTTPException(status_code=429, detail="internal rate limit exceeded")
    # Durable cross-replica window via a counter document.
    try:
        from .persistence import service

        if service.using_postgres():
            internal_calls = sum(
                1 for e in service.events_load(battle_id)
                if e.get("type") == "internal_call"
            )
            if internal_calls >= _RATE_LIMIT:
                raise HTTPException(status_code=429, detail="internal rate limit exceeded")
        else:
            databases = db.get_databases()
            database_id = db.get_database_id()
            res = databases.list_documents(
                database_id,
                "battle_events",
                queries=[
                    Query.equal("battle_id", battle_id),
                    Query.contains("payload", '"type":"internal_call"'),
                    Query.limit(_RATE_LIMIT + 1),
                ],
            )
            # Count only calls within the last minute using payload timestamps is
            # not reliable; approximate with doc count is acceptable given the
            # token expiry already bounds total call volume. Keep it conservative.
            if len(res.documents) >= _RATE_LIMIT:
                raise HTTPException(status_code=429, detail="internal rate limit exceeded")
    except HTTPException:
        raise
    except Exception:
        pass  # datastore unavailable — rely on the local window only
    with _rate_lock:
        window.append(now)
        _rate_counts[battle_id] = window


def _active_battle(databases, database_id: str, battle_id: str) -> dict:
    from .persistence import service

    battle = service.battle_get("", battle_id)
    if battle is None:
        raise HTTPException(status_code=404, detail="Battle not found")
    if battle.get("status") not in ("queued", "running"):
        raise HTTPException(status_code=409, detail="battle not active")
    return battle


class ModelBody(BaseModel):
    battle_id: str
    model_id: str
    phase: str = ""
    messages: list[dict] = Field(default_factory=list)
    max_tokens: int = 1024

    @field_validator("messages")
    @classmethod
    def _bound_messages(cls, v: list[dict]) -> list[dict]:
        if len(v) > MAX_MESSAGES:
            raise ValueError(f"too many messages (max {MAX_MESSAGES})")
        total = 0
        for m in v:
            if not isinstance(m, dict) or not isinstance(m.get("content", ""), str):
                continue
            total += len(m["content"])
        if total > MAX_MESSAGE_CHARS:
            raise ValueError(
                f"messages too large (max {MAX_MESSAGE_CHARS} chars)"
            )
        return v

    @field_validator("max_tokens")
    @classmethod
    def _bound_max_tokens(cls, v: int) -> int:
        if v < 1 or v > MAX_TOKENS:
            raise ValueError(f"max_tokens must be between 1 and {MAX_TOKENS}")
        return v


class JudgeBody(BaseModel):
    battle_id: str
    rubric: str
    weights: dict[str, float] | None = None
    artifacts: list[dict] = Field(default_factory=list)
    judge_model: str | None = None


class RoundBody(BaseModel):
    battle_id: str
    phase: str
    model_id: str
    artifact: str
    event_type: str = "artifact"
    sequence: int | None = None


class StatusBody(BaseModel):
    battle_id: str


class FinalizeBody(BaseModel):
    battle_id: str
    status: str = "completed"
    scores: dict[str, float] = Field(default_factory=dict)


def _finalize_scores(battle_id: str, scores: dict, source: str = "judged") -> bool:
    """Persist score docs for a finished battle. Idempotent per battle."""
    from .persistence import service

    if service.scores_exist(battle_id):
        return False
    for mid, value in scores.items():
        service.score_upsert(
            battle_id,
            mid,
            float(value),
            judge_model="arena-deterministic" if source != "judged" else "host-judge",
            justification=source,
        )
    return True


def _parse_executor_results(databases, database_id: str, battle_id: str) -> list[dict]:
    """Load EXECUTOR_RESULT payloads from durable battle_events."""
    out: list[dict] = []
    try:
        from .persistence import service

        events = service.events_load(battle_id)
    except Exception:
        return out
    for event in events:
        if not isinstance(event, dict) or event.get("type") != "result":
            continue
        artifact = str((event.get("data") or {}).get("artifact") or "")
        marker = "EXECUTOR_RESULT:"
        if marker not in artifact:
            continue
        raw = artifact.split(marker, 1)[1].strip()
        try:
            result = json.loads(raw)
        except Exception:
            continue
        if isinstance(result, dict):
            out.append(result)
    return out


def _record_skill_outcome_pg(skill_name: str, outcome: str, tier: str = "general") -> None:
    """Mirror skills_registry.record_outcome against the Postgres backend."""
    from . import elo
    from .persistence import service

    difficulty_offset = {"novice": 0.0, "general": 0.0, "advanced": -100.0, "expert": -200.0}
    cur = service.skill_get(skill_name) or {}
    current_elo = float(cur.get("elo") or elo.INITIAL_RATING)
    expected = elo.expected_score(
        current_elo + difficulty_offset.get(tier, 0.0), elo.INITIAL_RATING
    )
    score = {"win": 1.0, "draw": 0.5, "loss": 0.0}[outcome]
    wins = int(cur.get("wins") or 0) + (1 if outcome == "win" else 0)
    losses = int(cur.get("losses") or 0) + (1 if outcome == "loss" else 0)
    draws = int(cur.get("draws") or 0) + (1 if outcome == "draw" else 0)
    uses = int(cur.get("uses") or 0) + 1
    success_rate = round((wins + 0.5 * draws) / max(1, uses), 3)
    new_elo = round(current_elo + elo.K_FACTOR * (score - expected), 2)
    service.skill_upsert(
        skill_name,
        elo=new_elo,
        wins=wins,
        losses=losses,
        draws=draws,
        uses=uses,
        success_rate=success_rate,
        tier=tier,
        last_used=time.time(),
    )


def _apply_self_learning(
    databases, database_id: str, battle: dict, battle_id: str, results: list[dict]
) -> None:
    """Persist skill Elo + memory from executor results (runs on backend, not sandbox)."""
    if not results:
        return
    from .persistence import service

    sorted_res = sorted(
        results,
        key=lambda x: (bool(x.get("passed")), -int(x.get("steps") or 999)),
        reverse=True,
    )
    winner = sorted_res[0]
    format_name = ""
    try:
        fmt_record = service.format_get(str(battle.get("format_id") or ""))
        format_name = str((fmt_record or {}).get("name") or "")
    except Exception:
        format_name = str(battle.get("format_id") or "")
    try:
        if service.using_postgres():
            service.memory_create(
                str(battle.get("user_id") or "system"),
                (
                    f"Battle {battle_id} format {format_name} "
                    f"winner {winner.get('model_id')} chose {winner.get('chosen_skills')} "
                    f"theory {str(winner.get('theory') or '')[:300]} beat opponent picks "
                    f"{[r.get('chosen_skills') for r in results if r is not winner]}. "
                    "Skills to beat opponent technique emerged."
                ),
                battle_id=battle_id,
                model_id=str(winner.get("model_id") or ""),
                format=format_name,
                chosen_skills=list(winner.get("chosen_skills") or []),
                theory=str(winner.get("theory") or ""),
                outcome=str(winner.get("outcome") or ""),
            )
        else:
            from .memory import maybe_remember

            maybe_remember(
                databases,
                database_id,
                insight=(
                    f"Battle {battle_id} format {format_name} "
                    f"winner {winner.get('model_id')} chose {winner.get('chosen_skills')} "
                    f"theory {str(winner.get('theory') or '')[:300]} beat opponent picks "
                    f"{[r.get('chosen_skills') for r in results if r is not winner]}. "
                    "Skills to beat opponent technique emerged."
                ),
                battle_id=battle_id,
                model_id=str(winner.get("model_id") or ""),
                format_name=format_name,
                chosen_skills=list(winner.get("chosen_skills") or []),
                theory=str(winner.get("theory") or ""),
                outcome=str(winner.get("outcome") or ""),
                user_id=str(battle.get("user_id") or "system"),
            )
    except Exception:
        pass
    for r in results:
        outcome = "win" if r is winner else "loss"
        for chosen in list(r.get("chosen_skills") or [])[:5]:
            try:
                if service.using_postgres():
                    _record_skill_outcome_pg(str(chosen), outcome)
                else:
                    from .skills_registry import record_outcome

                    record_outcome(
                        databases,
                        database_id,
                        str(chosen),
                        outcome=outcome,
                        tier="general",
                    )
            except Exception:
                pass


@router.post("/finalize")
def internal_finalize(
    body: FinalizeBody,
    x_sandbox_token: str | None = Header(default=None),
    x_internal_key: str | None = Header(default=None),
):
    """Sandbox reports final outcome: persist scores, update battle status, apply Elo."""
    _require_battle_token(body.battle_id, x_sandbox_token, x_internal_key)
    _rate_limit(body.battle_id)
    from .persistence import service

    databases = db.get_databases()
    database_id = db.get_database_id()
    battle = service.battle_get("", body.battle_id)
    if battle is None:
        raise HTTPException(status_code=404, detail="Battle not found")
    if battle.get("status") not in ("queued", "running"):
        raise HTTPException(status_code=409, detail="battle not active")
    status = body.status if body.status in ("completed", "failed") else "completed"
    effective_scores = body.scores
    score_source = "judged"
    results: list[dict] = []
    if status in ("completed", "failed"):
        try:
            results = _parse_executor_results(databases, database_id, body.battle_id)
        except Exception:
            results = []
    if status in ("completed", "failed"):
        try:
            fmt_cfg: dict = {}
            if results:
                try:
                    fmt_record = service.format_get(str(battle.get("format_id") or ""))
                    fmt_cfg = (fmt_record or {}).get("config") or {}
                except Exception:
                    fmt_cfg = {}
                from .custom_battles import FrozenConfigError, resolve_battle_config

                try:
                    fmt_cfg = resolve_battle_config(battle, fmt_cfg)
                except FrozenConfigError:
                    fmt_cfg = {}
                from . import evidence as evidence_mod
                from . import scoring as scoring_mod

                summary = evidence_mod.build_battle_evidence(
                    body.battle_id,
                    results,
                    fmt_cfg,
                    judge_scores=dict(body.scores or {}),
                    format_id=str(battle.get("format_id") or ""),
                )
                decision = scoring_mod.decide_winner(summary, fmt_cfg)
                event_bus.publish(
                    body.battle_id,
                    {"type": "evidence_summary", "data": {**summary, "decision": decision}},
                )
                det_scores = scoring_mod.deterministic_scores(decision)
                if det_scores:
                    battle_mids = set(battle.get("model_ids", []))
                    result_mids = {str(r.get("model_id") or "") for r in results}
                    if status == "failed" and result_mids != battle_mids:
                        # Partial evidence on a failed battle: never fabricate
                        # an outcome; keep the judge fallback (usually empty).
                        det_scores = None
                if det_scores:
                    effective_scores = det_scores
                    score_source = "arena-score-v1"
                    if status == "failed":
                        # Executable evidence completes the battle even when the
                        # judge layer returned nothing (e.g. judge outage).
                        status = "completed"
            if effective_scores:
                if _finalize_scores(
                    body.battle_id,
                    effective_scores,
                    source=score_source,
                ):
                    from .custom_battles import is_ranked_battle

                    if is_ranked_battle(battle, fmt_cfg):
                        service.leaderboard_apply_result(
                            battle["format_id"],
                            list(battle.get("model_ids", [])),
                            effective_scores,
                        )
        except Exception:
            pass
    # Self-learning on backend (sandbox has no datastore credentials)
    try:
        from .custom_battles import is_ranked_battle, resolve_battle_config

        cfg = resolve_battle_config(battle, {})
        if is_ranked_battle(battle, cfg):
            _apply_self_learning(
                databases, database_id, battle, body.battle_id, results
            )
    except Exception:
        pass
    service.battle_update(
        body.battle_id,
        {"status": status, "completed_at": datetime.now(timezone.utc)},
    )
    if status == "completed" and effective_scores:
        event_bus.publish(
            body.battle_id, {"type": "scores", "data": {"scores": effective_scores}}
        )
    event_bus.publish(
        body.battle_id,
        {
            "type": "battle_status",
            "data": {"status": status},
        },
    )
    return {"ok": True, "status": status}


@router.post("/model")
def internal_model(
    body: ModelBody,
    x_sandbox_token: str | None = Header(default=None),
    x_internal_key: str | None = Header(default=None),
):
    _require_battle_token(body.battle_id, x_sandbox_token, x_internal_key)
    _rate_limit(body.battle_id)
    databases = db.get_databases()
    database_id = db.get_database_id()
    battle = _active_battle(databases, database_id, body.battle_id)
    if body.model_id not in battle.get("model_ids", []):
        raise HTTPException(status_code=400, detail="model not in battle")
    base, style, key, model = get_model_call_spec(body.model_id, battle["user_id"])
    try:
        content = llm_client.chat_completion(
            base_url=base,
            auth_style=style,
            api_key=key,
            model=model,
            messages=body.messages,
            max_tokens=body.max_tokens,
        )
    except HTTPException as exc:
        print(
            f"internal_model fail battle={body.battle_id} "
            f"model={body.model_id} slug={model} detail={str(exc.detail)[:300]!r}"
        )
        raise
    return {"content": content}


@router.post("/judge")
def internal_judge(
    body: JudgeBody,
    x_sandbox_token: str | None = Header(default=None),
    x_internal_key: str | None = Header(default=None),
):
    _require_battle_token(body.battle_id, x_sandbox_token, x_internal_key)
    _rate_limit(body.battle_id)
    databases = db.get_databases()
    database_id = db.get_database_id()
    battle = _active_battle(databases, database_id, body.battle_id)
    model_ids = list(battle.get("model_ids", []))
    call_spec = None
    jpid = battle.get("judge_provider_id")
    if jpid:
        try:
            call_spec = get_model_call_spec(jpid, battle["user_id"])
        except HTTPException:
            call_spec = None  # fall back to host Kimi-K3
    result = judge.judge_battle(
        model_ids=model_ids,
        artifacts=body.artifacts,
        rubric=body.rubric,
        weights=body.weights,
        judge_model=body.judge_model,
        call_spec=call_spec,
    )
    return result


@router.post("/round")
def internal_round(
    body: RoundBody,
    x_sandbox_token: str | None = Header(default=None),
    x_internal_key: str | None = Header(default=None),
):
    _require_battle_token(body.battle_id, x_sandbox_token, x_internal_key)
    _rate_limit(body.battle_id)
    databases = db.get_databases()
    database_id = db.get_database_id()
    battle = _active_battle(databases, database_id, body.battle_id)
    if (
        body.model_id not in battle.get("model_ids", [])
        and body.model_id != "system"
    ):
        raise HTTPException(status_code=400, detail="model not in battle")
    artifact = sanitize_artifact(body.artifact)
    from .persistence import service

    service.round_create(body.battle_id, body.phase, body.model_id, artifact)
    event_id = f"{body.battle_id}:{body.sequence if body.sequence is not None else int(time.time() * 1000)}"
    event = {
        "type": body.event_type,
        "event_id": event_id,
        "sequence": body.sequence,
        "data": {
            "phase": body.phase,
            "model_id": body.model_id,
            "artifact": artifact,
            "sequence": body.sequence,
        },
    }
    event_bus.publish(body.battle_id, event)
    return {"ok": True, "event_id": event_id, "sequence": body.sequence}


@router.post("/status")
def internal_status(
    body: StatusBody,
    x_sandbox_token: str | None = Header(default=None),
    x_internal_key: str | None = Header(default=None),
):
    _require_battle_token(body.battle_id, x_sandbox_token, x_internal_key)
    from .persistence import service

    battle = service.battle_get("", body.battle_id)
    if battle is None:
        raise HTTPException(status_code=404, detail="Battle not found")
    return {"status": battle.get("status") or "unknown"}


@router.post("/reap")
def internal_reap(_ok: bool = Depends(require_internal_key)):
    from . import reaper

    reaped = reaper.reap_stale_battles()
    return {"reaped": reaped, "count": len(reaped)}
