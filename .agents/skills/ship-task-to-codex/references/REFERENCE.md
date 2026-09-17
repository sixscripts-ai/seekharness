# Ship Task to Codex Protocol & Boundary Verification

## 1. The Delegation Contract

When delegating tasks from Apex (Antigravity) to Codex CLI:
1. **Prompt Word Budget**: Prompts must strictly remain below 800 words to avoid context bloat.
2. **Explicit Allowed Files**: The task must specify exact file paths that may be edited.
3. **Deterministic Test Verification**: A deterministic command (e.g. `pytest backend/tests/test_x.py`) must be specified.
4. **Zero Self-Reported Trust**: Apex never accepts Codex's conversational claim of task completion. Apex verifies:
   - Git diff stays within allowed file boundaries.
   - The test command passes with exit code 0.

## 2. Standard Prompt Template

```markdown
# Objective
[1-2 sentences on what needs to be implemented or fixed]

# Allowed Target Files
- `path/to/target_file.py`

# Constraints
- Do NOT modify any other files in the repository.
- Do NOT change existing function signatures unless explicitly instructed.
- All code must pass type checks and linting.

# Verification
Run the following test to verify your fix:
`pytest path/to/test.py`
```

## 3. Failure Remediation

If Codex fails to satisfy verification:
1. Inspect git diff for unintended mutations.
2. Revert out-of-scope changes: `git checkout -- <unintended_file>`.
3. Provide refined feedback or take over the implementation directly in Apex.
