"""Start a battle: prefer Modal Sandbox; fall back to in-process runner."""

from __future__ import annotations

import json
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from . import db, event_bus
from .battle_token import issue_battle_token
from .config import settings
from .sandbox.client import HttpTransport, InternalClient
from .sandbox.runner import run_battle_loop


def _backend_public_url() -> str:
    return os.environ.get(
        "BACKEND_PUBLIC_URL",
        "https://sixscripts--agent-arena-backend-fastapi-app.modal.run",
    )


def _skills_dir() -> Path:
    mounted = Path("/opt/arena-skills")
    if mounted.is_dir():
        return mounted
    return Path(__file__).resolve().parents[2] / ".agents" / "skills"


def _targets_dir() -> Path:
    env_dir = os.environ.get("ARENA_TARGETS_DIR")
    if env_dir and Path(env_dir).is_dir():
        return Path(env_dir)
    mounted = Path("/opt/arena-targets")
    if mounted.is_dir():
        return mounted
    return Path(__file__).resolve().parents[2] / "targets" / "library"


def _load_battle(battle_id: str):
    from .persistence import service

    battle = service.battle_get("", battle_id)
    if battle is None:
        raise RuntimeError(f"Battle {battle_id} not found")
    format_cfg: dict = {}
    try:
        fmt_record = service.format_get(str(battle.get("format_id") or ""))
        format_cfg = (fmt_record or {}).get("config") or {}
    except Exception:
        format_cfg = {}
    from .custom_battles import resolve_battle_config

    cfg = resolve_battle_config(battle, format_cfg)
    return None, None, battle, cfg


def _set_status(databases, database_id: str, battle_id: str, status: str) -> None:
    from .persistence import service

    try:
        payload = {"status": status}
        if service.using_postgres():
            if status == "running":
                payload["started_at"] = datetime.now(timezone.utc)
            if status in ("completed", "failed", "cancelled"):
                payload["completed_at"] = datetime.now(timezone.utc)
        elif status == "running":
            payload["started_at"] = time.time()
        service.battle_update(battle_id, payload)
    except Exception:
        pass
    event_bus.publish(battle_id, {"type": "battle_status", "data": {"status": status}})


def run_in_process(battle_id: str) -> None:
    """Hermetic/local path: runner in this process using HttpTransport to self or Fake."""
    from .custom_battles import FrozenConfigError

    try:
        databases, database_id, battle, cfg = _load_battle(battle_id)
    except FrozenConfigError as exc:
        _fail_with_reason(battle_id, str(exc))
        return
    key = settings().get("INTERNAL_API_KEY") or ""
    base = os.environ.get("INTERNAL_BASE_URL") or "http://127.0.0.1:8000"
    # When no server, use direct in-memory bridge via local functions
    if not key or os.environ.get("ARENA_INPROCESS_DIRECT") == "1":
        _run_direct(battle_id, databases, database_id, battle, cfg)
        return
    # Use a battle-scoped token over HTTP so the local path exercises the same
    # auth contract as the real sandbox (and never leaks the global key).
    sandbox_token = issue_battle_token(battle_id)
    client = InternalClient(HttpTransport(base, "", sandbox_token=sandbox_token))

    def status_check() -> str:
        from .persistence import service

        b = service.battle_get("", battle_id) or {}
        return b.get("status", "unknown")

    def on_status(status: str) -> None:
        _set_status(databases, database_id, battle_id, status)
        if status == "completed":
            _finalize_scores(databases, database_id, battle_id, battle, None)

    try:
        scores = run_battle_loop(
            battle_id=battle_id,
            format_config=cfg,
            model_ids=list(battle.get("model_ids") or []),
            round_visibility=battle.get("round_visibility", "isolated"),
            timeout_seconds=int(battle.get("timeout_seconds") or 600),
            client=client,
            status_check=status_check,
            on_status=on_status,
        )
        if scores:
            _finalize_scores(databases, database_id, battle_id, battle, scores)
    except Exception:
        _set_status(databases, database_id, battle_id, "failed")


