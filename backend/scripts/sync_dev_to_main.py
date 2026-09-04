#!/usr/bin/env python3
"""Sync all production tables, rows, and skills from Neon dev branch to main branch.

Order is strictly topologically sorted:
1. alembic_version
2. formats
3. providers
4. skills
5. battles (parent for drafts, participants, rounds, scores, events)
6. battle_drafts
7. battle_participants
8. rounds
9. scores
10. battle_events
11. leaderboard
12. memories
"""
from __future__ import annotations

import io
import os
import sys
from pathlib import Path
import psycopg
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parents[2]
ENV_FILE = ROOT_DIR / ".env"

MAIN_POOLED_URL = (
    "postgresql://neondb_owner:npg_EGjOZhdiBz92@"
    "ep-late-paper-a6xhbxsc-pooler.us-west-2.aws.neon.tech/neondb?sslmode=require"
)
MAIN_UNPOOLED_URL = (
    "postgresql://neondb_owner:npg_EGjOZhdiBz92@"
    "ep-late-paper-a6xhbxsc.us-west-2.aws.neon.tech/neondb?sslmode=require"
)

TABLES_IN_ORDER = [
    "alembic_version",
    "formats",
    "providers",
    "skills",
    "battles",
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


def main() -> int:
    load_dotenv(ENV_FILE)
    source_url = os.environ.get("DATABASE_URL_UNPOOLED") or os.environ.get("DATABASE_URL")
    if not source_url:
        print("Error: DATABASE_URL not found in .env", file=sys.stderr)
        return 1

    print("=== STEP 1: Audit Source (dev) and Target (main) Before Sync ===")
    source_counts = get_table_counts(source_url)
    target_counts_before = get_table_counts(MAIN_UNPOOLED_URL)

    print(f"{'Table':22} | {'dev (Source)':12} | {'main (Before)':12}")
    print("-" * 52)
    for t in TABLES_IN_ORDER:
        print(f"{t:22} | {source_counts.get(t, 0):12} | {target_counts_before.get(t, 0):12}")

    print("\n=== STEP 2: Streaming Tables via psycopg Binary COPY ===")
    with psycopg.connect(source_url) as src_conn, psycopg.connect(MAIN_UNPOOLED_URL) as tgt_conn:
        with tgt_conn.cursor() as tgt_cur:
            # Truncate all tables in one statement with CASCADE
            tables_joined = ", ".join(TABLES_IN_ORDER)
            print(f"Truncating tables on main: {tables_joined}...")
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

    print("\n=== STEP 3: Audit Target (main) After Sync ===")
    target_counts_after = get_table_counts(MAIN_UNPOOLED_URL)

    print(f"{'Table':22} | {'dev (Source)':12} | {'main (After)':12} | {'Status'}")
    print("-" * 62)
    mismatch = False
    for t in TABLES_IN_ORDER:
        src = source_counts.get(t, 0)
        tgt = target_counts_after.get(t, 0)
        status = "MATCH" if src == tgt else "MISMATCH"
        if src != tgt:
            mismatch = True
        print(f"{t:22} | {src:12} | {tgt:12} | {status}")

    if mismatch:
        print("\nERROR: Mismatch detected between dev and main!", file=sys.stderr)
        return 1

    print("\nAll tables match 100%! main branch is now fully in sync with dev.")

    print("\n=== STEP 4: Update .env URLs to point to main branch ===")
    env_content = ENV_FILE.read_text(encoding="utf-8")

    source_pooled = os.environ.get("DATABASE_URL", "")
    source_unpooled = os.environ.get("DATABASE_URL_UNPOOLED", "")

    if source_pooled and source_pooled in env_content:
        env_content = env_content.replace(source_pooled, MAIN_POOLED_URL)
    if source_unpooled and source_unpooled in env_content:
        env_content = env_content.replace(source_unpooled, MAIN_UNPOOLED_URL)

    ENV_FILE.write_text(env_content, encoding="utf-8")
    print(".env updated successfully to use main branch endpoints.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
