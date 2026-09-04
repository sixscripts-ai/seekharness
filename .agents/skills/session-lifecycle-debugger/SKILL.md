---
name: session-lifecycle-debugger
description: >
  Trace session creation, binding, freshness, rotation, expiry, invalidation, storage, and reuse across requests. Use this skill when diagnosing backend/sessions or when seeing signals: session lifecycle, session invalidation, token rotation, expiry, freshness, session, cookie.
license: MIT
compatibility: No special requirements
metadata:
  author: sixscripts-ai
  version: "1.0.0"
  context_cost: "large"
  roles: "general, builder, breaker"
  runtimes: "*"
---

# Session Lifecycle Debugger

## Overview

Trace session creation, binding, freshness, rotation, expiry, invalidation, storage, and reuse across requests.

- **Primary Index**: `backend/sessions`
- **Context Cost**: `large`
- **Applicable Roles**: `general, builder, breaker`

### Graph Indexes
- `backend/sessions`
- `security/replay`
- `debugging/state`

### Suggested Foundations
- None

## Step-by-Step Instructions

1. **Observe and Collect Baseline**:
   - Inspect visible logs, test outputs, or error traces without modifying code.
   - Run `TOOL read`, `TOOL grep`, or `TOOL ls` to understand the current workspace state.

2. **Formulate Hypotheses**:
   - Match symptoms against domain patterns for `backend/sessions`.
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

- `auth-flow-debugger`
- `session-replay-attacker`
- `state-flow-debugger`
- `idempotency-auditor`
- `trust-boundary-auditor`

## References

- Read [`references/REFERENCE.md`](references/REFERENCE.md) for deeper implementation patterns.
