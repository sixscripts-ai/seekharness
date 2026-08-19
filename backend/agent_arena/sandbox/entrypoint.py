"""Modal Sandbox entrypoint: drive battle via HTTP internal API."""

from __future__ import annotations

import json
import os
import sys


def main(battle_id: str) -> None:
    os.environ["ARENA_IN_SANDBOX"] = "1"
    base = os.environ["BACKEND_PUBLIC_URL"].rstrip("/")
    # Prefer the per-battle scoped token; fall back to the legacy global key
    # only for environments that still inject INTERNAL_API_KEY directly.
    sandbox_token = os.environ.get("BATTLE_TOKEN") or ""
    legacy_key = os.environ.get("INTERNAL_API_KEY") or ""
    if not sandbox_token and not legacy_key:
        print("missing BATTLE_TOKEN / INTERNAL_API_KEY", file=sys.stderr)
        sys.exit(2)
    bootstrap = os.environ.get("BATTLE_BOOTSTRAP_JSON")
    if not bootstrap:
        print("missing BATTLE_BOOTSTRAP_JSON", file=sys.stderr)
        sys.exit(2)
    data = json.loads(bootstrap)
    from agent_arena.sandbox.client import HttpTransport, InternalClient
    from agent_arena.sandbox.runner import run_battle_loop

    client = InternalClient(
        HttpTransport(base, legacy_key, sandbox_token=sandbox_token or None)
    )
    terminal: list[str] = []
    scores: dict = {}

    def status_check() -> str:
        try:
            return client.status(battle_id)
        except Exception:
            return "running"

    def on_status(status: str) -> None:
        terminal.append(status)
        try:
            client.round(
                battle_id, "system", "system", status, event_type="battle_status"
            )
        except Exception as exc:
            print(f"on_status({status}) failed: {exc}", file=sys.stderr)

    try:
        scores = run_battle_loop(
            battle_id=battle_id,
            format_config=data["format_config"],
            model_ids=data["model_ids"],
            round_visibility=data.get("round_visibility", "isolated"),
            timeout_seconds=int(data.get("timeout_seconds") or 600),
            client=client,
            status_check=status_check,
            on_status=on_status,
        )
        final = "completed" if scores else "failed"
    except Exception as exc:
        print(f"battle loop failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        final = "failed"
    try:
        client.finalize(
            battle_id, status=final, scores=scores if final == "completed" else {}
        )
    except Exception as exc:
        print(f"finalize({final}) failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise


if __name__ == "__main__":
    main(sys.argv[1])
