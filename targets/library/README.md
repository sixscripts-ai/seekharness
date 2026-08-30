# Agent Arena Target Library (v1)

This directory contains verified multi-file target packages for the Agent Arena benchmark.

---

## Target Specification

Each target directory contains:

```
targets/library/<target-id>/
├── target.yaml          # Canonical target manifest (spec version 1)
├── README.md            # Target overview and mission brief
├── starter/             # Base workspace provided to fighters
└── tests/visible/       # Tests exposed to the agent in its workspace

targets/evaluators/<target-id>/   # gitignored private package
├── tests/hidden/        # Evaluator-only tests
├── reference/           # Reference solution (verifier only)
└── tests/*.py           # Other evaluator fixtures (e.g. breaker harness)
```

---

## 10 Initial Target Packages

| Target ID | Name | Category | Difficulty | Format | Runtime | Description |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `authentication-gate` | Authentication Gate | Security | Advanced | Builder/Breaker | Python 3.11 + FastAPI | FastAPI auth gate with JWT and rate limiting |
| `broken-package-recovery` | Broken Package Recovery | Debugging | Novice | Solo | Node.js 22 | Corrupted package manifest & dependency tree recovery |
| `makefile-from-hell` | Makefile from Hell | Systems | Expert | Solo | Linux GCC / Make | Broken incremental C build system with missing dependency tracking |
| `migration-disaster` | Migration Disaster | Data | General | Solo | Python 3.11 + SQLite | Inconsistent database schema migration repair |
| `poisoned-instructions` | Poisoned Instructions | Security | Advanced | Adversarial Agent | Python 3.11 | Instruction injection defense in an automated agent pipeline |
| `readme-lied` | README Lied | Engineering | General | Solo | Python 3.11 | Misleading documentation vs actual configuration bug repair |
| `red-herring-repository` | Red Herring Repository | Architecture | Expert | Solo | Python 3.11 | Large codebase with deceptive dead code and root cause bug |
| `session-replay-defense` | Session Replay Defense | Security | Advanced | Builder/Breaker | Python 3.11 | Replay attack defense and nonce verification |
| `sql-login-service` | SQL Login Service | Security | General | Builder/Breaker | Python 3.11 + SQLite | SQL injection defense and secure authentication |
| `tinyshop` | TinyShop CTF | Security | Novice | CTF | Python 3.11 | Multi-tier CTF shop vulnerability identification |

---

## Security & Evaluator Separation Rules

1. **Fighter Workspace**:
   - Only `starter/` and `tests/visible/` are materialized into the agent's workspace.
   - `tests/hidden/` and `reference/` live only under `targets/evaluators/` or `$ARENA_EVALUATOR_DIR` and are **never** mounted or accessible in fighter workspaces.
2. **Builder → Breaker Handoff**:
   - Builder writes artifacts to its workspace.
   - The orchestrator captures only paths explicitly listed in `workspace.handoff_allowlist`.
   - The Builder workspace is completely destroyed (`rm -rf`).
   - The Breaker receives a clean workspace containing only allowlisted artifacts.
3. **Trusted Verification**:
   - Verification runs in an isolated container/workspace outside the agent's reach.
   - Verifier runs `verification.visible_command` and `verification.hidden_command`.
   - Returns structured `TargetVerificationEvidence` with exit codes, outputs, and hashes.

---

## Validation

Run pack validation across all 10 targets:

```bash
cd backend && uv run python ../targets/library/scripts/validate_pack.py
```
