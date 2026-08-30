#!/usr/bin/env python3
"""beforeShellExecution guard for Agent Arena. Fail-closed via hooks.json."""

from __future__ import annotations

import json
import re
import sys

_FORCE_PUSH = re.compile(
    r"git(?:\s+[^\n]*)?\spush\b[^\n]*(\s--force\b|\s--force-with-lease\b|\s-f\b)",
    re.I,
)
_HARD_RESET = re.compile(r"git(?:\s+[^\n]*)?\sreset\s+[^\n]*--hard\b", re.I)
_GIT_CLEAN = re.compile(r"git(?:\s+[^\n]*)?\sclean\b[^\n]*(-[a-zA-Z]*f|-f)", re.I)
_GIT_PUSH = re.compile(r"git(?:\s+[^\n]*)?\spush\b", re.I)
_SUDO = re.compile(r"(^|[;&|`\n])\s*sudo\b", re.I)
_DROP = re.compile(r"\bDROP\s+(TABLE|DATABASE|SCHEMA)\b", re.I)
_TRUNCATE = re.compile(r"\bTRUNCATE\b", re.I)
_VERCEL_PROD = re.compile(
    r"\b(npx\s+)?vercel\b[^\n]*(--prod|deploy\s+[^\n]*--prod|\bpromote\b)",
    re.I,
)
_MODAL_DEPLOY = re.compile(r"\bmodal\b[^\n]*\bdeploy\b", re.I)
_ALEMBIC = re.compile(r"\balembic\b[^\n]*\b(upgrade|downgrade)\b", re.I)
_APPWRITE_MUT = re.compile(
    r"\b(bootstrap_appwrite|appwrite\s+(push|deploy|delete|create|update|migrate))\b",
    re.I,
)
_SECRET_ENV = re.compile(
    r"\b(vercel\s+env|modal\s+secret|wrangler\s+secret)\b",
    re.I,
)
_BILLING = re.compile(
    r"\b(vercel\s+(domains?\s+buy|dns\s+add|purchase)|npx\s+vercel\s+domains?\s+buy)\b",
    re.I,
)
_CLOUD_DELETE = re.compile(
    r"\b(vercel\s+(project\s+rm|remove)|modal\s+app\s+delete|appwrite\s+(projects?\s+)?delete)\b",
    re.I,
)
_PSQL_WRITE = re.compile(r"\b(psql|postgres|neon)\b", re.I)
_SQL_WRITE = re.compile(
    r"\b(INSERT|UPDATE|DELETE|ALTER|CREATE|GRANT|REVOKE)\b",
    re.I,
)
_RM_RF = re.compile(r"\brm\s+(-[a-zA-Z]*r[a-zA-Z]*f|-[a-zA-Z]*f[a-zA-Z]*r)\b", re.I)


def _emit(permission: str, user_message: str = "", agent_message: str = "") -> None:
    payload: dict[str, str] = {"permission": permission}
    if user_message:
        payload["user_message"] = user_message
    if agent_message:
        payload["agent_message"] = agent_message
    sys.stdout.write(json.dumps(payload))
    sys.exit(0)


def _dangerous_rm(command: str) -> bool:
    if not _RM_RF.search(command):
        return False
    # Broad / home / repo-root wipes only. `rm -rf backend/.pytest_cache` stays allowed.
    return bool(
        re.search(
            r"rm\s+-[a-zA-Z]*\s+(--no-preserve-root\s+)?(/|/\*|~|\$HOME|\$\{HOME\}|\.|\.\.|\*)(\s|$)",
            command,
        )
    )


def classify(command: str) -> tuple[str, str, str]:
    if _SUDO.search(command):
        return "deny", "sudo is blocked in Agent Arena.", "Hook denied sudo."
    if _FORCE_PUSH.search(command):
        return "deny", "Force push is blocked.", "Hook denied git push --force."
    if _HARD_RESET.search(command):
        return "deny", "git reset --hard is blocked.", "Hook denied hard reset."
    if _GIT_CLEAN.search(command):
        return "deny", "git clean is blocked.", "Hook denied git clean."
    if _dangerous_rm(command):
        return "deny", "Broad rm -rf is blocked.", "Hook denied destructive rm -rf."
    if _DROP.search(command) or _TRUNCATE.search(command):
        return "deny", "DROP/TRUNCATE is blocked.", "Hook denied destructive SQL."
    if _BILLING.search(command):
        return "deny", "Billing/domain purchase is blocked.", "Hook denied billing command."
    if _CLOUD_DELETE.search(command):
        return "deny", "Cloud resource deletion is blocked.", "Hook denied cloud delete."
    return "allow", "", ""


def main() -> None:
    try:
        raw = sys.stdin.read()
        data = json.loads(raw) if raw.strip() else {}
        command = str(data.get("command") or "")
        permission, user_message, agent_message = classify(command)
        _emit(permission, user_message, agent_message)
    except Exception as exc:  # failClosed: emit deny JSON rather than crash
        _emit("deny", "Shell guard failed closed.", f"Hook error: {exc}")


if __name__ == "__main__":
    main()
