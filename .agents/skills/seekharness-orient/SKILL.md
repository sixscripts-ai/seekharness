---
name: seekharness-orient
description: >
  Use this skill to determine the current state of SeekHarness and identify the single
  next engineering boundary before starting work. Runs seekharness-dev preflight and
  lifecycle status to inspect environment health, database migrations, and battle boundaries.
license: MIT
compatibility: Requires Python 3.10+ and seekharness-dev CLI
metadata:
  author: villain
  version: "1.0"
allowed-tools: Bash(seekharness-dev:*) Read
---

# SeekHarness Orient

## Overview

`seekharness-orient` provides deterministic preflight and architectural orientation for SeekHarness. It evaluates the environment, checks database migration state, inspects the battle lifecycle stages, and reports the exact next uncompleted engineering boundary without guessing.

## Instructions

1. **Execute Orientation Script**:
   Run the bundled orientation script or use `seekharness-dev` directly:
   ```bash
   ./scripts/orient.py
   ```
   Or for machine-readable JSON:
   ```bash
   ./scripts/orient.py --json
   ```

2. **Evaluate Preflight Status**:
   - Check if backend virtualenv and frontend dependencies are available.
   - Check if git working tree contains uncommitted changes.
   - If any core environment check is marked `FAILED`, resolve it before modifying code.

3. **Identify Active Boundary**:
   - Read the `Next Active Boundary` section.
   - The boundaries follow a strict order:
     1. `semantic_verification`
     2. `battle_db`
     3. `service_lifecycle`
     4. `breaker_handoff`
     5. `trusted_completion`
   - Pick ONLY the first boundary reporting `PARTIAL`, `MISSING`, or `FAILED`.

4. **Select Next Action**:
   - If `semantic_verification` is `PARTIAL`: run `pytest backend/tests/test_builder_breaker_semantic_verification.py` to inspect missing components.
   - If `battle_db` is `PARTIAL`: check Neon branch manager tests.
   - If all boundaries are `VERIFIED`: seek next user directive or run full regression.

## Available Scripts

- **`scripts/orient.py`** — Executes `seekharness-dev preflight` and `seekharness-dev lifecycle`, formats output, and computes the next active boundary. Supports `--json`.

## Gotchas

- Never guess at architecture: if a module or test is missing, report `UNKNOWN` or `PARTIAL`.
- Do not run slow integration suites during orientation; preflight must finish in under 1 second.
- Local PostgreSQL and Appwrite checks report warning if ports are inactive, but do not block unit tests.

## Examples

### Text Output
```bash
$ ./scripts/orient.py
==================================================
           SEEKHARNESS ORIENTATION                
==================================================
Preflight Status: OK
Lifecycle Boundaries:
  - Semantic Verification & Target Guard       : VERIFIED
  - Battle DB & Ephemeral Branch Isolation     : VERIFIED
  - Service Lifecycle & Sandbox Reaper         : PARTIAL
Next Active Boundary:
  Stage ID   : service_lifecycle
  Stage Name : Service Lifecycle & Sandbox Reaper
  Status     : PARTIAL
  Action     : Boundary 'service_lifecycle' is currently PARTIAL and requires certification.
==================================================
```

### JSON Output
```bash
$ ./scripts/orient.py --json | jq .next_boundary
{
  "stage": "service_lifecycle",
  "name": "Service Lifecycle & Sandbox Reaper",
  "status": "PARTIAL",
  "reason": "Boundary 'service_lifecycle' is currently PARTIAL and requires certification."
}
```

## References

- Read [`references/REFERENCE.md`](references/REFERENCE.md) when seeking details on the 5 core boundaries or preflight health invariants.
