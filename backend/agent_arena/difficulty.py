"""Named difficulty presets for format/target execution contracts.

Kept free of Appwrite, FastAPI, and persistence imports so the fighter
sandbox can apply difficulty without pulling control-plane packages.
"""

from __future__ import annotations

DIFFICULTY_PRESETS = {
    "novice": {
        "limits": {
            "max_tool_turns": 3,
            "max_tool_steps": 8,
            "exec_timeout_seconds": 180,
        },
        "scoring": {"weights": {"tests": 0.7, "skills": 0.1, "theory": 0.2}},
    },
    "general": {
        "limits": {
            "max_tool_turns": 6,
            "max_tool_steps": 14,
            "exec_timeout_seconds": 240,
        },
        "scoring": {"weights": {"tests": 0.6, "skills": 0.2, "theory": 0.2}},
    },
    "advanced": {
        "limits": {
            "max_tool_turns": 8,
            "max_tool_steps": 20,
            "exec_timeout_seconds": 300,
        },
        "scoring": {"weights": {"tests": 0.5, "skills": 0.3, "theory": 0.2}},
    },
    "expert": {
        "limits": {
            "max_tool_turns": 12,
            "max_tool_steps": 30,
            "exec_timeout_seconds": 420,
        },
        "scoring": {"weights": {"tests": 0.4, "skills": 0.4, "theory": 0.2}},
    },
}


def apply_difficulty(cfg: dict, difficulty: str | None) -> dict:
    """Merge a named difficulty preset into a format config (E14).

    Only tunes limits/scoring — never containment. Preset limits override the
    manifest's own limits for the matching keys; other keys are preserved.
    """
    if not difficulty:
        return cfg
    preset = DIFFICULTY_PRESETS.get(difficulty)
    if not preset:
        return cfg
    out = dict(cfg)
    out["difficulty"] = difficulty
    manifest_limits = dict(out.get("limits") or {})
    manifest_limits.update(preset.get("limits") or {})
    out["limits"] = manifest_limits
    manifest_scoring = dict(out.get("scoring") or {})
    manifest_scoring.update(preset.get("scoring") or {})
    out["scoring"] = manifest_scoring
    for k, v in (preset.get("limits") or {}).items():
        out[k] = v
    return out
