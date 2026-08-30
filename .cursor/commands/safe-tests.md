---
name: safe-tests
description: Run local hermetic Agent Arena tests. Excludes evals, Modal, Appwrite, Neon, and provider APIs unless explicitly opted in.
---

# /safe-tests

May execute local/hermetic tests automatically. Do not deploy, migrate, or call paid providers.

## Verify isolation first

Confirm the command will **not** set `ARENA_INTEGRATION_TESTS=1` and will keep pytest markers deselected (`modal`, `integration`, `postgres`, `provider_eval`).

Credentials in `.env` do not imply permission.

## Run

Backend (required unless the user scoped frontend-only):

```bash
backend/.venv/bin/python -m pytest --ignore=tests/evals
```

Frontend if UI files are in play:

```bash
pnpm -C frontend check
```

Do not run `tests/evals`.

## Report

- Exact commands
- Confirmation that external integrations were excluded
- Pass / fail
- Any skipped integration/postgres/modal tests
