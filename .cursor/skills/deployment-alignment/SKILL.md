---
name: deployment-alignment
description: Read-only comparison of local HEAD, origin/main, dirty tree, Modal build SHA, Vercel version, migrations, and persistence mode. Use when asked what is deployed vs committed.
---

# Deployment alignment

Read-only. Do not deploy, migrate, push, or mutate cloud state.

## Compare

Collect each row with an evidence grade:

| Item | How |
| --- | --- |
| Local HEAD | `git rev-parse HEAD` |
| `origin/main` | `git fetch` is optional; prefer `git rev-parse origin/main` if present |
| Dirty tree | `git status --short` and `git diff --stat` |
| Modal build SHA | only where a build SHA is actually published/readable |
| Vercel deployment | only where a deployment id/SHA is actually readable |
| Migration state | local Alembic revision vs any proven remote revision |
| Persistence mode | Postgres vs Appwrite from config/code, not guesswork |

## Grades

| Grade | Meaning |
| --- | --- |
| `DEPLOYED` | Proven running in that environment |
| `COMMITTED` | Present in the named git ref |
| `UNCOMMITTED` | In the dirty tree only |
| `INFERRED` | Reasonable but not proven |
| `UNVERIFIED` | No trustworthy evidence |

Do not upgrade `INFERRED` or `UNVERIFIED` to `DEPLOYED`.

This repo already has a large uncommitted P0 / Change Set C tree. Report it as `UNCOMMITTED` unless it is also on the compared ref.

## Report

- Table of item / value / grade / evidence
- Whether local HEAD equals `origin/main`
- Whether Modal or Vercel SHA is proven
- Remaining uncertainty

## Examples

- Dirty `finalization.py` and Modal SHA unknown → local Change Set C is `UNCOMMITTED`, Modal SHA `UNVERIFIED`
- Browser shows a health SHA matching HEAD → that service can be `DEPLOYED` only if the SHA is actually on the response
