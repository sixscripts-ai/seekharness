---
name: compiler-linker-debugger
description: >
  Diagnose compilation and linking across flags, symbols, headers, object files, libraries, ABI expectations, and emitted artifacts. Use this skill when diagnosing build/compiler or when seeing signals: undefined symbol, linker error, compiler flag, gcc, header, object file, library.
license: MIT
compatibility: No special requirements
metadata:
  author: sixscripts-ai
  version: "1.0.0"
  context_cost: "medium"
  roles: "general, builder, breaker"
  runtimes: "c, cpp, *"
---

# Compiler Linker Debugger

## Overview

Diagnose compilation and linking across flags, symbols, headers, object files, libraries, ABI expectations, and emitted artifacts.

- **Primary Index**: `build/compiler`
- **Context Cost**: `medium`
- **Applicable Roles**: `general, builder, breaker`

### Graph Indexes
- `build/compiler`
- `runtime/processes`
- `investigation/dependencies`

### Suggested Foundations
- None

## Step-by-Step Instructions

1. **Observe and Collect Baseline**:
   - Inspect visible logs, test outputs, or error traces without modifying code.
   - Run `TOOL read`, `TOOL grep`, or `TOOL ls` to understand the current workspace state.

2. **Formulate Hypotheses**:
   - Match symptoms against domain patterns for `build/compiler`.
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

- `build-system-debugger`
- `makefile-debugger`
- `dependency-tracer`
- `subprocess-command-debugger`
- `runtime-inspector`

## References

- Read [`references/REFERENCE.md`](references/REFERENCE.md) for deeper implementation patterns.
