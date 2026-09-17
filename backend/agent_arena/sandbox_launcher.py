"""Start a battle: prefer Modal Sandbox; fall back to in-process runner."""

from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from . import db, event_bus
from .battle_token import issue_battle_token
from .config import settings
from .runtime_packaging import (
    attach_canonical_skill_yaml,
    attach_fighter_skills,
    canonical_skill_runtime_env,
    fighter_skill_directory,
    fighter_sandbox_pip_packages,
)
from .sandbox.client import HttpTransport, InternalClient
from .sandbox.runner import run_battle_loop
from .neon_branch_manager import (
    BranchResult,
    NeonBranchManager,
    NeonProvisioningError,
)
from .target_library import target_requires_battle_database

PUBLIC_SANDBOX_BOOT_FAILURE = "SANDBOX_BOOT_FAILURE"
BATTLE_DATABASE_PROVISIONING_FAILURE = "BATTLE_DATABASE_PROVISIONING_FAILURE"
BATTLE_LOAD_FAILURE = "BATTLE_LOAD_FAILURE"


class SandboxBootError(RuntimeError):
    """Sandbox process exited before useful execution."""


@dataclass(frozen=True)
class BattleDatabaseLease:
    """Trusted handle for one Battle's ephemeral database branch.

    Only the branch identifier is persisted. The application DSN remains in
    the trusted launcher for the future service process; the read-only DSN is
    the only database capability passed to the Fighter tool boundary.
    """

    manager: NeonBranchManager
    branch: BranchResult

    @property
    def read_only_database_url(self) -> str:
        return self.branch.read_only_database_url

    @property
    def application_database_url(self) -> str:
        """RW Battle-app capability; never expose this through Fighter tools."""
        return self.branch.database_url


_battle_database_leases: dict[str, BattleDatabaseLease] = {}
_battle_database_leases_lock = threading.Lock()


def _backend_public_url() -> str:
    return os.environ.get(
        "BACKEND_PUBLIC_URL",
        "https://sixscripts--agent-arena-backend-fastapi-app.modal.run",
    )


def _skills_dir() -> Path:
    return fighter_skill_directory()


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


def _set_status(
    databases,
    database_id: str,
    battle_id: str,
    status: str,
    reason: str | None = None,
) -> None:
    from .persistence import service

    try:
        payload: dict = {"status": status}
        if status == "failed" and reason:
            payload["failure_reason"] = reason
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
    data = {"status": status, "authoritative": True}
    if status == "failed" and reason:
        data["reason"] = reason
    event_bus.publish(battle_id, {"type": "battle_status", "data": data})


def _explicit_mock_mode() -> bool:
    return os.environ.get("ARENA_HERMETIC") == "1" or os.environ.get(
        "ARENA_USE_MOCK", "0"
    ).strip().lower() in ("1", "true", "yes", "on")


def _publish_database_cleanup(
    battle_id: str, status: str, *, reason: str | None = None
) -> None:
    data = {"status": status, "authoritative": True}
    if reason:
        data["reason"] = reason
    event_bus.publish(
        battle_id,
        {"type": "battle_database_cleanup", "data": data},
    )


def _publish_database_provisioned(
    battle_id: str, *, application_write: bool
) -> None:
    event_bus.publish(
        battle_id,
        {
            "type": "battle_database_provisioned",
            "data": {
                "status": "ready",
                "application_write": bool(application_write),
                "authoritative": True,
            },
        },
    )


def _delete_lease_branch(lease: BattleDatabaseLease) -> bool:
    try:
        return bool(lease.manager.delete_branch(lease.branch.branch_id))
    except Exception:
        return False


