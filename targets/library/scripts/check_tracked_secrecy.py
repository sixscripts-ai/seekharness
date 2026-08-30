#!/usr/bin/env python3
"""Fail if the git index tracks evaluator-private material.

Hermetic: uses only `git ls-files`. No network, no provider APIs.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]


def _listed(path: str) -> list[str]:
    return [
        line.strip()
        for line in subprocess.check_output(
            ["git", "ls-files", path],
            cwd=REPO_ROOT,
            text=True,
        ).splitlines()
        if line.strip()
    ]


def main() -> int:
    leaked: list[str] = []
    for path in _listed("targets/library"):
        posix = path.replace("\\", "/")
        if "/tests/hidden/" in posix:
            leaked.append(path)
        elif "/reference/" in posix:
            leaked.append(path)
        elif posix.endswith("/tests/breaker_harness.py") or posix.endswith(
            "tests/breaker_harness.py"
        ):
            leaked.append(path)

    evaluators = _listed("targets/evaluators")
    allowed = {"targets/evaluators/.gitkeep"}
    extra = [path for path in evaluators if path not in allowed]
    leaked.extend(extra)

    if leaked:
        print("tracked private evaluator paths:", file=sys.stderr)
        for path in leaked:
            print(f"  {path}", file=sys.stderr)
        return 1
    print("ok: no tracked private evaluator paths")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