def _run_direct(battle_id, databases, database_id, battle, cfg) -> None:
    """Call internal handlers without HTTP (tests + local)."""
    from .sandbox.client import FakeTransport, InternalClient
    from . import judge as judge_mod
    from .providers import get_model_call_spec
    from .redact import sanitize_artifact
    from . import llm_client

    transport = FakeTransport()

    # Wire FakeTransport to real model/judge when keys exist; else canned
    def model_post(path, body):
        if path == "/internal/model":
            try:
                base, style, key, model = get_model_call_spec(
                    body["model_id"], battle.get("user_id")
                )
                content = llm_client.chat_completion(
                    base_url=base,
                    auth_style=style,
                    api_key=key,
                    model=model,
                    messages=body.get("messages") or [],
                )
            except Exception:
                content = f"[stub:{body['model_id']}]"
            transport.rounds  # keep
            return {"content": content}
        if path == "/internal/judge":
            try:
                return judge_mod.judge_battle(
                    model_ids=list(battle.get("model_ids") or []),
                    artifacts=body.get("artifacts") or [],
                    rubric=body.get("rubric") or "score",
                    weights=body.get("weights"),
                )
            except Exception:
                mids = list(battle.get("model_ids") or [])
                scores = {m: 50.0 + i for i, m in enumerate(mids)}
                return {
                    "scores": scores,
                    "justifications": {m: "fallback" for m in mids},
                    "judge_model": "fallback",
                }
        if path == "/internal/round":
            art = sanitize_artifact(body.get("artifact", ""))
            from .persistence import service

            service.round_create(
                battle_id,
                body.get("phase", ""),
                body.get("model_id", ""),
                art,
                tool_trace=body.get("tool_trace"),
                verification_log=body.get("verification_log"),
                meta=body.get("meta"),
            )
            event_bus.publish(
                battle_id,
                {
                    "type": body.get("event_type", "artifact"),
                    "data": {
                        "phase": body.get("phase"),
                        "model_id": body.get("model_id"),
                        "artifact": art,
                    },
                },
            )
            return {"ok": True}
        raise RuntimeError(path)

    transport.post = model_post  # type: ignore[method-assign]
    client = InternalClient(transport)

    def status_check() -> str:
        from .persistence import service

        b = service.battle_get("", battle_id) or {}
        return b.get("status", "unknown")

    def on_status(status: str) -> None:
        _set_status(databases, database_id, battle_id, status)

    try:
        _set_status(databases, database_id, battle_id, "running")
        scores = run_battle_loop(
            battle_id=battle_id,
            format_config=cfg,
            model_ids=list(battle.get("model_ids") or []),
            round_visibility=battle.get("round_visibility", "isolated"),
            timeout_seconds=int(battle.get("timeout_seconds") or 600),
            client=client,
            status_check=status_check,
            on_status=on_status,
        )
        if scores:
            _finalize_scores(databases, database_id, battle_id, battle, scores)
            if battle.get("status") != "completed":
                _set_status(databases, database_id, battle_id, "completed")
    except Exception:
        _set_status(databases, database_id, battle_id, "failed")


def _finalize_scores(databases, database_id, battle_id, battle, scores) -> None:
    if not scores:
        return
    from .persistence import service

    for mid, value in scores.items():
        service.score_upsert(
            battle_id,
            mid,
            float(value),
            judge_model="host-judge",
            justification="judged",
        )
    try:
        from .custom_battles import is_ranked_battle, resolve_battle_config

        cfg = resolve_battle_config(battle, {})
        if is_ranked_battle(battle, cfg):
            service.leaderboard_apply_result(
                battle.get("format_id", ""),
                list(battle.get("model_ids") or []),
                scores,
            )
    except Exception:
        pass


