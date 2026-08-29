"""Owner-scoped pre-launch chat drafts for custom prompt battles."""

from __future__ import annotations

import json
from types import SimpleNamespace

from appwrite.exception import AppwriteException
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException

from . import db
from .auth import get_current_user, require_owner
from .battles import MAX_ACTIVE_BATTLES, _validate_model_ids, active_battle_count
from .custom_battles import (
    CUSTOM_FORMAT_NAME,
    MAX_MESSAGE_CHARS,
    FrozenConfigError,
    SpecValidationError,
    architect_complete,
    compile_format_config,
    compile_quick_spec,
    compile_verified_spec,
    draft_out,
    empty_spec,
    encode_transcript,
    now,
    spec_hash,
    validate_spec,
)
from .providers import is_host_model
from .schemas import (
    BattleDraftCreate,
    BattleDraftLaunch,
    BattleDraftMessage,
    BattleDraftSpecPatch,
)

router = APIRouter(prefix="/battle-drafts", tags=["battle-drafts"])


# --- Appwrite-era helpers (unchanged behavior) ---------------------------------


def _get_owned_draft(databases, database_id: str, draft_id: str, user_id: str):
    try:
        doc = databases.get_document(database_id, "battle_drafts", draft_id)
    except AppwriteException as exc:
        raise HTTPException(status_code=404, detail="Draft not found") from exc
    require_owner(doc.data.get("user_id"), user_id, resource="draft")
    return doc


def _custom_format_id(databases, database_id: str) -> str:
    from appwrite.query import Query

    res = databases.list_documents(
        database_id,
        "formats",
        queries=[Query.equal("name", CUSTOM_FORMAT_NAME), Query.limit(1)],
    )
    if not res.documents:
        raise HTTPException(status_code=500, detail="Custom prompt battle format is not seeded")
    return res.documents[0].id


def _parse_transcript(raw) -> list[dict]:
    if isinstance(raw, list):
        return list(raw)
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return []
        if isinstance(parsed, list):
            return parsed
    return []


def _parse_spec(raw) -> dict:
    if isinstance(raw, dict):
        return dict(raw)
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        if isinstance(parsed, dict):
            return parsed
    return {}


def _save_draft(databases, database_id: str, draft_id: str, payload: dict) -> None:
    databases.update_document(database_id, "battle_drafts", draft_id, payload)


# --- Postgres helpers ----------------------------------------------------------


def _pg_draft_doc(row) -> SimpleNamespace:
    """Wrap a BattleDraft row so draft_out() renders it exactly like Appwrite."""
    data = {
        "user_id": row.user_id,
        "mode": row.mode,
        "transcript": json.dumps(list(row.transcript or [])),
        "spec": dict(row.spec or {}),
        "revision": int(row.revision or 0),
        "status": row.status or "draft",
        "launched_battle_id": row.launched_battle_id,
        "architect_error": row.architect_error,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }
    return SimpleNamespace(id=row.id, data=data)


def _pg_custom_format_id() -> str:
    from .persistence import repositories
    from .persistence.session import session_scope

    with session_scope() as session:
        for row in repositories.formats.format_list(session):
            if row.name == CUSTOM_FORMAT_NAME:
                return row.id
    raise HTTPException(status_code=500, detail="Custom prompt battle format is not seeded")


def _compile_message(
    transcript: list[dict],
    spec: dict,
    mode: str,
    user_id: str,
    architect_provider_id: str | None,
):
    """Run the architect compiler on a transcript; return (transcript, spec, status, error)."""
    architect_error = ""
    status = "draft"
    try:
        encode_transcript(transcript)
        if mode == "verified":
            def _llm(messages):
                return architect_complete(
                    user_id, messages, provider_id=architect_provider_id
                )

            spec = compile_verified_spec(transcript, llm_complete=_llm)
            transcript.append(
                {
                    "role": "architect",
                    "content": f"Compiled verified spec: {spec.get('title')}",
                    "ts": now(),
                }
            )
        else:
            spec = compile_quick_spec(transcript)
            transcript.append(
                {
                    "role": "architect",
                    "content": f"Compiled quick spec: {spec.get('title')}",
                    "ts": now(),
                }
            )
        status = "ready"
    except (SpecValidationError, HTTPException) as exc:
        detail = exc.detail if isinstance(exc, HTTPException) else str(exc)
        architect_error = str(detail)
        transcript.append(
            {"role": "architect", "content": f"Could not compile spec: {architect_error}", "ts": now()}
        )
        if isinstance(exc, HTTPException) and exc.status_code >= 500:
            raise
    return transcript, spec, status, architect_error


