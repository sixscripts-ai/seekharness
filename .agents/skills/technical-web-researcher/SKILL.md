---
name: technical-web-researcher
description: >
  Search and navigate public technical sources to fill knowledge gaps about APIs, commands, packages, errors, specifications, and implementation techniques. Use this skill when diagnosing investigation/web-research or when seeing signals: technical documentation, error reference, package documentation, web research, specification, command lookup.
license: MIT
compatibility: No special requirements
metadata:
  author: sixscripts-ai
  version: "1.0.0"
  context_cost: "medium"
  roles: "general, builder, breaker"
  runtimes: "*"
---

# Technical Web Researcher

## Overview

Search and navigate public technical sources to fill knowledge gaps about APIs, commands, packages, errors, specifications, and implementation techniques.

- **Primary Index**: `investigation/web-research`
- **Context Cost**: `medium`
- **Applicable Roles**: `general, builder, breaker`

### Graph Indexes
- `investigation/web-research`
- `runtime/documentation`
- `interface/browser`
- `strategy/evidence`

### Suggested Foundations
- None

## Step-by-Step Instructions

1. **Observe and Collect Baseline**:
   - Inspect visible logs, test outputs, or error traces without modifying code.
   - Run `TOOL read`, `TOOL grep`, or `TOOL ls` to understand the current workspace state.

2. **Formulate Hypotheses**:
   - Match symptoms against domain patterns for `investigation/web-research`.
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

- `evidence-before-editing`
- `dependency-doctor`
- `runtime-inspector`
- `authority-source-finder`
- `configuration-auditor`

## References

- Read [`references/REFERENCE.md`](references/REFERENCE.md) for deeper implementation patterns.
