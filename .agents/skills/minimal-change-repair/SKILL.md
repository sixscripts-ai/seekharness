---
name: minimal-change-repair
description: >
  Search for a compact repair that resolves the demonstrated defect while preserving unrelated behavior and interfaces. Use this skill when diagnosing strategy/repair-style or when seeing signals: minimal patch, regression surface, compatibility, repair, small change, preserve interface.
license: MIT
compatibility: No special requirements
metadata:
  author: sixscripts-ai
  version: "1.0.0"
  context_cost: "small"
  roles: "general, builder"
  runtimes: "*"
---

# Minimal Change Repair

## Overview

Search for a compact repair that resolves the demonstrated defect while preserving unrelated behavior and interfaces.

- **Primary Index**: `strategy/repair-style`
- **Context Cost**: `small`
- **Applicable Roles**: `general, builder`

### Graph Indexes
- `strategy/repair-style`
- `testing/regression`
- `roles/builder`

### Suggested Foundations
- None

## Step-by-Step Instructions

1. **Observe and Collect Baseline**:
   - Inspect visible logs, test outputs, or error traces without modifying code.
   - Run `TOOL read`, `TOOL grep`, or `TOOL ls` to understand the current workspace state.

2. **Formulate Hypotheses**:
   - Match symptoms against domain patterns for `strategy/repair-style`.
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

- `root-cause-first`
- `regression-test-designer`
- `defensive-builder`
- `api-contract-auditor`
- `data-integrity-checker`

## References

- Read [`references/REFERENCE.md`](references/REFERENCE.md) for deeper implementation patterns.
