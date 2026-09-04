"""D5 fighter Skill Graph guidance and autonomy (hermetic, no provider calls)."""

from __future__ import annotations

from pathlib import Path

from agent_arena.sandbox.executors.advanced_executor import (
    ToolSession,
    build_fighter_system_prompt,
)
from agent_arena.skills import (
    fighter_skill_graph_guidance,
    guidance_word_count,
    load_skill_graph,
)
from agent_arena.skills.discovery import skill_capability_affinity
from agent_arena.skills.guidance import (
    GUIDANCE_MAX_CHARS,
    GUIDANCE_MAX_EXAMPLE_SKILL_IDS,
    GUIDANCE_MAX_WORDS,
    GUIDANCE_MIN_WORDS,
    PROMPT_MAX_CHARS,
)

FORBIDDEN_MANDATORY = (
    "you must use skills",
    "always load a skill first",
    "follow recommended skills",
    "complete prerequisites",
    "maximum 3 skills",
    "loading this skill enables",
    "enables a capability",
    "grants permission",
    "grants network",
    "skills pool (pick",
    "on turn 1 only",
    "emit skills:",
    "pick 3 skills",
    "use_skill once per chosen skill",
)

FORBIDDEN_PRIVATE = (
    "hidden_command",
    "hidden_hash",
    "hidden_test",
    "hidden tests",
    "BATTLE_TOKEN",
    "OPENROUTER_API_KEY",
    "HOST_OPENROUTER_KEY",
    "JUDGE_MODAL_KEY",
    "JUDGE_MODAL_SECRET",
    "/opt/arena-evaluators",
    "reference solution",
    "visible_command",
    "evaluator path",
)


def _bootstrap(**overrides) -> str:
    kwargs = {
        "role": "attacker",
        "format_name": "TinyShop",
        "mission": "fix the shop",
        "network_allowed": False,
        "max_steps": 14,
        "max_turns": 6,
        "judge_only": False,
        "custom": False,
    }
    kwargs.update(overrides)
    kwargs.pop("skill_list_text", None)
    kwargs.pop("opponent_info", None)
    kwargs.pop("prior", None)
    isolated = kwargs.pop("isolated_target", False)
    if isolated:
        kwargs["custom"] = True
    return build_fighter_system_prompt(**kwargs)


def test_fighter_prompt_contains_skills_guidance():
    prompt = _bootstrap()
    assert "skills()" in prompt
    assert 'skills(index="security")' in prompt
    assert 'skills(search="session replay token")' in prompt
    assert 'skills(skill="auth-flow-debugger")' in prompt
    assert "optional advisory expertise" in prompt


def test_fighter_prompt_contains_use_skill():
    prompt = _bootstrap()
    assert "use_skill" in prompt
    assert 'use_skill("auth-flow-debugger")' in prompt


def test_skills_are_described_as_optional_advisory():
    prompt = _bootstrap().lower()
    guidance = fighter_skill_graph_guidance().lower()
    assert "optional expertise" in guidance
    assert "advisory" in guidance
    assert "optional advisory expertise" in prompt
    for phrase in FORBIDDEN_MANDATORY:
        assert phrase not in prompt
        assert phrase not in guidance


def test_prompt_does_not_contain_mandatory_skill_pool_or_turn1_pick():
    prompt = _bootstrap()
    isolated = _bootstrap(isolated_target=True, custom=True)
    for text in (prompt, isolated):
        assert "SKILLS POOL (pick" not in text
        assert "On turn 1 only" not in text
        assert "emit SKILLS:" not in text
        assert "pick 3 skills" not in text.lower()
        assert "once per chosen skill" not in text
        assert "Opponent also picks" not in text


def test_prompt_does_not_require_initial_use_skill():
    prompt = _bootstrap().lower()
    assert "no skill is automatically required" in prompt
    assert "zero, one, or multiple skills" in prompt
    assert "always load" not in prompt
    assert "must use_skill" not in prompt


def test_shortlist_is_advisory_and_not_exclusive():
    prompt = _bootstrap()
    assert "OPTIONAL STARTING SUGGESTIONS" not in prompt
    assert "SKILLS POOL" not in prompt
    assert "skills()" in prompt
    assert "zero, one, or multiple skills" in prompt


def test_prompt_size_regression_guard():
    guidance = fighter_skill_graph_guidance()
    prompt = _bootstrap()
    words = guidance_word_count(guidance)
    assert GUIDANCE_MIN_WORDS <= words <= GUIDANCE_MAX_WORDS
    assert len(guidance) <= GUIDANCE_MAX_CHARS
    assert len(prompt) <= PROMPT_MAX_CHARS
    assert guidance == fighter_skill_graph_guidance()


