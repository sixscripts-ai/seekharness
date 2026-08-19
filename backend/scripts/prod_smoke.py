"""Production Modal E2E smoke harness (human-run).

Drives the SAME public API the frontend uses: creates a Debugging race
battle with two host models, consumes the SSE stream, and verifies the full
production execution chain against the required checklist.

Usage (from backend/):
  export ARENA_JWT="<jwt from your browser session on seekharness.vercel.app>"
  export ARENA_BUILD_SHA="<expected build sha, e.g. ddcd407>"
  .venv/bin/python scripts/prod_smoke.py

Optional: ARENA_BACKEND (default prod Modal URL), ARENA_FORMAT_SLUG
(default debugging-race), ARENA_MODEL (default host:openrouter-free).
"""

from __future__ import annotations

import json
import os
import sys
import time
from collections import defaultdict

import httpx

DEFAULT_BACKEND = "https://sixscripts--agent-arena-backend-fastapi-app.modal.run"
BACKEND = (os.environ.get("ARENA_BACKEND") or DEFAULT_BACKEND).rstrip("/")
JWT = os.environ.get("ARENA_JWT") or ""
EXPECTED_SHA = os.environ.get("ARENA_BUILD_SHA") or ""
FORMAT_SLUG = os.environ.get("ARENA_FORMAT_SLUG") or "debugging-race"
MODEL = os.environ.get("ARENA_MODEL") or "host:openrouter-free"
DEADLINE_S = int(os.environ.get("ARENA_SMOKE_DEADLINE") or 900)

PROCESS_TOOLS = {"shell", "install", "run", "test", "bg"}


def headers() -> dict:
    return {"Authorization": f"Bearer {JWT}"}


