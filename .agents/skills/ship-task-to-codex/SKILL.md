---
name: ship-task-to-codex
description: >
  Use this skill when delegating bounded, self-contained implementation tasks to Codex CLI.
  Formats a bounded prompt under 800 words, executes codex non-interactively, inspects
  resulting git diffs, and independently verifies claims with automated tests.
license: MIT
compatibility: Requires Python 3.10+ and codex-cli 0.153+
metadata:
  author: villain
  version: "1.0"
allowed-tools: Bash(codex:*) Bash(pytest:*) Bash(git:*) Read
---

# Ship Task to Codex

## Overview

`ship-task-to-codex` operationalizes the Apex-to-Codex delegation pipeline. It enforces tight prompt budgeting (<800 words), restricts file mutations to declared boundaries, invokes Codex non-interactively, and verifies completion using independent git diff analysis and test execution.

## Instructions

1. **Scope the Delegation Target**:
   - Ensure the task is self-contained and touches a small, clearly defined set of files.
   - Formulate explicit constraints and a deterministic verification command.

2. **Verify Prompt Word Budget**:
   - Prompts must not exceed 800 words.
   - Validate using `--dry-run`:
     ```bash
     ./scripts/ship_task.py --task "Implement helper method in cli.py" --allowed-files "dev/seekharness_dev/cli.py" --test-cmd "pytest dev/tests/test_cli.py" --dry-run
     ```

3. **Ship to Codex**:
   - Execute the task:
     ```bash
     ./scripts/ship_task.py --task "..." --allowed-files "..." --test-cmd "..."
     ```

4. **Review Verification Report**:
   - Inspect the resulting report:
     - `Within Bounds`: Must be `YES`.
     - `Tests Verified`: Must be `PASS`.
   - If `FAILED`, inspect test failures or boundary violations immediately.

## Available Scripts

- **`scripts/ship_task.py`** — Validates prompt budget, checks Codex CLI health, runs `codex exec`, audits git diff against allowed files, and executes verification tests. Supports `--dry-run`, `--json`, `--task`, `--prompt-file`, `--allowed-files`, `--test-cmd`.

## Gotchas

- Never pass large, unpruned context files in the task prompt; reference file paths instead.
- If Codex touches files outside `--allowed-files`, the script flags boundary violations.
- Never trust Codex's conversational claim that a task is done without verifying through tests.

## Examples

### Dry-Run Validation
```bash
$ ./scripts/ship_task.py --task "Fix typo in docstring" --dry-run
[DRY-RUN] Prompt passed budget check: 4/800 words.
[DRY-RUN] Codex CLI: codex-cli 0.153.3
[DRY-RUN] Allowed files: Any
[DRY-RUN] Test command: None
```

### Full Execution & Verification
```bash
$ ./scripts/ship_task.py \
    --task "Add version flag test" \
    --allowed-files "dev/tests/test_cli.py" \
    --test-cmd "pytest dev/tests/test_cli.py"
Shipping bounded task (5 words) to Codex CLI...
==================================================
           CODEX TASK EXECUTION REPORT            
==================================================
Result           : SUCCESS
Codex Exit Code  : 0
Within Bounds    : YES
Tests Verified   : PASS
==================================================
```

## References

- Read [`references/REFERENCE.md`](references/REFERENCE.md) for prompt templates, boundary enforcement contracts, and remediation procedures.
