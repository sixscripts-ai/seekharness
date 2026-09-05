#!/usr/bin/env python3
"""reconcile_scores.py - Repair proven diagnostic 0.0 score wipeouts.

Writes scores only when every existing score row is a zero untrusted/diagnostic
wipeout and an Arena-authored arena-score-v1 event covers the same
participants. Commits an Elo-pending marker in the same transaction. Does not
apply Elo.

Usage:
    python reconcile_scores.py <battle_id> [--dry-run] [--database-url <url>]
    python reconcile_scores.py --all [--dry-run] [--database-url <url>]
    python reconcile_scores.py <battle_id> --acknowledge-elo [--database-url <url>]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

try:
    import psycopg
except ImportError:
    print("Error: psycopg is required. Install via `pip install psycopg[binary]`", file=sys.stderr)
    sys.exit(1)

PENDING_STATUS = "scores_repaired_elo_pending"
ACK_STATUS = "elo_acknowledged"
REPAIR_PREFIX = "Authoritative-reconciled:"
ARENA_SCORE_SOURCE = "arena-score-v1"
EXIT_OK = 0
EXIT_REFUSED = 1
EXIT_ELO_PENDING = 2


def discover_db_url(override: str | None = None) -> str:
    if override:
        return override
    url = os.environ.get("DATABASE_URL") or os.environ.get("DATABASE_URL_MAIN")
    if not url:
        for cand in [
            Path("agent-arena/.env"),
            Path(".env"),
            Path("../.env"),
            Path("agent-arena/.env.local"),
            Path(".env.local"),
            Path("../.env.local"),
        ]:
            if cand.is_file():
                lines = cand.read_text().splitlines()
                for line in lines:
                    line = line.strip()
                    if line.startswith("DATABASE_URL_MAIN="):
                        val = line.split("=", 1)[1].strip().strip("'\"")
                        if val and "silent-fog" not in val:
                            return val
                for line in lines:
                    line = line.strip()
                    if line.startswith("DATABASE_URL="):
                        val = line.split("=", 1)[1].strip().strip("'\"")
                        if val and "silent-fog" not in val:
                            return val
    if not url:
        raise RuntimeError("DATABASE_URL is not set and could not be discovered.")
    return url


def is_diagnostic_wipeout(score: float, justification: str | None) -> bool:
    just = (justification or "").lower()
    return abs(float(score)) < 0.01 and (
        "untrusted" in just or "diagnostic" in just
    )


def is_authoritative_score_event(payload: Any) -> bool:
    """Whether a durable event was emitted by Arena finalization.

    Sandbox `judge` telemetry is evidence only. A repair may reuse only the
    score event emitted after trusted verification and deterministic scoring.
    """
    return (
        isinstance(payload, dict)
        and payload.get("authoritative") is True
        and payload.get("source") == ARENA_SCORE_SOURCE
    )


def parse_authoritative_score_payload(
    payload: Any,
) -> tuple[dict[str, float], dict[str, str], str] | None:
    """Parse an Arena-authored authoritative score event, never judge prose."""
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except Exception:
            return None
    if not is_authoritative_score_event(payload):
        return None

    raw_scores = payload.get("scores")
    if not isinstance(raw_scores, dict) or not raw_scores:
        return None
    try:
        true_scores = {str(mid): float(val) for mid, val in raw_scores.items()}
    except (TypeError, ValueError):
        return None
    raw_just = payload.get("justifications") or {}
    justifications = {
        str(mid): str(text)
        for mid, text in raw_just.items()
        if isinstance(text, (str, int, float))
    } if isinstance(raw_just, dict) else {}
    return true_scores, justifications, ARENA_SCORE_SOURCE


def validate_repair(
    current_scores: list[tuple[str, float, str | None, str | None]],
    participants: list[str],
    true_scores: dict[str, float],
) -> str | None:
    if not current_scores:
        return "No score rows exist; refuse to insert authoritative scores."
    current_ids = [mid for mid, _, _, _ in current_scores]
    expected = set(participants) if participants else set(current_ids)
    if set(current_ids) != expected:
        return "Score rows do not match battle participants."
    if set(true_scores) != expected:
        return "Judge score map does not match expected participants."
    for mid, score, _judge, just in current_scores:
        if not is_diagnostic_wipeout(score, just):
            return (
                f"Refusing overwrite of non-wipeout score for {mid} "
                f"(score={score!r})."
            )
    return None


def scores_already_match(
    current_scores: list[tuple[str, float, str | None, str | None]],
    true_scores: dict[str, float],
) -> bool:
    if not current_scores:
        return False
    for mid, score, _judge, just in current_scores:
        if mid not in true_scores:
            return False
        if abs(float(score) - float(true_scores[mid])) >= 0.01:
            return False
        if REPAIR_PREFIX not in str(just or ""):
            return False
    return True


def _fetch_score_rows(cur, battle_id: str) -> list[tuple[str, float, str | None, str | None]]:
    cur.execute(
        """
        SELECT model_id, score, judge_model, justification
        FROM scores WHERE battle_id = %s
        ORDER BY model_id
        FOR UPDATE
        """,
        (battle_id,),
    )
    return [(r[0], float(r[1]), r[2], r[3]) for r in cur.fetchall()]


def _fetch_participants(cur, battle_id: str) -> list[str]:
    cur.execute(
        """
        SELECT model_id FROM battle_participants
        WHERE battle_id = %s ORDER BY position
        """,
        (battle_id,),
    )
    return [r[0] for r in cur.fetchall()]


def _fetch_authoritative_score_payload(cur, battle_id: str) -> Any | None:
    cur.execute(
        """
        SELECT payload
        FROM battle_events
        WHERE battle_id = %s AND event_type = 'scores'
        ORDER BY created_at DESC LIMIT 1
        """,
        (battle_id,),
    )
    row = cur.fetchone()
    return None if not row else row[0]


def _fetch_reconciliation(cur, battle_id: str) -> tuple[str, dict] | None:
    cur.execute(
        """
        SELECT status, repaired_scores
        FROM score_reconciliations WHERE battle_id = %s
        FOR UPDATE
        """,
        (battle_id,),
    )
    row = cur.fetchone()
    if not row:
        return None
    payload = row[1] if isinstance(row[1], dict) else {}
    return str(row[0]), payload


def _upsert_pending(cur, battle_id: str, judge_model: str, true_scores: dict[str, float]) -> None:
    cur.execute(
        """
        INSERT INTO score_reconciliations
            (battle_id, status, judge_model, repaired_scores)
        VALUES (%s, %s, %s, %s::jsonb)
        ON CONFLICT (battle_id) DO UPDATE
        SET status = EXCLUDED.status,
            judge_model = EXCLUDED.judge_model,
            repaired_scores = EXCLUDED.repaired_scores,
            updated_at = now()
        WHERE score_reconciliations.status = %s
        """,
        (
            battle_id,
            PENDING_STATUS,
            judge_model,
            json.dumps(true_scores),
            PENDING_STATUS,
        ),
    )


def _rollback_result(conn, result: dict[str, Any]) -> dict[str, Any]:
    """Release row locks before a read-only/refused reconciliation result."""
    conn.rollback()
    return result


def reconcile_battle(conn, battle_id: str, dry_run: bool = False) -> dict[str, Any]:
    with conn.cursor() as cur:
        current_scores = _fetch_score_rows(cur, battle_id)
        participants = _fetch_participants(cur, battle_id)
        existing = _fetch_reconciliation(cur, battle_id)
        payload = _fetch_authoritative_score_payload(cur, battle_id)
        if payload is None:
            return _rollback_result(conn, {
                "battle_id": battle_id,
                "status": "REFUSED",
                "reason": "NO_AUTHORITATIVE_SCORE_EVENT_FOUND",
            })
        if not is_authoritative_score_event(payload):
            return _rollback_result(conn, {
                "battle_id": battle_id,
                "status": "REFUSED",
                "reason": "UNTRUSTED_SCORE_EVENT",
            })
        parsed = parse_authoritative_score_payload(payload)
        if parsed is None:
            return _rollback_result(conn, {
                "battle_id": battle_id,
                "status": "REFUSED",
                "reason": "MALFORMED_AUTHORITATIVE_SCORE_EVENT",
            })
        true_scores, justifications, score_source = parsed

        if existing and existing[0] == ACK_STATUS:
            return _rollback_result(conn, {
                "battle_id": battle_id,
                "status": "ALREADY_ACKNOWLEDGED",
                "scores": true_scores,
            })

        if scores_already_match(current_scores, true_scores):
            if not dry_run and (existing is None or existing[0] != PENDING_STATUS):
                _upsert_pending(cur, battle_id, score_source, true_scores)
                conn.commit()
            else:
                conn.rollback()
            return {
                "battle_id": battle_id,
                "status": PENDING_STATUS,
                "handoff": PENDING_STATUS,
                "idempotent": True,
                "scores": true_scores,
                "judge_model": score_source,
            }

        error = validate_repair(current_scores, participants, true_scores)
        if error:
            return _rollback_result(conn, {
                "battle_id": battle_id,
                "status": "REFUSED",
                "reason": error,
            })

        if dry_run:
            return _rollback_result(conn, {
                "battle_id": battle_id,
                "status": "WOULD_RECONCILE",
                "handoff": PENDING_STATUS,
                "old_scores": {r[0]: float(r[1]) for r in current_scores},
                "new_scores": true_scores,
                "judge_model": score_source,
            })

        for mid, tscore in true_scores.items():
            just = str(justifications.get(mid, "Reconciled from authoritative judge event"))
            full_just = f"{REPAIR_PREFIX} {just[:250]}"
            cur.execute(
                """
                UPDATE scores
                SET score = %s, judge_model = %s, justification = %s
                WHERE battle_id = %s AND model_id = %s
                  AND score = 0
                  AND (
                    justification ILIKE '%%untrusted%%'
                    OR justification ILIKE '%%diagnostic%%'
                  )
                """,
                (float(tscore), score_source, full_just, battle_id, mid),
            )
            if cur.rowcount != 1:
                conn.rollback()
                return {
                    "battle_id": battle_id,
                    "status": "REFUSED",
                    "reason": f"Conditional update failed for {mid}; no overwrite performed.",
                }
        _upsert_pending(cur, battle_id, score_source, true_scores)
        conn.commit()

        return {
            "battle_id": battle_id,
            "status": PENDING_STATUS,
            "handoff": PENDING_STATUS,
            "old_scores": {r[0]: float(r[1]) for r in current_scores},
            "new_scores": true_scores,
            "judge_model": score_source,
        }


def acknowledge_elo(conn, battle_id: str, dry_run: bool = False) -> dict[str, Any]:
    with conn.cursor() as cur:
        existing = _fetch_reconciliation(cur, battle_id)
        if existing is None:
            return _rollback_result(conn, {
                "battle_id": battle_id,
                "status": "REFUSED",
                "reason": "No Elo-pending reconciliation marker; refuse acknowledge.",
            })
        if existing[0] == ACK_STATUS:
            return _rollback_result(conn, {
                "battle_id": battle_id,
                "status": "ALREADY_ACKNOWLEDGED",
                "idempotent": True,
            })
        if existing[0] != PENDING_STATUS:
            return _rollback_result(conn, {
                "battle_id": battle_id,
                "status": "REFUSED",
                "reason": f"Unexpected reconciliation status {existing[0]!r}.",
            })
        if dry_run:
            return _rollback_result(conn, {
                "battle_id": battle_id,
                "status": "WOULD_ACKNOWLEDGE",
            })
        cur.execute(
            """
            UPDATE score_reconciliations
            SET status = %s, updated_at = now()
            WHERE battle_id = %s AND status = %s
            """,
            (ACK_STATUS, battle_id, PENDING_STATUS),
        )
        if cur.rowcount != 1:
            conn.rollback()
            return {
                "battle_id": battle_id,
                "status": "REFUSED",
                "reason": "Conditional acknowledge failed.",
            }
        conn.commit()
        return {
            "battle_id": battle_id,
            "status": ACK_STATUS,
            "idempotent": False,
        }


def find_untrusted_battles(conn) -> list[str]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT DISTINCT battle_id
            FROM scores
            WHERE justification ILIKE '%%untrusted%%'
               OR (score = 0.0 AND justification ILIKE '%%diagnostic%%')
            ORDER BY battle_id
            """
        )
        return [r[0] for r in cur.fetchall()]


