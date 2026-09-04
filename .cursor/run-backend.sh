#!/usr/bin/env bash
# Agent Arena backend (FastAPI on uvicorn), port 8000.
#
# Reads config from the repo-root .env (loaded by agent_arena.config) plus any
# Cloud Agent secret env vars. Defaults to the in-process mock battle runner
# (ARENA_USE_MOCK=1) because a Cloud Agent has no Modal sandbox / host model
# keys; export ARENA_USE_MOCK=0 to use the real sandbox launcher instead.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT/backend"
export PATH="$HOME/.local/bin:$PATH"
export PERSISTENCE_BACKEND="${PERSISTENCE_BACKEND:-postgres}"
export ARENA_USE_MOCK="${ARENA_USE_MOCK:-1}"

exec .venv/bin/python -m uvicorn agent_arena.main:app --host 0.0.0.0 --port 8000
