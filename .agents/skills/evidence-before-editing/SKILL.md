---
name: evidence-before-editing
description: >
  Establish what the repository and runtime are actually doing before relying on assumptions about the defect. Use this skill when diagnosing strategy/evidence or when seeing signals: evidence, baseline, observe, inspect, verify, diagnosis.
license: MIT
compatibility: No special requirements
metadata:
  author: sixscripts-ai
  version: "1.0.0"
  context_cost: "small"
  roles: "general, builder, breaker"
  runtimes: "*"
---

# Evidence Before Editing

## Overview

Establish what the repository and runtime are actually doing before relying on assumptions about the defect.

- **Primary Index**: `strategy/evidence`
- **Context Cost**: `small`
- **Applicable Roles**: `general, builder, breaker`

### Graph Indexes
- `strategy/evidence`
- `investigation/repository`
- `testing/verification`

### Suggested Foundations
- None

## Step-by-Step Instructions

1. **Observe and Collect Baseline**:
   - Inspect visible logs, test outputs, or error traces without modifying code.
   - Run `TOOL read`, `TOOL grep`, or `TOOL ls` to understand the current workspace state.

2. **Formulate Hypotheses**:
   - Match symptoms against domain patterns for `strategy/evidence`.
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

- `test-surface-mapper`
- `runtime-inspector`
- `authority-source-finder`
- `technical-web-researcher`
- `regression-test-designer`

## References

- Read [`references/REFERENCE.md`](references/REFERENCE.md) for deeper implementation patterns.
