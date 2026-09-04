---
name: repository-cartographer
description: >
  Construct an execution-oriented map of an unfamiliar codebase, its important structure, entrypoints, tests, configuration, dependencies, and artifacts. Use this skill when diagnosing investigation/repository or when seeing signals: repository structure, codebase map, module ownership, architecture, directories, entrypoints.
license: MIT
compatibility: No special requirements
metadata:
  author: sixscripts-ai
  version: "1.0.0"
  context_cost: "medium"
  roles: "general, builder, breaker"
  runtimes: "*"
---

# Repository Cartographer

## Overview

Construct an execution-oriented map of an unfamiliar codebase, its important structure, entrypoints, tests, configuration, dependencies, and artifacts.

- **Primary Index**: `investigation/repository`
- **Context Cost**: `medium`
- **Applicable Roles**: `general, builder, breaker`

### Graph Indexes
- `investigation/repository`
- `investigation/entrypoints`
- `artifacts/workspaces`

### Suggested Foundations
- None

## Step-by-Step Instructions

1. **Observe and Collect Baseline**:
   - Inspect visible logs, test outputs, or error traces without modifying code.
   - Run `TOOL read`, `TOOL grep`, or `TOOL ls` to understand the current workspace state.

2. **Formulate Hypotheses**:
   - Match symptoms against domain patterns for `investigation/repository`.
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

- `entrypoint-tracer`
- `dependency-tracer`
- `test-surface-mapper`
- `configuration-auditor`
- `git-history-forensics`

## References

- Read [`references/REFERENCE.md`](references/REFERENCE.md) for deeper implementation patterns.
