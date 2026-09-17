---
name: defensive-builder
description: >
  Reason from explicit correctness and security invariants while constructing repairs or implementations that remain robust under adversarial use. Use this skill when diagnosing roles/builder or when seeing signals: defensive construction, security invariant, robust implementation, builder, hardening, defense.
license: MIT
compatibility: No special requirements
metadata:
  author: sixscripts-ai
  version: "1.0.0"
  context_cost: "large"
  roles: "builder"
  runtimes: "*"
---

# Defensive Builder

## Overview

Reason from explicit correctness and security invariants while constructing repairs or implementations that remain robust under adversarial use.

- **Primary Index**: `roles/builder`
- **Context Cost**: `large`
- **Applicable Roles**: `builder`

### Graph Indexes
- `roles/builder`
- `strategy/repair-style`
- `security/trust-boundaries`

### Suggested Foundations
- None

## Step-by-Step Instructions

1. **Observe and Collect Baseline**:
   - Inspect visible logs, test outputs, or error traces without modifying code.
   - Run `TOOL read`, `TOOL grep`, or `TOOL ls` to understand the current workspace state.

2. **Formulate Hypotheses**:
   - Match symptoms against domain patterns for `roles/builder`.
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

- `minimal-change-repair`
- `trust-boundary-auditor`
- `regression-test-designer`
- `authorization-boundary-auditor`
- `data-integrity-checker`

## References

- Read [`references/REFERENCE.md`](references/REFERENCE.md) for deeper implementation patterns.
