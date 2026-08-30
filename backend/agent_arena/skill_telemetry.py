"""Public-safe Skill Graph activity envelopes.

Skill activity is observational only. This module deliberately returns compact
references and never serializes a skill body or discovery response.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any

SKILL_EVENT_TYPES = frozenset(
    {
        "skill_index_browse",
        "skill_search",
        "skill_card_view",
        "skill_load",
    }
)

_SENSITIVE_QUERY_RE = re.compile(
    r"(?:api[_-]?key|battle[_-]?token|password|secret|private[_-]?key|"
    r"hidden[_-]?(?:test|command|output)|reference[_-]?(?:solution|file)|"
    r"evaluator|/opt/arena|target\.md)\s*[:=]",
    re.IGNORECASE,
)
_PRIVATE_QUERY_MARKERS = (
    "hidden",
    "reference",
    "evaluator",
    "flag",
    "private fixture",
    "private",
    "protected file",
    "target.md",
    "secret",
    "credential",
    "api key",
    "battle token",
)


def safe_skill_id(value: Any) -> str:
    """Return a bounded identifier suitable for a public event."""
    raw = " ".join(str(value or "").split())
    if not raw:
        return ""
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,119}", raw):
        return raw
    return f"unknown:{hashlib.sha256(raw.encode('utf-8')).hexdigest()[:16]}"


def safe_skill_query(value: Any) -> str:
    """Keep useful search context while blocking obvious private material."""
    raw = " ".join(str(value or "").split())
    if not raw:
        return ""
    lowered = raw.lower()
    if _SENSITIVE_QUERY_RE.search(raw) or any(
        marker in lowered for marker in _PRIVATE_QUERY_MARKERS
    ):
        return "[redacted]"
    return raw[:160]


def _canonical_id(resolver: Any, reference: Any) -> str:
    raw = safe_skill_id(reference)
    if not raw:
        return ""
    try:
        canonical = resolver.resolve(raw)
    except Exception:
        canonical = None
    return safe_skill_id(getattr(canonical, "id", None) or raw)


def skill_event_for_call(
    call: dict[str, Any],
    resolver: Any,
) -> tuple[str, dict[str, str]] | None:
    """Map one executed skill tool call to its compact observable event."""
    tool = str(call.get("tool") or "").strip().lower()

    if tool == "skills":
        # `chosen` is a suggestion/selection signal, not a load or browse.
        if "chosen" in call:
            return None
        if call.get("index") is not None:
            return "skill_index_browse", {"index": safe_skill_id(call["index"])}
        if call.get("search") is not None:
            return "skill_search", {"query": safe_skill_query(call["search"])}
        if call.get("skill") is not None:
            return "skill_card_view", {
                "skill_id": _canonical_id(resolver, call["skill"])
            }
        # `skills()` and `skills(list=True)` are catalog navigation.
        return "skill_index_browse", {}

    if tool == "use_skill":
        return "skill_load", {
            "skill_id": _canonical_id(resolver, call.get("name"))
        }

    return None


def public_skill_tool_output(
    call: dict[str, Any],
    *,
    success: bool,
    resolver: Any,
) -> str:
    """Summarize skill-tool output without exposing its response body."""
    activity = skill_event_for_call(call, resolver)
    if activity is None:
        chosen = [
            safe_skill_id(value)
            for value in (call.get("chosen") or [])
            if safe_skill_id(value)
        ]
        return f"SKILLS_CHOSEN {','.join(chosen)}" if chosen else "SKILLS_BROWSE"

    event_type, fields = activity
    parts = [event_type]
    for key in ("skill_id", "index", "query"):
        if fields.get(key):
            parts.append(f"{key}={fields[key]}")
    if event_type == "skill_load":
        parts.append("loaded=true" if success else "loaded=false")
    return " ".join(parts)


def public_skill_file_read(path: Any) -> str | None:
    """Replace a mounted SKILL.md body with a non-sensitive read marker."""
    raw = str(path or "").replace("\\", "/")
    if ".agents/skills/" not in raw or not raw.endswith("/SKILL.md"):
        return None
    skill_name = raw.split(".agents/skills/", 1)[1].split("/", 1)[0]
    return f"SKILL_FILE_READ {safe_skill_id(skill_name)}"
