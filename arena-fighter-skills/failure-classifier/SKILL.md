---
name: failure-classifier
description: >
  Classify an observed failure by likely layer and mechanism before committing to a repair strategy. Use this skill when diagnosing debugging/failure-analysis or when seeing signals: failure classification, infrastructure failure, environment failure, dependency failure, configuration failure, runtime failure.
license: MIT
compatibility: No special requirements
metadata:
  author: sixscripts-ai
  version: "1.0.0"
  context_cost: "small"
  roles: "general, builder, breaker"
  runtimes: "*"
---

# Failure Classifier

## Overview

Classify an observed failure by likely layer and mechanism before committing to a repair strategy.

- **Primary Index**: `debugging/failure-analysis`
- **Context Cost**: `small`
- **Applicable Roles**: `general, builder, breaker`

### Graph Indexes
- `debugging/failure-analysis`
- `runtime/dependencies`
- `testing/verification`

### Suggested Foundations
- None

## Step-by-Step Instructions

1. **Observe and Collect Baseline**:
   - Inspect visible logs, test outputs, or error traces without modifying code.
   - Run `TOOL read`, `TOOL grep`, or `TOOL ls` to understand the current workspace state.

2. **Formulate Hypotheses**:
   - Match symptoms against domain patterns for `debugging/failure-analysis`.
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

- `traceback-triage`
- `runtime-inspector`
- `dependency-doctor`
- `configuration-auditor`
- `failure-driven-replanning`

## References

- Read [`references/REFERENCE.md`](references/REFERENCE.md) for deeper implementation patterns.
