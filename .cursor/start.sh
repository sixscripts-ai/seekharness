#!/usr/bin/env bash
# Per-boot reconciliation for Agent Arena.
#
# When a Postgres DATABASE_URL is available (injected as a Cloud Agent secret),
# bring the schema and playable formats up to date so the backend is usable the
# moment its terminal starts. Both operations are idempotent:
#   - `alembic upgrade head` is a no-op when already at head.
#   - the format seed upserts the 8 git source-of-truth formats.
#
# With no DATABASE_URL the app still boots (GET /health only needs the public
# Appwrite endpoint/project id); this step simply no-ops so start still returns.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"
export PATH="$HOME/.local/bin:$PATH"

# Load the repo-root .env into this shell so DATABASE_URL / PERSISTENCE_BACKEND
# set there are visible, without tripping on '&' in connection strings.
if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1090
  eval "$(backend/.venv/bin/python - <<'PY'
import shlex
from pathlib import Path
for line in Path(".env").read_text().splitlines():
    line = line.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    k, v = line.split("=", 1)
    print(f"export {k}={shlex.quote(v)}")
PY
)"
  set +a
fi

PERSISTENCE_BACKEND="${PERSISTENCE_BACKEND:-postgres}"
if [ "$PERSISTENCE_BACKEND" = "postgres" ] && [ -n "${DATABASE_URL:-}" ]; then
  echo "[start] applying database migrations..."
  ( cd backend && .venv/bin/python -m alembic upgrade head )
  echo "[start] seeding playable formats..."
  ( cd backend && .venv/bin/python -m scripts.seed_formats_postgres )
else
  echo "[start] DATABASE_URL not set (or non-postgres); skipping migrations/seed."
fi

echo "[start] done."
