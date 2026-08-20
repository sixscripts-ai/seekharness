from agent_arena.seed_formats import (
    CATALOG_FORMAT_DEFINITIONS,
    ENGINE_TEMPLATES,
    FORMAT_DEFINITIONS,
    ALL_FORMATS,
    build_format,
    is_playable_format,
)


def test_exactly_seven_playable_formats():
    assert len(FORMAT_DEFINITIONS) == 7
    assert len(ALL_FORMATS) == 7


def test_playable_names():
    names = {name for name, _, _ in FORMAT_DEFINITIONS}
    assert names == {
        "Auth system vs breaker",
        "Tool-using coding race",
        "Debugging race",
        "Code review duel",
        "RE solve race",
        "Pwn exploit race",
        "Injection agent vs hardened agent",
    }


def test_catalog_kept_as_backlog():
    catalog = {name for name, _, _ in CATALOG_FORMAT_DEFINITIONS}
    playable = {name for name, _, _ in FORMAT_DEFINITIONS}
    assert "WAF builder vs bypasser" in catalog
    assert "Two-agent duel" in catalog
    assert catalog.isdisjoint(playable)


def test_all_engines_still_defined():
    engines = {eng for _, eng, _ in FORMAT_DEFINITIONS + CATALOG_FORMAT_DEFINITIONS}
    assert engines == set(ENGINE_TEMPLATES)


def test_every_seeded_format_is_playable():
    for cfg in ALL_FORMATS:
        assert is_playable_format(cfg), cfg["name"]


def test_is_playable_format_gates():
    assert is_playable_format({"engine": "agent_tool_race"})
    assert is_playable_format({"engine": "same_target_race", "universal": True})
    assert is_playable_format({"engine": "build_and_break", "battle_plan": True})
    assert not is_playable_format({"engine": "build_and_break"})
    assert not is_playable_format(
        {"engine": "agent_tool_race", "hidden": True}
    )
    assert not is_playable_format(
        {"engine": "agent_tool_race", "playable": False}
    )


def test_build_format_shape():
    cfg = build_format("Code review duel", "same_target_race", "Two reviewers on one target")
    assert cfg["id"] == "code-review-duel"
    assert cfg["engine"] == "same_target_race"
    assert cfg["sandbox_image"] == "python:3.11-slim"
    assert cfg["timeout_seconds"] == 600
    assert cfg["round_visibility"] == "isolated"
    assert set(["roles", "phases", "judge_rubric", "scoring_weights"]) <= set(cfg)


def test_ids_are_unique():
    ids = [build_format(n, e, d)["id"] for n, e, d in FORMAT_DEFINITIONS]
    assert len(ids) == len(set(ids))
