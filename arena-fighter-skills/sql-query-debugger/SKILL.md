---
name: sql-query-debugger
description: >
  Diagnose SQL semantics, parameter binding, filtering, joins, aggregation, null behavior, and database-specific query behavior. Use this skill when diagnosing data/sql or when seeing signals: sql query, parameter binding, join bug, sqlite, postgres, filter, null.
license: MIT
compatibility: No special requirements
metadata:
  author: sixscripts-ai
  version: "1.0.0"
  context_cost: "medium"
  roles: "general, builder, breaker"
  runtimes: "sql, *"
---

# Sql Query Debugger

## Overview

Diagnose SQL semantics, parameter binding, filtering, joins, aggregation, null behavior, and database-specific query behavior.

- **Primary Index**: `data/sql`
- **Context Cost**: `medium`
- **Applicable Roles**: `general, builder, breaker`

### Graph Indexes
- `data/sql`
- `security/injection`
- `data/integrity`

### Suggested Foundations
- None

## Step-by-Step Instructions

1. **Observe and Collect Baseline**:
   - Inspect visible logs, test outputs, or error traces without modifying code.
   - Run `TOOL read`, `TOOL grep`, or `TOOL ls` to understand the current workspace state.

2. **Formulate Hypotheses**:
   - Match symptoms against domain patterns for `data/sql`.
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

- `injection-tester`
- `data-integrity-checker`
- `transaction-consistency-debugger`
- `schema-drift-auditor`
- `database-migration-debugger`

## References

- Read [`references/REFERENCE.md`](references/REFERENCE.md) for deeper implementation patterns.
