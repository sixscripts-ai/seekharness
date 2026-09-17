# Git Worktree Reconciliation & Hygiene Reference

## 1. Git Worktree Lifecycle for Parallel Agents

When multiple tasks or agents run in parallel, use Git worktrees to maintain full workspace isolation without mutating the working directory:

1. **Creation**:
   Create a dedicated worktree linked to a feature branch:
   ```bash
   git worktree add -b feat/<task-id> .worktrees/<task-id> HEAD
   ```

2. **Isolation Guarantee**:
   All edits, builds, and test executions must occur strictly inside `.worktrees/<task-id>`. The primary working tree remains unperturbed.

3. **Reconciliation & Extraction**:
   Inspect changes in the worktree using `scripts/reconcile.py`. If changes pass boundary certification, merge or rebase them into `main`.

4. **Pruning & Cleanup**:
   Remove the worktree and prune metadata:
   ```bash
   git worktree remove --force .worktrees/<task-id>
   git worktree prune
   ```

## 2. Change Categorization Protocol

Changes must be grouped by architectural boundaries:
- `dev_tooling`: `dev/` directory (CLI, test harnesses, internal scripts).
- `agent_skills`: `.agents/skills/`, `arena-fighter-skills/`.
- `backend`: Core server, models, APIs, and alembic migrations.
- `frontend`: React/Next.js dashboard and components.
- `targets`: Target definitions and verification manifests.
- `other`: Root configurations and documentation.

## 3. User Protection Gate

Never stage or discard untracked files or modifications outside the bounded scope of the task. If uncommitted user edits exist, confirm they are preserved before checking out or merging branches.
