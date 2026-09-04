---
name: failure-driven-replanning
description: >
  Use unsuccessful commands, tests, experiments, and attempted repairs as information for revising the current approach. Use this skill when diagnosing strategy/replanning or when seeing signals: replan, failed-attempt, contradictory evidence, recovery, feedback, adaptation.
license: MIT
compatibility: No special requirements
metadata:
  author: sixscripts-ai
  version: "1.0.0"
  context_cost: "medium"
  roles: "general, builder, breaker"
  runtimes: "*"
---

# Failure Driven Replanning

## Overview

Use unsuccessful commands, tests, experiments, and attempted repairs as information for revising the current approach.

- **Primary Index**: `strategy/replanning`
- **Context Cost**: `medium`
- **Applicable Roles**: `general, builder, breaker`

### Graph Indexes
- `strategy/replanning`
- `debugging/failure-analysis`
- `strategy/hypothesis`

### Suggested Foundations
- None

## Step-by-Step Instructions

1. **Observe and Collect Baseline**:
   - Inspect visible logs, test outputs, or error traces without modifying code.
   - Run `TOOL read`, `TOOL grep`, or `TOOL ls` to understand the current workspace state.

2. **Formulate Hypotheses**:
   - Match symptoms against domain patterns for `strategy/replanning`.
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

- `hypothesis-driven-debugging`
- `failure-classifier`
- `minimal-reproduction-builder`
- `runtime-inspector`
- `technical-web-researcher`

## References

- Read [`references/REFERENCE.md`](references/REFERENCE.md) for deeper implementation patterns.
