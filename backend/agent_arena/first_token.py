"""First-token watchdog: Arena timeout when a battle never reaches a model/tool event.

A first token is a persisted model result or a parsed tool call. SSE preview,
phase_start, heartbeats, and UI EXECUTING are not first tokens. Sandbox JSON
does not choose the outcome; this module only classifies evidence and clocks.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any, Callable, Iterable

DEFAULT_FIRST_TOKEN_SECONDS = 120.0
ENV_BUDGET = "ARENA_FIRST_TOKEN_SECONDS"
FAILURE_REASON = "no_first_token"

NOT_FIRST_TOKEN_EVENT_TYPES = frozenset(
    {
        "phase_start",
        "battle_status",
        "preview",
        "heartbeat",
        "error",
        "skill_search",
        "skill_load",
        "skill_offered",
        "skill_ranked",
        "skill_eligible",
    }
)
FIRST_TOKEN_EVENT_TYPES = frozenset({"result"})
FIRST_TOKEN_ACTIONS = frozenset(
    {
        "tool_parse_success",
        "tool_parse_failed",
        "parse_failure_limit",
    }
)


def first_token_budget_seconds(timeout_seconds: int | float | None = None) -> float:
    raw = os.environ.get(ENV_BUDGET, str(DEFAULT_FIRST_TOKEN_SECONDS))
    try:
        budget = float(raw)
    except (TypeError, ValueError):
        budget = DEFAULT_FIRST_TOKEN_SECONDS
    timeout = float(timeout_seconds or 600)
    return max(1.0, min(budget, timeout))


def started_clock_unix(started_at: Any) -> float | None:
    """First-token clock for a started battle. Queued rows with null started_at skip this."""
    if started_at is None:
        return None
    if isinstance(started_at, datetime):
        if started_at.tzinfo is None:
            started_at = started_at.replace(tzinfo=timezone.utc)
        return started_at.timestamp()
    try:
        return float(started_at)
    except (TypeError, ValueError):
        return None


def silence_reason(age_seconds: float, budget_seconds: float) -> str:
    return (
        f"{FAILURE_REASON} after {int(age_seconds)}s "
        f"(budget {int(budget_seconds)}s)"
    )


def first_token_expired(
    *,
    started_at: Any,
    now: float,
    timeout_seconds: int | float | None,
    has_first_token: bool,
) -> str:
    """Return a failure reason when a started battle is silent past the budget."""
    if has_first_token:
        return ""
    clock = started_clock_unix(started_at)
    if clock is None:
        return ""
    budget = first_token_budget_seconds(timeout_seconds)
    age = now - clock
    if age <= budget:
        return ""
    return silence_reason(age, budget)


def _nested_dicts(payload: Any) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    if isinstance(payload, dict):
        found.append(payload)
        data = payload.get("data")
        if isinstance(data, dict):
            found.append(data)
    return found


def _parse_artifact(artifact: Any) -> dict[str, Any] | None:
    if isinstance(artifact, dict):
        return artifact
    if not isinstance(artifact, str):
        return None
    text = artifact.strip()
    if text.startswith("EXECUTOR_RESULT:"):
        return {"_executor_result": True}
    if not text.startswith("{"):
        return None
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _action_from_payload(payload: Any) -> str:
    for node in _nested_dicts(payload):
        action = str(node.get("action") or "").strip().lower()
        if action:
            return action
        inner = _parse_artifact(node.get("artifact"))
        if inner is None:
            continue
        if inner.get("_executor_result"):
            return "executor_result"
        action = str(inner.get("action") or "").strip().lower()
        if action:
            return action
    return ""


def is_first_token_event(event_type: str | None, payload: Any = None) -> bool:
    et = str(event_type or "").strip().lower()
    if et in FIRST_TOKEN_EVENT_TYPES:
        return True
    if et in NOT_FIRST_TOKEN_EVENT_TYPES:
        return False
    action = _action_from_payload(payload)
    if action in FIRST_TOKEN_ACTIONS or action == "executor_result":
        return True
    return False


def has_first_token(
    events: Iterable[tuple[str | None, Any]],
) -> bool:
    return any(is_first_token_event(event_type, payload) for event_type, payload in events)


def is_transport_timeout(exc: BaseException) -> bool:
    """True when the model HTTP call never returned a body."""
    if isinstance(exc, TimeoutError):
        return True
    name = type(exc).__name__.lower()
    if "timeout" in name:
        return True
    msg = str(exc).lower()
    return "timed out" in msg or "timeout exception" in msg


def emit_status(
    on_status: Callable[..., Any] | None,
    status: str,
    reason: str | None = None,
) -> None:
    if on_status is None:
        return
    if reason:
        try:
            on_status(status, reason)
            return
        except TypeError:
            pass
    on_status(status)
