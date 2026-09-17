---
name: reconcile-worktree
description: >
  Use this skill when reconciling git changes, merging parallel worktrees, or preparing
  commits in SeekHarness. Analyzes git porcelain diffs, separates coherent change sets,
  protects uncommitted user edits, and prunes transient worktrees.
license: MIT
compatibility: Requires Python 3.10+ and git
metadata:
  author: villain
  version: "1.0"
allowed-tools: Bash(git:*) Read
---

# Reconcile Worktree

## Overview

`reconcile-worktree` maintains git repository hygiene across single-agent and multi-agent development sessions. It inspects `git status --porcelain=v1`, categorizes staged and unstaged files into architectural domain sets, detects active parallel git worktrees, and prevents accidental loss of uncommitted work.

## Instructions

1. **Inspect Working Tree & Worktrees**:
   Run the reconciliation script:
   ```bash
   ./scripts/reconcile.py
   ```
   Or to list active worktrees only:
   ```bash
   ./scripts/reconcile.py --worktrees
   ```

2. **Categorize Changes**:
   - Check which subsystems have modifications: `backend`, `dev_tooling`, `agent_skills`, `frontend`, or `targets`.
   - Ensure changes from different subsystems are not mixed together in a single bulk commit.

3. **Safeguard Uncommitted Edits**:
   - Identify any untracked or modified files that do not belong to the current task.
   - Do NOT run `git checkout -- .` or `git reset --hard` blindly.
   - Stash or isolate uncommitted user changes before performing merges.

4. **Prune Transient Worktrees**:
   - Once a task in a parallel worktree is verified, merge or cherry-pick the verified commits.
   - Remove the worktree path cleanly:
     ```bash
     git worktree remove --force .worktrees/<task-name>
     git worktree prune
     ```

## Available Scripts

- **`scripts/reconcile.py`** — Analyzes git status porcelain, categorizes changes by architectural component, and audits active worktrees. Supports `--worktrees` and `--json`.

## Gotchas

- Git porcelain lines starting with `??` indicate untracked files; verify whether they are build artifacts before adding to `.gitignore`.
- Always prune worktree metadata after deleting worktree folders to avoid dangling git refs.
- Never commit broken tests or unverified migrations.

## Examples

### Change Set Overview
```bash
$ ./scripts/reconcile.py
==================================================
         GIT WORKTREE RECONCILIATION              
==================================================
Total Changes    : 12
  Staged         : 4
  Unstaged       : 6
  Untracked      : 2

Categorized Changes:
  - dev_tooling     : 4 files
  - backend         : 6 files
  - other           : 2 files

Active Worktrees : 1
  * /Users/villain/Developer/seekharness/agent-arena [refs/heads/main]
==================================================
```

### JSON Inspection
```bash
$ ./scripts/reconcile.py --json | jq .status.categories
{
  "dev_tooling": 4,
  "agent_skills": 0,
  "backend": 6,
  "frontend": 0,
  "targets": 0,
  "other": 2
}
```

## References

- Read [`references/REFERENCE.md`](references/REFERENCE.md) when managing parallel worktree lifecycles or branch merging protocols.
