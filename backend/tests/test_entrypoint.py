import json

from agent_arena.sandbox import entrypoint


def test_entrypoint_empty_scores_finalizes_failed(monkeypatch):
    calls = []

    class FakeTransport:
        def __init__(self, *a, **k):
            pass

    class FakeClient:
        def __init__(self, transport):
            pass

        def status(self, battle_id):
            return "running"

        def round(self, *a, **k):
            pass

        def finalize(self, battle_id, status, scores=None):
            calls.append((battle_id, status, scores or {}))
            return {}

    monkeypatch.setenv("BACKEND_PUBLIC_URL", "https://example.invalid")
    monkeypatch.setenv("BATTLE_TOKEN", "tok")
    monkeypatch.setenv(
        "BATTLE_BOOTSTRAP_JSON",
        json.dumps(
            {
                "format_config": {
                    "engine": "scripted",
                    "roles": ["a", "b", "judge"],
                    "phases": [],
                },
                "model_ids": ["m1", "m2"],
                "timeout_seconds": 10,
            }
        ),
    )
    monkeypatch.setattr("agent_arena.sandbox.client.HttpTransport", FakeTransport)
    monkeypatch.setattr("agent_arena.sandbox.client.InternalClient", FakeClient)
    monkeypatch.setattr("agent_arena.sandbox.runner.run_battle_loop", lambda **k: {})
    entrypoint.main("b-empty")
    assert calls
    assert calls[0][0] == "b-empty"
    assert calls[0][1] == "failed"
    assert calls[0][2] == {}


def test_entrypoint_on_status_is_sandbox_hint(monkeypatch):
    rounds = []

    class FakeTransport:
        def __init__(self, *a, **k):
            pass

    class FakeClient:
        def __init__(self, transport):
            pass

        def status(self, battle_id):
            return "running"

        def round(self, *a, **k):
            rounds.append((a, k))

        def finalize(self, battle_id, status, scores=None):
            return {}

    def run_loop(**kwargs):
        kwargs["on_status"]("failed")
        return {}

    monkeypatch.setenv("BACKEND_PUBLIC_URL", "https://example.invalid")
    monkeypatch.setenv("BATTLE_TOKEN", "tok")
    monkeypatch.setenv(
        "BATTLE_BOOTSTRAP_JSON",
        json.dumps(
            {
                "format_config": {
                    "engine": "scripted",
                    "roles": ["a", "b", "judge"],
                    "phases": [],
                },
                "model_ids": ["m1", "m2"],
                "timeout_seconds": 10,
            }
        ),
    )
    monkeypatch.setattr("agent_arena.sandbox.client.HttpTransport", FakeTransport)
    monkeypatch.setattr("agent_arena.sandbox.client.InternalClient", FakeClient)
    monkeypatch.setattr("agent_arena.sandbox.runner.run_battle_loop", run_loop)
    entrypoint.main("b-hint")
    assert rounds
    args, kwargs = rounds[0]
    artifact = kwargs.get("artifact") or (args[3] if len(args) > 3 else "")
    payload = json.loads(artifact)
    assert payload["status"] == "failed"
    assert payload["authoritative"] is False
    assert kwargs.get("event_type") == "battle_status" or (
        len(args) > 4 and args[4] == "battle_status"
    )

def test_entrypoint_scores_finalizes_completed(monkeypatch):
    calls = []

    class FakeTransport:
        def __init__(self, *a, **k):
            pass

    class FakeClient:
        def __init__(self, transport):
            pass

        def status(self, battle_id):
            return "running"

        def round(self, *a, **k):
            pass

        def finalize(self, battle_id, status, scores=None):
            calls.append((status, scores or {}))
            return {}

    monkeypatch.setenv("BACKEND_PUBLIC_URL", "https://example.invalid")
    monkeypatch.setenv("BATTLE_TOKEN", "tok")
    monkeypatch.setenv(
        "BATTLE_BOOTSTRAP_JSON",
        json.dumps(
            {
                "format_config": {"engine": "scripted", "roles": ["a", "b", "judge"]},
                "model_ids": ["m1", "m2"],
            }
        ),
    )
    monkeypatch.setattr("agent_arena.sandbox.client.HttpTransport", FakeTransport)
    monkeypatch.setattr("agent_arena.sandbox.client.InternalClient", FakeClient)
    monkeypatch.setattr(
        "agent_arena.sandbox.runner.run_battle_loop",
        lambda **k: {"m1": 90.0, "m2": 10.0},
    )
    entrypoint.main("b-ok")
    assert calls[0][0] == "completed"
    assert calls[0][1] == {"m1": 90.0, "m2": 10.0}


def test_battle_create_difficulty():
    from pydantic import ValidationError

    from agent_arena.schemas import BattleCreate

    ok = BattleCreate(format_id="f", model_ids=["a", "b"], difficulty="expert")
    assert ok.difficulty == "expert"
    blank = BattleCreate(format_id="f", model_ids=["a", "b"])
    assert blank.difficulty is None
    try:
        BattleCreate(format_id="f", model_ids=["a", "b"], difficulty="insane")
        assert False, "invalid difficulty should fail"
    except ValidationError:
        pass
