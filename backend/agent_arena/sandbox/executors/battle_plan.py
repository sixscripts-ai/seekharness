"""BattlePlan domain model, parser, and least-privilege handoff.

A BattlePlan is an explicit multi-phase contract: spawn → materialize → loop →
snapshot → verify → commit. Handoffs copy allowlisted artifact bytes + a
manifest only — never a whole workspace, never harness files, never secrets.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_SAFE_REL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]*$")
_FORBIDDEN_NAMES = {
    ".env",
    ".env.local",
    ".arena_secret",
    ".netrc",
    "id_rsa",
    "id_ed25519",
    "credentials.json",
}
_FORBIDDEN_SUFFIXES = (".pem", ".key", ".p12", ".pfx")
_HARNESS_PATHS = {"tests/test_target.py", "test_target.py"}


@dataclass(frozen=True)
class PlanPhase:
    phase_id: str
    phase_type: str
    actor: str
    required_outputs: list[str] = field(default_factory=list)
    handoff_from: list[str] = field(default_factory=list)
    handoff_artifacts: list[str] = field(default_factory=list)
    protected_artifacts: list[str] = field(default_factory=list)
    starter_files: dict[str, str] = field(default_factory=dict)
    test_code: str = ""
    workspace_policy: str = "fresh"


@dataclass(frozen=True)
class BattlePlan:
    plan_id: str
    format_id: str
    phases: list[PlanPhase]


def has_battle_plan(format_config: dict | None) -> bool:
    cfg = format_config or {}
    flag = cfg.get("battle_plan")
    if flag in (None, False, "", 0):
        return False
    return True


def parse_battle_plan(format_config: dict | None) -> BattlePlan | None:
    """Return a BattlePlan when the format opts in; otherwise None."""
    cfg = format_config or {}
    if not has_battle_plan(cfg):
        return None
    raw = cfg.get("battle_plan")
    phase_specs: list[dict] = []
    if isinstance(raw, dict):
        phase_specs = list(raw.get("phases") or raw.get("phase_plans") or [])
        plan_id = str(raw.get("plan_id") or cfg.get("id") or cfg.get("name") or "plan")
    else:
        phase_specs = list(cfg.get("phase_plans") or [])
        plan_id = str(cfg.get("id") or cfg.get("name") or "plan")
    if not phase_specs:
        phase_specs = _derive_phase_specs(cfg)
    if not phase_specs:
        return None
    role_tests = cfg.get("role_test_code") or {}
    phases: list[PlanPhase] = []
    for spec in phase_specs:
        if not isinstance(spec, dict):
            continue
        phase_id = str(spec.get("phase_id") or spec.get("name") or "").strip()
        actor = str(spec.get("actor") or "").strip()
        phase_type = str(spec.get("phase_type") or phase_id or "phase").strip()
        if not phase_id or not actor or actor == "judge" or phase_type == "judge":
            continue
        test_code = str(
            spec.get("test_code")
            or role_tests.get(actor)
            or cfg.get("test_code")
            or ""
        )
        starter = spec.get("starter_files") if isinstance(spec.get("starter_files"), dict) else {}
        phases.append(
            PlanPhase(
                phase_id=phase_id,
                phase_type=phase_type,
                actor=actor,
                required_outputs=_str_list(spec.get("required_outputs")),
                handoff_from=_str_list(spec.get("handoff_from")),
                handoff_artifacts=_str_list(spec.get("handoff_artifacts")),
                protected_artifacts=_str_list(spec.get("protected_artifacts")),
                starter_files={str(k): str(v) for k, v in starter.items()},
                test_code=test_code,
                workspace_policy=str(spec.get("workspace_policy") or "fresh"),
            )
        )
    if not phases:
        return None
    return BattlePlan(
        plan_id=plan_id,
        format_id=str(cfg.get("id") or cfg.get("name") or ""),
        phases=phases,
    )


def _derive_phase_specs(cfg: dict) -> list[dict]:
    specs: list[dict] = []
    for raw in cfg.get("phases") or []:
        if not isinstance(raw, dict):
            continue
        name = str(raw.get("name") or "")
        parts = [p for p in (raw.get("participants") or []) if p and p != "judge"]
        if not name or not parts or name == "judge":
            continue
        specs.append(
            {
                "phase_id": name,
                "phase_type": name,
                "actor": parts[0],
                "handoff_from": [
                    str(x)
                    for x in (raw.get("inputs") or [])
                    if x and x != "judge"
                ],
                "required_outputs": _str_list(
                    ((cfg.get("artifacts") or {}).get("required"))
                ),
            }
        )
    return specs


def _str_list(value: Any) -> list[str]:
    if not isinstance(value, (list, tuple)):
        return []
    out: list[str] = []
    for item in value:
        text = str(item or "").strip()
        if text:
            out.append(text)
    return out


def safe_relpath(rel: str) -> str | None:
    text = str(rel or "").replace("\\", "/").strip()
    if not text or text.startswith("/") or ".." in text.split("/"):
        return None
    if not _SAFE_REL.match(text):
        return None
    return text


def is_forbidden_handoff(rel: str) -> bool:
    path = (rel or "").replace("\\", "/").strip()
    while path.startswith("./"):
        path = path[2:]
    if not path or path.startswith("/"):
        return True
    name = Path(path).name
    if path in _HARNESS_PATHS or name in _FORBIDDEN_NAMES:
        return True
    if name.startswith(".env"):
        return True
    lower = name.lower()
    if any(lower.endswith(sfx) for sfx in _FORBIDDEN_SUFFIXES):
        return True
    return False


def snapshot_handoff(work: Path, artifact_refs: list[str]) -> dict[str, Any]:
    """Copy allowlisted files from a fighter workspace into a handoff snapshot."""
    root = work.resolve()
    files: dict[str, bytes] = {}
    manifest: list[dict[str, Any]] = []
    for ref in artifact_refs:
        rel = safe_relpath(ref)
        if rel is None or is_forbidden_handoff(rel):
            manifest.append({"path": ref, "rejected": True})
            continue
        path = (root / rel).resolve()
        try:
            path.relative_to(root)
        except ValueError:
            manifest.append({"path": rel, "rejected": True})
            continue
        if not path.is_file():
            manifest.append({"path": rel, "missing": True})
            continue
        data = path.read_bytes()
        files[rel] = data
        manifest.append(
            {
                "path": rel,
                "sha256": hashlib.sha256(data).hexdigest(),
                "bytes": len(data),
            }
        )
    return {"files": files, "manifest": manifest}


def write_allowed_file(work: Path, rel: str, data: bytes | str) -> bool:
    safe = safe_relpath(rel)
    if safe is None or is_forbidden_handoff(safe):
        return False
    root = work.resolve()
    dest = (root / safe).resolve()
    try:
        dest.relative_to(root)
    except ValueError:
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    payload = data if isinstance(data, bytes) else str(data).encode("utf-8")
    dest.write_bytes(payload)
    return True


def restore_protected(work: Path, protected: dict[str, bytes]) -> None:
    """Rewrite protected artifacts from the frozen handoff snapshot."""
    for rel, data in (protected or {}).items():
        write_allowed_file(work, rel, data)
