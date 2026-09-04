---
name: filesystem-path-auditor
description: >
  Analyze how paths are constructed, normalized, resolved, copied, linked, mounted, and constrained across filesystem boundaries. Use this skill when diagnosing security/filesystem or when seeing signals: symlink, path traversal, path normalization, filesystem, cwd, mount, workspace.
license: MIT
compatibility: No special requirements
metadata:
  author: sixscripts-ai
  version: "1.0.0"
  context_cost: "large"
  roles: "general, builder, breaker"
  runtimes: "*"
---

# Filesystem Path Auditor

## Overview

Analyze how paths are constructed, normalized, resolved, copied, linked, mounted, and constrained across filesystem boundaries.

- **Primary Index**: `security/filesystem`
- **Context Cost**: `large`
- **Applicable Roles**: `general, builder, breaker`

### Graph Indexes
- `security/filesystem`
- `runtime/workspaces`
- `artifacts/workspaces`
- `security/trust-boundaries`

### Suggested Foundations
- None

## Step-by-Step Instructions

1. **Observe and Collect Baseline**:
   - Inspect visible logs, test outputs, or error traces without modifying code.
   - Run `TOOL read`, `TOOL grep`, or `TOOL ls` to understand the current workspace state.

2. **Formulate Hypotheses**:
   - Match symptoms against domain patterns for `security/filesystem`.
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

- `artifact-workspace-versioning`
- `secure-code-execution`
- `subprocess-command-debugger`
- `trust-boundary-auditor`
- `repository-cartographer`

## References

- Read [`references/REFERENCE.md`](references/REFERENCE.md) for deeper implementation patterns.
