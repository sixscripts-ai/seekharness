"""Standalone read-only verifier for the Appwrite -> PostgreSQL backfill.

Compares Appwrite source counts against PostgreSQL destination counts and
performs lightweight integrity checks WITHOUT importing the FastAPI framework
or the persistence repositories. Only sqlalchemy core + appwrite SDK + the
models metadata are used.

Usage (from backend/):
  ./.venv/bin/python scripts/verify_backfill.py
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_BACKEND = _HERE.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

# Collections in migration order, with the destination table name (identical).
COLLECTIONS = [
    "formats", "providers", "battles", "battle_drafts", "battle_events",
    "rounds", "scores", "leaderboard", "skills", "memories",
]

TABLE_MAP = {
    "formats": "Format",
    "providers": "Provider",
    "battles": "Battle",
    "battle_participants": "BattleParticipant",
    "battle_drafts": "BattleDraft",
    "battle_events": "BattleEvent",
    "rounds": "Round",
    "scores": "Score",
    "leaderboard": "LeaderboardEntry",
    "skills": "SkillRecord",
    "memories": "Memory",
}

TABLES = list(COLLECTIONS) + ["battle_participants"]


def _doc_id(doc):
    if isinstance(doc, dict):
        return doc.get("id") or doc.get("$id")
    return getattr(doc, "id", None)


def _doc_data(doc):
    if isinstance(doc, dict):
        return dict(doc.get("data", doc))
    return dict(getattr(doc, "data", {}) or {})


def read_appwrite_counts():
    """Return (counts, failed) reading every collection read-only."""
    from appwrite.query import Query
    from agent_arena import db

    databases = db.get_databases()
    database_id = db.get_database_id()
    counts = {}
    failed = {}
    for coll in COLLECTIONS:
        try:
            res = databases.list_documents(database_id, coll, queries=[Query.limit(1000)])
            counts[coll] = len(res.documents)
        except Exception as exc:
            failed[coll] = exc
            counts[coll] = None
    return counts, failed


def read_destination_counts():
    from sqlalchemy import select, func
    from agent_arena.persistence.engine import engine
    from agent_arena.persistence import models as M

    out = {}
    eng = engine()
    with eng.connect() as c:
        for tbl in TABLES:
            model = getattr(M, TABLE_MAP.get(tbl, tbl.replace("_", "")))
            n = c.execute(select(func.count()).select_from(model)).scalar()
            out[tbl] = n
    return out


def collect_source_anomalies():
    """Lightweight integrity checks over Appwrite source only."""
    from appwrite.query import Query
    from agent_arena import db

    databases = db.get_databases()
    database_id = db.get_database_id()

    def all_docs(coll):
        try:
            res = databases.list_documents(database_id, coll, queries=[Query.limit(1000)])
            return res.documents
        except Exception:
            return []

    battles = [_doc_data(d) for d in all_docs("battles")]
    battle_ids = {_doc_id(d) for d in all_docs("battles")}

    report = {}

    # participants sum vs battles
    model_ids_unparseable = 0
    participant_expected = 0
    for b in battles:
        raw = b.get("model_ids")
        try:
            if isinstance(raw, list):
                ids = [str(x) for x in raw]
            elif isinstance(raw, str) and raw.strip():
                ids = json.loads(raw)
                if not isinstance(ids, list):
                    ids = [p.strip() for p in raw.split(",") if p.strip()]
            else:
                ids = []
            participant_expected += len(ids)
        except Exception:
            model_ids_unparseable += 1
    report["participant_expected"] = participant_expected
    report["model_ids_unparseable"] = model_ids_unparseable

    # orphans
    orphans = {}
    for coll, fk in (("battle_events", "battle_id"), ("rounds", "battle_id"), ("scores", "battle_id")):
        n = 0
        for d in all_docs(coll):
            if _doc_data(d).get(fk) not in battle_ids:
                n += 1
        orphans[coll] = n
    report["orphans"] = orphans

    # scores duplicates
    sc = Counter()
    for d in all_docs("scores"):
        dd = _doc_data(d)
        sc[(dd.get("battle_id"), dd.get("model_id"))] += 1
    report["scores_dup"] = {k: v for k, v in sc.items() if v > 1}

    # leaderboard duplicates
    lb = Counter()
    for d in all_docs("leaderboard"):
        dd = _doc_data(d)
        lb[(dd.get("model_id"), dd.get("format_id"))] += 1
    report["leaderboard_dup"] = {k: v for k, v in lb.items() if v > 1}

    return report


def main() -> int:
    print("==== VERIFY BACKFILL (framework-free, read-only) ====")
    src_counts, failed = read_appwrite_counts()
    dst_counts = read_destination_counts()

    print("\n[SOURCE vs DESTINATION COUNTS]")
    for coll in COLLECTIONS:
        src = src_counts.get(coll)
        src_txt = "FAILED" if src is None else str(src)
        print(f"  {coll:<20} source={src_txt:<8} dest={dst_counts.get(coll, '?')}")
    print(f"  {'battle_participants':<20} source=n/a     dest={dst_counts.get('battle_participants', '?')} (derived)")

    print("\n[PARTICIPANTS SUM vs BATTLES]")
    print(f"  battle_participants={dst_counts.get('battle_participants', '?')}  battles={dst_counts.get('battles', '?')}")

    anomalies = collect_source_anomalies()
    print("\n[SOURCE PARTICIPANTS (expected from model_ids incl. unparseable-skipped)]")
    print(f"  expected participants={anomalies['participant_expected']}  battles with unparseable model_ids={anomalies['model_ids_unparseable']}")

    print("\n[ORPHAN ROWS (source) vs destination]")
    for coll, n in anomalies["orphans"].items():
        print(f"  {coll}: source orphans={n}  dest rows={dst_counts.get(coll, '?')}")

    print("\n[DUPLICATE IDENTITIES (source, kept-first)]")
    if anomalies["scores_dup"]:
        print(f"  scores dupes: {anomalies['scores_dup']}")
    else:
        print("  scores dupes: (none)")
    if anomalies["leaderboard_dup"]:
        print(f"  leaderboard dupes: {anomalies['leaderboard_dup']}")
    else:
        print("  leaderboard dupes: (none)")

    print("\n[COLLECTIONS FAILED]")
    if failed:
        for coll, exc in failed.items():
            code = getattr(exc, "code", None)
            kind = f" (HTTP {code})" if code else ""
            print(f"  {coll}: {type(exc).__name__}{kind}")
    else:
        print("  (none)")

    print("\n==== END VERIFY ====")
    return 0


if __name__ == "__main__":
    sys.exit(main())
