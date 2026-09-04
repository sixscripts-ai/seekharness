---
name: audit-target
description: Read-only target-integrity audit for the requested target id or library path.
---

# /audit-target

Read-only target leakage audit. `/target-leakage` is the same command under the product name.

Invoke the `target-integrity-audit` skill for the target named in the prompt (or the library loader if no id is given).

Do not modify targets, manifests, or application source.

Cover manifest, runtime, visible/private files, evaluator/reference exposure, Builder/Breaker handoff, direct read, shell, Python, subprocess, absolute paths, symlinks, and public Git leakage.

Use synthetic markers only. Do not paste real hidden evaluator contents.

## Report

- Target id
- ISOLATED / LEAKED / UNVERIFIED
- Attack paths
- Recommended hermetic tests (`test_target_security.py`, `test_evaluator_isolation.py`)