# --- Routes --------------------------------------------------------------------


@router.post("", status_code=201)
def create_draft(body: BattleDraftCreate, user_id: str = Depends(get_current_user)):
    from .persistence import service

    mode = body.mode
    spec = empty_spec(mode)
    if service.using_postgres():
        from .persistence import repositories
        from .persistence.session import session_scope

        with session_scope() as session:
            row = repositories.drafts.draft_create(
                session, user_id=user_id, mode=mode, transcript=[], spec=spec
            )
            doc = _pg_draft_doc(row)
        return draft_out(doc)
    databases = db.get_databases()
    database_id = db.get_database_id()
    payload = {
        "user_id": user_id,
        "mode": mode,
        "transcript": json.dumps([]),
        "spec": json.dumps(spec),
        "revision": 0,
        "status": "draft",
        "created_at": now(),
        "updated_at": now(),
    }
    doc = databases.create_document(database_id, "battle_drafts", "unique()", payload)
    return draft_out(doc)


@router.get("/{draft_id}")
def get_draft(draft_id: str, user_id: str = Depends(get_current_user)):
    from .persistence import service

    if service.using_postgres():
        from .persistence import repositories
        from .persistence.session import session_scope

        with session_scope() as session:
            row = repositories.drafts.draft_get(session, draft_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Draft not found")
        require_owner(row.user_id, user_id, resource="draft")
        return draft_out(_pg_draft_doc(row))
    databases = db.get_databases()
    database_id = db.get_database_id()
    doc = _get_owned_draft(databases, database_id, draft_id, user_id)
    return draft_out(doc)


@router.post("/{draft_id}/messages")
def post_message(
    draft_id: str,
    body: BattleDraftMessage,
    user_id: str = Depends(get_current_user),
):
    from .persistence import service

    if service.using_postgres():
        from .persistence import repositories
        from .persistence.session import session_scope

        with session_scope() as session:
            row = repositories.drafts.draft_get(session, draft_id)
            if row is None:
                raise HTTPException(status_code=404, detail="Draft not found")
            require_owner(row.user_id, user_id, resource="draft")
            if row.status == "launched":
                raise HTTPException(status_code=409, detail="Draft already launched")
            content = body.content.strip()
            if not content:
                raise HTTPException(status_code=400, detail="Message is empty")
            if len(content) > MAX_MESSAGE_CHARS:
                raise HTTPException(status_code=400, detail="Message too long")
            transcript = list(row.transcript or [])
            transcript.append({"role": "user", "content": content, "ts": now()})
            mode = row.mode or "quick"
            transcript, spec, status, architect_error = _compile_message(
                transcript,
                dict(row.spec or {}),
                mode,
                user_id,
                body.architect_provider_id,
            )
            updated, _applied = repositories.drafts.draft_update(
                session,
                draft_id,
                expected_revision=row.revision,
                transcript=transcript,
                spec=spec,
                status=status,
                architect_error=architect_error,
            )
            if updated is None:
                raise HTTPException(status_code=404, detail="Draft not found")
            return draft_out(_pg_draft_doc(updated))
    databases = db.get_databases()
    database_id = db.get_database_id()
    doc = _get_owned_draft(databases, database_id, draft_id, user_id)
    if doc.data.get("status") == "launched":
        raise HTTPException(status_code=409, detail="Draft already launched")
    content = body.content.strip()
    if not content:
        raise HTTPException(status_code=400, detail="Message is empty")
    if len(content) > MAX_MESSAGE_CHARS:
        raise HTTPException(status_code=400, detail="Message too long")
    transcript = _parse_transcript(doc.data.get("transcript"))
    transcript.append({"role": "user", "content": content, "ts": now()})
    mode = doc.data.get("mode") or "quick"
    spec = _parse_spec(doc.data.get("spec"))
    transcript, spec, status, architect_error = _compile_message(
        transcript, spec, mode, user_id, body.architect_provider_id
    )
    packed = encode_transcript(transcript)
    revision = int(doc.data.get("revision") or 0) + 1
    _save_draft(
        databases,
        database_id,
        draft_id,
        {
            "transcript": packed,
            "spec": json.dumps(spec),
            "revision": revision,
            "status": status,
            "updated_at": now(),
            "architect_error": architect_error,
        },
    )
    return draft_out(databases.get_document(database_id, "battle_drafts", draft_id))


@router.patch("/{draft_id}/spec")
def patch_spec(
    draft_id: str,
    body: BattleDraftSpecPatch,
    user_id: str = Depends(get_current_user),
):
    from .persistence import service

    if service.using_postgres():
        from .persistence import repositories
        from .persistence.session import session_scope

        with session_scope() as session:
            row = repositories.drafts.draft_get(session, draft_id)
            if row is None:
                raise HTTPException(status_code=404, detail="Draft not found")
            require_owner(row.user_id, user_id, resource="draft")
            if row.status == "launched":
                raise HTTPException(status_code=409, detail="Draft already launched")
            mode = row.mode or "quick"
            current = dict(row.spec or {})
            incoming = body.model_dump(exclude_unset=True)
            current.update({k: v for k, v in incoming.items() if v is not None})
            try:
                spec = validate_spec(current, mode, dry_run=mode == "verified")
                status = "ready"
                architect_error = ""
            except SpecValidationError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            updated, _applied = repositories.drafts.draft_update(
                session,
                draft_id,
                expected_revision=row.revision,
                spec=spec,
                status=status,
                architect_error=architect_error,
            )
            if updated is None:
                raise HTTPException(status_code=404, detail="Draft not found")
            return draft_out(_pg_draft_doc(updated))
    databases = db.get_databases()
    database_id = db.get_database_id()
    doc = _get_owned_draft(databases, database_id, draft_id, user_id)
    if doc.data.get("status") == "launched":
        raise HTTPException(status_code=409, detail="Draft already launched")
    mode = doc.data.get("mode") or "quick"
    current = _parse_spec(doc.data.get("spec"))
    incoming = body.model_dump(exclude_unset=True)
    current.update({k: v for k, v in incoming.items() if v is not None})
    try:
        spec = validate_spec(current, mode, dry_run=mode == "verified")
        status = "ready"
        architect_error = ""
    except SpecValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    revision = int(doc.data.get("revision") or 0) + 1
    _save_draft(
        databases,
        database_id,
        draft_id,
        {
            "spec": json.dumps(spec),
            "revision": revision,
            "status": status,
            "updated_at": now(),
            "architect_error": architect_error,
        },
    )
    return draft_out(databases.get_document(database_id, "battle_drafts", draft_id))


@router.post("/{draft_id}/launch", status_code=201)
def launch_draft(
    draft_id: str,
    body: BattleDraftLaunch,
    background: BackgroundTasks,
    user_id: str = Depends(get_current_user),
):
    from .persistence import service

    if service.using_postgres():
        from .persistence import repositories
        from .persistence.session import session_scope

        with session_scope() as session:
            row = repositories.drafts.draft_get(session, draft_id)
            if row is None:
                raise HTTPException(status_code=404, detail="Draft not found")
            require_owner(row.user_id, user_id, resource="draft")
            current_rev = int(row.revision or 0)
            if body.revision != current_rev:
                raise HTTPException(
                    status_code=409,
                    detail=f"spec revision mismatch (have {current_rev}, got {body.revision})",
                )
            if row.status == "launched" and row.launched_battle_id:
                return {
                    "id": row.launched_battle_id,
                    "status": "queued",
                    "draft_id": draft_id,
                    "spec_hash": spec_hash(dict(row.spec or {})),
                }
            if row.status != "ready":
                raise HTTPException(status_code=400, detail="Spec is not approved")
            if len(set(body.model_ids)) != len(body.model_ids):
                raise HTTPException(status_code=400, detail="model_ids must be unique")
            spec = dict(row.spec or {})
            mode = row.mode or "quick"
            try:
                frozen = compile_format_config(
                    spec,
                    mode=mode,
                    n_fighters=len(body.model_ids),
                    transcript=list(row.transcript or []),
                )
                if mode == "verified":
                    validate_spec(spec, mode, dry_run=True)
            except (SpecValidationError, FrozenConfigError) as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            _validate_model_ids(None, None, user_id, body.model_ids)
            if body.judge_provider_id and not is_host_model(body.judge_provider_id):
                _validate_model_ids(None, None, user_id, [body.judge_provider_id])
            if active_battle_count(None, None, user_id) >= MAX_ACTIVE_BATTLES:
                raise HTTPException(
                    status_code=429,
                    detail=f"Concurrency limit reached: {MAX_ACTIVE_BATTLES} active battles",
                )
            digest = spec_hash(spec)
            payload = {
                "user_id": user_id,
                "format_id": _pg_custom_format_id(),
                "model_ids": body.model_ids,
                "arena_size": len(body.model_ids),
                "status": "queued",
                "timeout_seconds": body.timeout_seconds,
                "round_visibility": "isolated",
                "saved": body.save,
                "draft_id": draft_id,
                "battle_config": frozen,
                "spec_hash": digest,
                "custom_title": str(spec.get("title") or CUSTOM_FORMAT_NAME)[:200],
                "ranked": False,
            }
            if body.judge_provider_id:
                payload["judge_provider_id"] = body.judge_provider_id
            battle = service.battle_create_raw(user_id, payload)
            repositories.drafts.draft_update(
                session,
                draft_id,
                expected_revision=current_rev,
                status="launched",
                launched_battle_id=battle["id"],
            )
        import os

        from . import mock_runner, sandbox_launcher

        if os.environ.get("ARENA_USE_MOCK") == "1":
            background.add_task(mock_runner.run_battle, battle["id"])
        else:
            background.add_task(sandbox_launcher.start_battle, battle["id"])
        return {
            "id": battle["id"],
            "status": "queued",
            "draft_id": draft_id,
            "spec_hash": digest,
        }
    databases = db.get_databases()
    database_id = db.get_database_id()
    doc = _get_owned_draft(databases, database_id, draft_id, user_id)
    current_rev = int(doc.data.get("revision") or 0)
    if body.revision != current_rev:
        raise HTTPException(
            status_code=409,
            detail=f"spec revision mismatch (have {current_rev}, got {body.revision})",
        )
    if doc.data.get("status") == "launched" and doc.data.get("launched_battle_id"):
        return {
            "id": doc.data["launched_battle_id"],
            "status": "queued",
            "draft_id": draft_id,
            "spec_hash": spec_hash(_parse_spec(doc.data.get("spec"))),
        }
    if doc.data.get("status") != "ready":
        raise HTTPException(status_code=400, detail="Spec is not approved")
    if len(set(body.model_ids)) != len(body.model_ids):
        raise HTTPException(status_code=400, detail="model_ids must be unique")
    spec = _parse_spec(doc.data.get("spec"))
    mode = doc.data.get("mode") or "quick"
    try:
        frozen = compile_format_config(
            spec,
            mode=mode,
            n_fighters=len(body.model_ids),
            transcript=_parse_transcript(doc.data.get("transcript")),
        )
        if mode == "verified":
            validate_spec(spec, mode, dry_run=True)
    except (SpecValidationError, FrozenConfigError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _validate_model_ids(databases, database_id, user_id, body.model_ids)
    if body.judge_provider_id and not is_host_model(body.judge_provider_id):
        _validate_model_ids(databases, database_id, user_id, [body.judge_provider_id])
    if active_battle_count(databases, database_id, user_id) >= MAX_ACTIVE_BATTLES:
        raise HTTPException(
            status_code=429,
            detail=f"Concurrency limit reached: {MAX_ACTIVE_BATTLES} active battles",
        )
    digest = spec_hash(spec)
    payload = {
        "user_id": user_id,
        "format_id": _custom_format_id(databases, database_id),
        "model_ids": body.model_ids,
        "arena_size": len(body.model_ids),
        "status": "queued",
        "timeout_seconds": body.timeout_seconds,
        "round_visibility": "isolated",
        "saved": body.save,
        "draft_id": draft_id,
        "battle_config": json.dumps(frozen),
        "spec_hash": digest,
        "custom_title": str(spec.get("title") or CUSTOM_FORMAT_NAME)[:200],
        "ranked": False,
    }
    if body.judge_provider_id:
        payload["judge_provider_id"] = body.judge_provider_id
    battle = databases.create_document(database_id, "battles", "unique()", payload)
    _save_draft(
        databases,
        database_id,
        draft_id,
        {
            "status": "launched",
            "launched_battle_id": battle.id,
            "updated_at": now(),
        },
    )
    import os

    from . import mock_runner, sandbox_launcher

    if os.environ.get("ARENA_USE_MOCK") == "1":
        background.add_task(mock_runner.run_battle, battle.id)
    else:
        background.add_task(sandbox_launcher.start_battle, battle.id)
    return {
        "id": battle.id,
        "status": "queued",
        "draft_id": draft_id,
        "spec_hash": digest,
    }
