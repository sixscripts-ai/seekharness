import json
import pytest

from agent_arena.battles import stream_battle
from agent_arena.persistence import service


@pytest.mark.asyncio
async def test_stream_battle_cross_replica_and_filtering(monkeypatch):
    user_id = "user-test"
    battle_id = "battle-cross-replica-1"

    # Mock battle ownership and retrieval
    battle_state = {"id": battle_id, "user_id": user_id, "status": "running"}
    monkeypatch.setattr(service, "battle_get", lambda uid, bid: dict(battle_state))

    # Mock durable events
    durable_events = [
        {
            "type": "battle_status",
            "data": {"status": "running"},
            "event_id": "ev-1",
            "created_at": 100.0,
        },
        {
            "type": "internal_call",
            "data": {"ts": 101.0},
            "event_id": "rate_internal_1",
            "created_at": 101.0,
        },
    ]

    def mock_events_load(bid, since_created_at=None):
        if since_created_at is None:
            return list(durable_events)
        return [e for e in durable_events if e["created_at"] >= since_created_at]

    monkeypatch.setattr(service, "events_load", mock_events_load)

    # Mock local event bus
    bus_events = []
    import agent_arena.battles as battles_mod
    monkeypatch.setattr(battles_mod.event_bus, "subscribe", lambda bid: list(bus_events))

    # Disable sleep in test
    monkeypatch.setattr(battles_mod.time, "sleep", lambda s: None)

    # Obtain generator
    response = stream_battle(battle_id, user_id=user_id)
    gen = response.body_iterator

    # Step 1: Initial snapshot should yield ev-1, skipping rate_internal_1
    first_item = await anext(gen)
    assert first_item["event"] == "battle_status"
    assert json.loads(first_item["data"])["status"] == "running"

    # Step 2: Simulate another replica writing to DB and local bus receiving an event
    durable_events.append({
        "type": "round_start",
        "data": {"round": 1},
        "event_id": "ev-replica-b",
        "created_at": 105.0,
    })
    # Also add an internal_call from replica B
    durable_events.append({
        "type": "internal_call",
        "data": {"ts": 106.0},
        "event_id": "rate_internal_2",
        "created_at": 106.0,
    })
    # Local bus has an event and a duplicate of ev-replica-b
    bus_events.append({
        "type": "round_start",
        "data": {"round": 1},
        "event_id": "ev-replica-b",
        "created_at": 105.0,
    })
    bus_events.append({
        "type": "artifact",
        "data": {"content": "hello world"},
        "event_id": "ev-bus-local",
        "created_at": 107.0,
    })

    # Generator should yield ev-replica-b (only once!) and ev-bus-local, skipping internal_call
    item2 = await anext(gen)
    assert item2["event"] == "round_start"
    assert json.loads(item2["data"])["round"] == 1

    item3 = await anext(gen)
    assert item3["event"] == "artifact"
    assert json.loads(item3["data"])["content"] == "hello world"

    # Next iteration heartbeat
    item4 = await anext(gen)
    assert item4["event"] == "heartbeat"

    # Step 3: Transition battle to completed
    battle_state["status"] = "completed"

    # Advance generator: should yield done and then terminate (StopAsyncIteration)
    item5 = await anext(gen)
    assert item5["event"] == "done"
    assert json.loads(item5["data"])["status"] == "completed"
    assert json.loads(item5["data"])["authoritative"] is True

    with pytest.raises(StopAsyncIteration):
        await anext(gen)


@pytest.mark.asyncio
async def test_stream_battle_fallback_dedupe_without_event_id(monkeypatch):
    user_id = "user-test"
    battle_id = "battle-fallback-dedupe"

    battle_state = {"id": battle_id, "user_id": user_id, "status": "running"}
    monkeypatch.setattr(service, "battle_get", lambda uid, bid: dict(battle_state))

    # Event without event_id
    raw_event = {
        "type": "custom_notice",
        "data": {"info": "first"},
        "event_id": "",
        "created_at": 200.0,
    }

    monkeypatch.setattr(service, "events_load", lambda bid, since_created_at=None: [raw_event])

    import agent_arena.battles as battles_mod
    # Bus also has the exact same event without event_id
    monkeypatch.setattr(battles_mod.event_bus, "subscribe", lambda bid: [raw_event])
    monkeypatch.setattr(battles_mod.time, "sleep", lambda s: None)

    response = stream_battle(battle_id, user_id=user_id)
    gen = response.body_iterator

    # Initial snapshot yields it
    item1 = await anext(gen)
    assert item1["event"] == "custom_notice"

    # Next iteration in while loop: duplicate from bus or DB is skipped, only heartbeat yielded
    item2 = await anext(gen)
    assert item2["event"] == "heartbeat"
