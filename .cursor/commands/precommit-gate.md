---
name: precommit-gate
description: Read-only pre-commit review of status, diff, commit boundary, migrations, and relevant regression scope. Does not commit.
---

# /precommit-gate

Read-only. Do not commit, push, restore, or clean.

Collect:

```bash
git status --short
git diff --check
git diff --stat
git log -8 --oneline
```

## Review

1. **Commit boundary** — would this commit mix unrelated P0 / Change Set C work with the intended slice?
2. **Migrations** — any Alembic / schema files? Do not apply them.
3. **Secrets** — no `.env`, keys, or tokens
4. **Relevant regression gate** — name the `regression-gate` steps that should run; run hermetic tests only if the user asked this command to execute them. Default is read-only listing.

`git diff --check` may already fail on pre-existing application whitespace. Report that separately from new `.cursor` or intended-slice issues.

## Report

- What should be in vs out of the next commit
- Migration risk
- Recommended hermetic test commands
- Explicit statement: nothing was committed
