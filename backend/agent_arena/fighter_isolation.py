"""Fighter code must never execute on a host that can read evaluator material.

The trusted backend mounts private evaluator packages (hidden tests, reference
solutions) at `$ARENA_EVALUATOR_DIR`. Removing that variable from a child
environment does not unmount the directory: an in-process fighter can still
`open()` the well-known path. So the runner *selection* itself is the control.

When private evaluator storage is visible on this host, a target battle may only
run through the isolated sandbox path, which receives a materialized public tree
and no evaluator mount.
"""

from __future__ import annotations

from .target_library import private_evaluator_storage_present

# Runners that execute fighter code (or stand in for it) in the backend's own
# process and filesystem namespace.
SAME_HOST_MODES = frozenset({"in_process", "mock"})


class FighterIsolationError(RuntimeError):
    """Raised when a same-host runner would serve a private-evaluator target."""


def battle_target_id(battle: dict | None, cfg: dict | None = None) -> str:
    """Resolve the target id a battle will verify against."""
    for source in (battle or {}, cfg or {}):
        if not isinstance(source, dict):
            continue
        value = str(source.get("target_id") or "").strip()
        if value:
            return value
    return ""


def isolation_required(target_id: str) -> bool:
    """True when this battle must not run on the evaluator-bearing host."""
    if not str(target_id or "").strip():
        return False
    return private_evaluator_storage_present()


def assert_isolated_fighter_execution(target_id: str, *, mode: str) -> None:
    """Fail closed when `mode` would run a target battle on this host.

    Non-target battles are unaffected: they never resolve evaluator material.
    """
    if mode not in SAME_HOST_MODES:
        return
    if not isolation_required(target_id):
        return
    raise FighterIsolationError(
        f"target '{target_id}' cannot run via '{mode}': private evaluator storage "
        "is mounted on this host. Target battles require the isolated sandbox "
        "path (ARENA_USE_MODAL_SANDBOX=1)."
    )
