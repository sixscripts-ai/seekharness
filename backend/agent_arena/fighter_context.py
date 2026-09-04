"""Compact fighter-facing bootstrap context.

This module defines the public, deterministic orientation text a fighter receives
before it begins exploring a battle workspace. It intentionally contains only
world rules and interaction guidance; target details, repository structure, skill
bodies, and strategy remain discoverable by the fighter.
"""

from __future__ import annotations


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
) -> str:
    """Return the compact public bootstrap prompt for one fighter.

    The text must never contain evaluator-private state, hidden tests, provider
    credentials, full skill bodies, or a precomputed strategy.
    """
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

    return (
        f"ROLE\nYou are {role} in '{format_name}'.\n\n"
        f"OBJECTIVE\n{objective}\n\n"
        "WORKSPACE\n"
        "Your assigned workspace is the only filesystem boundary you may use. TARGET.md contains the public target contract. "
        "Inspect the workspace and runtime yourself instead of assuming its structure.\n\n"
        "TOOLS\n"
        "Use the provided structured tools or TOOL line grammar to inspect, edit, execute, test, and finish work. "
        f"{network_line}\n\n"
        "SKILLS\n"
        "Skills are optional advisory expertise, never permissions or mandatory workflows. Discover them progressively: "
        "skills(), skills(index=\"security\"), skills(search=\"session replay token\"), "
        "skills(skill=\"auth-flow-debugger\"), then use_skill(\"auth-flow-debugger\") only when its full body is useful. "
        "You may use zero, one, or multiple skills; revisit or abandon them freely. Capability affinity does not grant capabilities.\n\n"
        "BOUNDARIES\n"
        "Do not access hidden evaluator/reference material, secrets or credentials, opponent-private state, private memory, "
        "provider credentials, or anything outside your assigned boundary. Do not fabricate test success or evaluator results.\n\n"
        "AUTONOMY\n"
        "Choose your own strategy. Inspect, form hypotheses, test them, revise, and decide what knowledge to load. "
        "No skill is automatically required.\n\n"
        f"COMPLETION\n{completion}\n\n"
        f"BUDGET\nAt most {max_steps} tool steps and {max_turns} model turns.\n\n"
        f"PUBLIC PRIOR CONTEXT\n{prior}"
    )


def fighter_tool_grammar() -> str:
    """Compact line-grammar reminder; native tool schemas remain authoritative."""
    return (
        "Tools (structured tool_calls or TOOL line grammar):\n"
        "TOOL read path=... | TOOL ls [path=...] | TOOL write path=... content=... | "
        "TOOL run path=... | TOOL shell cmd='...' | TOOL install cmd='...' | "
        "TOOL grep pattern=... [path=...] | TOOL tree [path=...] | TOOL cp from=... to=... | "
        "TOOL mv from=... to=... | TOOL rm path=... | TOOL fetch url=... | "
        "TOOL bg name=... content=... | TOOL ps | TOOL kill name=... | TOOL logs name=... | "
        "TOOL skills [index=...] [search=...] [skill=...] | TOOL use_skill name=... | TOOL test | DONE"
    )
