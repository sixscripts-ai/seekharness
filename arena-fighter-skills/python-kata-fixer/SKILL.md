---
name: python-kata-fixer
description: >
  Fix a shared Python TARGET by writing solution.py, then run the repo-owned
  tests/test_target.py harness. Use for tool-using coding races and kata repair.
---

# Python Kata Fixer

## Instructions

1. Read `TARGET.md` for the buggy specification.
2. Write a correct `solution.py` that exports the required function(s).
3. Do not print `TEST_PASS` yourself. Run `TOOL test` so the harness file `tests/test_target.py` decides pass/fail via assertions and exit code.
4. Keep the workspace. Edit in place across turns instead of rewriting from scratch.

## Common Issues

- Case-sensitive palindrome checks
- Forgetting to ignore non-alphanumeric characters
- Importing from the wrong module name (harness imports `solution`)

## References

- Workspace files: `TARGET.md`, `solution.py`, `tests/test_target.py`, `THEORY.md`

## Examples

```
TOOL read path=TARGET.md
TOOL write path=solution.py
def is_palindrome(s: str) -> bool:
    n = "".join(c.lower() for c in s if c.isalnum())
    return n == n[::-1]
END_TOOL
TOOL test
DONE
```
