import json
import os
import subprocess
from pathlib import Path


def get_codex_health() -> dict:
    script_path = os.path.expanduser("~/.gemini/config/skills/maintain-codex/scripts/check_codex_health.py")
    if os.path.exists(script_path):
        try:
            res = subprocess.run([script_path, "--json"], capture_output=True, text=True, timeout=5)
            if res.stdout.strip():
                return json.loads(res.stdout)
        except Exception as e:
            return {"status": "DEGRADED", "error": f"Failed to execute maintain-codex script: {e}"}

    # Fallback if maintain-codex script is not found
    import shutil
    has_cli = bool(shutil.which("codex"))
    has_host = os.path.exists(os.path.expanduser("~/.local/bin/codex-code-mode-host"))
    status = "HEALTHY" if (has_cli and has_host) else "DEGRADED"
    return {
        "status": status,
        "checks": {
            "cli": "OK" if has_cli else "MISSING",
            "code_mode_host": "OK" if has_host else "MISSING"
        }
    }
