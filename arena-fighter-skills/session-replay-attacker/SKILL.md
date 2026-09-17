---
name: session-replay-attacker
description: >
  Analyze token/session freshness, reuse, expiry, nonce binding, rotation, and cross-context replay weaknesses. Use this skill when diagnosing security/replay or when seeing signals: session replay, token reuse, nonce freshness, expiry, rotation, session, replay.
license: MIT
compatibility: No special requirements
metadata:
  author: sixscripts-ai
  version: "1.0.0"
  context_cost: "large"
  roles: "general, breaker"
  runtimes: "*"
---

# Session Replay Attacker

## Overview

Analyze token/session freshness, reuse, expiry, nonce binding, rotation, and cross-context replay weaknesses.

- **Primary Index**: `security/replay`
- **Context Cost**: `large`
- **Applicable Roles**: `general, breaker`

### Graph Indexes
- `security/replay`
- `backend/sessions`
- `security/authentication`

### Suggested Foundations
- None

## Step-by-Step Instructions

1. **Observe and Collect Baseline**:
   - Inspect visible logs, test outputs, or error traces without modifying code.
   - Run `TOOL read`, `TOOL grep`, or `TOOL ls` to understand the current workspace state.

2. **Formulate Hypotheses**:
   - Match symptoms against domain patterns for `security/replay`.
   - Separate verified facts from unverified assumptions.

3. **Verify with Targeted Probing**:
   - Execute targeted tests (`TOOL test`) or specific diagnostics.
   - Narrow down failure points before changing implementation logic.

4. **Apply Minimal Targeted Changes**:
   - Make small, localized edits using `TOOL write` preserving existing conventions.
   - Keep changes isolated to the required fix.

5. **Validate and Regression-Test**:
   - Re-run test suites with `TOOL test`.
   - Confirm the defect is resolved and no unrelated tests were broken.

## Gotchas & Failure Modes

- Avoid speculative refactoring before establishing reproducible evidence.
- Do not assume external network access is available unless explicitly permitted by the target.
- Path operations must stay within the assigned workspace.

## Related Skills

- `session-lifecycle-debugger`
- `auth-flow-debugger`
- `idempotency-auditor`
- `invariant-breaker`
- `exploit-evidence-builder`

## References

- Read [`references/REFERENCE.md`](references/REFERENCE.md) for deeper implementation patterns.
