#!/usr/bin/env python3
"""Preview findings.v1.json ingest via agent_arena.evidence.

No second validator. Calls build_phase_result with the file in EXECUTOR_RESULT
files, matching Battle ingest.

Usage (from repo root):
    backend/.venv/bin/python \\
      .agents/plugins/arena-ops/skills/develop-finding/scripts/normalize_findings.py \\
      [scratch/findings.v1.json]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[6]
_BACKEND = _REPO / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from agent_arena.evidence import FINDINGS_ARTIFACT, build_phase_result  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    path = Path(args[0] if args else "scratch/findings.v1.json")
    if not path.is_file():
        print(json.dumps({"error": "missing_file", "path": str(path)}), file=sys.stderr)
        return 2
    raw = path.read_text(encoding="utf-8")
    phase = build_phase_result(
        {
            "outcome": "COMPLETED",
            "files": {FINDINGS_ARTIFACT: raw},
        }
    )
    print(
        json.dumps(
            {
                "path": str(path),
                "findings_ingest": phase["findings_ingest"],
                "findings": phase["findings"],
            },
            indent=2,
        )
    )
    ingest = phase["findings_ingest"]
    if ingest == "valid":
        return 0
    if ingest == "absent":
        return 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
