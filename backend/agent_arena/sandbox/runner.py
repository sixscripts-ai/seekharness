"""Battle loop: role map, phases (skip judge), executors, host judge."""

from __future__ import annotations

import threading
import time
from typing import Callable

from ..difficulty import apply_difficulty
from .agent_runtime import resolve_role_runtime_bindings
from .client import InternalClient
from .executors import get_executor


def playable_roles(roles: list[str]) -> list[str]:
    return [r for r in roles if r != "judge"]


def map_roles(roles: list[str], model_ids: list[str]) -> dict[str, str]:
    playable = playable_roles(roles)
    if len(playable) != len(model_ids):
        raise ValueError(f"role/model mismatch: {playable} vs {model_ids}")
    return dict(zip(playable, model_ids))


def run_battle_loop(
    *,
    battle_id: str,
    format_config: dict,
    model_ids: list[str],
    round_visibility: str = "isolated",
    timeout_seconds: int = 600,
    client: InternalClient,
    status_check: Callable[[], str] | None = None,
    on_status: Callable[[str], None] | None = None,
    battle_ro_database_url: str | None = None,
) -> dict:
    """Resolve the executor and drive the battle. Returns scores dict."""
    deadline = time.time() + timeout_seconds
    abort = threading.Event()
    watchdog_done = threading.Event()

    def watchdog():
        remaining = max(0.0, deadline - time.time())
        if watchdog_done.wait(remaining):
            return
        if watchdog_done.is_set():
            return
        abort.set()
        if on_status:
            on_status("failed")

    wd = threading.Thread(target=watchdog, daemon=True)
    wd.start()

    try:
        if on_status:
            on_status("running")
        cfg = format_config
        difficulty = (format_config or {}).get("difficulty")
        if difficulty:
            try:
                cfg = apply_difficulty(format_config, difficulty)
            except Exception:
                cfg = format_config
        roles = cfg.get("roles", [])
        role_to_model = map_roles(roles, model_ids)
        bindings = resolve_role_runtime_bindings(role_to_model, cfg)
        role_to_model = {
            role: binding.model_id for role, binding in bindings.items()
        }
        executor = get_executor(cfg)
        return executor.run_battle(
            battle_id=battle_id,
            format_config=cfg,
            model_ids=model_ids,
            round_visibility=round_visibility,
            timeout_seconds=timeout_seconds,
            role_to_model=role_to_model,
            client=client,
            status_check=status_check,
            on_status=on_status,
            deadline=deadline,
            stop=abort,
            battle_ro_database_url=battle_ro_database_url,
        )
    except Exception:
        if on_status:
            on_status("failed")
        raise
    finally:
        watchdog_done.set()
