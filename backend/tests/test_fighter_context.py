from agent_arena.fighter_context import build_fighter_system_prompt, fighter_tool_grammar


def test_fighter_bootstrap_is_compact_optional_and_progressive():
    prompt = build_fighter_system_prompt(
        role="builder",
        format_name="Target battle",
        mission="Repair the public auth flow.",
        network_allowed=False,
        max_steps=14,
        max_turns=6,
    )

    assert "Repair the public auth flow." in prompt
    assert "TARGET.md" in prompt
    assert "skills()" in prompt
    assert 'skills(index="security")' in prompt
    assert 'skills(search="session replay token")' in prompt
    assert 'skills(skill="auth-flow-debugger")' in prompt
    assert 'use_skill("auth-flow-debugger")' in prompt
    assert "optional advisory expertise" in prompt
    assert "zero, one, or multiple skills" in prompt
    assert "Capability affinity does not grant capabilities" in prompt
    assert "Network access is not allowed" in prompt
    assert "trusted evaluator determines success" in prompt
    assert len(prompt) < 3500


def test_fighter_bootstrap_does_not_force_strategy_or_dump_skill_catalog():
    prompt = build_fighter_system_prompt(
        role="breaker",
        format_name="Security battle",
        network_allowed=True,
        max_steps=20,
        max_turns=8,
    )

    forbidden = (
        "SKILLS POOL",
        "pick 3",
        "On turn 1",
        "must use a skill",
        "Discovery Quality",
        "hidden_hash",
        "hidden_command",
        "BATTLE_TOKEN",
        "OPENROUTER_API_KEY",
    )
    for text in forbidden:
        assert text not in prompt

    # The bootstrap gives discovery examples, not the full catalog.
    assert prompt.count("auth-flow-debugger") == 2
    assert "technical-web-researcher" not in prompt
    assert "Network access is available" in prompt


def test_fighter_tool_grammar_exposes_discovery_without_skill_dump():
    grammar = fighter_tool_grammar()
    assert "TOOL skills [index=...] [search=...] [skill=...]" in grammar
    assert "TOOL use_skill name=..." in grammar
    assert "SKILLS POOL" not in grammar
    assert len(grammar) < 1000