def provision_battle_database(
    battle_id: str,
    *,
    database_config: dict | None = None,
) -> BattleDatabaseLease:
    """Provision and record the Battle-scoped database capability.

    Production lifecycle state is stored in the PostgreSQL Battle row. The
    in-memory path exists only for hermetic/mock tests, where external
    persistence is deliberately unavailable. No control-plane DSN is ever
    consulted or persisted.
    """
    from .persistence import service

    postgres = service.using_postgres()
    if not postgres and not _explicit_mock_mode():
        raise NeonProvisioningError(
            "ARENA_INFRA_FAILURE: Battle database lifecycle requires PostgreSQL persistence"
        )

    manager = NeonBranchManager()
    try:
        branch = manager.create_ephemeral_branch(battle_id)
    except NeonProvisioningError:
        raise
    except Exception as exc:
        raise NeonProvisioningError(
            "ARENA_INFRA_FAILURE: Battle database provisioning failed"
        ) from exc

    try:
        branch_id = str(getattr(branch, "branch_id", "") or "").strip()
        application_database_url = str(
            getattr(branch, "database_url", "") or ""
        ).strip()
        read_only_database_url = str(
            getattr(branch, "read_only_database_url", "") or ""
        ).strip()
    except Exception as exc:
        raise NeonProvisioningError(
            "ARENA_INFRA_FAILURE: Battle database capability invalid"
        ) from exc

    if not branch_id or not application_database_url or not read_only_database_url:
        deleted = False
        if branch_id:
            try:
                deleted = bool(manager.delete_branch(branch_id))
            except Exception:
                deleted = False
        if branch_id and not deleted:
            _publish_database_cleanup(
                battle_id,
                "failed",
                reason="provisioning_capability_revoke_failed",
            )
        raise NeonProvisioningError(
            "ARENA_INFRA_FAILURE: Battle database capabilities unavailable"
        )

    initializer = getattr(manager, "initialize_battle_database", None)
    if callable(initializer):
        try:
            initializer(branch, database_config=dict(database_config or {}))
        except NeonProvisioningError:
            if branch_id and not _delete_lease_branch(
                BattleDatabaseLease(manager=manager, branch=branch)
            ):
                _publish_database_cleanup(
                    battle_id,
                    "failed",
                    reason="provisioning_initialization_revoke_failed",
                )
            raise
        except Exception as exc:
            if branch_id and not _delete_lease_branch(
                BattleDatabaseLease(manager=manager, branch=branch)
            ):
                _publish_database_cleanup(
                    battle_id,
                    "failed",
                    reason="provisioning_initialization_revoke_failed",
                )
            raise NeonProvisioningError(
                "ARENA_INFRA_FAILURE: Battle database initialization failed"
            ) from exc

    lease = BattleDatabaseLease(manager=manager, branch=branch)
    with _battle_database_leases_lock:
        _battle_database_leases[battle_id] = lease

    if postgres:
        try:
            service.battle_update(
                battle_id,
                {"battle_db_branch_id": branch_id},
            )
        except Exception as exc:
            # Keep the lease in memory if deletion itself fails so a later
            # terminal cleanup can retry using the exact branch handle.
            if _delete_lease_branch(lease):
                with _battle_database_leases_lock:
                    _battle_database_leases.pop(battle_id, None)
            _publish_database_cleanup(
                battle_id,
                "failed",
                reason="provisioning_metadata_persist_failed",
            )
            raise NeonProvisioningError(
                "ARENA_INFRA_FAILURE: Battle database handle persistence failed"
            ) from exc

    config = database_config or {}
    _publish_database_provisioned(
        battle_id,
        application_write=bool(config.get("application_write", False)),
    )
    return lease


