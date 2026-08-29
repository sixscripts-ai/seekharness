#!/usr/bin/env python3
"""extract_battle_telemetry.py - Extract and summarize battle telemetry from Neon PostgreSQL.

Usage:
    python extract_battle_telemetry.py <battle_id> [--json] [--database-url <url>]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from typing import Any

try:
    import psycopg
except ImportError:
    print("Error: psycopg is required. Install via `pip install psycopg[binary]`", file=sys.stderr)
    sys.exit(1)


def get_connection_url(override_url: str | None = None) -> str:
    if override_url:
        return override_url
    url = os.environ.get("DATABASE_URL")
    if not url:
        # Fallback to local .env or .env.local
        from pathlib import Path
        for cand in [Path(".env.local"), Path("../.env.local"), Path(".env")]:
            if cand.is_file():
                for line in cand.read_text().splitlines():
                    if line.strip().startswith("DATABASE_URL="):
                        val = line.split("=", 1)[1].strip().strip("'\"")
                        if val:
                            return val
    if not url:
        raise RuntimeError("DATABASE_URL is not set and could not be discovered.")
    return url


def extract_telemetry(battle_id: str, db_url: str) -> dict[str, Any]:
    clean_url = db_url.replace("-pooler.", ".")
    with psycopg.connect(clean_url) as conn:
        with conn.cursor() as cur:
            # 1. Fetch Battle Record
            cur.execute(
                """
                SELECT id, user_id, format_id, arena_size, status, started_at, completed_at,
                       failure_reason, difficulty, target_id, target_version, target_manifest_hash
                FROM battles WHERE id = %s
                """,
                (battle_id,),
            )
            row = cur.fetchone()
            if not row:
                raise LookupError(f"Battle {battle_id} not found in database.")

            battle = {
                "id": row[0],
                "user_id": row[1],
                "format_id": row[2],
                "arena_size": row[3],
                "status": row[4],
                "started_at": row[5].isoformat() if row[5] else None,
                "completed_at": row[6].isoformat() if row[6] else None,
                "failure_reason": row[7],
                "difficulty": row[8],
                "target_id": row[9],
                "target_version": row[10],
                "target_manifest_hash": row[11],
            }

            # 2. Fetch Participants
            cur.execute(
                """
                SELECT position, model_id, role
                FROM battle_participants WHERE battle_id = %s
                ORDER BY position
                """,
                (battle_id,),
            )
            participants = [
                {"position": r[0], "model_id": r[1], "role": r[2]}
                for r in cur.fetchall()
            ]

            # 3. Fetch Scores
            cur.execute(
                """
                SELECT model_id, score, judge_model, justification
                FROM scores WHERE battle_id = %s
                """,
                (battle_id,),
            )
            scores = [
                {
                    "model_id": r[0],
                    "score": float(r[1]),
                    "judge_model": r[2],
                    "justification": r[3],
                }
                for r in cur.fetchall()
            ]

            # 4. Fetch Battle Events
            cur.execute(
                """
                SELECT id, event_type, payload, created_at
                FROM battle_events WHERE battle_id = %s
                ORDER BY created_at ASC
                """,
                (battle_id,),
            )
            events_raw = cur.fetchall()
            events = []
            skills_loaded: set[str] = set()
            tool_calls_count = 0
            verifier_outputs = []

            for eid, ev_type, payload, cat in events_raw:
                p = payload if isinstance(payload, dict) else {}
                data = p.get("data", {}) if isinstance(p.get("data"), dict) else {}
                artifact = p.get("artifact") or data.get("artifact") or ""
                
                # Detect chosen skills
                if "SKILLS_CHOSEN" in str(artifact):
                    skills_part = str(artifact).split("SKILLS_CHOSEN", 1)[1].strip()
                    for s in skills_part.replace(",", " ").split():
                        if s:
                            skills_loaded.add(s)

                # Detect action logs
                if ev_type == "action_log":
                    tool_calls_count += 1
                    if "TEST_PASS" in str(artifact) or "TEST_FAIL" in str(artifact):
                        verifier_outputs.append(str(artifact))

                events.append({
                    "id": eid,
                    "event_type": ev_type,
                    "model_id": p.get("model_id"),
                    "phase": p.get("phase"),
                    "sequence": p.get("sequence"),
                    "payload": p,
                    "created_at": cat.isoformat() if cat else None,
                })

            return {
                "battle": battle,
                "participants": participants,
                "scores": scores,
                "skills_loaded": sorted(list(skills_loaded)),
                "total_events": len(events),
                "total_tool_calls": tool_calls_count,
                "verifier_outputs": verifier_outputs,
                "events": events,
            }


def main():
    parser = argparse.ArgumentParser(description="Extract Agent Arena Battle Telemetry.")
    parser.add_argument("battle_id", help="UUID of the battle")
    parser.add_argument("--json", action="store_true", help="Output raw JSON")
    parser.add_argument("--database-url", default=None, help="PostgreSQL connection string")
    args = parser.parse_args()

    try:
        url = get_connection_url(args.database_url)
        telemetry = extract_telemetry(args.battle_id, url)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    if args.json:
        print(json.dumps(telemetry, indent=2))
        return

    b = telemetry["battle"]
    print(f"==================================================")
    print(f"🎯 BATTLE TELEMETRY SUMMARY: {b['id']}")
    print(f"==================================================")
    print(f"Status:       {b['status'].upper()}")
    print(f"Format:       {b['format_id']}")
    print(f"Target:       {b['target_id'] or 'None (Standard Arena Duel)'}")
    if b['target_manifest_hash']:
        print(f"Manifest:     {b['target_manifest_hash'][:16]}...")
    print(f"Duration:     {b['started_at']} -> {b['completed_at']}")
    print(f"Total Events: {telemetry['total_events']} ({telemetry['total_tool_calls']} tool calls)")
    print(f"Skills:       {', '.join(telemetry['skills_loaded']) if telemetry['skills_loaded'] else 'None'}")
    print(f"Participants:")
    for p in telemetry["participants"]:
        print(f"  - [{p['role']}] {p['model_id']}")
    print(f"Scores:")
    for s in telemetry["scores"]:
        print(f"  - {s['model_id']}: {s['score']} ({s['judge_model']})")
    if telemetry["verifier_outputs"]:
        print(f"Verifier Output:")
        for vo in telemetry["verifier_outputs"]:
            print(f"  > {vo[:150]}")
    print(f"==================================================")


if __name__ == "__main__":
    main()