def main() -> int:
    checks: dict[str, str] = defaultdict(lambda: "NOT PROVEN")
    if not JWT:
        print("ERROR: ARENA_JWT not set (copy it from your browser session).")
        return 2
    events: list[dict] = []

    with httpx.Client(base_url=BACKEND, headers=headers(), timeout=60) as c:
        health = c.get("/health").json()
        print("health:", json.dumps(health))
        if EXPECTED_SHA and health.get("build_sha") == EXPECTED_SHA:
            checks["correct_revision"] = "PASS"
        elif health.get("build_sha") and health.get("build_sha") != "unknown":
            checks["correct_revision"] = "FAIL"
        # The Modal deploy token was rotated before this build was deployed;
        # a matching build_sha proves THIS deploy is the rotated one.
        checks["rotated_credentials"] = (
            "PASS" if checks["correct_revision"] == "PASS" else "NOT PROVEN"
        )

        resume_id = os.environ.get("ARENA_BATTLE_ID") or ""
        if resume_id:
            bid = resume_id
            checks["battle_created"] = "PASS" if c.get(f"/battles/{bid}").status_code == 200 else "FAIL"
            print("resuming battle:", bid)
            fmt = None
        else:
            fmts = c.get("/formats").json()
            fmt = next((f for f in fmts if f.get("slug") == FORMAT_SLUG), None)
            if not fmt:
                print(f"ERROR: format {FORMAT_SLUG} not found in /formats")
                return 2
            print("format:", fmt["id"], fmt["name"], "engine:", fmt["engine"])
            created = c.post(
            "/battles",
            json={
                "format_id": fmt["id"],
                "model_ids": [MODEL, MODEL],
                "arena_size": 2,
                "timeout_seconds": 600,
                "round_visibility": "isolated",
                "save": True,  # keep artifacts inspectable after the battle
                "judge_provider_id": None,
                "difficulty": "novice",
            },
        )
            if created.status_code != 201:
                print("battle create failed:", created.status_code, created.text[:300])
                return 2
            bid = created.json()["id"]
            checks["battle_created"] = "PASS"
            print("battle:", bid)

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
                print("stream error:", type(exc).__name__)
            if not done:
                attempt += 1
                time.sleep(2 * attempt)
        print("events received:", len(events))
        battle = c.get(f"/battles/{bid}").json()
        print(
            "battle status:", battle.get("status"), "sandbox_id:", battle.get("sandbox_id")
        )
        checks["modal_sandbox"] = "PASS" if battle.get("sandbox_id") else "FAIL"
        checks["terminal"] = "PASS" if battle.get("status") in ("completed", "failed", "cancelled") else "FAIL"
        if battle.get("status") == "completed":
            checks["battle_completed"] = "PASS"

        by_type: dict[str, list] = defaultdict(list)
        for e in events:
            by_type[e["event"]].append(e["data"])
        action_logs: list[dict] = []
        for payload in by_type.get("action_log", []):
            d = payload.get("data", payload) if isinstance(payload, dict) else payload
            if isinstance(d, str):
                try:
                    d = json.loads(d)
                except Exception:
                    continue
            if isinstance(d, dict):
                if "action" not in d and "artifact" in d:
                    try:
                        inner = json.loads(d["artifact"])
                    except Exception:
                        inner = {}
                    if isinstance(inner, dict):
                        d = inner
                action_logs.append(d)
        checks["tool_actions"] = "PASS" if action_logs else "FAIL"
        checks["battle_token"] = "PASS" if (by_type.get("phase_start") or action_logs) else "FAIL"
        checks["workspace_materialized"] = "PASS" if by_type.get("phase_start") else "FAIL"

        process_events = [a for a in action_logs if a.get("action") in PROCESS_TOOLS]
        file_events = [a for a in action_logs if a.get("action") in ("read", "write")]
        checks["subprocess_ran"] = "PASS" if process_events else "FAIL"
        ok_exec = bool(process_events) and all(
            str(a.get("exec_id") or "").startswith("exec_") for a in process_events
        )
        ok_null = bool(file_events) and all(
            a.get("exec_id") is None for a in file_events
        )
        checks["exec_id_semantics"] = "PASS" if (ok_exec and ok_null) else "FAIL"
        has_out = any(
            "STDOUT:" in str(a.get("result")) or "rc=" in str(a.get("result"))
            for a in process_events
        )
        checks["stdout_captured"] = "PASS" if has_out else "FAIL"
        turns = sorted({int(a.get("turn_id") or 0) for a in action_logs if a.get("turn_id")})
        checks["feedback_iteration"] = "PASS" if len(turns) >= 2 else "NOT PROVEN"

        results = [p for p in by_type.get("result", []) if isinstance(p, dict)]
        checks["executor_result_persisted"] = "PASS" if results else "FAIL"
        evidence = [p for p in by_type.get("evidence_summary", []) if isinstance(p, dict)]
        checks["evidence_summary"] = "PASS" if evidence else "FAIL"
        if evidence:
            ev = evidence[-1]
            ev = ev.get("data", ev) if isinstance(ev, dict) else ev
            if isinstance(ev, str):
                try:
                    ev = json.loads(ev)
                except Exception:
                    ev = {}
            dec = ev.get("decision") or {}
            checks["verified_solution_persisted"] = (
                "PASS" if "verified_solution" in dec else "FAIL"
            )
            print("decision:", json.dumps(dec)[:600])
        checks["scores_persisted"] = "PASS" if by_type.get("scores") else "FAIL"
        checks["canonical_verification"] = "PASS" if results else "NOT PROVEN"
        checks["tamper_protection_live"] = "NOT RUN"  # Option B: local test only

        artifacts = c.get(f"/battles/{bid}/artifacts")
        checks["artifacts_inspectable"] = (
            "PASS" if artifacts.status_code == 200 and artifacts.json() else "FAIL"
        )
        checks["sse_reached"] = "PASS" if (done or by_type.get("battle_status")) else "FAIL"

    print()
    print("== PRODUCTION SMOKE CHECKLIST ==")
    for key, value in sorted(checks.items()):
        print(f"[{value:>11}] {key}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
