---
name: minimal-reproduction-builder
description: >
  Reduce a complex failure to the smallest experiment, input, command, or execution path that still demonstrates the behavior. Use this skill when diagnosing debugging/reproduction or when seeing signals: minimal reproduction, repro case, isolate failure, experiment, testcase, reduce.
license: MIT
compatibility: No special requirements
metadata:
  author: sixscripts-ai
  version: "1.0.0"
  context_cost: "medium"
  roles: "general, builder, breaker"
  runtimes: "*"
---

# Minimal Reproduction Builder

## Overview

Reduce a complex failure to the smallest experiment, input, command, or execution path that still demonstrates the behavior.

- **Primary Index**: `debugging/reproduction`
- **Context Cost**: `medium`
- **Applicable Roles**: `general, builder, breaker`

### Graph Indexes
- `debugging/reproduction`
- `testing/verification`
- `strategy/hypothesis`

### Suggested Foundations
- None

## Step-by-Step Instructions

1. **Observe and Collect Baseline**:
   - Inspect visible logs, test outputs, or error traces without modifying code.
   - Run `TOOL read`, `TOOL grep`, or `TOOL ls` to understand the current workspace state.

2. **Formulate Hypotheses**:
   - Match symptoms against domain patterns for `debugging/reproduction`.
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
- `regression-test-designer`
- `edge-case-hunter`
- `concurrency-race-debugger`

## References

- Read [`references/REFERENCE.md`](references/REFERENCE.md) for deeper implementation patterns.
