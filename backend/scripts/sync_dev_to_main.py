#!/usr/bin/env python3
"""Sync production tables from a source Neon URL to a main/target Neon URL.

Reads connection strings from the environment (typically repo-root `.env`):
- source: DATABASE_URL_UNPOOLED or DATABASE_URL
- target: DATABASE_URL_UNPOOLED_MAIN or DATABASE_URL_MAIN

Refuses to run without an explicit `--yes` confirmation. Never writes `.env`.

Order is strictly topologically sorted:
1. alembic_version
2. formats
3. providers
4. skills
5. battles (parent)
6. battle_results (child of battles)
7. battle_drafts
8. battle_participants
9. rounds
10. scores
11. battle_events
12. leaderboard
13. memories
"""
from __future__ import annotations

import argparse
import io
import os
import sys
from pathlib import Path

import psycopg
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parents[2]
ENV_FILE = ROOT_DIR / ".env"

TABLES_IN_ORDER = [
    "alembic_version",
    "formats",
    "providers",
    "skills",
    "battles",
    "battle_results",
    "battle_drafts",
    "battle_participants",
    "rounds",
    "scores",
    "battle_events",
    "leaderboard",
    "memories",
]


def get_table_counts(conn_str: str) -> dict[str, int]:
    counts = {}
    with psycopg.connect(conn_str) as conn:
        with conn.cursor() as cur:
            for table in TABLES_IN_ORDER:
                try:
                    cur.execute(f"SELECT count(*) FROM {table}")
                    counts[table] = cur.fetchone()[0]
                except Exception:
                    counts[table] = -1
    return counts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Copy all listed tables from the source Neon database to the "
            "main/target database. Truncates the target first. Destructive."
        )
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Required confirmation to TRUNCATE the target and COPY rows.",
    )
    args = parser.parse_args(argv)

    load_dotenv(ENV_FILE)
    source_url = os.environ.get("DATABASE_URL_UNPOOLED") or os.environ.get(
        "DATABASE_URL"
    )
    target_url = os.environ.get("DATABASE_URL_UNPOOLED_MAIN") or os.environ.get(
        "DATABASE_URL_MAIN"
    )
    if not source_url:
        print(
            "Error: DATABASE_URL_UNPOOLED or DATABASE_URL is required",
            file=sys.stderr,
        )
        return 1
    if not target_url:
        print(
            "Error: DATABASE_URL_UNPOOLED_MAIN or DATABASE_URL_MAIN is required",
            file=sys.stderr,
        )
        return 1
    if not args.yes:
        print(
            "Error: refusing to TRUNCATE without --yes",
            file=sys.stderr,
        )
        return 1

    print("=== STEP 1: Audit Source and Target Before Sync ===")
    source_counts = get_table_counts(source_url)
    target_counts_before = get_table_counts(target_url)

    print(f"{'Table':22} | {'source':12} | {'target (Before)':16}")
    print("-" * 56)
    for t in TABLES_IN_ORDER:
        print(
            f"{t:22} | {source_counts.get(t, 0):12} | {target_counts_before.get(t, 0):16}"
        )

    print("\n=== STEP 2: Streaming Tables via psycopg Binary COPY ===")
    with psycopg.connect(source_url) as src_conn, psycopg.connect(
        target_url
    ) as tgt_conn:
        with tgt_conn.cursor() as tgt_cur:
            tables_joined = ", ".join(TABLES_IN_ORDER)
            print(f"Truncating tables on target: {tables_joined}...")
            tgt_cur.execute(f"TRUNCATE TABLE {tables_joined} CASCADE")

            for table in TABLES_IN_ORDER:
                src_count = source_counts.get(table, 0)
                if src_count == 0:
                    print(f" - {table}: 0 rows, skipping copy.")
                    continue

                print(f" - Copying {table} ({src_count} rows)...", end="", flush=True)
                buf = io.BytesIO()

                with src_conn.cursor() as src_cur:
                    with src_cur.copy(f"COPY {table} TO STDOUT (FORMAT binary)") as copy:
                        for chunk in copy:
                            buf.write(chunk)

                buf.seek(0)
                with tgt_cur.copy(f"COPY {table} FROM STDIN (FORMAT binary)") as copy:
                    while chunk := buf.read(65536):
                        copy.write(chunk)

                print(f" done ({buf.getbuffer().nbytes} bytes).")

        tgt_conn.commit()

    print("\n=== STEP 3: Audit Target After Sync ===")
    target_counts_after = get_table_counts(target_url)

    print(f"{'Table':22} | {'source':12} | {'target (After)':14} | {'Status'}")
    print("-" * 66)
    mismatch = False
    for t in TABLES_IN_ORDER:
        src = source_counts.get(t, 0)
        tgt = target_counts_after.get(t, 0)
        status = "MATCH" if src == tgt else "MISMATCH"
        if src != tgt:
            mismatch = True
        print(f"{t:22} | {src:12} | {tgt:14} | {status}")

    if mismatch:
        print("\nERROR: Mismatch detected between source and target!", file=sys.stderr)
        return 1

    print("\nAll tables match. Target is in sync with source.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