def cleanup_battle_database(
    battle_id: str,
    *,
    branch_id: str | None = None,
    clear_persisted: bool = True,
) -> bool:
    """Idempotently revoke the Battle branch without changing its outcome."""
    from .persistence import service

    with _battle_database_leases_lock:
        lease = _battle_database_leases.get(battle_id)

    requested_branch_id = str(branch_id or "").strip()
    lease_branch_id = (
        str(lease.branch.branch_id or "").strip() if lease is not None else ""
    )
    persisted_branch_id = ""
    try:
        battle = service.battle_get("", battle_id) or {}
        persisted_branch_id = str(battle.get("battle_db_branch_id") or "").strip()
    except Exception:
        persisted_branch_id = ""

    trusted_branch_id = lease_branch_id or persisted_branch_id
    if lease_branch_id and persisted_branch_id and lease_branch_id != persisted_branch_id:
        _publish_database_cleanup(
            battle_id,
            "failed",
            reason="branch_identity_mismatch",
        )
        return False
    if requested_branch_id and trusted_branch_id and requested_branch_id != trusted_branch_id:
        _publish_database_cleanup(
            battle_id,
            "failed",
            reason="branch_identity_mismatch",
        )
        return False
    if requested_branch_id and not trusted_branch_id:
        _publish_database_cleanup(
            battle_id,
            "failed",
            reason="branch_identity_unbound",
        )
        return False

    resolved_branch_id = trusted_branch_id or requested_branch_id
    if not resolved_branch_id:
        return True

    manager = lease.manager if lease is not None else NeonBranchManager()
    try:
        deleted = bool(manager.delete_branch(resolved_branch_id))
    except Exception:
        deleted = False
    if not deleted:
        _publish_database_cleanup(battle_id, "failed", reason="branch_revoke_failed")
        return False

    with _battle_database_leases_lock:
        current = _battle_database_leases.get(battle_id)
        if current is not None and current.branch.branch_id == resolved_branch_id:
            _battle_database_leases.pop(battle_id, None)

    if clear_persisted:
        try:
            if service.using_postgres():
                service.battle_update(battle_id, {"battle_db_branch_id": None})
        except Exception:
            _publish_database_cleanup(
                battle_id,
                "failed",
                reason="cleanup_metadata_clear_failed",
            )
            return False

    _publish_database_cleanup(battle_id, "completed")
    return True


def _fail_database_provisioning(battle_id: str) -> None:
    """Record a host-owned infrastructure result; never a Fighter loss."""
    from .finalization import fail_closed_incomplete

    try:
        fail_closed_incomplete(
            battle_id,
            reason=BATTLE_DATABASE_PROVISIONING_FAILURE,
        )
    except Exception:
        _fail_with_reason(battle_id, BATTLE_DATABASE_PROVISIONING_FAILURE)


def run_in_process(
    battle_id: str, *, battle_db_lease: BattleDatabaseLease | None = None
) -> None:
    """Hermetic/local path: runner in this process using HttpTransport to self or Fake."""
    from .custom_battles import FrozenConfigError
    from .fighter_isolation import (
        FighterIsolationError,
        assert_isolated_fighter_execution,
        battle_target_id,
    )

    try:
        databases, database_id, battle, cfg = _load_battle(battle_id)
    except FrozenConfigError as exc:
        _fail_with_reason(battle_id, str(exc))
        return

    try:
        assert_isolated_fighter_execution(
            battle_target_id(battle, cfg), mode="in_process"
        )
    except FighterIsolationError as exc:
        _fail_with_reason(battle_id, str(exc))
        return
    try:
        database_required = target_requires_battle_database(cfg)
    except Exception as exc:
        _fail_with_reason(battle_id, f"{BATTLE_LOAD_FAILURE}: {exc}")
        return

    if battle_db_lease is not None and not database_required:
        _fail_with_reason(
            battle_id,
            f"{BATTLE_DATABASE_PROVISIONING_FAILURE}: unexpected database lease",
        )
        return

    owns_lease = False
    lease = battle_db_lease
    if lease is None and database_required:
        try:
            lease = provision_battle_database(
                battle_id,
                database_config=cfg.get("database"),
            )
        except NeonProvisioningError:
            _fail_database_provisioning(battle_id)
            return
        owns_lease = True

    try:
        battle_ro_database_url = lease.read_only_database_url if lease else None
        key = settings().get("INTERNAL_API_KEY") or ""
        base = os.environ.get("INTERNAL_BASE_URL") or "http://127.0.0.1:8000"
        # When no server, use direct in-memory bridge via local functions.
        if not key or os.environ.get("ARENA_INPROCESS_DIRECT") == "1":
            _run_direct(
                battle_id,
                databases,
                database_id,
                battle,
                cfg,
                battle_ro_database_url=battle_ro_database_url,
            )
            return
        # Use a battle-scoped token over HTTP so the local path exercises the same
        # auth contract as the real sandbox (and never leaks the global key).
        sandbox_token = issue_battle_token(battle_id)
        client = InternalClient(HttpTransport(base, "", sandbox_token=sandbox_token))

        def status_check() -> str:
            from .persistence import service

            b = service.battle_get("", battle_id) or {}
            return b.get("status", "unknown")

        def on_status(status: str, reason: str | None = None) -> None:
            _set_status(databases, database_id, battle_id, status, reason=reason)
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
                battle_ro_database_url=battle_ro_database_url,
            )
            if scores:
                _finalize_scores(databases, database_id, battle_id, battle, scores)
        except Exception:
            _set_status(databases, database_id, battle_id, "failed")
    finally:
        if owns_lease:
            cleanup_battle_database(battle_id)


