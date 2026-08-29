#!/usr/bin/env python3
"""Deception-resilience benchmark: run solo target battles against real models.

Queries the target library (targets/library), compiles each target to its
authoritative battle_config, and (in --launch mode) creates + starts battles
end-to-end on the configured persistence backend, one model per battle.

Signal captured: judge score (ranked requires hidden-test pass), plus the
enriched round artifacts (tool_trace / verification_log / meta) when the
executor records them. Mock runs are labeled meta.is_mock=true so they can be
filtered out of the value extraction.

Usage:
    PERSISTENCE_BACKEND=postgres DATABASE_URL=<neon url> \
        .venv/bin/python scripts/deception_benchmark.py \
        --models host:opencode-go host:modal-kimi --reps 2 --launch --wait

Without --launch this is a dry-run plan (no database writes).
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_TARGETS = [
    "poisoned-instructions",  # agent-security / advanced / adversarial_agent
    "readme-lied",  # software-engineering / general / solo
    "red-herring-repository",  # agent-tool-use / expert / solo
]
DEFAULT_MODELS = ["host:opencode-go", "host:modal-kimi"]
TERMINAL = {"completed", "failed", "cancelled"}


def _format_id(cfg: dict) -> str:
    """Reuse the first playable seeded format; battle_create replaces its config
    with the frozen target contract and re-validates against compiled roles."""
    from agent_arena.persistence import service

    fmts = service.formats_list() or []
    for f in fmts:
        fmt_cfg = f.get("config") or {}
        if fmt_cfg.get("custom") or fmt_cfg.get("require_draft"):
            continue
        # "Auth system vs breaker" (build_and_break) is the canonical playable
        # anchor the frontend already uses for all target battles.
        if fmt_cfg.get("roles"):
            return f["id"]
    raise SystemExit("no playable seeded format found — run bootstrap first")


def _plan(args) -> list[dict]:
    from agent_arena.target_library import (
        compile_target_to_battle_config,
        get_target_library,
    )

    lib = get_target_library()
    rows = []
    for slug in args.targets:
        bundle = lib.get_target(slug)
        if bundle is None:
            raise SystemExit(f"target not found in library: {slug}")
        for model in args.models:
            rows.append(
                {
                    "target": bundle.id,
                    "name": bundle.name,
                    "category": bundle.category,
                    "difficulty": bundle.difficulty,
                    "format": bundle.format,
                    "model": model,
                    "arena_size": 1,
                    "exec_timeout_seconds": bundle.limits.exec_timeout_seconds,
                    "bundle": bundle,
                }
            )
    return rows


def _launch(args, row: dict, fmt_id: str, batch: str, out_writer) -> dict:
    from agent_arena.persistence import service
    from agent_arena.sandbox_launcher import start_battle

    bundle: object = row.pop("bundle")
    battle = service.battle_create(
        args.user,
        format_id=fmt_id,
        model_ids=[row["model"]],
        arena_size=1,
        timeout_seconds=int(row["exec_timeout_seconds"] or 600),
        round_visibility="isolated",
        save=args.save,
        target_id=row["target"],
    )
    battle_id = battle["id"]
    t = threading.Thread(target=start_battle, args=(battle_id,), daemon=True)
    t.start()
    rec = {
        "batch": batch,
        "target": row["target"],
        "difficulty": row["difficulty"],
        "model": row["model"],
        "battle_id": battle_id,
        "status_at_launch": battle.get("status", "queued"),
        "queued_or_terminal_at": datetime.now(timezone.utc).isoformat(),
    }
    out_writer.writerow(rec)
    return rec


def _wait(recs: list[dict], timeout_s: float) -> None:
    from agent_arena.persistence import service

    deadline = time.time() + timeout_s
    pending = {r["battle_id"] for r in recs}
    while pending and time.time() < deadline:
        for bid in list(pending):
            try:
                b = service.battle_get("", bid) or {}
                if b.get("status") in TERMINAL:
                    pending.discard(bid)
            except Exception:
                pass
        if pending:
            time.sleep(3)
    if pending:
        print(
            f"  still pending after {timeout_s:.0f}s: {sorted(pending)}",
            file=sys.stderr,
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--targets", nargs="*", default=DEFAULT_TARGETS)
    parser.add_argument("--models", nargs="*", default=DEFAULT_MODELS)
    parser.add_argument("--reps", type=int, default=2)
    parser.add_argument("--launch", action="store_true", help="create + start battles")
    parser.add_argument(
        "--wait", type=float, default=0.0, help="wait N seconds for terminal status"
    )
    parser.add_argument(
        "--save", action="store_true", default=True, help="save=1 so scores persist"
    )
    parser.add_argument("--user", default="bench:operator")
    parser.add_argument(
        "--out",
        default=None,
        help="csv path (default scripts/out/deception_benchmark.csv)",
    )
    args = parser.parse_args()

    rows = _plan(args)
    print(
        f"\nDeception benchmark plan: {len(rows)} battles "
        f"({len(args.targets)} targets x {len(args.models)} models x {args.reps} reps)"
    )
    print(f"{'target':28} {'difficulty':10} {'model':22} size timeout")
    for row in rows:
        print(
            f"{row['target']:28} {row['difficulty']:10} {row['model']:22} "
            f"{row['arena_size']}   {row['exec_timeout_seconds']}s"
        )

    if not args.launch:
        print("\nDRY-RUN: pass --launch to create battles on the configured backend.")
        return 0

    fmt_id = _format_id({})
    out_dir = Path(args.out or "scripts/out")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "deception_benchmark.csv"
    batch = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    recs: list[dict] = []
    with out_path.open("w", newline="") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=[
                "batch",
                "target",
                "difficulty",
                "model",
                "battle_id",
                "status_at_launch",
                "queued_or_terminal_at",
            ],
        )
        writer.writeheader()
        for _ in range(args.reps):
            for row in rows:
                try:
                    recs.append(_launch(args, dict(row), fmt_id, batch, writer))
                except Exception as exc:
                    print(
                        f"  launch failed {row['target']}/{row['model']}: {exc}",
                        file=sys.stderr,
                    )
    print(f"\nLaunched {len(recs)} battles (format_id={fmt_id}) -> {out_path}")
    for r in recs:
        print(f"  {r['battle_id']} {r['target']} {r['model']} {r['status_at_launch']}")

    if args.wait:
        print(f"\nWaiting up to {args.wait:.0f}s for terminal status...")
        _wait(recs, args.wait)
        from agent_arena.persistence import service

        for r in recs:
            b = service.battle_get("", r["battle_id"]) or {}
            print(
                f"  {r['battle_id'][:16]} {b.get('status')} "
                f"failure_reason={b.get('failure_reason')}"
            )
    return 0


if __name__ == "__main__":
    main()