def test_initial_prompt_does_not_dump_catalog_or_bodies():
    prompt = _bootstrap()
    graph = load_skill_graph()
    skill_ids = [skill.id for skill in graph.all_skills()]
    mentioned = [skill_id for skill_id in skill_ids if skill_id in prompt]
    assert len(skill_ids) == 63
    assert len(graph.all_indexes()) == 65
    assert len(mentioned) <= GUIDANCE_MAX_EXAMPLE_SKILL_IDS
    assert "auth-flow-debugger" in mentioned
    assert "SKILL.md" not in fighter_skill_graph_guidance()
    for skill in graph.all_skills():
        if skill.body:
            assert skill.body not in prompt


def test_battle_starts_with_zero_loaded_skills(tmp_path: Path):
    session = ToolSession(tmp_path)
    assert session.skill_reads == set()
    assert session.steps == 0


def test_fighter_may_run_a_normal_tool_before_loading_a_skill(tmp_path: Path):
    session = ToolSession(tmp_path)
    listed = session.ls(count_step=True)
    written = session.write("notes.txt", "start without skills", count_step=True)

    assert listed.success is True
    assert written.success is True
    assert session.skill_reads == set()
    assert session.steps == 2


def test_browsing_does_not_mark_a_skill_loaded(tmp_path: Path):
    session = ToolSession(tmp_path)
    root = session.skills(count_step=False)
    index = session.skills(index="security", count_step=False)
    search = session.skills(search="session replay token", count_step=False)
    card = session.skills(skill="auth-flow-debugger", count_step=False)

    assert root.success is True
    assert index.success is True
    assert search.success is True
    assert card.success is True
    assert session.skill_reads == set()
    assert "SKILL GRAPH ROOT INDEXES" in root.output
    assert "auth-flow-debugger" in card.output


def test_multiple_skills_can_be_explicitly_loaded_without_cap(tmp_path: Path):
    skill_ids = [
        "auth-flow-debugger",
        "python-kata-fixer",
        "secure-code-execution",
        "hypothesis-driven-debugging",
    ]
    for skill_id in skill_ids:
        skill_dir = tmp_path / ".agents" / "skills" / skill_id
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(f"body-{skill_id}\n", encoding="utf-8")
    session = ToolSession(tmp_path)

    results = [session.use_skill(skill_id, count_step=False) for skill_id in skill_ids]

    assert all(result.success for result in results)
    assert session.skill_reads == set(skill_ids)
    assert len(session.skill_reads) == 4


def test_full_graph_remains_discoverable_beyond_shortlist(tmp_path: Path):
    session = ToolSession(tmp_path)
    prompt = _bootstrap()
    browsed = session.skills(count_step=False)

    assert "python-kata-fixer" not in prompt
    assert "SKILL GRAPH ROOT INDEXES" in browsed.output
    assert "13 roots" in browsed.output
    assert "63 skills" in browsed.output


def test_capability_affinity_still_grants_nothing(tmp_path: Path):
    skill_dir = tmp_path / ".agents" / "skills" / "technical-web-researcher"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: technical-web-researcher\n---\nbody\n",
        encoding="utf-8",
    )
    session = ToolSession(tmp_path, allow_network=False)
    prompt = _bootstrap().lower()

    assert skill_capability_affinity("technical-web-researcher") == ("web_research",)
    loaded = session.use_skill("technical-web-researcher", count_step=False)
    denied = session.shell("curl https://example.com", count_step=False)

    assert "does not grant capabilities" in prompt
    assert loaded.success is True
    assert session.allow_network is False
    assert denied.success is False
    assert denied.policy_rejected is True


def test_guidance_and_bootstrap_contain_no_private_or_secret_metadata():
    for blob in (fighter_skill_graph_guidance(), _bootstrap()):
        lowered = blob.lower()
        for token in FORBIDDEN_PRIVATE:
            assert token.lower() not in lowered
        assert "sk-or-" not in blob


def test_guidance_does_not_start_d6_telemetry():
    text = fighter_skill_graph_guidance().lower()
    assert "telemetry" not in text
    assert "analytics" not in text
    assert "recommendation learning" not in text
    assert "outcome correlation" not in text


def test_d5_uses_no_network_or_provider_key(monkeypatch):
    def fail_network(*args, **kwargs):
        raise AssertionError("D5 guidance must not make network requests")

    monkeypatch.setattr("urllib.request.urlopen", fail_network)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("HOST_OPENROUTER_KEY", raising=False)

    assert "skills()" in _bootstrap()
