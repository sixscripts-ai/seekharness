---
name: review-diff
description: Read-only review of the current git diff. Classify findings as BLOCKER, MAJOR, or MINOR.
---

# /review-diff

Read-only. Do not edit, commit, restore, or clean the tree.

Run:

```bash
git status --short
git diff --check
git diff
```

Review staged and unstaged application changes. Preserve unrelated dirty work.

## Classify

- **BLOCKER** — trust-boundary break, authoritative-result corruption, secret leak, or fighter-accessible hidden data
- **MAJOR** — correctness or concurrency gap without proven isolation/finalization impact
- **MINOR** — style, docs, or non-behavioral nits

Do not "fix" pre-existing P0 whitespace from `git diff --check` unless the user asked to change those files.

## Report

- Scope of the diff
- BLOCKER / MAJOR / MINOR list
- Whether Change Set C / target / frontend files are mixed with unrelated work
