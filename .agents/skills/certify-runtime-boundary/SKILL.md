---
name: certify-runtime-boundary
description: >
  Use this skill to certify a runtime boundary in SeekHarness before declaring a phase complete.
  Executes negative tests, invariant checks, schema validations, and regression suites to ensure
  zero silent failures or state corruptions.
license: MIT
compatibility: Requires Python 3.10+ and pytest
metadata:
  author: villain
  version: "1.0"
allowed-tools: Bash(pytest:*) Bash(seekharness-dev:*) Read
---

# Certify Runtime Boundary

## Overview

`certify-runtime-boundary` provides automated verification for critical SeekHarness runtime interfaces. It guarantees that an architectural boundary meets its functional requirements, correctly enforces security and isolation invariants, and rejects invalid inputs with deterministic negative test coverage.

## Instructions

1. **Select Boundary to Certify**:
   Choose from the five core SeekHarness boundaries:
   - `semantic_verification`
   - `battle_db`
   - `service_lifecycle`
   - `breaker_handoff`
   - `trusted_completion`

2. **Execute Certification**:
   Run the bundled certification script:
   ```bash
   ./scripts/certify.py --boundary battle_db
   ```
   Or verify all boundaries simultaneously:
   ```bash
   ./scripts/certify.py --all
   ```

3. **Analyze Results**:
   - `[CERTIFIED]`: All boundary tests passed cleanly.
   - `[UNVERIFIED]`: Either test files are missing or test assertions failed.

4. **Remediate Failures**:
   - If tests fail, inspect the stdout/stderr snippet.
   - Run the failing test in verbose mode using `backend/.venv/bin/pytest -v <test_path>`.
   - Re-run `./scripts/certify.py --boundary <name>` until certified.

## Available Scripts

- **`scripts/certify.py`** — Automates boundary invariant test runs and reports pass/fail certification status. Supports `--boundary <name>`, `--all`, and `--json`.

## Gotchas

- Certification requires the backend virtualenv at `backend/.venv/bin/pytest`.
- Never bypass a failing test with `@pytest.mark.skip` unless approved by user.
- Integration tests involving external networks must be mocked or executed in designated sandboxes.

## Examples

### Certify Specific Boundary
```bash
$ ./scripts/certify.py --boundary battle_db
==================================================
 BOUNDARY CERTIFICATION: battle_db
==================================================
Status       : CERTIFIED
Exit Code    : 0
Output       : .................. [100%]
18 passed in 0.57s
==================================================
```

### JSON Format for Automated Pipelines
```bash
$ ./scripts/certify.py --boundary battle_db --json | jq .certified
true
```

## References

- Read [`references/REFERENCE.md`](references/REFERENCE.md) when defining new invariants or adding negative tests to a boundary.
