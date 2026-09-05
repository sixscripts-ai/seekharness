---
name: discover-evidence
description: Operator-only Evidence discovery. Orchestrates arena-ops domain reviews, then develop-finding.
---

# /discover-evidence

Invoke the arena-ops `discover-evidence` skill.

Do not mount this on Fighters. Do not modify Format artifacts.required. Do not write Official Result fields (`passed`, score, winner).

Run the manifest only: domain skills stage candidates; `develop-finding` is the sole writer of `scratch/findings.v1.json` (or an explicit operator path).

A Finding is Evidence if a Battle later has that file. It is never an Official Result. Severity never sets passed, score, or winner.

Do not write exploits, exploit PoCs, or attack procedures. Do not paste Hidden Evaluator contents. Do not print secrets.

## Report

- Domain skills run / skipped
- Candidate paths staged
- Finding artifact path (written by `develop-finding` only)
- Reminder: `findings_ingest` is absent until a Battle has `findings.v1.json` in EXECUTOR_RESULT files