def _exit_for_results(results: list[dict[str, Any]]) -> int:
    statuses = [r["status"] for r in results]
    if any(s == "REFUSED" for s in statuses):
        return EXIT_REFUSED
    if any(s == PENDING_STATUS for s in statuses):
        return EXIT_ELO_PENDING
    if any(s == "WOULD_RECONCILE" for s in statuses):
        return EXIT_ELO_PENDING
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Reconcile diagnostic 0.0 score wipeouts.")
    parser.add_argument("battle_id", nargs="?", default=None, help="Specific Battle UUID")
    parser.add_argument("--all", action="store_true", help="Scan untrusted/diagnostic wipeouts")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing")
    parser.add_argument(
        "--acknowledge-elo",
        action="store_true",
        help="Mark a pending repair as Elo-acknowledged. Does not apply Elo.",
    )
    parser.add_argument("--database-url", default=None, help="PostgreSQL connection string override")
    args = parser.parse_args(argv)

    if not args.battle_id and not args.all:
        parser.print_help()
        return EXIT_REFUSED
    if args.acknowledge_elo and args.all:
        print("Error: --acknowledge-elo requires a single battle_id.", file=sys.stderr)
        return EXIT_REFUSED

    url = discover_db_url(args.database_url)
    clean_url = url.replace("-pooler.", ".")

    with psycopg.connect(clean_url) as conn:
        if args.acknowledge_elo:
            res = acknowledge_elo(conn, args.battle_id, dry_run=args.dry_run)
            print(f"[{res['status']}] Battle: {args.battle_id} ({res.get('reason', 'OK')})")
            if res["status"] in (ACK_STATUS, "ALREADY_ACKNOWLEDGED", "WOULD_ACKNOWLEDGE"):
                return EXIT_OK
            return EXIT_REFUSED

        target_ids = [args.battle_id] if args.battle_id else find_untrusted_battles(conn)
        if not args.battle_id:
            print(f"Found {len(target_ids)} battles with un-trusted/diagnostic scores in database.")
        if not target_ids:
            print("No matching battles found to reconcile.")
            return EXIT_OK

        print(f"--- Reconciling {len(target_ids)} Battle(s) (Dry Run: {args.dry_run}) ---")
        results = []
        pending_count = 0
        for bid in target_ids:
            res = reconcile_battle(conn, bid, dry_run=args.dry_run)
            results.append(res)
            status = res["status"]
            if status in (PENDING_STATUS, "WOULD_RECONCILE"):
                pending_count += 1
                print(f"[{status}] Battle: {bid}")
                if "old_scores" in res:
                    print(f"  Old Scores: {res['old_scores']}")
                    print(f"  New Scores: {res['new_scores']}")
                print(f"  Judge:      {res.get('judge_model')}")
                print(f"  Handoff:    {PENDING_STATUS} (Elo not applied)")
            else:
                print(f"[{status}] Battle: {bid} ({res.get('reason', 'OK')})")

        print("--------------------------------------------------")
        print(
            f"Complete. {pending_count} battle(s) "
            f"{'would be ' if args.dry_run else ''}score-repaired with {PENDING_STATUS}."
        )
        print("Leaderboard Elo is stale until --acknowledge-elo after a separate Elo job.")
        return _exit_for_results(results)


if __name__ == "__main__":
    sys.exit(main())
