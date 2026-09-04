---
name: subprocess-command-debugger
description: >
  Diagnose process-launch behavior including executable resolution, arguments, quoting, working directory, environment, pipes, signals, and exit status. Use this skill when diagnosing runtime/processes or when seeing signals: subprocess, exit code, PATH resolution, command, cwd, environment, pipe, signal.
license: MIT
compatibility: No special requirements
metadata:
  author: sixscripts-ai
  version: "1.0.0"
  context_cost: "medium"
  roles: "general, builder, breaker"
  runtimes: "*"
---

# Subprocess Command Debugger

## Overview

Diagnose process-launch behavior including executable resolution, arguments, quoting, working directory, environment, pipes, signals, and exit status.

- **Primary Index**: `runtime/processes`
- **Context Cost**: `medium`
- **Applicable Roles**: `general, builder, breaker`

### Graph Indexes
- `runtime/processes`
- `debugging/failure-analysis`
- `security/code-execution`

### Suggested Foundations
- None

## Step-by-Step Instructions

1. **Observe and Collect Baseline**:
   - Inspect visible logs, test outputs, or error traces without modifying code.
   - Run `TOOL read`, `TOOL grep`, or `TOOL ls` to understand the current workspace state.

2. **Formulate Hypotheses**:
   - Match symptoms against domain patterns for `runtime/processes`.
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

- `runtime-inspector`
- `secure-code-execution`
- `filesystem-path-auditor`
- `configuration-auditor`
- `traceback-triage`

## References

- Read [`references/REFERENCE.md`](references/REFERENCE.md) for deeper implementation patterns.