def _run_direct(
    battle_id,
    databases,
    database_id,
    battle,
    cfg,
    *,
    battle_ro_database_url: str | None = None,
) -> None:
    """Call internal handlers without HTTP (tests + local)."""
    from .sandbox.client import FakeTransport, InternalClient
    from . import judge as judge_mod
    from .providers import get_model_call_spec, reasoning_request_fields
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
                if (key or "").startswith("sk-test") or "example" in (base or ""):
                    content = (
                        "TOOL write path=solution.py\n"
                        "def is_palindrome(s: str) -> bool:\n"
                        "    clean = ''.join(c.lower() for c in s if c.isalnum())\n"
                        "    return clean == clean[::-1]\n"
                        "END_TOOL\n"
                        "DONE"
                    )
                    return {"content": content, "tool_calls": []}
                else:
                    resp = llm_client.chat_completion(
                        base_url=base,
                        auth_style=style,
                        api_key=key,
                        model=model,
                        messages=body.get("messages") or [],
                        max_tokens=body.get("max_tokens") or 1024,
                        temperature=body.get("temperature")
                        if body.get("temperature") is not None
                        else 0.7,
                        tools=body.get("tools"),
                        tool_choice=body.get("tool_choice"),
                        provider_request_fields=reasoning_request_fields(
                            body["model_id"], body.get("reasoning_effort")
                        ),
                    )
                    return {
                        "content": resp.text if hasattr(resp, "text") else str(resp),
                        "tool_calls": [c.model_dump() for c in resp.tool_calls]
                        if hasattr(resp, "tool_calls")
                        else [],
                        "raw": getattr(resp, "raw", None),
                    }
            except Exception as exc:
                return {"content": f"[stub:{body.get('model_id')}]", "tool_calls": []}
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
            from .battle_public import annotate_sandbox_status_event

            service.round_create(
                battle_id,
                body.get("phase", ""),
                body.get("model_id", ""),
                art,
                tool_trace=body.get("tool_trace"),
                verification_log=body.get("verification_log"),
                meta=body.get("meta"),
            )
            data = {
                "phase": body.get("phase"),
                "model_id": body.get("model_id"),
                "artifact": art,
            }
            if body.get("event_type") == "battle_status":
                data = annotate_sandbox_status_event(data, art)
            event_bus.publish(
                battle_id,
                {
                    "type": body.get("event_type", "artifact"),
                    "data": data,
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

    def on_status(status: str, reason: str | None = None) -> None:
        _set_status(databases, database_id, battle_id, status, reason=reason)

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
            battle_ro_database_url=battle_ro_database_url,
        )
        _finalize_scores(databases, database_id, battle_id, battle, scores)
    except Exception:
        _set_status(databases, database_id, battle_id, "failed")


def _finalize_scores(databases, database_id, battle_id, battle, scores) -> None:
    """Local/in-process completion goes through sandbox-end finalization.

    Loop/judge scores are untrusted hints only. They cannot write Elo or
    authoritative BattleResult rows. Missing trusted evidence fail-closes.
    """
    del databases, database_id, battle
    from .finalization import sandbox_end_finalize

    sandbox_end_finalize(
        battle_id,
        caller_scores=scores if scores else None,
    )


def try_spawn_modal_sandbox(
    battle_id: str, *, battle_ro_database_url: str | None = None
) -> tuple[str, object]:
    """Spawn Modal Sandbox running the runner. Returns (sandbox_id, sandbox) or raises."""
    from .hermetic import assert_not_hermetic

    assert_not_hermetic("modal")
    try:
        import modal
    except ImportError as exc:
        raise RuntimeError("modal SDK not installed") from exc
    key = settings().get("INTERNAL_API_KEY") or ""
    if not key:
        raise RuntimeError("INTERNAL_API_KEY not configured")
    battle_ro_database_url = str(battle_ro_database_url or "").strip()
    databases, _database_id, battle, cfg = _load_battle(battle_id)
    # Issue a battle-scoped, expiring token. The sandbox receives ONLY this
    # token — never the global INTERNAL_API_KEY — so a compromised sandbox
    # cannot use the shared key to reach other battles or users' provider keys.
    sandbox_token = issue_battle_token(battle_id)
    from .target_library import fighter_visible_battle_config

    bootstrap = {
        "format_config": fighter_visible_battle_config(cfg),
        "model_ids": list(battle.get("model_ids") or []),
        "round_visibility": battle.get("round_visibility", "isolated"),
        "timeout_seconds": int(battle.get("timeout_seconds") or 600),
    }
    app = modal.App.lookup("agent-arena-backend", create_if_missing=True)
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
            "util-linux",
        )
        .pip_install(*fighter_sandbox_pip_packages())
        .add_local_python_source("agent_arena")
    )
    image = attach_canonical_skill_yaml(image)
    image = attach_fighter_skills(image)
    public_targets = None
    if targets_dir.is_dir():
        import shutil
        import tempfile

        from .target_library import materialize_fighter_visible_library

        public_targets = Path(tempfile.mkdtemp(prefix="arena-fighter-targets-"))
        materialize_fighter_visible_library(targets_dir, public_targets)
        image = image.add_local_dir(str(public_targets), remote_path="/opt/arena-targets")
    secret_values = {
        "BATTLE_TOKEN": sandbox_token,
        "BACKEND_PUBLIC_URL": _backend_public_url(),
        "BATTLE_BOOTSTRAP_JSON": json.dumps(bootstrap),
        "ARENA_SKILLS_ROOT": "/opt/arena-skills",
        "ARENA_TARGETS_DIR": "/opt/arena-targets",
        **canonical_skill_runtime_env(),
    }
    if battle_ro_database_url:
        # Keep the explicit Battle capability last in case packaging env
        # additions ever grow a similarly named variable.
        secret_values["BATTLE_RO_DATABASE_URL"] = battle_ro_database_url
    secret = modal.Secret.from_dict(secret_values)
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
    try:
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
        return sandbox_id, sb
    finally:
        if public_targets is not None:
            import shutil

            shutil.rmtree(public_targets, ignore_errors=True)


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


