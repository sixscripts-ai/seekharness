"""D5 fighter Skill Graph usage guidance.

Compact, deterministic, target-independent, and model-independent. Safe to
inject into every fighter session. Does not load catalog rows, skill bodies,
or grant capabilities.
"""

from __future__ import annotations

GUIDANCE_MIN_WORDS = 80
GUIDANCE_MAX_WORDS = 200
GUIDANCE_MAX_CHARS = 1800
GUIDANCE_MAX_EXAMPLE_SKILL_IDS = 4
PROMPT_MAX_CHARS = 6000

_FIGHTER_SKILL_GRAPH_GUIDANCE = """\
Skill Graph is available as optional expertise.

Use skills() to browse categories.
Use skills(index="security") to inspect an index.
Use skills(search="session replay token") to search compact metadata.
Use skills(skill="auth-flow-debugger") to inspect a compact skill card.
Use use_skill("auth-flow-debugger") only when you want the full skill body.

Skills are advisory. You may use none, one, or several; revisit or abandon them as useful. You may start solving immediately without loading any skill. A short suggestion list may appear below; the full public Skill Graph stays available through skills(). Unlisted skills are still available.

Skill metadata never grants tools, network access, or permissions. Loading a skill does not enable network, web search, credentials, or tools. Arena policy still decides what you can do.\
"""


def fighter_skill_graph_guidance() -> str:
    """Return the public Skill Graph usage block for fighter bootstrap."""
    return _FIGHTER_SKILL_GRAPH_GUIDANCE


def guidance_word_count(text: str | None = None) -> int:
    return len((text if text is not None else fighter_skill_graph_guidance()).split())
