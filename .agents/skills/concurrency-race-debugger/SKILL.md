---
name: concurrency-race-debugger
description: >
  Analyze failures whose outcome depends on overlapping operations, scheduling, ordering, or shared mutable state. Use this skill when diagnosing debugging/concurrency or when seeing signals: race condition, interleaving, lost update, concurrency, lock, shared state, check then act.
license: MIT
compatibility: No special requirements
metadata:
  author: sixscripts-ai
  version: "1.0.0"
  context_cost: "large"
  roles: "general, builder, breaker"
  runtimes: "*"
---

# Concurrency Race Debugger

## Overview

Analyze failures whose outcome depends on overlapping operations, scheduling, ordering, or shared mutable state.

- **Primary Index**: `debugging/concurrency`
- **Context Cost**: `large`
- **Applicable Roles**: `general, builder, breaker`

### Graph Indexes
- `debugging/concurrency`
- `runtime/processes`
- `data/transactions`
- `testing/verification`

### Suggested Foundations
- None

## Step-by-Step Instructions

1. **Observe and Collect Baseline**:
   - Inspect visible logs, test outputs, or error traces without modifying code.
   - Run `TOOL read`, `TOOL grep`, or `TOOL ls` to understand the current workspace state.

2. **Formulate Hypotheses**:
   - Match symptoms against domain patterns for `debugging/concurrency`.
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

- `state-flow-debugger`
- `transaction-consistency-debugger`
- `async-control-flow-debugger`
- `idempotency-auditor`
- `minimal-reproduction-builder`

## References

- Read [`references/REFERENCE.md`](references/REFERENCE.md) for deeper implementation patterns.
