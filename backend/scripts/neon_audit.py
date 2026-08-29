#!/usr/bin/env python3
"""Operator audit of the Neon battle database (source of truth).

Dumps a terminal-friendly report: status funnel, target coverage, mock vs real
artifact quality, queue age, failure reasons, score/elo signal, and the
Appwrite-vs-Neon split-brain indicator. Read-only; never mutates data.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from collections import Counter

from sqlalchemy import text


def _engine():
    try:
        from agent_arena.persistence.engine import engine
        return engine()
    except Exception as exc:
        sys.stderr.write(f"engine init failed: {exc}\n")
        return None


def fmt_dt(v):
    if v is None:
        return "?"
    if v.tzinfo is None:
        v = v.replace(tzinfo=timezone.utc)
    return v.strftime("%Y-%m-%d %H:%M")


def is_mock_artifact(s):
    if not s:
        return None
    return "[mock:" in s


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true", help="emit JSON to stdout")
    ap.add_argument("--limit", type=int, default=100000)
    args = ap.parse_args()

    eng = _engine()
    if eng is None:
        return 2
    with eng.connect() as conn:
        total = conn.execute(text("SELECT count(*) FROM battles")).scalar()
        by_status = dict(conn.execute(text("SELECT status, count(*) FROM battles GROUP BY status")).fetchall())
        by_target = dict(conn.execute(text("SELECT coalesce(target_id,'<none>') t, count(*) FROM battles GROUP BY t ORDER BY 2 DESC")).fetchall())
        completed = conn.execute(text("SELECT count(*) FROM battles WHERE status='completed'")).scalar()
        failed_total = by_status.get("failed", 0)
        queued_total = by_status.get("queued", 0)
        running_total = by_status.get("running", 0)

        # queue age (oldest queued)
        oldest = conn.execute(text("SELECT min(created_at) FROM battles WHERE status='queued'")).scalar()
        now = datetime.now(timezone.utc)
        q_age_h = None
        if oldest:
            if oldest.tzinfo is None:
                oldest = oldest.replace(tzinfo=timezone.utc)
            q_age_h = round((now - oldest).total_seconds() / 3600, 1)

        # failing: how many battles have zero rounds
        zero_rounds = conn.execute(text(
            "SELECT count(*) FROM battles b LEFT JOIN rounds r ON r.battle_id=b.id "
            "WHERE b.status='failed' AND r.id IS NULL"
        )).scalar()

        # artifact quality on completed rounds
        round_tot = conn.execute(text("SELECT count(*) FROM rounds")).scalar()
        mock_rounds = 0
        real_rounds = 0
        blob_len = conn.execute(text("SELECT count(*) FROM rounds WHERE length(artifact)>200")).scalar()
        rows = conn.execute(text(
            "SELECT r.artifact, b.status FROM rounds r JOIN battles b ON b.id=r.battle_id "
            "ORDER BY r.created_at DESC LIMIT :lim"
        ), {"lim": args.limit}).fetchall()
        for art, _ in rows:
            if is_mock_artifact(art):
                mock_rounds += 1
            elif art:
                real_rounds += 1

        # scores
        score_tot = conn.execute(text("SELECT count(*) FROM scores")).scalar()
        mock_score_tot = conn.execute(text("SELECT count(*) FROM scores WHERE judge_model='mock'")).scalar()
        # battles w/ completed but no scores
        no_scores = conn.execute(text(
            "SELECT count(*) FROM battles b WHERE b.status='completed' "
            "AND NOT EXISTS (SELECT 1 FROM scores s WHERE s.battle_id=b.id)"
        )).scalar()

        # memory / enrichment
        mem_tot = conn.execute(text("SELECT count(*) FROM memories")).scalar()
        drafts = conn.execute(text("SELECT count(*) FROM battle_drafts")).scalar()

        # leaderboard signal
        lb_top = conn.execute(text(
            "SELECT model_id, scope, elo, games_played FROM leaderboard "
            "ORDER BY games_played DESC, elo DESC LIMIT 10"
        )).fetchall()

        # participation across targets / formats
        parts = conn.execute(text(
            "SELECT count(DISTINCT model_id) FROM battle_participants"
        )).scalar()

        # split brain: PERSISTENCE_BACKEND in env
        pb = os.environ.get("PERSISTENCE_BACKEND") or "unset (defaults to appwrite)"
        db_url = os.environ.get("DATABASE_URL") or "unset"

        report = {
            "battles_total": int(total or 0),
            "by_status": {k: int(v) for k, v in by_status.items()},
            "by_target": {k: int(v) for k, v in by_target.items()},
            "completed": int(completed or 0),
            "failed_total": int(failed_total or 0),
            "failed_with_zero_rounds": int(zero_rounds or 0),
            "queued_total": int(queued_total or 0),
            "queued_oldest_age_hours": q_age_h,
            "running_total": int(running_total or 0),
            "rounds_total": int(round_tot or 0),
            "rounds_mock": int(mock_rounds),
            "rounds_real": int(real_rounds),
            "rounds_long_artifact_gt200": int(blob_len or 0),
            "scores_total": int(score_tot or 0),
            "scores_mock_judge": int(mock_score_tot or 0),
            "completed_without_scores": int(no_scores or 0),
            "memories_total": int(mem_tot or 0),
            "battle_drafts_total": int(drafts or 0),
            "distinct_participant_models": int(parts or 0),
            "leaderboard_top": [dict(r._mapping) for r in lb_top],
            "deployment": {
                "persistence_backend_env": pb,
                "database_url_set": bool(db_url and "unset" not in db_url.lower()),
            },
        }

    if args.json:
        print(json.dumps(report, indent=2, default=str))
        return 0

    print("=== NEON BATTLE AUDIT ===")
    print(f"battles total       : {report['battles_total']}")
    print(f"status              : " + ", ".join(f"{k}={v}" for k, v in sorted(report['by_status'].items())))
    print(f"completed           : {report['completed']}  failed={report['failed_total']} (zero-rounds={report['failed_with_zero_rounds']})")
    print(f"queued              : {report['queued_total']}  oldest_age_h={report['queued_oldest_age_hours']}")
    print(f"running (zombies?)  : {report['running_total']}")
    print(f"target coverage     : " + ", ".join(f"{k}={v}" for k, v in report['by_target'].items()))
    print(f"distinct models     : {report['distinct_participant_models']}")
    print(f"rounds              : {report['rounds_total']}  mock={report['rounds_mock']} real={report['rounds_real']} >200ch={report['rounds_long_artifact_gt200']}")
    print(f"scores              : {report['scores_total']}  mock_judge={report['scores_mock_judge']} completed_without={report['completed_without_scores']}")
    print(f"memories            : {report['memories_total']}")
    print(f"battle_drafts       : {report['battle_drafts_total']}")
    print(f"deployment checkbox : persistence_backend={report['deployment']['persistence_backend_env']} db_url_set={report['deployment']['database_url_set']}")
    print("leaderboard (top by games):")
    for row in report['leaderboard_top']:
        print(f"  {str(row['model_id'])[:30]:30} {str(row['scope'])[:20]:20} elo={row['elo']:.1f} games={row['games_played']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
