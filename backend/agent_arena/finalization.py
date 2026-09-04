"""Centralized Transactional & Idempotent Battle Finalization (Change Set C).

Establishes a single authoritative finalization boundary:
1. Row lock on Battle row (SELECT ... FOR UPDATE) to serialize concurrent finalization calls.
2. Idempotency guard: If battle is already finalized, returns existing authoritative state (0 duplicate side-effects).
3. Derives verifiable facts from synchronous rounds and evidence using deterministic round selection rules.
4. Persists canonical BattleResult records in the SAME database transaction.
5. Persists scores idempotently in the SAME transaction.
6. Applies Leaderboard Elo ratings with sorted row locks and race-safe missing row creation in the SAME transaction.
7. Applies Skill Attribution & Memory Learning in the SAME transaction.
8. Commits transaction atomically and transitions status to completed.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from . import db, event_bus
from .custom_battles import FrozenConfigError, is_ranked_battle, resolve_battle_config
from .evidence import build_battle_evidence
from .persistence import repositories, service
from .persistence.models import Battle, LeaderboardEntry
from .persistence.service import using_postgres
from .persistence.session import session_scope
from .results import (
    EXECUTOR_RESULT_MARKER,
    TRUSTED_VERIFICATION_MARKER,
    UNTRUSTED_EXECUTION,
    is_infra_outcome,
    is_learnable_model_outcome,
    normalize_participant_identity,
    participant_status_from_outcome,
    sanitize_untrusted_executor_payload,
)
from .scoring import decide_winner, deterministic_scores

logger = logging.getLogger(__name__)

TERMINAL_BATTLE_STATUSES = frozenset({"completed", "failed", "cancelled"})
ACTIVE_FINALIZE_STATUSES = frozenset({"queued", "running"})
INCOMPLETE_EVIDENCE = "INCOMPLETE_EVIDENCE"


def is_terminal_battle_status(status: str | None) -> bool:
    return str(status or "") in TERMINAL_BATTLE_STATUSES


def derive_trusted_scores(
    *,
    battle_id: str,
    results: list[dict],
    fmt_cfg: dict,
    battle_model_ids: list[str],
    format_id: str = "",
    untrusted_hint_scores: dict | None = None,
) -> tuple[dict[str, float] | None, str, str | None, dict | None, dict | None]:
    """Authoritative scores from trusted evidence only.

    `untrusted_hint_scores` (sandbox/caller JSON) are never copied into the
    returned scores. Missing evidence yields INCOMPLETE_EVIDENCE.
    """
    del untrusted_hint_scores
    expected = [str(m) for m in (battle_model_ids or []) if str(m)]
    if not results:
        return None, "", INCOMPLETE_EVIDENCE, None, None
    if expected and len(results) < len(expected):
        return None, "", INCOMPLETE_EVIDENCE, None, None
    trusted_rows = [r for r in results if r.get("_trusted")]
    if not trusted_rows:
        ids = expected or [
            str(r.get("model_id") or "") for r in results if str(r.get("model_id") or "")
        ]
        diagnostic = {mid: 0.0 for mid in ids if mid}
        if not diagnostic:
            return None, "", INCOMPLETE_EVIDENCE, None, None
        return diagnostic, "untrusted-diagnostic", None, None, None
    summary = build_battle_evidence(
        battle_id,
        trusted_rows,
        fmt_cfg,
        judge_scores=None,
        format_id=format_id,
    )
    decision = decide_winner(summary, fmt_cfg)
    det_scores = deterministic_scores(decision, summary)
    if not det_scores:
        return None, "", INCOMPLETE_EVIDENCE, summary, decision
    return det_scores, "arena-score-v1", None, summary, decision


def _already_finalized_payload(
    *,
    status: str,
    results: list | None = None,
    scores: dict | None = None,
    score_rows: list | None = None,
) -> dict[str, Any]:
    return {
        "ok": True,
        "status": status,
        "already_finalized": True,
        "authoritative": _stored_completion_is_authoritative(
            status, results or [], score_rows or []
        ),
        "results": results or [],
        "scores": scores or {},
    }


def _stored_completion_is_authoritative(
    status: str, results: list, score_rows: list
) -> bool:
    if status != "completed":
        return False
    verifs = [
        str(
            item.get("verification_status")
            if isinstance(item, dict)
            else getattr(item, "verification_status", "")
        )
        for item in (results or [])
    ]
    if any(v in {"verified_pass", "verified_fail"} for v in verifs):
        return True
    justifications = []
    for item in score_rows or []:
        if isinstance(item, dict):
            justifications.append(str(item.get("justification") or ""))
        else:
            justifications.append(str(getattr(item, "justification", "") or ""))
    if justifications:
        return any("arena-score-v1" in j for j in justifications)
    return False


def _retryable_incomplete_payload(status: str, error: str | None = None) -> dict[str, Any]:
    return {
        "ok": False,
        "status": status,
        "already_finalized": False,
        "authoritative": False,
        "retryable": True,
        "error": error or INCOMPLETE_EVIDENCE,
        "scores": {},
        "results": [],
    }


def _parse_marked_json(artifact: str, marker: str) -> dict | None:
    if marker not in str(artifact or ""):
        return None
    raw = str(artifact).split(marker, 1)[1].strip()
    try:
        payload = json.loads(raw)
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def _iter_round_like(session: Session | None, battle_id: str) -> list[dict]:
    rows: list[dict] = []
    try:
        if session is not None:
            from .persistence.models import Round

            round_rows = session.scalars(
                select(Round)
                .where(Round.battle_id == battle_id)
                .order_by(Round.created_at)
            ).all()
            for idx, r in enumerate(round_rows):
                rows.append(
                    {
                        "phase": r.phase,
                        "model_id": r.model_id,
                        "artifact": r.artifact,
                        "sequence": idx,
                    }
                )
        else:
            for idx, r in enumerate(service.rounds_list(battle_id)):
                item = dict(r)
                item.setdefault("sequence", idx)
                rows.append(item)
    except Exception:
        pass
    return rows


def _extract_trusted_verifications(
    battle_id: str,
    session: Session | None = None,
) -> list[dict]:
    """Load host-persisted trusted verifier records (not sandbox EXECUTOR_RESULT)."""
    found: list[dict] = []
    for idx, r in enumerate(_iter_round_like(session, battle_id)):
        payload = _parse_marked_json(str(r.get("artifact") or ""), TRUSTED_VERIFICATION_MARKER)
        if not payload:
            continue
        phase = str(payload.get("phase") or r.get("phase") or "main")
        role = str(payload.get("role") or "fighter")
        model_id = str(payload.get("model_id") or r.get("model_id") or "")
        item = {**payload, "phase": phase, "role": role, "model_id": model_id}
        found.append(item)
        del idx
    return found


def _merge_trusted_authority(
    telemetry: list[dict],
    trusted: list[dict],
    *,
    require_trusted: bool,
) -> list[dict]:
    """Sandbox EXECUTOR_RESULT is telemetry only. Trusted verifier owns pass/fail."""
    if not require_trusted:
        return [sanitize_untrusted_executor_payload(item) for item in telemetry]
    if not trusted:
        return []

    by_identity: dict[tuple[str, str, str], dict] = {}
    by_model: dict[str, dict] = {}
    bb_trusted: list[dict] = []
    for tv in trusted:
        _bid, phase, role, model_id = normalize_participant_identity(
            str(tv.get("battle_id") or ""),
            phase=str(tv.get("phase") or "main"),
            role=str(tv.get("role") or "fighter"),
            model_id=str(tv.get("model_id") or ""),
        )
        key = (phase, role, model_id)
        by_identity[key] = tv
        if model_id:
            by_model.setdefault(model_id, tv)
        if str(tv.get("kind") or "").strip().lower() == "builder_breaker":
            bb_trusted.append(tv)

    merged: list[dict] = []
    used: set[int] = set()
    for tel in telemetry:
        _bid, phase, role, model_id = normalize_participant_identity(
            str(tel.get("battle_id") or ""),
            phase=str(tel.get("phase") or "main"),
            role=str(tel.get("role") or "fighter"),
            model_id=str(tel.get("model_id") or ""),
        )
        tv = by_identity.get((phase, role, model_id)) or by_model.get(model_id)
        if tv is None and bb_trusted:
            tv = bb_trusted[0]
        if tv is None:
            continue
        used.add(id(tv))
        item = dict(tel)
        passed = bool(tv.get("passed"))
        kind = str(tv.get("kind") or "solo").strip().lower()
        if kind == "builder_breaker":
            if role == "builder":
                passed = bool(tv.get("builder_passed", tv.get("passed")))
            elif role == "breaker":
                passed = bool(tv.get("breaker_passed", tv.get("passed")))
        stored_vs = str(tv.get("verification_status") or "")
        outcome = str(tv.get("outcome") or "")
        if stored_vs == "not_attempted":
            item["passed"] = False
            item["outcome"] = "VERIFICATION_NOT_ATTEMPTED"
            item["verification_status"] = "not_attempted"
        elif stored_vs == "infra_failure" or is_infra_outcome(outcome):
            item["outcome"] = outcome if is_infra_outcome(outcome) else "VERIFY_ERROR"
            item["passed"] = False
            item["verification_status"] = "infra_failure"
        else:
            item["passed"] = passed
            item["outcome"] = "TEST_PASS" if passed else "TEST_FAIL"
            item["verification_status"] = (
                "verified_pass" if item["passed"] else "verified_fail"
            )
        if tv.get("executor_outcome"):
            item["executor_outcome"] = tv.get("executor_outcome")
        elif tel.get("executor_outcome"):
            item["executor_outcome"] = tel.get("executor_outcome")
        if tv.get("terminal_reason"):
            item["terminal_reason"] = tv.get("terminal_reason")
        elif tel.get("terminal_reason"):
            item["terminal_reason"] = tel.get("terminal_reason")
        item["phase"] = phase
        item["role"] = role
        item["model_id"] = model_id
        item["_trusted"] = True
        merged.append(item)

    for tv in trusted:
        if id(tv) in used:
            continue
        _bid, phase, role, model_id = normalize_participant_identity(
            str(tv.get("battle_id") or ""),
            phase=str(tv.get("phase") or "main"),
            role=str(tv.get("role") or "fighter"),
            model_id=str(tv.get("model_id") or ""),
        )
        if not model_id:
            continue
        passed = bool(tv.get("passed"))
        if str(tv.get("kind") or "").strip().lower() == "builder_breaker":
            if role == "builder":
                passed = bool(tv.get("builder_passed", tv.get("passed")))
            elif role == "breaker":
                passed = bool(tv.get("breaker_passed", tv.get("passed")))
        stored_vs = str(tv.get("verification_status") or "")
        if stored_vs == "not_attempted":
            outcome = "VERIFICATION_NOT_ATTEMPTED"
            passed = False
            verif_status = "not_attempted"
        elif stored_vs == "infra_failure" or is_infra_outcome(str(tv.get("outcome") or "")):
            outcome = str(tv.get("outcome") or "VERIFY_ERROR")
            passed = False
            verif_status = "infra_failure"
        else:
            outcome = "TEST_PASS" if passed else "TEST_FAIL"
            verif_status = "verified_pass" if passed else "verified_fail"
        extra = {
            "model_id": model_id,
            "phase": phase,
            "role": role,
            "passed": passed,
            "outcome": outcome,
            "steps": 0,
            "artifact_checks": {"present": [], "missing": []},
            "verification_status": verif_status,
            "_trusted": True,
        }
        if tv.get("executor_outcome"):
            extra["executor_outcome"] = tv.get("executor_outcome")
        if tv.get("terminal_reason"):
            extra["terminal_reason"] = tv.get("terminal_reason")
        merged.append(extra)
    return merged


def _extract_results_from_sources(
    battle_id: str,
    databases,
    database_id: str,
    session: Session | None = None,
) -> list[dict]:
    """Load EXECUTOR_RESULT telemetry from rounds (then events). One per identity."""
    del databases, database_id
    candidates_by_identity: dict[tuple[str, str, str], list[tuple[int, dict]]] = {}

    for idx, r in enumerate(_iter_round_like(session, battle_id)):
        payload = _parse_marked_json(str(r.get("artifact") or ""), EXECUTOR_RESULT_MARKER)
        if not payload:
            continue
        _bid, phase, role, model_id = normalize_participant_identity(
            battle_id,
            phase=str(payload.get("phase") or r.get("phase") or "main"),
            role=str(payload.get("role") or "fighter"),
            model_id=str(payload.get("model_id") or r.get("model_id") or ""),
        )
        key = (phase, role, model_id)
        seq = int(r.get("sequence") or idx)
        item = sanitize_untrusted_executor_payload(
            {**payload, "phase": phase, "role": role, "model_id": model_id}
        )
        candidates_by_identity.setdefault(key, []).append((seq, item))

    if not candidates_by_identity:
        try:
            events = service.events_load(battle_id)
            for idx, event in enumerate(events):
                if not isinstance(event, dict) or event.get("type") != "result":
                    continue
                artifact = str((event.get("data") or {}).get("artifact") or "")
                payload = _parse_marked_json(artifact, EXECUTOR_RESULT_MARKER)
                if not payload:
                    continue
                _bid, phase, role, model_id = normalize_participant_identity(
                    battle_id,
                    phase=str(payload.get("phase") or "main"),
                    role=str(payload.get("role") or "fighter"),
                    model_id=str(payload.get("model_id") or ""),
                )
                key = (phase, role, model_id)
                item = sanitize_untrusted_executor_payload(
                    {**payload, "phase": phase, "role": role, "model_id": model_id}
                )
                candidates_by_identity.setdefault(key, []).append((idx, item))
        except Exception:
            pass

    out: list[dict] = []
    for key, cand_list in candidates_by_identity.items():
        def _score_cand(entry: tuple[int, dict]) -> tuple[int, int]:
            seq, p = entry
            # Sequence only. Sandbox TEST_PASS/TEST_FAIL must not win selection.
            return (seq, 0)

        best_cand = max(cand_list, key=_score_cand)[1]
        out.append(best_cand)
        del key

    return out


def _resolve_results_for_finalize(
    battle_id: str,
    battle_dict: dict,
    *,
    override_results: list[dict] | None,
    session: Session | None,
    databases,
    database_id: str,
) -> list[dict]:
    if override_results is not None:
        tagged = []
        for row in override_results:
            item = dict(row)
            item["_trusted"] = True
            tagged.append(item)
        return tagged
    telemetry = _extract_results_from_sources(
        battle_id, databases, database_id, session=session
    )
    require_trusted = bool(str(battle_dict.get("target_id") or "").strip())
    trusted: list[dict] = []
    if require_trusted:
        trusted = _extract_trusted_verifications(battle_id, session=session)
    return _merge_trusted_authority(
        telemetry, trusted, require_trusted=require_trusted
    )


def finalize_battle(
    battle_id: str,
    *,
    caller_status: str | None = None,
    caller_scores: dict[str, float] | None = None,
    judge_model: str | None = None,
    override_results: list[dict] | None = None,
) -> dict[str, Any]:
    """Execute centralized transactional & idempotent finalization.

    Sandbox/caller scores are untrusted hints only and are never persisted as
    authoritative values. Terminal battles cannot be resurrected.
    """
    del caller_status  # sandbox status is not authoritative
    databases = None
    database_id = ""
    evidence_summary = None
    decision = None
    status = "failed"
    effective_scores: dict[str, float] = {}
    score_source = ""
    finalize_error: str | None = None

    if using_postgres():
        with session_scope() as session:
            battle_row = session.scalars(
                select(Battle).where(Battle.id == battle_id).with_for_update()
            ).first()

            if battle_row is None:
                return {"ok": False, "status": "not_found", "error": "Battle not found"}

            if (
                battle_row.finalized_at is not None
                or is_terminal_battle_status(battle_row.status)
            ):
                res_rows = repositories.results.results_list_by_battle(session, battle_id)
                score_rows = repositories.scores.score_list(session, battle_id)
                return _already_finalized_payload(
                    status=battle_row.status,
                    results=[
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
                            "finalized_at": r.finalized_at.isoformat() if r.finalized_at else None,
                        }
                        for r in res_rows
                    ],
                    scores={s.model_id: s.score for s in score_rows},
                    score_rows=score_rows,
                )

            if battle_row.status not in ACTIVE_FINALIZE_STATUSES:
                return _already_finalized_payload(status=battle_row.status)

            battle_dict = {
                "id": battle_row.id,
                "user_id": battle_row.user_id,
                "format_id": battle_row.format_id,
                "status": battle_row.status,
                "arena_size": battle_row.arena_size,
                "model_ids": repositories.battles.battle_model_ids(session, battle_id),
                "ranked": battle_row.ranked,
                "target_id": battle_row.target_id,
                "context_mode": (battle_row.battle_config or {}).get("context_mode", "strict")
                if isinstance(battle_row.battle_config, dict)
                else "strict",
                "battle_config": battle_row.battle_config or {},
            }

            results = _resolve_results_for_finalize(
                battle_id,
                battle_dict,
                override_results=override_results,
                session=session,
                databases=databases,
                database_id=database_id,
            )

            fmt_cfg: dict = {}
            try:
                fmt_row = repositories.formats.format_get(session, battle_row.format_id)
                fmt_cfg = fmt_row.config if fmt_row else {}
            except Exception:
                fmt_cfg = {}
            try:
                fmt_cfg = resolve_battle_config(battle_dict, fmt_cfg)
            except FrozenConfigError:
                fmt_cfg = dict(battle_row.battle_config or {}) or fmt_cfg

            effective_scores, score_source, finalize_error, evidence_summary, decision = (
                derive_trusted_scores(
                    battle_id=battle_id,
                    results=results,
                    fmt_cfg=fmt_cfg,
                    battle_model_ids=list(battle_dict["model_ids"]),
                    format_id=battle_row.format_id,
                    untrusted_hint_scores=caller_scores,
                )
            )
            effective_scores = dict(effective_scores or {})

            now_utc = datetime.now(timezone.utc)
            if not effective_scores:
                return _retryable_incomplete_payload(
                    battle_row.status, finalize_error or INCOMPLETE_EVIDENCE
                )

            status = "completed"
            seen_identities: set[tuple[str, str, str]] = set()
            for r_payload in results:
                _bid, phase, role, mid = normalize_participant_identity(
                    battle_id,
                    phase=str(r_payload.get("phase") or "main"),
                    role=str(r_payload.get("role") or "fighter"),
                    model_id=str(r_payload.get("model_id") or ""),
                )
                if not mid:
                    continue
                ident = (phase, role, mid)
                if ident in seen_identities:
                    continue
                seen_identities.add(ident)
                sc = float(effective_scores.get(mid, 0.0))
                passed = bool(r_payload.get("passed"))
                term_reason = str(
                    r_payload.get("executor_outcome")
                    or r_payload.get("terminal_reason")
                    or r_payload.get("outcome")
                    or ("TEST_PASS" if passed else "TEST_FAIL")
                )
                if not r_payload.get("_trusted"):
                    sc = 0.0
                    passed = False
                    term_reason = UNTRUSTED_EXECUTION
                part_status = participant_status_from_outcome(
                    term_reason, passed=passed
                )
                stored_vs = str(r_payload.get("verification_status") or "")
                if is_infra_outcome(term_reason):
                    verif_status = "infra_failure"
                    passed = False
                elif stored_vs in {
                    "unverified",
                    "not_attempted",
                    "verified_pass",
                    "verified_fail",
                    "infra_failure",
                }:
                    verif_status = stored_vs
                    if stored_vs in {"unverified", "not_attempted"}:
                        passed = False
                else:
                    verif_status = "verified_pass" if passed else "verified_fail"
                if r_payload.get("_trusted"):
                    art_checks = r_payload.get("artifact_checks") or {}
                    artifact_refs = list(art_checks.get("present") or [])
                    metrics = {
                        "steps": r_payload.get("steps", 0),
                        "turns": r_payload.get("turns", 0),
                        "duration_ms": r_payload.get("duration_ms", 0),
                        "tool_errors": r_payload.get("tool_errors", 0),
                        "parse_errors": r_payload.get("parse_errors", 0),
                    }
                else:
                    artifact_refs = []
                    metrics = {}
                repositories.results.result_upsert(
                    session,
                    battle_id=battle_id,
                    phase=phase,
                    role=role,
                    model_id=mid,
                    status=part_status,
                    passed=passed,
                    score=sc,
                    verification_status=verif_status,
                    termination_reason=term_reason,
                    artifact_refs=artifact_refs,
                    metrics=metrics,
                    result_version=1,
                    finalized_at=now_utc,
                )

            score_judge = judge_model or "arena-deterministic"
            for mid, sc in effective_scores.items():
                repositories.scores.score_insert(
                    session,
                    battle_id=battle_id,
                    model_id=mid,
                    score=float(sc),
                    judge_model=score_judge,
                    justification=f"Finalized via {score_source}",
                )

            learnable = score_source == "arena-score-v1" and all(
                is_learnable_model_outcome(str(r.get("outcome") or "")) for r in results
            )
            if is_ranked_battle(battle_dict, fmt_cfg) and learnable:
                _apply_leaderboard_elo_pg(session, battle_dict, effective_scores)
                _apply_self_learning_pg(session, battle_dict, results)

            battle_row.status = "completed"
            battle_row.failure_reason = None
            battle_row.completed_at = now_utc
            battle_row.finalized_at = now_utc
            session.flush()

    else:
        battle_dict = service.battle_get("", battle_id)
        if battle_dict is None:
            return {"ok": False, "status": "not_found", "error": "Battle not found"}

        current_status = str(battle_dict.get("status") or "")
        if is_terminal_battle_status(current_status):
            score_rows = service.scores_list(battle_id)
            return _already_finalized_payload(
                status=current_status,
                scores={s["model_id"]: s["score"] for s in score_rows},
                score_rows=score_rows,
            )
        if current_status not in ACTIVE_FINALIZE_STATUSES:
            return _already_finalized_payload(status=current_status)

        results = _resolve_results_for_finalize(
            battle_id,
            battle_dict,
            override_results=override_results,
            session=None,
            databases=databases,
            database_id=database_id,
        )
        fmt_cfg = {}
        try:
            fmt_record = service.format_get(str(battle_dict.get("format_id") or ""))
            fmt_cfg = (fmt_record or {}).get("config") or {}
        except Exception:
            fmt_cfg = {}
        try:
            fmt_cfg = resolve_battle_config(battle_dict, fmt_cfg)
        except FrozenConfigError:
            fmt_cfg = dict(battle_dict.get("battle_config") or {}) or fmt_cfg

        effective_scores, score_source, finalize_error, evidence_summary, decision = (
            derive_trusted_scores(
                battle_id=battle_id,
                results=results,
                fmt_cfg=fmt_cfg,
                battle_model_ids=list(battle_dict.get("model_ids") or []),
                format_id=str(battle_dict.get("format_id") or ""),
                untrusted_hint_scores=caller_scores,
            )
        )
        effective_scores = dict(effective_scores or {})

        if not effective_scores:
            return _retryable_incomplete_payload(
                current_status, finalize_error or INCOMPLETE_EVIDENCE
            )
        status = "completed"
        score_judge = judge_model or "arena-deterministic"
        for mid, sc in effective_scores.items():
            service.score_upsert(
                battle_id,
                mid,
                float(sc),
                judge_model=score_judge,
                justification=f"Finalized via {score_source}",
            )
        learnable = score_source == "arena-score-v1" and all(
            is_learnable_model_outcome(str(r.get("outcome") or "")) for r in results
        )
        if is_ranked_battle(battle_dict, fmt_cfg) and learnable:
            service.leaderboard_apply_result(
                str(battle_dict.get("format_id") or ""),
                list(battle_dict.get("model_ids") or []),
                effective_scores,
            )
            from .internal_router import _apply_self_learning

            _apply_self_learning(databases, database_id, battle_dict, battle_id, results)
        service.battle_update(
            battle_id,
            {"status": "completed", "completed_at": datetime.now(timezone.utc)},
        )

    if evidence_summary is not None:
        event_bus.publish(
            battle_id,
            {"type": "evidence_summary", "data": {**evidence_summary, "decision": decision}},
        )
    if status == "completed" and effective_scores and score_source == "arena-score-v1":
        from .battle_public import (
            aggregate_verification_status,
            public_winner,
            verified_solution_from_results,
        )

        verified = bool((decision or {}).get("verified_solution")) or verified_solution_from_results(
            results
        )
        event_bus.publish(
            battle_id,
            {
                "type": "scores",
                "data": {
                    "scores": effective_scores,
                    "authoritative": True,
                    "source": score_source,
                    "verified_solution": verified,
                    "verification_status": aggregate_verification_status(results),
                    "winner": public_winner(
                        verified_solution=verified, results=results
                    ),
                    "termination_reason": (results or [{}])[0].get("executor_outcome")
                    or (results or [{}])[0].get("terminal_reason")
                    or (results or [{}])[0].get("outcome")
                    if results
                    else None,
                },
            },
        )
    event_bus.publish(battle_id, {"type": "battle_status", "data": {"status": status}})

    payload = {
        "ok": True,
        "status": status,
        "already_finalized": False,
        "authoritative": status == "completed" and score_source == "arena-score-v1",
        "scores": effective_scores,
    }
    if finalize_error:
        payload["error"] = finalize_error
    return payload


def _apply_leaderboard_elo_pg(
    session: Session,
    battle: dict,
    scores: dict[str, float],
) -> None:
    """Apply Elo updates with sorted row locks on LeaderboardEntry to eliminate lost updates.

    Handles nonexistent rows race-safely via PostgreSQL ON CONFLICT DO NOTHING before acquiring
    the row lock with SELECT ... FOR UPDATE.
    """
    from . import elo as elo_mod

    model_ids = list(battle.get("model_ids") or [])
    if len(model_ids) < 2:
        return

    target_id = str(battle.get("target_id") or "").strip()
    format_id = str(battle.get("format_id") or "").strip()

    scopes = []
    if target_id:
        scopes.append(f"target:{target_id}")
    elif format_id:
        scopes.append(format_id)

    if "overall" not in scopes:
        scopes.append("overall")

    # Sort model IDs to acquire row locks in deterministic order across all concurrent battles
    sorted_mids = sorted(model_ids)

    for scope in scopes:
        locked_rows: dict[str, LeaderboardEntry] = {}
        for mid in sorted_mids:
            # Race-safe insert of nonexistent row
            insert_stmt = (
                pg_insert(LeaderboardEntry)
                .values(
                    model_id=mid,
                    scope=scope,
                    elo=elo_mod.INITIAL_RATING,
                    games_played=0,
                )
                .on_conflict_do_nothing(index_elements=["model_id", "scope"])
            )
            session.execute(insert_stmt)

            # Re-select with exclusive row lock
            locked = session.scalars(
                select(LeaderboardEntry)
                .where(
                    LeaderboardEntry.model_id == mid,
                    LeaderboardEntry.scope == scope,
                )
                .with_for_update()
            ).one()
            locked_rows[mid] = locked

        # Compute pairwise rating adjustments
        for i in range(len(model_ids)):
            for j in range(i + 1, len(model_ids)):
                a, b = model_ids[i], model_ids[j]
                sa = float(scores.get(a, 0))
                sb = float(scores.get(b, 0))
                row_a = locked_rows[a]
                row_b = locked_rows[b]
                ra = row_a.elo
                rb = row_b.elo
                outcome_a = 1.0 if sa > sb else (0.0 if sa < sb else 0.5)
                new_a, new_b = elo_mod.update_ratings(ra, rb, outcome_a)
                ga = row_a.games_played + 1
                gb = row_b.games_played + 1
                row_a.elo = new_a
                row_a.games_played = ga
                row_b.elo = new_b
                row_b.games_played = gb


def _apply_self_learning_pg(
    session: Session,
    battle: dict,
    results: list[dict],
) -> None:
    """Apply skill attribution and winner memory learning inside the SAME Postgres session."""
    context_mode = str(battle.get("context_mode") or "strict").lower().strip()
    if context_mode not in ("adaptive", "assisted") or not results:
        return

    from .skills import compute_skill_attributions

    # 1. Skill attribution inside SAME session
    attributions = compute_skill_attributions(results)
    for role, attrs in attributions.items():
        for attr in attrs:
            skill_id = attr["skill_id"]
            outcome = attr["outcome"]
            _record_skill_outcome_session(session, str(skill_id), outcome)

    # 2. Winner memory learning through Change Set B policy (not a raw insert)
    passed_results = [r for r in results if r.get("passed")]
    if passed_results:
        winner = min(passed_results, key=lambda x: int(x.get("steps") or 999))
        format_id = str(battle.get("format_id") or "")
        user_id = str(battle.get("user_id") or "").strip()
        battle_id = str(battle.get("id") or "")
        if not user_id:
            return

        insight_text = (
            f"Battle {battle_id} format {format_id} "
            f"winner {winner.get('model_id')} chose {winner.get('chosen_skills')} "
            f"theory {str(winner.get('theory') or '')[:300]}."
        )

        from .memory import maybe_remember_pg

        maybe_remember_pg(
            session,
            insight=insight_text,
            battle_id=battle_id,
            model_id=str(winner.get("model_id") or ""),
            target_id=str(battle.get("target_id") or ""),
            role=str(winner.get("role") or "general"),
            visibility_class="model_private",
            format_name=format_id,
            chosen_skills=list(winner.get("chosen_skills") or []),
            theory=str(winner.get("theory") or ""),
            outcome=str(winner.get("outcome") or "TEST_PASS"),
            user_id=user_id,
            context_mode=context_mode,
        )


def _record_skill_outcome_session(
    session: Session,
    skill_name: str,
    outcome: str,
    tier: str = "general",
) -> None:
    """Transactional skill performance recording using a locked skill row."""
    from . import elo as elo_mod

    difficulty_offset = {"novice": 0.0, "general": 0.0, "advanced": -100.0, "expert": -200.0}
    row = repositories.skills.skill_lock_for_update(session, skill_name)
    current_elo = float(row.elo)
    expected = elo_mod.expected_score(
        current_elo + difficulty_offset.get(tier, 0.0), elo_mod.INITIAL_RATING
    )
    score = {"win": 1.0, "draw": 0.5, "loss": 0.0}[outcome]
    row.wins = (row.wins or 0) + (1 if outcome == "win" else 0)
    row.losses = (row.losses or 0) + (1 if outcome == "loss" else 0)
    row.draws = (row.draws or 0) + (1 if outcome == "draw" else 0)
    row.uses = (row.uses or 0) + 1
    row.success_rate = round((row.wins + 0.5 * row.draws) / max(1, row.uses), 3)
    row.elo = round(current_elo + elo_mod.K_FACTOR * (score - expected), 2)
    row.tier = tier
    row.last_used = datetime.now(timezone.utc)
