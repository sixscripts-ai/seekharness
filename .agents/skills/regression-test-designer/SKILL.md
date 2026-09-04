---
name: regression-test-designer
description: >
  Design focused tests that demonstrate a defect, protect intended repaired behavior, and avoid overfitting to one implementation. Use this skill when diagnosing testing/regression or when seeing signals: regression test, before after proof, behavioral assertion, test design, coverage, assertion.
license: MIT
compatibility: No special requirements
metadata:
  author: sixscripts-ai
  version: "1.0.0"
  context_cost: "medium"
  roles: "general, builder"
  runtimes: "*"
---

# Regression Test Designer

## Overview

Design focused tests that demonstrate a defect, protect intended repaired behavior, and avoid overfitting to one implementation.

- **Primary Index**: `testing/regression`
- **Context Cost**: `medium`
- **Applicable Roles**: `general, builder`

### Graph Indexes
- `testing/regression`
- `testing/verification`
- `strategy/evidence`

### Suggested Foundations
- None

## Step-by-Step Instructions

1. **Observe and Collect Baseline**:
   - Inspect visible logs, test outputs, or error traces without modifying code.
   - Run `TOOL read`, `TOOL grep`, or `TOOL ls` to understand the current workspace state.

2. **Formulate Hypotheses**:
   - Match symptoms against domain patterns for `testing/regression`.
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

- `minimal-reproduction-builder`
- `test-surface-mapper`
- `minimal-change-repair`
- `edge-case-hunter`
- `evidence-before-editing`

## References

- Read [`references/REFERENCE.md`](references/REFERENCE.md) for deeper implementation patterns.
