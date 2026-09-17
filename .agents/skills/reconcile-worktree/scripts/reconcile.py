#!/usr/bin/env python3
"""
reconcile.py - Git worktree reconciliation and porcelain change set analyzer.
Categorizes unstaged/staged files, protects uncommitted user edits, and audits worktree hygiene.
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path


def run_git(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(["git"] + cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def get_git_status(repo_root: Path) -> dict:
    proc = run_git(["status", "--porcelain=v1"], repo_root)
    if proc.returncode != 0:
        return {"error": proc.stderr.strip()}

    lines = [line for line in proc.stdout.splitlines() if line.strip()]
    staged = []
    unstaged = []
    untracked = []

    categorized = {
        "dev_tooling": [],
        "agent_skills": [],
        "backend": [],
        "frontend": [],
        "targets": [],
        "other": []
    }

    for line in lines:
        code = line[:2]
        filepath = line[3:].strip()
        # Handle renames e.g. "R  old -> new"
        if " -> " in filepath:
            filepath = filepath.split(" -> ")[-1]

        item = {"status": code, "path": filepath}

        if code[0] in ("M", "A", "D", "R"):
            staged.append(item)
        if code[1] in ("M", "D"):
            unstaged.append(item)
        if code == "??":
            untracked.append(item)

        # Categorize
        if filepath.startswith("dev/"):
            categorized["dev_tooling"].append(filepath)
        elif filepath.startswith(".agents/") or filepath.startswith("arena-fighter-skills/"):
            categorized["agent_skills"].append(filepath)
        elif filepath.startswith("backend/"):
            categorized["backend"].append(filepath)
        elif filepath.startswith("frontend/"):
            categorized["frontend"].append(filepath)
        elif filepath.startswith("targets/"):
            categorized["targets"].append(filepath)
        else:
            categorized["other"].append(filepath)

    return {
        "total_changed": len(lines),
        "staged_count": len(staged),
        "unstaged_count": len(unstaged),
        "untracked_count": len(untracked),
        "categories": {k: len(v) for k, v in categorized.items()},
        "details": {
            "staged": staged,
            "unstaged": unstaged,
            "untracked": untracked,
            "categorized": categorized
        }
    }


def get_active_worktrees(repo_root: Path) -> list[dict]:
    proc = run_git(["worktree", "list", "--porcelain"], repo_root)
    if proc.returncode != 0:
        return []

    worktrees = []
    current = {}
    for line in proc.stdout.splitlines():
        if not line.strip():
            if current:
                worktrees.append(current)
                current = {}
            continue
        parts = line.split(" ", 1)
        key = parts[0]
        val = parts[1] if len(parts) > 1 else ""
        if key == "worktree":
            current["path"] = val
        elif key == "HEAD":
            current["commit"] = val
        elif key == "branch":
            current["branch"] = val
        elif key == "bare":
            current["bare"] = True
        elif key == "detached":
            current["detached"] = True

    if current:
        worktrees.append(current)
    return worktrees


def main():
    parser = argparse.ArgumentParser(description="Analyze git porcelain diffs and manage parallel worktrees.")
    parser.add_argument("--json", action="store_true", help="Output in JSON format")
    parser.add_argument("--worktrees", action="store_true", help="List active worktrees only")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parent.parent.parent.parent.parent
    if not (repo_root / ".git").exists():
        repo_root = Path.cwd()

    if args.worktrees:
        wts = get_active_worktrees(repo_root)
        if args.json:
            print(json.dumps(wts, indent=2))
        else:
            print(f"Active Git Worktrees ({len(wts)}):")
            for wt in wts:
                print(f"  Path  : {wt.get('path')}")
                print(f"  Branch: {wt.get('branch', 'detached')}")
                print(f"  Commit: {wt.get('commit', '')[:8]}")
                print()
        return

    status = get_git_status(repo_root)
    worktrees = get_active_worktrees(repo_root)

    res = {
        "status": status,
        "worktrees": worktrees
    }

    if args.json:
        print(json.dumps(res, indent=2))
        return

    print("==================================================")
    print("         GIT WORKTREE RECONCILIATION              ")
    print("==================================================")
    print(f"Total Changes    : {status.get('total_changed')}")
    print(f"  Staged         : {status.get('staged_count')}")
    print(f"  Unstaged       : {status.get('unstaged_count')}")
    print(f"  Untracked      : {status.get('untracked_count')}")
    print("\nCategorized Changes:")
    for cat, count in status.get("categories", {}).items():
        if count > 0:
            print(f"  - {cat:<16}: {count} files")
    print(f"\nActive Worktrees : {len(worktrees)}")
    for wt in worktrees:
        print(f"  * {wt.get('path')} [{wt.get('branch', 'detached')}]")
    print("==================================================")


if __name__ == "__main__":
    main()
