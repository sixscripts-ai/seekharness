"""Production smoke for custom prompt battles (Quick + Verified).

Usage (from backend/):
  export ARENA_JWT="<jwt>"
  export ARENA_BUILD_SHA="<deployed sha>"
  .venv/bin/python scripts/prod_smoke_custom.py quick
  .venv/bin/python scripts/prod_smoke_custom.py verified
"""

from __future__ import annotations

import json
import os
import sys
import time

import httpx

DEFAULT_BACKEND = "https://sixscripts--agent-arena-backend-fastapi-app.modal.run"
BACKEND = (os.environ.get("ARENA_BACKEND") or DEFAULT_BACKEND).rstrip("/")
JWT = os.environ.get("ARENA_JWT") or ""
EXPECTED_SHA = os.environ.get("ARENA_BUILD_SHA") or ""
MODELS = [
    os.environ.get("ARENA_MODEL") or "host:openrouter-free",
    os.environ.get("ARENA_MODEL_B") or "host:or-nemotron-super",
]
DEADLINE_S = int(os.environ.get("ARENA_SMOKE_DEADLINE") or 900)

VERIFIED_SPEC = {
    "title": "Add two numbers",
    "brief": "Implement add(a, b) in solution.py so tests pass.",
    "deliverables": ["solution.py"],
    "constraints": ["Python only. No network."],
    "required_artifacts": ["solution.py"],
    "judge_rubric": "Correct add() implementation.",
    "test_code": (
        "from solution import add\n"
        "def main():\n"
        "    assert add(1, 2) == 3\n"
        "    assert add(0, 0) == 0\n"
        "    print('TEST_PASS')\n"
        "if __name__ == '__main__':\n"
        "    main()\n"
    ),
}


def headers() -> dict:
    return {"Authorization": f"Bearer {JWT}"}


def wait_stream(c: httpx.Client, bid: str) -> tuple[list[dict], dict]:
    events: list[dict] = []
    done = False
    attempt = 0
    start = time.time()
    while not done and attempt < 5 and time.time() - start < DEADLINE_S:
        try:
            with c.stream("GET", f"/battles/{bid}/stream", timeout=None) as r:
                event_type, data_lines = None, []
                for raw in r.iter_lines():
                    if raw.startswith("event:"):
                        event_type = raw.split(":", 1)[1].strip()
                    elif raw.startswith("data:"):
                        data_lines.append(raw.split(":", 1)[1].strip())
                    elif raw == "":
                        if event_type and data_lines:
                            try:
                                payload = json.loads("".join(data_lines))
                            except Exception:
                                payload = {}
                            events.append({"event": event_type, "data": payload})
                        event_type, data_lines = None, []
                    if any(e["event"] == "done" for e in events[-2:]):
                        done = True
                        break
        except Exception as exc:
            print("stream error:", type(exc).__name__, exc)
        if not done:
            attempt += 1
            time.sleep(2 * attempt)
    battle = c.get(f"/battles/{bid}").json()
    return events, battle


def main() -> int:
    mode = (sys.argv[1] if len(sys.argv) > 1 else "quick").strip().lower()
    if mode not in {"quick", "verified"}:
        print("usage: prod_smoke_custom.py [quick|verified]")
        return 2
    if not JWT:
        print("ERROR: ARENA_JWT not set")
        return 2
    with httpx.Client(base_url=BACKEND, headers=headers(), timeout=60) as c:
        health = c.get("/health").json()
        print("health:", json.dumps(health))
        if EXPECTED_SHA and health.get("build_sha") != EXPECTED_SHA:
            print("ERROR: build_sha mismatch", health.get("build_sha"), "!=", EXPECTED_SHA)
            return 2
        created = c.post("/battle-drafts", json={"mode": mode})
        if created.status_code != 201:
            print("create draft failed:", created.status_code, created.text[:400])
            return 2
        draft_id = created.json()["id"]
        print("draft:", draft_id, "mode:", mode)
        if mode == "quick":
            msg = c.post(
                f"/battle-drafts/{draft_id}/messages",
                json={"content": "Write solution.py that prints hello from the arena."},
            )
            if msg.status_code != 200:
                print("message failed:", msg.status_code, msg.text[:400])
                return 2
            draft = msg.json()
        else:
            patched = c.patch(f"/battle-drafts/{draft_id}/spec", json=VERIFIED_SPEC)
            if patched.status_code != 200:
                print("spec patch failed:", patched.status_code, patched.text[:400])
                return 2
            draft = patched.json()
        if draft.get("status") != "ready":
            print("draft not ready:", json.dumps(draft)[:500])
            return 2
        launch = c.post(
            f"/battle-drafts/{draft_id}/launch",
            json={
                "revision": draft["revision"],
                "model_ids": MODELS,
                "timeout_seconds": 600,
                "save": True,
            },
        )
        if launch.status_code != 201:
            print("launch failed:", launch.status_code, launch.text[:400])
            return 2
        bid = launch.json()["id"]
        print("battle:", bid, "spec_hash:", launch.json().get("spec_hash"))
        events, battle = wait_stream(c, bid)
        print("events:", len(events), "status:", battle.get("status"), "ranked:", battle.get("ranked"))
        cfg = battle.get("battle_config") or {}
        if isinstance(cfg, str):
            cfg = json.loads(cfg)
        print("evaluation_mode:", cfg.get("evaluation_mode"), "custom:", cfg.get("custom"))
        if battle.get("ranked") is not False:
            print("FAIL: custom battle should be unranked")
            return 1
        if battle.get("status") not in ("completed", "failed", "cancelled"):
            print("FAIL: battle did not reach a terminal status")
            return 1
        types = {e["event"] for e in events}
        if "battle_status" not in types and "done" not in types:
            print("FAIL: no status events")
            return 1
        print("PASS", mode, bid)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
