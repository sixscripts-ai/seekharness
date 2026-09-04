#!/usr/bin/env bash
# Idempotent Cloud Agent bootstrap for Agent Arena.
#
# Prepares both services against the checked-out source:
#   - uv (Python package manager) + backend venv with backend[dev]
#   - frontend pnpm dependencies
#   - a non-secret repo-root .env scaffold (from .env.example) with a
#     generated FERNET_KEY, so the backend can import without hand-editing.
#
# It must terminate and be safe to re-run. It never starts servers, runs
# migrations, or requires any secret. Secrets (DATABASE_URL, APPWRITE_API_KEY,
# HOST_* keys, JUDGE_MODAL_*) are injected as Cloud Agent env vars at runtime.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

# --- uv -------------------------------------------------------------------
if ! command -v uv >/dev/null 2>&1; then
  export PATH="$HOME/.local/bin:$PATH"
  if ! command -v uv >/dev/null 2>&1; then
    echo "[install] installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
  fi
fi
export PATH="$HOME/.local/bin:$PATH"
uv --version

# --- backend venv + deps --------------------------------------------------
if [ ! -x backend/.venv/bin/python ]; then
  echo "[install] creating backend/.venv (python 3.12)..."
  uv venv backend/.venv --python 3.12
fi
echo "[install] installing backend[dev]..."
VIRTUAL_ENV="$REPO_ROOT/backend/.venv" uv pip install --python backend/.venv/bin/python -e "./backend[dev]"

# --- frontend deps --------------------------------------------------------
echo "[install] installing frontend deps..."
pnpm -C frontend install

# --- non-secret .env scaffold --------------------------------------------
if [ ! -f .env ]; then
  echo "[install] creating .env from .env.example..."
  cp .env.example .env
fi
# Generate a FERNET_KEY if the scaffold left it blank (needed to import/encrypt
# provider keys). This is a local dev key, never a committed secret.
if ! grep -qE '^FERNET_KEY=.+' .env; then
  FK="$(backend/.venv/bin/python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')"
  backend/.venv/bin/python - "$FK" <<'PY'
import re, sys
fk = sys.argv[1]
p = ".env"
s = open(p).read()
s = re.sub(r'^FERNET_KEY=.*$', 'FERNET_KEY=' + fk, s, flags=re.M)
open(p, "w").write(s)
print("[install] generated FERNET_KEY in .env")
PY
fi

echo "[install] done."
