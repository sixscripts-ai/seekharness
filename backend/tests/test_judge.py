import json

import pytest

from agent_arena import judge


def test_parse_json_object_strips_fences():
    raw = '```json\n{"scores": {"a": 10}, "reasoning": "ok"}\n```'
    parsed = judge._parse_json_object(raw)
    assert parsed["scores"]["a"] == 10


def test_parse_json_object_extracts_embedded():
    raw = 'Here you go:\n{"scores": {"m1": 50.5}, "reasoning": "fine"}\nThanks'
    parsed = judge._parse_json_object(raw)
    assert parsed["scores"]["m1"] == 50.5


def test_clamp():
    assert judge._clamp(-5) == 0.0
    assert judge._clamp(150) == 100.0
    assert judge._clamp(42.3) == 42.3


def test_judge_battle_retry_and_redact(monkeypatch):
    calls = {"n": 0}

    def fake_chat(**kwargs):
        calls["n"] += 1
        if calls["n"] < 2:
            raise RuntimeError("transient")
        return json.dumps({
            "scores": {"m-a": 80, "m-b": 60},
            "reasoning": "A wins. key sk-abcdefghijklmnopqrstuvwxyz123456",
        })

    monkeypatch.setattr(judge.llm_client, "chat_completion", fake_chat)
    result = judge.judge_battle(
        model_ids=["m-a", "m-b"],
        artifacts=[],
        rubric="score fairly",
        call_spec=("https://example.invalid/v1", "bearer", "k", "model-x"),
    )
    assert result["scores"]["m-a"] == 80.0
    assert result["scores"]["m-b"] == 60.0
    assert "sk-" not in result["justifications"]["m-a"]
    assert "[REDACTED]" in result["justifications"]["m-a"]
    assert calls["n"] == 2


def test_judge_battle_fails_after_retries(monkeypatch):
    monkeypatch.setattr(
        judge.llm_client,
        "chat_completion",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("always")),
    )
    with pytest.raises(Exception):
        judge.judge_battle(
            model_ids=["m-a", "m-b"],
            artifacts=[],
            rubric="x",
            call_spec=("https://example.invalid/v1", "bearer", "k", "m"),
        )


def test_compact_artifacts_filters_and_truncates():
    artifacts = [
        {"phase": "p1", "model_id": "m1", "artifact": '{"files": {"a.py": "' + ("x" * 2000) + '"}}', "role": "builder"},
        {"phase": "p2", "model_id": "m2", "artifact": "Normal artifact", "role": "breaker"},
        {"phase": "p3", "model_id": "m1", "artifact": "Long text " * 200, "role": "builder"},
    ]
    compacted = judge._compact_artifacts(artifacts, max_art_len=100)
    assert len(compacted) == 2
    assert compacted[0]["artifact"] == "Normal artifact"
    assert compacted[1]["artifact"].endswith("... [truncated]")
    assert len(compacted[1]["artifact"]) == 100 + len("... [truncated]")


def test_parse_json_object_rejects_empty():
    with pytest.raises(ValueError, match="Empty response"):
        judge._parse_json_object("")
    with pytest.raises(ValueError, match="Empty response"):
        judge._parse_json_object("   ")

