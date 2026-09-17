---
name: auth-flow-debugger
description: >
  Trace identity from credential presentation through verification, identity establishment, token/session creation, and later authentication checks. Use this skill when diagnosing backend/authentication or when seeing signals: authentication flow, credential verification, identity establishment, token, login, authentication, principal.
license: MIT
compatibility: No special requirements
metadata:
  author: sixscripts-ai
  version: "1.0.0"
  context_cost: "large"
  roles: "general, builder, breaker"
  runtimes: "*"
---

# Auth Flow Debugger

## Overview

Trace identity from credential presentation through verification, identity establishment, token/session creation, and later authentication checks.

- **Primary Index**: `backend/authentication`
- **Context Cost**: `large`
- **Applicable Roles**: `general, builder, breaker`

### Graph Indexes
- `backend/authentication`
- `security/authentication`
- `debugging/state`

### Suggested Foundations
- None

## Step-by-Step Instructions

1. **Observe and Collect Baseline**:
   - Inspect visible logs, test outputs, or error traces without modifying code.
   - Run `TOOL read`, `TOOL grep`, or `TOOL ls` to understand the current workspace state.

2. **Formulate Hypotheses**:
   - Match symptoms against domain patterns for `backend/authentication`.
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
- `authorization-boundary-auditor`
- `trust-boundary-auditor`
- `state-flow-debugger`
- `api-contract-auditor`

## References

- Read [`references/REFERENCE.md`](references/REFERENCE.md) for deeper implementation patterns.
