"""Sandbox → backend callbacks. Hidden from OpenAPI; auth via X-Sandbox-Token."""

from __future__ import annotations

import hmac
import json
import re
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
from .results import TRUSTED_VERIFICATION_MARKER

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
    tools: list[dict] | None = None
    tool_choice: str | None = None

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
    judge_model: str | None = None


class VerifyBody(BaseModel):
    battle_id: str
    target_id: str = ""
    kind: str = ""
    phase: str = ""
    role: str = ""
    model_id: str = ""
    submitted_files: dict[str, str] = Field(default_factory=dict)
    builder_files: dict[str, str] = Field(default_factory=dict)
    breaker_files: dict[str, str] = Field(default_factory=dict)


_TARGET_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")


def _trusted_verifier_kind(fmt_cfg: dict) -> str:
    fmt_kind = str(fmt_cfg.get("format") or "").strip().lower()
    phases = (fmt_cfg.get("battle_plan") or {}).get("phases") or []
    actors = {str(p.get("actor") or "") for p in phases if isinstance(p, dict)}
    if fmt_kind == "builder_breaker" or actors == {"builder", "breaker"}:
        return "builder_breaker"
    return "solo"


def _derive_verify_binding(battle: dict, fmt_cfg: dict, body: VerifyBody) -> tuple[str, str, str, str, str]:
    """target_id and kind come from trusted battle/format/plan, never the sandbox."""
    target_id = str(battle.get("target_id") or "").strip() or str(
        fmt_cfg.get("target_id") or ""
    ).strip()
    if not target_id:
        raise HTTPException(status_code=400, detail="battle has no bound target")
    if not _TARGET_ID_RE.match(target_id):
        raise HTTPException(status_code=400, detail="invalid bound target_id")
    hint_target = str(body.target_id or "").strip()
    if hint_target and hint_target != target_id:
        raise HTTPException(status_code=400, detail="target_id does not match battle")
    if "/" in hint_target or "\\" in hint_target or ".." in hint_target:
        raise HTTPException(status_code=400, detail="target_id does not match battle")

    kind = _trusted_verifier_kind(fmt_cfg)
    hint_kind = str(body.kind or "").strip().lower()
    if hint_kind and hint_kind != kind:
        raise HTTPException(status_code=400, detail="verifier kind does not match battle")

    model_ids = [str(m) for m in (battle.get("model_ids") or [])]
    roles = [str(r).lower() for r in (fmt_cfg.get("roles") or [])]
    plan_phases = [
        str(p.get("phase_id") or p.get("name") or "")
        for p in ((fmt_cfg.get("battle_plan") or {}).get("phases") or [])
        if isinstance(p, dict)
    ]

    model_id = str(body.model_id or "").strip()
    if kind != "builder_breaker" and model_ids:
        if not model_id or model_id not in model_ids:
            raise HTTPException(status_code=400, detail="model is not a battle participant")
    elif model_id and model_ids and model_id not in model_ids:
        raise HTTPException(status_code=400, detail="model is not a battle participant")
    role = str(body.role or "").strip().lower()
    if role and roles and role not in roles:
        raise HTTPException(status_code=400, detail="role does not match battle plan")
    phase = str(body.phase or "").strip()
    if phase and plan_phases and phase not in plan_phases:
        raise HTTPException(status_code=400, detail="phase does not match battle plan")
    return target_id, kind, phase, role, model_id


