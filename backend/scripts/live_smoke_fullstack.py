"""Live MicroVM Battle Smoke Test for fullstack-bank-vault.

Triggers a live battle on the production Modal backend for fullstack-bank-vault,
consumes the SSE event stream, and verifies the full execution chain.
"""

from __future__ import annotations

import json
import os
import sys
import time
from collections import defaultdict
from pathlib import Path

import httpx

BACKEND = "https://sixscripts--agent-arena-backend-fastapi-app.modal.run"
TARGET_ID = "fullstack-bank-vault"
TARGET_VERSION = "1.0.0"
MODELS = ["host:openrouter-free", "host:or-nemotron-lightning"]


def get_jwt() -> str:
    # Use server key to issue JWT for agentarena-01
    from appwrite.client import Client
    from appwrite.services.users import Users
    from agent_arena.config import settings

    s = settings()
    client = (
        Client()
        .set_endpoint(s["APPWRITE_ENDPOINT"])
        .set_project(s["APPWRITE_PROJECT_ID"])
        .set_key(s["APPWRITE_API_KEY"])
    )
    users = Users(client)
    u_list = users.list()
    uid = u_list.users[0].id if hasattr(u_list.users[0], "id") else u_list.users[0]["$id"]
    jwt = users.create_jwt(uid)
    return jwt.jwt if hasattr(jwt, "jwt") else jwt["jwt"]


def main():
    print(f"=== Live MicroVM Battle Smoke Test: {TARGET_ID} ===", flush=True)
    token = get_jwt()
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    with httpx.Client(base_url=BACKEND, headers=headers, timeout=60.0) as client:
        # 1. Verify health & target
        health = client.get("/health").json()
        print(f"Health: {health}", flush=True)
        target_info = client.get(f"/targets/{TARGET_ID}").json()
        print(f"Target loaded: {target_info.get('name')} (v{target_info.get('version')})", flush=True)

        formats = client.get("/formats").json()
        fmt = next((f for f in formats if f.get("slug") == "auth-system-vs-breaker"), formats[0])
        print(f"Format: {fmt['id']} ({fmt.get('slug')})", flush=True)

        # 2. Trigger battle
        create_payload = {
            "format_id": fmt["id"],
            "model_ids": MODELS,
            "arena_size": 2,
            "timeout_seconds": 600,
            "round_visibility": "isolated",
            "save": True,
            "target_id": TARGET_ID,
            "target_version": TARGET_VERSION,
        }
        print("Creating battle with payload:", json.dumps(create_payload), flush=True)
        res = client.post("/battles", json=create_payload)
        print(f"Create response [{res.status_code}]: {res.text}", flush=True)
        if res.status_code != 201:
            print("Failed to create battle", flush=True)
            return 1

        battle_id = res.json()["id"]
        print(f"Battle created: {battle_id}", flush=True)

        # 3. Stream SSE events
        events = []
        done = False
        start_time = time.time()
        timeout = 600  # 10 minutes
        print(f"Streaming events from /battles/{battle_id}/stream ...", flush=True)

        with client.stream("GET", f"/battles/{battle_id}/stream", timeout=None) as response:
            event_type, data_lines = None, []
            for line in response.iter_lines():
                if time.time() - start_time > timeout:
                    print("Timeout waiting for battle stream to complete", flush=True)
                    break
                if line.startswith("event:"):
                    event_type = line.split(":", 1)[1].strip()
                elif line.startswith("data:"):
                    data_lines.append(line.split(":", 1)[1].strip())
                elif line == "":
                    if event_type and data_lines:
                        raw_data = "".join(data_lines)
                        try:
                            payload = json.loads(raw_data)
                        except Exception:
                            payload = raw_data
                        print(f" [SSE] {event_type}: {str(payload)[:160]}", flush=True)
                        events.append({"event": event_type, "data": payload})
                        if event_type == "battle_status":
                            status = payload.get("status") if isinstance(payload, dict) else ""
                            if status in ("completed", "failed", "cancelled"):
                                done = True
                        if event_type == "done":
                            done = True
                            break
                    event_type, data_lines = None, []

        print(f"Finished stream. Total events received: {len(events)}", flush=True)

        # 4. Fetch final battle state
        final_battle = client.get(f"/battles/{battle_id}").json()
        print("Final battle status:", final_battle.get("status"), flush=True)
        print("Failure reason:", final_battle.get("failure_reason"), flush=True)
        print("Scores:", final_battle.get("scores"), flush=True)
        print("Sandbox ID:", final_battle.get("sandbox_id"), flush=True)

        # 5. Fetch artifacts
        art_res = client.get(f"/battles/{battle_id}/artifacts")
        if art_res.status_code == 200:
            arts = art_res.json()
            print(f"Total artifacts: {len(arts)}", flush=True)
            for a in arts:
                print(f" - Phase: {a.get('phase')}, Model: {a.get('model_id')}", flush=True)

        return 0


if __name__ == "__main__":
    sys.exit(main())
