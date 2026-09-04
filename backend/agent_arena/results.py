"""Canonical Authoritative Battle Result Contract (Change Set C).

Establishes a single canonical result identity (battle_id, phase, role, model_id)
and structured authoritative lifecycle states (provisional -> verified -> final).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any

TRUSTED_VERIFICATION_MARKER = "TRUSTED_VERIFICATION:"
EXECUTOR_RESULT_MARKER = "EXECUTOR_RESULT:"

# Sandbox EXECUTOR_RESULT may report that execution happened. It must not
# encode pass/fail/score authority. Backend rewrite uses this marker.
UNTRUSTED_EXECUTION = "UNTRUSTED_EXECUTION"

# Fail-closed: sandbox telemetry may keep only identity. Structural and
# score-like fields cannot influence competitive ranking.
_UNTRUSTED_KEEP = frozenset({"model_id", "role", "phase", "battle_id"})

# Display-only executor stop reasons. Never TEST_PASS / scores / winner.
_DISPLAY_TERMINAL = frozenset(
    {
        "turn_budget_exhausted",
        "step_budget_exhausted",
        "TURN_BUDGET_EXCEEDED",
        "STEP_BUDGET_EXCEEDED",
        "MAX_TURNS_EXCEEDED",
        "PARSE_RECOVERY_EXHAUSTED",
        "cancelled",
        "canceled",
        "completed",
        "test_failed",
    }
)

INFRA_OUTCOMES = frozenset(
    {
        "PROVIDER_ERROR",
        "PROVIDER_TIMEOUT",
        "SANDBOX_ERROR",
        "CANCELLED",
        "CANCELED",
        "TIMEOUT",
        "VERIFY_ERROR",
        "VERIFICATION_ERROR",
        "EXECUTOR_CRASH",
        "INFRASTRUCTURE_FAILURE",
        "SANDBOX_BOOT_FAILURE",
        "INCOMPLETE_EVIDENCE",
        "NO_FIRST_TOKEN",
        "INVALID",
    }
)

LEARNABLE_OUTCOMES = frozenset(
    {
        "TEST_PASS",
        "TEST_FAIL",
        "STEP_BUDGET_EXCEEDED",
        "MAX_TURNS_EXCEEDED",
        "PARSE_RECOVERY_EXHAUSTED",
        "JUDGE_ONLY",
        "PASS",
        "FAIL",
        "WIN",
        "LOSS",
        "COMPLETED",
        "PASSED",
        "FAILED",
    }
)


@dataclass
class AuthoritativeResult:
    """Canonical authoritative result representing one fighter's verified final outcome."""

    battle_id: str
    phase: str = "main"
    role: str = "fighter"
    model_id: str = ""
    status: str = "completed"  # completed, timeout, crashed, policy_violation, incomplete, failed
    passed: bool = False
    score: float = 0.0
    verification_status: str = "unverified"  # verified_pass, verified_fail, unverified, not_attempted, infra_failure, policy_invalid
    termination_reason: str | None = None  # TEST_PASS, TEST_FAIL, STEP_BUDGET_EXCEEDED, PROVIDER_ERROR, etc.
    artifact_refs: list[str] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)
    finalized_at: datetime | None = None
    result_version: int = 1

    @property
    def identity(self) -> tuple[str, str, str, str]:
        """Canonical composite identity tuple."""
        return (self.battle_id, self.phase, self.role, self.model_id)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        if self.finalized_at is not None:
            data["finalized_at"] = self.finalized_at.isoformat()
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AuthoritativeResult:
        dt = data.get("finalized_at")
        if isinstance(dt, str):
            try:
                dt = datetime.fromisoformat(dt)
            except Exception:
                dt = None
        elif not isinstance(dt, datetime):
            dt = None

        return cls(
            battle_id=str(data.get("battle_id") or ""),
            phase=str(data.get("phase") or "main"),
            role=str(data.get("role") or "fighter"),
            model_id=str(data.get("model_id") or ""),
            status=str(data.get("status") or "completed"),
            passed=bool(data.get("passed", False)),
            score=float(data.get("score", 0.0)),
            verification_status=str(data.get("verification_status") or "unverified"),
            termination_reason=data.get("termination_reason"),
            artifact_refs=list(data.get("artifact_refs") or []),
            metrics=dict(data.get("metrics") or {}),
            finalized_at=dt,
            result_version=int(data.get("result_version") or 1),
        )


