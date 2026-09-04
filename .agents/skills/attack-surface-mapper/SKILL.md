---
name: attack-surface-mapper
description: >
  Enumerate externally influenceable interfaces, reachable operations, identities, resources, and trust transitions to identify meaningful attack paths. Use this skill when diagnosing security/attack-surface or when seeing signals: attack surface, reachable interface, entrypoint inventory, exploit surface, external input, boundary.
license: MIT
compatibility: No special requirements
metadata:
  author: sixscripts-ai
  version: "1.0.0"
  context_cost: "large"
  roles: "general, breaker"
  runtimes: "*"
---

# Attack Surface Mapper

## Overview

Enumerate externally influenceable interfaces, reachable operations, identities, resources, and trust transitions to identify meaningful attack paths.

- **Primary Index**: `security/attack-surface`
- **Context Cost**: `large`
- **Applicable Roles**: `general, breaker`

### Graph Indexes
- `security/attack-surface`
- `security/trust-boundaries`
- `roles/breaker`

### Suggested Foundations
- None

## Step-by-Step Instructions

1. **Observe and Collect Baseline**:
   - Inspect visible logs, test outputs, or error traces without modifying code.
   - Run `TOOL read`, `TOOL grep`, or `TOOL ls` to understand the current workspace state.

2. **Formulate Hypotheses**:
   - Match symptoms against domain patterns for `security/attack-surface`.
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

- `trust-boundary-auditor`
- `authorization-boundary-auditor`
- `invariant-breaker`
- `exploit-evidence-builder`
- `entrypoint-tracer`

## References

- Read [`references/REFERENCE.md`](references/REFERENCE.md) for deeper implementation patterns.
