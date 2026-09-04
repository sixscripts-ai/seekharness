---
name: authority-source-finder
description: >
  Determine which implementation, specification, test, configuration source, or generated artifact currently governs behavior when sources disagree. Use this skill when diagnosing investigation/authority or when seeing signals: source of truth, conflicting sources, stale documentation, authority, duplicate implementation, generated.
license: MIT
compatibility: No special requirements
metadata:
  author: sixscripts-ai
  version: "1.0.0"
  context_cost: "medium"
  roles: "general, builder, breaker"
  runtimes: "*"
---

# Authority Source Finder

## Overview

Determine which implementation, specification, test, configuration source, or generated artifact currently governs behavior when sources disagree.

- **Primary Index**: `investigation/authority`
- **Context Cost**: `medium`
- **Applicable Roles**: `general, builder, breaker`

### Graph Indexes
- `investigation/authority`
- `security/adversarial-instructions`
- `strategy/evidence`

### Suggested Foundations
- None

## Step-by-Step Instructions

1. **Observe and Collect Baseline**:
   - Inspect visible logs, test outputs, or error traces without modifying code.
   - Run `TOOL read`, `TOOL grep`, or `TOOL ls` to understand the current workspace state.

2. **Formulate Hypotheses**:
   - Match symptoms against domain patterns for `investigation/authority`.
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

- `adversarial-repository-reader`
- `git-history-forensics`
- `configuration-auditor`
- `evidence-before-editing`
- `repository-cartographer`

## References

- Read [`references/REFERENCE.md`](references/REFERENCE.md) for deeper implementation patterns.
