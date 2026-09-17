---
name: input-validation-auditor
description: >
  Analyze parsing, normalization, validation, canonicalization, type, range, and format assumptions at input boundaries. Use this skill when diagnosing security/input-validation or when seeing signals: input validation, canonicalization, normalization, parser, malformed, type check, range.
license: MIT
compatibility: No special requirements
metadata:
  author: sixscripts-ai
  version: "1.0.0"
  context_cost: "medium"
  roles: "general, builder, breaker"
  runtimes: "*"
---

# Input Validation Auditor

## Overview

Analyze parsing, normalization, validation, canonicalization, type, range, and format assumptions at input boundaries.

- **Primary Index**: `security/input-validation`
- **Context Cost**: `medium`
- **Applicable Roles**: `general, builder, breaker`

### Graph Indexes
- `security/input-validation`
- `backend/api`
- `debugging/edge-cases`

### Suggested Foundations
- None

## Step-by-Step Instructions

1. **Observe and Collect Baseline**:
   - Inspect visible logs, test outputs, or error traces without modifying code.
   - Run `TOOL read`, `TOOL grep`, or `TOOL ls` to understand the current workspace state.

2. **Formulate Hypotheses**:
   - Match symptoms against domain patterns for `security/input-validation`.
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

- `injection-tester`
- `api-contract-auditor`
- `edge-case-hunter`
- `trust-boundary-auditor`
- `browser-ui-debugger`

## References

- Read [`references/REFERENCE.md`](references/REFERENCE.md) for deeper implementation patterns.
