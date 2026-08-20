from agent_arena.custom_battles import (
    FrozenConfigError,
    SpecValidationError,
    compile_format_config,
    compile_quick_spec,
    compile_verified_spec,
    fighter_role_names,
    is_judge_only,
    is_ranked_battle,
    resolve_battle_config,
    spec_hash,
    validate_spec,
)
import pytest


def test_quick_compile_from_transcript():
    spec = compile_quick_spec(
        [{"role": "user", "content": "Write a palindrome checker in Rust"}]
    )
    assert spec["mode"] == "quick"
    assert "Rust" in spec["brief"] or "palindrome" in spec["title"].lower()
    cfg = compile_format_config(spec, mode="quick", n_fighters=2, transcript=[])
    assert cfg["judge_only"] is True
    assert cfg["evaluation_mode"] == "quick"
    assert cfg["roles"] == ["fighter_1", "fighter_2", "judge"]
    assert cfg["test_code"] == ""
    assert is_judge_only(cfg)


def test_verified_spec_requires_real_tests():
    spec = {
        "title": "Add",
        "brief": "Implement add(a, b).",
        "required_artifacts": ["solution.py"],
        "test_code": (
            "from solution import add\n"
            "def main():\n"
            "    assert add(1, 2) == 3\n"
            "    print('TEST_PASS')\n"
            "if __name__ == '__main__':\n"
            "    main()\n"
        ),
        "starter_files": {"solution.py": "def add(a, b):\n    return 0\n"},
    }
    out = validate_spec(spec, "verified", dry_run=True)
    assert "TEST_PASS" in out["test_code"]
    cfg = compile_format_config(out, mode="verified", n_fighters=3)
    assert cfg["roles"][:3] == fighter_role_names(3)
    assert cfg["judge_only"] is False
    assert spec_hash(out) == cfg["spec_hash"]


def test_verified_rejects_unsafe_import_and_weak_tests():
    with pytest.raises(SpecValidationError):
        validate_spec(
            {
                "title": "x",
                "brief": "x",
                "test_code": "import os\nprint('TEST_PASS')\n",
            },
            "verified",
            dry_run=False,
        )
    with pytest.raises(SpecValidationError):
        validate_spec(
            {
                "title": "x",
                "brief": "x",
                "test_code": "print('TEST_PASS')\n",
            },
            "verified",
            dry_run=True,
        )


def test_rejects_path_escape_and_secret_files():
    with pytest.raises(SpecValidationError):
        validate_spec(
            {
                "title": "x",
                "brief": "x",
                "starter_files": {"../evil.py": "x"},
            },
            "quick",
            dry_run=False,
        )
    with pytest.raises(SpecValidationError):
        validate_spec(
            {
                "title": "x",
                "brief": "x",
                "starter_files": {".env": "SECRET=1"},
            },
            "quick",
            dry_run=False,
        )


def test_verified_architect_uses_llm_json():
    payload = {
        "title": "Add",
        "brief": "add two numbers",
        "deliverables": ["solution.py"],
        "constraints": ["python"],
        "required_artifacts": ["solution.py"],
        "judge_rubric": "correctness",
        "starter_files": {},
        "test_code": (
            "from solution import add\n"
            "def main():\n"
            "    assert add(2, 2) == 4\n"
            "    print('TEST_PASS')\n"
            "if __name__ == '__main__':\n"
            "    main()\n"
        ),
        "languages": ["python3"],
    }

    def llm(_messages):
        import json

        return json.dumps(payload)

    spec = compile_verified_spec(
        [{"role": "user", "content": "add two numbers"}], llm_complete=llm
    )
    assert spec["title"] == "Add"


def test_resolve_battle_config_fail_closed():
    with pytest.raises(FrozenConfigError):
        resolve_battle_config({"draft_id": "d1"}, {"custom": True})
    frozen = {"custom": True, "evaluation_mode": "quick", "name": "X"}
    cfg = resolve_battle_config(
        {"battle_config": frozen, "draft_id": "d1"}, {"custom": True}
    )
    assert cfg["name"] == "X"
    ranked = is_ranked_battle({"ranked": False, "draft_id": "d1"}, cfg)
    assert ranked is False
    assert is_ranked_battle({"user_id": "u"}, {"engine": "agent_tool_race"}) is True