def _boot_wait_seconds() -> float:
    raw = os.environ.get("ARENA_SANDBOX_BOOT_WAIT_SECONDS", "15")
    try:
        return max(0.0, float(raw))
    except ValueError:
        return 15.0


def _sandbox_exit_code(sb: object) -> int | None:
    poll = getattr(sb, "poll", None)
    if callable(poll):
        try:
            code = poll()
        except Exception:
            code = None
        if code is not None:
            return int(code)
    code = getattr(sb, "returncode", None)
    if code is not None:
        return int(code)
    return None


def await_sandbox_bootstrap(sb: object, *, timeout_seconds: float | None = None) -> None:
    """Fail if the sandbox process dies before useful execution starts."""
    wait = _boot_wait_seconds() if timeout_seconds is None else max(0.0, timeout_seconds)
    deadline = time.monotonic() + wait
    while True:
        if _sandbox_exit_code(sb) is not None:
            raise SandboxBootError("sandbox exited before useful execution")
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return
        time.sleep(min(0.25, remaining))


def fail_sandbox_boot(battle_id: str, *, sandbox_id: str | None = None) -> None:
    """Mark a boot failure immediately. No verify, no Elo, no fighter-visible details."""
    if sandbox_id:
        stop_sandbox(sandbox_id)
    from .finalization import fail_closed_incomplete

    try:
        fail_closed_incomplete(battle_id, reason=PUBLIC_SANDBOX_BOOT_FAILURE)
    except Exception:
        pass
    cleanup_battle_database(battle_id)


