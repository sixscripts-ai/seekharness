---
name: invariant-breaker
description: >
  Search for inputs, states, sequences, or boundary crossings that violate a claimed correctness or security invariant. Use this skill when diagnosing security/attack-surface or when seeing signals: break invariant, bypass condition, violate guarantee, adversarial, boundary, sequence.
license: MIT
compatibility: No special requirements
metadata:
  author: sixscripts-ai
  version: "1.0.0"
  context_cost: "large"
  roles: "general, breaker"
  runtimes: "*"
---

# Invariant Breaker

## Overview

Search for inputs, states, sequences, or boundary crossings that violate a claimed correctness or security invariant.

- **Primary Index**: `security/attack-surface`
- **Context Cost**: `large`
- **Applicable Roles**: `general, breaker`

### Graph Indexes
- `security/attack-surface`
- `roles/breaker`
- `debugging/edge-cases`

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

- `attack-surface-mapper`
- `edge-case-hunter`
- `authorization-boundary-auditor`
- `session-replay-attacker`
- `exploit-evidence-builder`

## References

- Read [`references/REFERENCE.md`](references/REFERENCE.md) for deeper implementation patterns.
