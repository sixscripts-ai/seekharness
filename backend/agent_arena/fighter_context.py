"""Compact fighter-facing bootstrap context and agent prompt generation.

This module defines the public, deterministic orientation text a fighter receives
before it begins exploring a battle workspace. Incorporates specialized agent
personas and behavioral guidelines from agent_arena.agents when configured.
"""

from __future__ import annotations

from typing import Iterable, Set


TOOL_GRAMMAR_MAP = {
    "read": "TOOL read path=...",
    "ls": "TOOL ls [path=...]",
    "write": "TOOL write path=... content=...",
    "run": "TOOL run path=...",
    "shell": "TOOL shell cmd='...'",
    "install": "TOOL install cmd='...'",
    "grep": "TOOL grep pattern=... [path=...]",
    "tree": "TOOL tree [path=...]",
    "cp": "TOOL cp from=... to=...",
    "mv": "TOOL mv from=... to=...",
    "rm": "TOOL rm path=...",
    "clean": "TOOL clean path=...",
    "fetch": "TOOL fetch url=...",
    "bg": "TOOL bg name=... content=...",
    "ps": "TOOL ps",
    "kill": "TOOL kill name=...",
    "logs": "TOOL logs name=...",
    "skills": "TOOL skills [index=...] [search=...] [skill=...]",
    "use_skill": "TOOL use_skill name=...",
    "test": "TOOL test",
    "done": "DONE",
}


def _compact_bullets(items: list[str], *, per_item: int) -> str:
    """Keep every configured guidance item present within the prompt budget."""
    compact: list[str] = []
    for item in items:
        text = " ".join(str(item).split())
        if len(text) > per_item:
            text = text[: max(1, per_item - 3)].rstrip() + "..."
        compact.append(f"- {text}")
    return "\n".join(compact)


def build_fighter_system_prompt(
    *,
    role: str,
    format_name: str,
    mission: str = "",
    network_allowed: bool = False,
    max_steps: int,
    max_turns: int,
    judge_only: bool = False,
    custom: bool = False,
    prior_public_context: str = "",
    agent_id: str | None = None,
) -> str:
    """Return the public bootstrap prompt for one fighter or configured agent.

    The text must never contain evaluator-private state, hidden tests, provider
    credentials, full skill bodies, or a precomputed strategy.
    """
    from .agents import get_agent, get_agent_for_role

    agent = get_agent(agent_id) if agent_id else (
        get_agent_for_role(role)
        if str(role).strip().lower()
        in {"builder", "breaker", "fighter", "judge", "reviewer"}
        else None
    )

    objective = mission.strip() or "Read TARGET.md for the public objective and acceptance contract."
    completion = (
        "Write the required artifacts from TARGET.md, write THEORY.md, then emit DONE. "
        "There is no canonical public test harness; the trusted evaluator determines success."
        if judge_only
        else (
            "Write the required artifacts from TARGET.md and THEORY.md. Use TOOL test when useful. "
            "After you are satisfied with the result, emit DONE. The trusted evaluator determines success."
        )
    )
    if custom and not judge_only:
        completion = (
            "Write the required artifacts from TARGET.md and THEORY.md. Use TOOL test when useful. "
            "After you are satisfied with the result, emit DONE. The trusted evaluator determines success."
        )

    network_line = (
        "Network access is available only through the tools and policy exposed to this fighter."
        if network_allowed
        else "Network access is not allowed for this fighter."
    )
    prior = prior_public_context.strip() or "(none)"

    # Base role identity
    role_header = f"ROLE\nYou are {role} in '{format_name}'."
    if agent:
        role_header += f" Agent Persona: {agent.name} ({agent.agent_id}).\n\n{agent.system_prompt}"

    behavior_section = ""
    if agent and agent.behavioral_instructions:
        bullets = _compact_bullets(agent.behavioral_instructions, per_item=118)
        behavior_section = f"\n\nBEHAVIORAL GUIDELINES\n{bullets}"

    anti_patterns_section = ""
    if agent and agent.anti_patterns:
        bullets = _compact_bullets(agent.anti_patterns, per_item=75)
        anti_patterns_section = f"\n\nANTI-PATTERNS (DO NOT DO)\n{bullets}"

    stopping_details = completion
    if agent and agent.evidence_contract.stopping_condition:
        stopping_details = f"{agent.evidence_contract.stopping_condition}\n{completion}"

    return (
        f"{role_header}\n\n"
        f"OBJECTIVE\n{objective}\n\n"
        "WORKSPACE\n"
        "Use only your assigned workspace. TARGET.md is the public contract; inspect before acting.\n\n"
        "TOOLS\n"
        "Use only provided structured tools or TOOL grammar. "
        f"{network_line}\n\n"
        "SKILLS\n"
        "Skills are optional advisory expertise and never grant permissions. Discover progressively: "
        "skills(), skills(index=\"security\"), skills(search=\"session replay token\"), "
        "skills(skill=\"auth-flow-debugger\"), then use_skill(\"auth-flow-debugger\") if useful. "
        "Use zero, one, or multiple skills. Capability affinity does not grant capabilities.\n\n"
        "BOUNDARIES\n"
        "Never access hidden evaluator/reference material, credentials, opponent-private state, "
        "private memory, or anything outside your boundary. Never fabricate evidence.\n\n"
        "AUTONOMY\n"
        "Inspect, test hypotheses, revise, and choose relevant knowledge. "
        f"No skill is automatically required.{behavior_section}{anti_patterns_section}\n\n"
        f"COMPLETION & EVIDENCE\n{stopping_details}\n\n"
        f"BUDGET\nAt most {max_steps} tool steps and {max_turns} model turns.\n\n"
        f"PUBLIC PRIOR CONTEXT\n{prior}"
    )


def fighter_tool_grammar(allowed_tools: Iterable[str] | None = None) -> str:
    """Compact line-grammar reminder filtered to allowed tools if specified."""
    if allowed_tools is not None:
        allowed_set: Set[str] = {str(t).strip().lower() for t in allowed_tools}
        parts = [
            grammar
            for tool_name, grammar in TOOL_GRAMMAR_MAP.items()
            if tool_name in allowed_set or tool_name == "done"
        ]
        if not parts:
            parts = [TOOL_GRAMMAR_MAP["done"]]
        return "Tools (structured tool_calls or TOOL line grammar):\n" + " | ".join(parts)

    return (
        "Tools (structured tool_calls or TOOL line grammar):\n"
        "TOOL read path=... | TOOL ls [path=...] | TOOL write path=... content=... | "
        "TOOL run path=... | TOOL shell cmd='...' | TOOL install cmd='...' | "
        "TOOL grep pattern=... [path=...] | TOOL tree [path=...] | TOOL cp from=... to=... | "
        "TOOL mv from=... to=... | TOOL rm path=... | TOOL fetch url=... | "
        "TOOL bg name=... content=... | TOOL ps | TOOL kill name=... | TOOL logs name=... | "
        "TOOL skills [index=...] [search=...] [skill=...] | TOOL use_skill name=... | TOOL test | DONE"
    )