def normalize_participant_identity(
    battle_id: str,
    *,
    phase: str | None = None,
    role: str | None = None,
    model_id: str = "",
) -> tuple[str, str, str, str]:
    """Normalize phase, role, and model_id to canonical string keys."""
    norm_phase = str(phase or "main").strip().lower() or "main"
    norm_role = str(role or "fighter").strip().lower() or "fighter"
    norm_model = str(model_id or "").strip()
    return (str(battle_id), norm_phase, norm_role, norm_model)


def sanitize_untrusted_executor_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Keep only identity from sandbox EXECUTOR_RESULT.

    Pass/fail, scores, artifacts, steps, errors, infra claims, and unknown
    keys are discarded. The backend records UNTRUSTED_EXECUTION only.
    """
    raw = dict(payload or {})
    item = {key: raw[key] for key in _UNTRUSTED_KEEP if key in raw}
    item["outcome"] = UNTRUSTED_EXECUTION
    item["passed"] = False
    item["verification_status"] = "unverified"
    item["_trusted"] = False
    raw_term = str(raw.get("terminal_reason") or "")
    raw_exec = str(raw.get("executor_outcome") or raw.get("outcome") or "")
    if raw_term in _DISPLAY_TERMINAL:
        item["terminal_reason"] = raw_term
    if raw_exec in _DISPLAY_TERMINAL:
        item["executor_outcome"] = raw_exec
    return item


def is_infra_outcome(outcome: str | None) -> bool:
    """True when the outcome is infrastructure, not a learnable model result."""
    norm = str(outcome or "").strip().upper()
    if not norm:
        return False
    if norm in INFRA_OUTCOMES:
        return True
    if any(
        tok in norm
        for tok in (
            "PROVIDER",
            "SANDBOX",
            "INFRA",
            "VERIFY_ERROR",
            "VERIFICATION_ERROR",
            "EXECUTOR_CRASH",
            "NO_FIRST_TOKEN",
            "INCOMPLETE_EVIDENCE",
        )
    ):
        return True
    return False


def is_learnable_model_outcome(outcome: str | None) -> bool:
    """True when the outcome may update Elo, skill, or memory as model performance."""
    norm = str(outcome or "").strip().upper()
    if not norm or is_infra_outcome(norm):
        return False
    return norm in LEARNABLE_OUTCOMES


def participant_status_from_outcome(outcome: str | None, *, passed: bool = False) -> str:
    """Map a termination/outcome marker to a participant lifecycle status."""
    out = str(outcome or "").upper()
    if out in (
        "TEST_PASS",
        "TEST_FAIL",
        "JUDGE_ONLY",
        "PASS",
        "FAIL",
        "WIN",
        "LOSS",
        UNTRUSTED_EXECUTION,
        "COMPLETED",
    ):
        return "completed"
    if "BUDGET" in out or out == "TIMEOUT" or "TIMEOUT" in out:
        return "timeout"
    if "POLICY" in out:
        return "policy_violation"
    if is_infra_outcome(out):
        return "crashed"
    if passed:
        return "completed"
    return "completed" if out else "incomplete"


def aggregate_scores_by_model(scores_by_identity: dict[tuple[str, str, str], float]) -> dict[str, float]:
    """Fold (phase, role, model_id) scores into per-model totals for the scores table."""
    aggregated: dict[str, float] = {}
    for (_phase, _role, model_id), score in scores_by_identity.items():
        mid = str(model_id or "")
        if not mid:
            continue
        aggregated[mid] = aggregated.get(mid, 0.0) + float(score)
    return aggregated
