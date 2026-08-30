#!/bin/sh
# sessionEnd side effect only. Cursor ignores hook output for this event.
cat >/dev/null
cd "${CURSOR_PROJECT_DIR:-.}" || exit 0
echo "=== session-end git status --short ==="
git status --short
echo "=== session-end git diff --check ==="
git diff --check || true
exit 0
