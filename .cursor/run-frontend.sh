#!/usr/bin/env bash
# Agent Arena frontend (Vite dev server), port 3000.
#
# Points at the local backend by default so the SPA exercises this VM's API;
# override VITE_MODAL_URL to target a deployed backend instead.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT/frontend"
export VITE_MODAL_URL="${VITE_MODAL_URL:-http://localhost:8000}"

exec pnpm dev --host 0.0.0.0 --port 3000
