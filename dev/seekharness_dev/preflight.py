import json
import os
import subprocess
from pathlib import Path


def get_preflight_data(repo_root: Path) -> dict:
    data = {
        "repo_root": str(repo_root),
        "branch": "UNKNOWN",
        "dirty_files": [],
        "staged_files": [],
        "applicable_agents_files": [],
        "env_status": {},
        "migration_head": "UNKNOWN",
        "target_working_tree_state": "CLEAN"
    }

    # Git branch
    try:
        res = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True, timeout=2
        )
        if res.returncode == 0:
            data["branch"] = res.stdout.strip()
    except Exception:
        pass

    # Dirty and staged files
    try:
        res = subprocess.run(
            ["git", "-C", str(repo_root), "status", "--porcelain"],
            capture_output=True, text=True, timeout=2
        )
        if res.returncode == 0:
            dirty = []
            staged = []
            for line in res.stdout.splitlines():
                if not line.strip():
                    continue
                status = line[:2]
                fname = line[3:].strip()
                if status[0] in ("M", "A", "D", "R", "C"):
                    staged.append(fname)
                if status[1] in ("M", "D") or status == "??":
                    dirty.append(fname)
            data["dirty_files"] = dirty
            data["staged_files"] = staged
    except Exception:
        pass

    # Applicable AGENTS.md files
    agents_files = []
    candidates = [
        repo_root.parent / "AGENTS.md",
        repo_root / "AGENTS.md",
        repo_root / "backend" / "AGENTS.md",
        repo_root / "frontend" / "AGENTS.md",
        repo_root / "targets" / "AGENTS.md"
    ]
    for c in candidates:
        if c.exists():
            agents_files.append(str(c))
    data["applicable_agents_files"] = agents_files

    # Environment availability
    venv_py = repo_root / "backend" / ".venv" / "bin" / "python"
    node_mods = repo_root / "frontend" / "node_modules"
    data["env_status"] = {
        "backend_venv": "AVAILABLE" if venv_py.exists() else "MISSING",
        "frontend_node_modules": "AVAILABLE" if node_mods.exists() else "MISSING"
    }

    # Migration head
    versions_dir = repo_root / "backend" / "alembic" / "versions"
    if versions_dir.exists():
        py_files = sorted(versions_dir.glob("*.py"))
        if py_files:
            data["migration_head"] = py_files[-1].name

    # Target working tree state
    target_dirty = [f for f in data["dirty_files"] if f.startswith("targets/")]
    if target_dirty:
        data["target_working_tree_state"] = f"DIRTY ({len(target_dirty)} files)"

    return data
