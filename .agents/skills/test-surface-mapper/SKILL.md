---
name: test-surface-mapper
description: >
  Determine what available tests execute, assert, and leave untested without assuming visible tests fully describe correct behavior. Use this skill when diagnosing testing/visible-tests or when seeing signals: test surface, visible tests, assertion coverage, harness, behavior contract, coverage.
license: MIT
compatibility: No special requirements
metadata:
  author: sixscripts-ai
  version: "1.0.0"
  context_cost: "medium"
  roles: "general, builder, breaker"
  runtimes: "*"
---

# Test Surface Mapper

## Overview

Determine what available tests execute, assert, and leave untested without assuming visible tests fully describe correct behavior.

- **Primary Index**: `testing/visible-tests`
- **Context Cost**: `medium`
- **Applicable Roles**: `general, builder, breaker`

### Graph Indexes
- `testing/visible-tests`
- `investigation/repository`
- `testing/verification`

### Suggested Foundations
- None

## Step-by-Step Instructions

1. **Observe and Collect Baseline**:
   - Inspect visible logs, test outputs, or error traces without modifying code.
   - Run `TOOL read`, `TOOL grep`, or `TOOL ls` to understand the current workspace state.

2. **Formulate Hypotheses**:
   - Match symptoms against domain patterns for `testing/visible-tests`.
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

- `regression-test-designer`
- `evidence-before-editing`
- `minimal-reproduction-builder`
- `api-contract-auditor`
- `edge-case-hunter`

## References

- Read [`references/REFERENCE.md`](references/REFERENCE.md) for deeper implementation patterns.
