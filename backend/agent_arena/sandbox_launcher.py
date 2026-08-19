"""Start a battle: prefer Modal Sandbox; fall back to in-process runner."""

from __future__ import annotations

import json
import os
import threading
import time
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


def _load_battle(battle_id: str):
    databases = db.get_databases()
    database_id = db.get_database_id()
    battle = databases.get_document(database_id, "battles", battle_id)
    format_doc = databases.get_document(
        database_id, "formats", battle.data["format_id"]
    )
    cfg = json.loads(format_doc.data["config"])
    return databases, database_id, battle, cfg


def _set_status(databases, database_id: str, battle_id: str, status: str) -> None:
    try:
        payload = {"status": status}
        if status == "running":
            payload["started_at"] = time.time()
        databases.update_document(database_id, "battles", battle_id, payload)
    except Exception:
        pass
    event_bus.publish(battle_id, {"type": "battle_status", "data": {"status": status}})


def run_in_process(battle_id: str) -> None:
    """Hermetic/local path: runner in this process using HttpTransport to self or Fake."""
    databases, database_id, battle, cfg = _load_battle(battle_id)
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
        b = databases.get_document(database_id, "battles", battle_id)
        return b.data["status"]

    def on_status(status: str) -> None:
        _set_status(databases, database_id, battle_id, status)
        if status == "completed":
            _finalize_scores(databases, database_id, battle_id, battle, None)

    try:
        scores = run_battle_loop(
            battle_id=battle_id,
            format_config=cfg,
            model_ids=list(battle.data["model_ids"]),
            round_visibility=battle.data.get("round_visibility", "isolated"),
            timeout_seconds=int(battle.data.get("timeout_seconds") or 600),
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
                    body["model_id"], battle.data["user_id"]
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
                    model_ids=list(battle.data["model_ids"]),
                    artifacts=body.get("artifacts") or [],
                    rubric=body.get("rubric") or "score",
                    weights=body.get("weights"),
                )
            except Exception:
                mids = list(battle.data["model_ids"])
                scores = {m: 50.0 + i for i, m in enumerate(mids)}
                return {
                    "scores": scores,
                    "justifications": {m: "fallback" for m in mids},
                    "judge_model": "fallback",
                }
        if path == "/internal/round":
            art = sanitize_artifact(body.get("artifact", ""))
            databases.create_document(
                database_id,
                "rounds",
                "unique()",
                {
                    "battle_id": battle_id,
                    "phase": body.get("phase", ""),
                    "model_id": body.get("model_id", ""),
                    "artifact": art,
                },
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
        b = databases.get_document(database_id, "battles", battle_id)
        return b.data["status"]

    def on_status(status: str) -> None:
        _set_status(databases, database_id, battle_id, status)

    try:
        _set_status(databases, database_id, battle_id, "running")
        scores = run_battle_loop(
            battle_id=battle_id,
            format_config=cfg,
            model_ids=list(battle.data["model_ids"]),
            round_visibility=battle.data.get("round_visibility", "isolated"),
            timeout_seconds=int(battle.data.get("timeout_seconds") or 600),
            client=client,
            status_check=status_check,
            on_status=on_status,
        )
        if scores:
            _finalize_scores(databases, database_id, battle_id, battle, scores)
            if battle.data.get("status") != "completed":
                _set_status(databases, database_id, battle_id, "completed")
    except Exception:
        _set_status(databases, database_id, battle_id, "failed")


def _finalize_scores(databases, database_id, battle_id, battle, scores) -> None:
    if not scores:
        return
    from . import leaderboard

    for mid, value in scores.items():
        databases.create_document(
            database_id,
            "scores",
            "unique()",
            {
                "battle_id": battle_id,
                "model_id": mid,
                "score": float(value),
                "judge_model": "host-judge",
                "justification": "judged",
            },
        )
    try:
        leaderboard.apply_result(
            databases,
            database_id,
            battle.data["format_id"],
            list(battle.data["model_ids"]),
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
        "model_ids": list(battle.data["model_ids"]),
        "round_visibility": battle.data.get("round_visibility", "isolated"),
        "timeout_seconds": int(battle.data.get("timeout_seconds") or 600),
    }
    app = modal.App.lookup("agent-arena-backend", create_if_missing=True)
    skills_dir = _skills_dir()
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
    secret = modal.Secret.from_dict(
        {
            "BATTLE_TOKEN": sandbox_token,
            "BACKEND_PUBLIC_URL": _backend_public_url(),
            "BATTLE_BOOTSTRAP_JSON": json.dumps(bootstrap),
            "ARENA_SKILLS_ROOT": "/opt/arena-skills",
        }
    )
    sb = modal.Sandbox.create(
        "python",
        "-c",
        (f"from agent_arena.sandbox.entrypoint import main; main({battle_id!r})"),
        image=image,
        secrets=[secret],
        timeout=int(os.environ.get("SANDBOX_TIMEOUT", "900")),
        encrypted_ports=[8080, 8081],
        app=app,
    )
    sandbox_id = (
        getattr(sb, "object_id", None) or getattr(sb, "sandbox_id", None) or str(sb)
    )
    if not sandbox_id:
        raise RuntimeError("Modal sandbox created without an id")
    # Preview tunnels: 8080 -> player_a (model_ids[0]), 8081 -> player_b (model_ids[1])
    _persist_preview_urls(battle_id, list(battle.data["model_ids"]), sb)
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
        databases = db.get_databases()
        try:
            databases.update_document(
                db.get_database_id(),
                "battles",
                battle_id,
                {"preview_urls": json.dumps(previews)},
            )
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
    databases = db.get_databases()
    database_id = db.get_database_id()
    try:
        databases.update_document(
            database_id,
            "battles",
            battle_id,
            {"status": "failed", "failure_reason": reason},
        )
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
            databases = db.get_databases()
            databases.update_document(
                db.get_database_id(),
                "battles",
                battle_id,
                {"sandbox_id": sandbox_id},
            )
        except Exception:
            pass
        _set_status(db.get_databases(), db.get_database_id(), battle_id, "running")
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
