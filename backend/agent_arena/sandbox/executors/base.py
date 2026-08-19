from __future__ import annotations

import json
import threading
import time
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from ..client import InternalClient


def judge_weights(format_config: dict) -> dict[str, float] | None:
    """Merge nested scoring.weights (tests/skills/theory) with phase scoring_weights.

    Criteria from the challenge manifest / difficulty preset go in first; phase
    keys overwrite on collision so existing format rubrics stay intact.
    """
    merged: dict[str, float] = {}
    criteria = (format_config.get("scoring") or {}).get("weights") or {}
    phases = format_config.get("scoring_weights") or {}
    if isinstance(criteria, dict):
        for key, value in criteria.items():
            if isinstance(value, (int, float)):
                merged[str(key)] = float(value)
    if isinstance(phases, dict):
        for key, value in phases.items():
            if isinstance(value, (int, float)):
                merged[str(key)] = float(value)
    return merged or None


class Executor:
    def run_phase(
        self,
        *,
        client: "InternalClient",
        battle_id: str,
        phase: dict,
        role_to_model: dict[str, str],
        history: list[dict],
        format_config: dict,
        round_visibility: str,
    ) -> list[dict[str, Any]]:
        """Execute one phase; return list of artifact dicts."""
        raise NotImplementedError

    def run_battle(
        self,
        *,
        battle_id: str,
        format_config: dict,
        model_ids: list[str],
        round_visibility: str,
        timeout_seconds: int,
        role_to_model: dict[str, str],
        client: "InternalClient",
        status_check: "Callable[[], str] | None" = None,
        on_status: "Callable[[str], None] | None" = None,
        deadline: float | None = None,
        stop: "threading.Event | None" = None,
    ) -> dict:
        """Default: drive the generic phase loop via run_phase. Returns scores dict."""
        if deadline is None:
            deadline = time.time() + (timeout_seconds or 600)
        phases = format_config.get("phases", [])
        history: list[dict] = []

        for phase in phases:
            halted = self.halted(status_check, deadline)
            if halted:
                if on_status:
                    on_status(halted)
                return {}
            participants = [p for p in phase.get("participants", []) if p != "judge"]
            if not participants:
                continue
            client.round(
                battle_id,
                phase["name"],
                "system",
                f"phase_start:{phase['name']}",
                event_type="phase_start",
            )
            arts = self.run_phase(
                client=client,
                battle_id=battle_id,
                phase=phase,
                role_to_model=role_to_model,
                history=history,
                format_config=format_config,
                round_visibility=round_visibility,
            )
            history.extend(arts)

        return self.finish(
            client=client,
            battle_id=battle_id,
            format_config=format_config,
            history=history,
            on_status=on_status,
        )

    def finish(
        self,
        *,
        client: "InternalClient",
        battle_id: str,
        format_config: dict,
        history: list[dict],
        on_status: "Callable[[str], None] | None" = None,
    ) -> dict:
        rubric = format_config.get("judge_rubric") or "Score each model 0-100 fairly."
        weights = judge_weights(format_config)
        result = client.judge(battle_id, rubric, history, weights=weights)
        scores = result.get("scores") or {}
        client.round(
            battle_id, "judge", "system", json.dumps(result), event_type="scores"
        )
        if on_status:
            on_status("completed")
        return scores

    @staticmethod
    def halted(status_check, deadline) -> str | None:
        if status_check and status_check() == "cancelled":
            return "cancelled"
        if deadline and time.time() > deadline:
            return "failed"
        return None

    @staticmethod
    def guard(value, markers: list[str], default: str = "INCONCLUSIVE"):
        if not isinstance(value, str):
            return value
        v = value.upper()
        if not markers:
            return v
        for m in markers:
            m = m.upper()
            if v == m or (m.endswith("_") and v.startswith(m)):
                return v
        return default

    @staticmethod
    def emit_result(
        client: "InternalClient",
        battle_id: str,
        phase: str,
        result: dict,
    ) -> str:
        payload = json.dumps(result)
        line = f"EXECUTOR_RESULT: {payload}"
        client.round(battle_id, phase, "system", line, event_type="result")
        return line