def _persist_trusted_verification(
    battle_id: str,
    *,
    target_id: str,
    kind: str,
    phase: str,
    role: str,
    model_id: str,
    payload: dict,
) -> None:
    record = {
        "source": "trusted_verifier",
        "target_id": target_id,
        "kind": kind,
        "phase": phase or "main",
        "role": role or "fighter",
        "model_id": model_id,
        "passed": bool(payload.get("passed")),
        "builder_passed": payload.get("builder_passed"),
        "breaker_passed": payload.get("breaker_passed"),
        "manifest_hash": payload.get("manifest_hash") or "",
        "outcome": "TEST_PASS" if payload.get("passed") else "TEST_FAIL",
    }
    artifact = TRUSTED_VERIFICATION_MARKER + " " + json.dumps(record)
    from .persistence import service as persist

    persist.round_create(battle_id, phase or "verify", model_id, artifact)



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
    """Persist skill Elo + memory from executor results (runs on backend, not sandbox).

    Mode-gated: Strict Benchmark mode has 0 historical side-effects.
    Adaptive Mode: Updates skill Elo and persists compact, model-scoped lessons.
    """
    if not results:
        return
    context_mode = str(battle.get("context_mode") or "strict").lower().strip()
    if context_mode not in ("adaptive", "assisted"):
        # Strict mode: strictly zero historical persistence or learning mutation
        return

    from .persistence import service
    from .skills import compute_skill_attributions

    # Only fighters that actually passed are eligible to win
    passed_results = [r for r in results if r.get("passed")]
    winner = None
    if passed_results:
        winner = min(passed_results, key=lambda x: int(x.get("steps") or 999))

    format_name = ""
    try:
        fmt_record = service.format_get(str(battle.get("format_id") or ""))
        format_name = str((fmt_record or {}).get("name") or "")
    except Exception:
        format_name = str(battle.get("format_id") or "")

    target_id = str(battle.get("target_id") or format_name)
    user_id = str(battle.get("user_id") or "system")

    # Learnable lesson persistence: Store model-authored insight from authoritative winner
    if winner is not None:
        try:
            insight_text = (
                f"Battle {battle_id} format {format_name} "
                f"winner {winner.get('model_id')} chose {winner.get('chosen_skills')} "
                f"theory {str(winner.get('theory') or '')[:300]}."
            )
            if service.using_postgres():
                from .memory import maybe_remember_pg
                from .persistence.session import session_scope

                with session_scope() as session:
                    maybe_remember_pg(
                        session,
                        insight=insight_text,
                        battle_id=battle_id,
                        model_id=str(winner.get("model_id") or ""),
                        target_id=target_id,
                        role=str(winner.get("role") or "general"),
                        visibility_class="model_private",
                        format_name=format_name,
                        chosen_skills=list(winner.get("chosen_skills") or []),
                        theory=str(winner.get("theory") or ""),
                        outcome=str(winner.get("outcome") or "TEST_PASS"),
                        user_id=user_id,
                        context_mode=context_mode,
                    )
            else:
                from .memory import maybe_remember

                maybe_remember(
                    databases,
                    database_id,
                    insight=insight_text,
                    battle_id=battle_id,
                    model_id=str(winner.get("model_id") or ""),
                    target_id=target_id,
                    role=str(winner.get("role") or "general"),
                    visibility_class="model_private",
                    authoritative_status="verified_pass",
                    format_name=format_name,
                    chosen_skills=list(winner.get("chosen_skills") or []),
                    theory=str(winner.get("theory") or ""),
                    outcome=str(winner.get("outcome") or "TEST_PASS"),
                    user_id=user_id,
                    context_mode=context_mode,
                )
        except Exception:
            pass


    attributions = compute_skill_attributions(results)
    for role, attrs in attributions.items():
        for attr in attrs:
            skill_id = attr["skill_id"]
            outcome = attr["outcome"]
            try:
                if service.using_postgres():
                    _record_skill_outcome_pg(str(skill_id), outcome)
                else:
                    from .skills_registry import record_outcome

                    record_outcome(
                        databases,
                        database_id,
                        str(skill_id),
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
    """Sandbox reports final outcome: persist scores, update battle status, apply Elo transactionally and idempotently."""
    _require_battle_token(body.battle_id, x_sandbox_token, x_internal_key)
    _rate_limit(body.battle_id)

    from .finalization import finalize_battle

    result = finalize_battle(
        body.battle_id,
        caller_status=body.status,
        caller_scores=body.scores,
        judge_model=body.judge_model,
    )
    if result.get("status") == "not_found":
        raise HTTPException(status_code=404, detail="Battle not found")
    return result


@router.post("/verify")
def internal_verify(
    body: VerifyBody,
    x_sandbox_token: str | None = Header(default=None),
    x_internal_key: str | None = Header(default=None),
):
    """Trusted target verification. Hidden/reference files live only on the host.

    The fighter sandbox never receives evaluator-private files; it submits
    workspace contents here. Sandbox-supplied scores are not accepted.
    """
    _require_battle_token(body.battle_id, x_sandbox_token, x_internal_key)
    _rate_limit(body.battle_id)
    databases = None
    database_id = ""
    from .persistence import service

    battle = _active_battle(databases, database_id, body.battle_id)

    from .custom_battles import FrozenConfigError, resolve_battle_config
    from .target_library import get_target_library, get_trusted_library_root
    from .target_verifier import (
        verify_builder_breaker_submission,
        verify_target_submission,
    )

    fmt_cfg: dict = {}
    try:
        fmt_record = service.format_get(str(battle.get("format_id") or ""))
        fmt_cfg = (fmt_record or {}).get("config") or {}
    except Exception:
        fmt_cfg = {}
    try:
        fmt_cfg = resolve_battle_config(battle, fmt_cfg)
    except FrozenConfigError:
        fmt_cfg = dict(battle.get("battle_config") or {}) or fmt_cfg

    target_id, kind, phase, role, model_id = _derive_verify_binding(battle, fmt_cfg, body)

    bundle = get_target_library(get_trusted_library_root()).get_target(target_id)
    if bundle is None:
        raise HTTPException(status_code=404, detail="target not found")
    if str(bundle.format or "").strip().lower() == "builder_breaker":
        kind = "builder_breaker"
    hint_kind = str(body.kind or "").strip().lower()
    if hint_kind and hint_kind != kind:
        raise HTTPException(status_code=400, detail="verifier kind does not match battle")
    frozen_manifest = str(
        battle.get("target_manifest_hash") or fmt_cfg.get("manifest_hash") or ""
    )
    frozen_hidden = str(fmt_cfg.get("hidden_hash") or "")
    if frozen_manifest and bundle.manifest_hash != frozen_manifest:
        raise HTTPException(status_code=409, detail="target manifest hash mismatch")
    if frozen_hidden and bundle.hidden_hash != frozen_hidden:
        raise HTTPException(status_code=409, detail="target hidden hash mismatch")

    if kind == "builder_breaker":
        ev = verify_builder_breaker_submission(
            bundle,
            body.builder_files,
            body.breaker_files,
            trusted_host=True,
        )
        public = {
            "ok": True,
            "target_id": ev.target_id,
            "passed": bool(ev.builder_passed),
            "builder_passed": ev.builder_passed,
            "breaker_passed": ev.breaker_passed,
        }
        _persist_trusted_verification(
            body.battle_id,
            target_id=target_id,
            kind=kind,
            phase=phase,
            role=role,
            model_id=model_id,
            payload={
                "passed": ev.builder_passed,
                "builder_passed": ev.builder_passed,
                "breaker_passed": ev.breaker_passed,
                "manifest_hash": ev.manifest_hash,
            },
        )
        return public

    ev = verify_target_submission(
        bundle,
        body.submitted_files,
        run_visible=True,
        run_hidden=True,
        trusted_host=True,
    )
    public = {
        "ok": True,
        "target_id": ev.target_id,
        "passed": ev.passed,
        "visible_passed": ev.visible_passed,
    }
    _persist_trusted_verification(
        body.battle_id,
        target_id=target_id,
        kind=kind,
        phase=phase,
        role=role,
        model_id=model_id,
        payload={
            "passed": ev.passed,
            "manifest_hash": ev.manifest_hash,
        },
    )
    return public



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
        resp = llm_client.chat_completion(
            base_url=base,
            auth_style=style,
            api_key=key,
            model=model,
            messages=body.messages,
            max_tokens=body.max_tokens,
            tools=body.tools,
            tool_choice=body.tool_choice,
            return_response_obj=True,
        )
    except HTTPException as exc:
        print(
            f"internal_model fail battle={body.battle_id} "
            f"model={body.model_id} slug={model} detail={str(exc.detail)[:300]!r}"
        )
        raise
    if isinstance(resp, str):
        return {
            "content": resp,
            "tool_calls": [],
            "finish_reason": "stop",
            "latency_ms": 0,
        }
    return {
        "content": getattr(resp, "text", str(resp or "")),
        "tool_calls": getattr(resp, "native_tool_calls", []),
        "finish_reason": getattr(resp, "raw_finish_reason", None),
        "latency_ms": getattr(resp, "latency_ms", 0),
    }


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
    if TRUSTED_VERIFICATION_MARKER.rstrip(":") in artifact:
        raise HTTPException(
            status_code=400,
            detail="trusted verification cannot be submitted via /round",
        )
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
