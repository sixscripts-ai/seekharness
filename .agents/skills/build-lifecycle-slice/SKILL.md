---
name: build-lifecycle-slice
description: >
  Use this skill when implementing a vertical slice across the SeekHarness battle lifecycle.
  Enforces single vertical slice discipline across backend, target, verifier, and frontend
  with the 4-tier evidence ladder: IMPLEMENTED, WIRED, TESTED, LIVE_OBSERVED.
license: MIT
compatibility: Requires Python 3.10+ and seekharness-dev CLI
metadata:
  author: villain
  version: "1.0"
allowed-tools: Bash(pytest:*) Bash(seekharness-dev:*) Read
---

# Build Lifecycle Slice

## Overview

`build-lifecycle-slice` enforces disciplined vertical-slice engineering across the SeekHarness battle lifecycle. Rather than writing broad horizontal layers that remain untested, this skill guides implementation through four progressive evidence tiers: `IMPLEMENTED`, `WIRED`, `TESTED`, and `LIVE_OBSERVED`.

## Instructions

1. **Select the Active Slice**:
   Run orientation or inspect slice status to select the single boundary under development:
   ```bash
   ./scripts/check_slice.py --boundary semantic_verification
   ```

2. **Advance to `IMPLEMENTED`**:
   - Write the core logic in `backend/agent_arena/` or targets.
   - Run syntax checks and isolated unit tests.
   - Ensure all public functions have strict type annotations.

3. **Advance to `WIRED`**:
   - Wire the implementation into the relevant routers, models, or runner dispatchers.
   - Run `check_slice.py` to verify no required glue files are missing.

4. **Advance to `TESTED`**:
   - Write negative test cases covering timeouts, malformed requests, and invalid state transitions.
   - Run focused pytest on the boundary:
     ```bash
     pytest backend/tests/test_<boundary_name>.py
     ```

5. **Advance to `LIVE_OBSERVED`**:
   - Verify that the slice runs end-to-end without unhandled exceptions or state leakage.
   - Confirm with `./scripts/check_slice.py --boundary <name>`.

## Available Scripts

- **`scripts/check_slice.py`** — Evaluates one or all boundaries against the 4-tier evidence ladder. Supports `--boundary <name>`, `--all`, and `--json`.

## Gotchas

- Never proceed to advance a secondary boundary while the current boundary remains unverified (`PENDING`).
- Slices must preserve backwards compatibility with existing database migrations and API schemas.
- Do not mark a slice `LIVE_OBSERVED` based solely on code review; run actual tests.

## Examples

### Check Single Boundary Maturity
```bash
$ ./scripts/check_slice.py --boundary service_lifecycle
==================================================
 SLICE MATURITY EVALUATION: service_lifecycle
==================================================
Highest Evidence Tier : LIVE_OBSERVED
  [ACHIEVED] Tier: IMPLEMENTED
  [ACHIEVED] Tier: WIRED
  [ACHIEVED] Tier: TESTED
  [ACHIEVED] Tier: LIVE_OBSERVED
==================================================
```

### Check All Boundaries
```bash
$ ./scripts/check_slice.py --all
[IMPLEMENTED  ] semantic_verification
[LIVE_OBSERVED] battle_db
[LIVE_OBSERVED] service_lifecycle
[LIVE_OBSERVED] breaker_handoff
[LIVE_OBSERVED] trusted_completion
```

## References

- Read [`references/REFERENCE.md`](references/REFERENCE.md) when defining new evidence criteria or reviewing lifecycle progression rules.