def _fail_with_reason(battle_id: str, reason: str) -> None:
    from .persistence import service

    try:
        service.battle_update(battle_id, {"status": "failed", "failure_reason": reason})
    except Exception:
        pass
    event_bus.publish(battle_id, {"type": "error", "data": {"message": reason}})
    event_bus.publish(
        battle_id,
        {"type": "battle_status", "data": {"status": "failed", "reason": reason, "authoritative": True}},
    )


def start_battle(battle_id: str) -> None:
    """Entry used by BackgroundTasks / Modal."""
    lease: BattleDatabaseLease | None = None
    remote_started = False
    try:
        if os.environ.get("ARENA_USE_MODAL_SANDBOX") == "1":
            sandbox_id = ""
            try:
                # Resolve the frozen Battle before allocating an external
                # branch, so an unknown/invalid Battle cannot leak a branch.
                _, _, _battle, cfg = _load_battle(battle_id)
                database_required = target_requires_battle_database(cfg)
            except Exception:
                fail_sandbox_boot(battle_id)
                return
            if database_required:
                try:
                    lease = provision_battle_database(
                        battle_id,
                        database_config=cfg.get("database"),
                    )
                except NeonProvisioningError:
                    _fail_database_provisioning(battle_id)
                    return
            try:
                sandbox_id, sb = try_spawn_modal_sandbox(
                    battle_id,
                    battle_ro_database_url=(
                        lease.read_only_database_url if lease is not None else None
                    ),
                )
                try:
                    from .persistence import service

                    service.battle_update(battle_id, {"sandbox_id": sandbox_id})
                except Exception:
                    pass
                await_sandbox_bootstrap(sb)
            except Exception:
                print(f"{PUBLIC_SANDBOX_BOOT_FAILURE} battle_id={battle_id}")
                fail_sandbox_boot(battle_id, sandbox_id=sandbox_id or None)
                return
            _set_status(None, None, battle_id, "running")
            remote_started = True
            return

        # No sandbox available: a target battle must not silently degrade to a
        # same-host runner that can read the evaluator mount.
        from .fighter_isolation import (
            FighterIsolationError,
            assert_isolated_fighter_execution,
            battle_target_id,
        )

        try:
            _, _, battle, cfg = _load_battle(battle_id)
        except Exception:
            _fail_with_reason(battle_id, BATTLE_LOAD_FAILURE)
            return
        try:
            assert_isolated_fighter_execution(
                battle_target_id(battle, cfg), mode="in_process"
            )
        except FighterIsolationError as exc:
            _fail_with_reason(battle_id, str(exc))
            return
        try:
            database_required = target_requires_battle_database(cfg)
        except Exception as exc:
            _fail_with_reason(battle_id, f"{BATTLE_LOAD_FAILURE}: {exc}")
            return
        if database_required:
            try:
                lease = provision_battle_database(
                    battle_id,
                    database_config=cfg.get("database"),
                )
            except NeonProvisioningError:
                _fail_database_provisioning(battle_id)
                return
        os.environ.setdefault("ARENA_INPROCESS_DIRECT", "1")
        if os.environ.get("ARENA_IN_SANDBOX") != "1":
            os.environ["ARENA_IN_SANDBOX"] = "1"
        run_in_process(battle_id, battle_db_lease=lease)
    finally:
        if lease is not None and not remote_started:
            cleanup_battle_database(battle_id)


def stop_sandbox(sandbox_id: str) -> None:
    if not sandbox_id:
        return
    try:
        import modal

        sb = modal.Sandbox.from_id(sandbox_id)
        sb.terminate()
    except Exception:
        pass