def try_spawn_modal_sandbox(battle_id: str) -> str:
    """Spawn Modal Sandbox running the runner. Returns sandbox_id or raises."""
    try:
        import modal
    except ImportError as exc:
        raise RuntimeError("modal SDK not installed") from exc
    key = settings().get("INTERNAL_API_KEY") or ""
    if not key:
        raise RuntimeError("INTERNAL_API_KEY not configured")
    databases, _database_id, battle, cfg = _load_battle(battle_id)
    # Issue a battle-scoped, expiring token. The sandbox receives ONLY this
    # token — never the global INTERNAL_API_KEY — so a compromised sandbox
    # cannot use the shared key to reach other battles or users' provider keys.
    sandbox_token = issue_battle_token(battle_id)
    bootstrap = {
        "format_config": cfg,
        "model_ids": list(battle.get("model_ids") or []),
        "round_visibility": battle.get("round_visibility", "isolated"),
        "timeout_seconds": int(battle.get("timeout_seconds") or 600),
    }
    app = modal.App.lookup("agent-arena-backend", create_if_missing=True)
    skills_dir = _skills_dir()
    targets_dir = _targets_dir()
    image = (
        modal.Image.debian_slim(python_version="3.11")
        .apt_install(
            "build-essential",
            "git",
            "curl",
            "wget",
            "ripgrep",
            "tree",
            "jq",
            "nodejs",
            "npm",
            "ca-certificates",
        )
        .pip_install("httpx", "pytest")
        .add_local_python_source("agent_arena")
    )
    if skills_dir.is_dir():
        image = image.add_local_dir(str(skills_dir), remote_path="/opt/arena-skills")
    if targets_dir.is_dir():
        image = image.add_local_dir(str(targets_dir), remote_path="/opt/arena-targets")
    secret = modal.Secret.from_dict(
        {
            "BATTLE_TOKEN": sandbox_token,
            "BACKEND_PUBLIC_URL": _backend_public_url(),
            "BATTLE_BOOTSTRAP_JSON": json.dumps(bootstrap),
            "ARENA_SKILLS_ROOT": "/opt/arena-skills",
            "ARENA_TARGETS_DIR": "/opt/arena-targets",
        }
    )
    preview_on = (
        bool((cfg.get("environment") or {}).get("preview"))
        and len(battle.get("model_ids") or []) == 2
    )
    create_kwargs = {
        "image": image,
        "secrets": [secret],
        "timeout": int(os.environ.get("SANDBOX_TIMEOUT", "900")),
        "app": app,
    }
    if preview_on:
        create_kwargs["encrypted_ports"] = [8080, 8081]
    sb = modal.Sandbox.create(
        "python",
        "-c",
        (f"from agent_arena.sandbox.entrypoint import main; main({battle_id!r})"),
        **create_kwargs,
    )
    sandbox_id = (
        getattr(sb, "object_id", None) or getattr(sb, "sandbox_id", None) or str(sb)
    )
    if not sandbox_id:
        raise RuntimeError("Modal sandbox created without an id")
    if preview_on:
        _persist_preview_urls(battle_id, list(battle.get("model_ids") or []), sb)
    return sandbox_id


def _persist_preview_urls(battle_id: str, model_ids: list[str], sb) -> None:
    """Wait briefly for Modal tunnels, then persist + publish preview URLs."""
    try:
        tunnels = {}
        for _ in range(30):
            try:
                tunnels = sb.tunnels()
                if tunnels:
                    break
            except Exception:
                pass
            time.sleep(1)
        if not tunnels:
            return
        previews = {}
        model_by_port = {
            8080: model_ids[0] if len(model_ids) > 0 else "",
            8081: model_ids[1] if len(model_ids) > 1 else "",
        }
        for port, tunnel in tunnels.items():
            url = getattr(tunnel, "url", None)
            if url and port in model_by_port and model_by_port[port]:
                previews[model_by_port[port]] = url
        if not previews:
            return
        from .persistence import service

        try:
            service.battle_update(battle_id, {"preview_urls": previews})
        except Exception:
            pass
        for model_id, url in previews.items():
            event_bus.publish(
                battle_id,
                {
                    "type": "preview",
                    "data": {"model_id": model_id, "url": url},
                },
            )
    except Exception:
        pass


def _fail_with_reason(battle_id: str, reason: str) -> None:
    from .persistence import service

    try:
        service.battle_update(battle_id, {"status": "failed", "failure_reason": reason})
    except Exception:
        pass
    event_bus.publish(battle_id, {"type": "error", "data": {"message": reason}})
    event_bus.publish(
        battle_id,
        {"type": "battle_status", "data": {"status": "failed", "reason": reason}},
    )


def start_battle(battle_id: str) -> None:
    """Entry used by BackgroundTasks / Modal."""
    if os.environ.get("ARENA_USE_MODAL_SANDBOX") == "1":
        try:
            sandbox_id = try_spawn_modal_sandbox(battle_id)
        except Exception as exc:
            reason = f"Sandbox spawn failed: {type(exc).__name__}: {exc}"
            print(reason)
            _fail_with_reason(battle_id, reason)
            return
        try:
            from .persistence import service

            service.battle_update(battle_id, {"sandbox_id": sandbox_id})
        except Exception:
            pass
        _set_status(None, None, battle_id, "running")
        return
    os.environ.setdefault("ARENA_INPROCESS_DIRECT", "1")
    if os.environ.get("ARENA_IN_SANDBOX") != "1":
        os.environ["ARENA_IN_SANDBOX"] = "1"
    run_in_process(battle_id)


def stop_sandbox(sandbox_id: str) -> None:
    if not sandbox_id:
        return
    try:
        import modal

        sb = modal.Sandbox.from_id(sandbox_id)
        sb.terminate()
    except Exception:
        pass
