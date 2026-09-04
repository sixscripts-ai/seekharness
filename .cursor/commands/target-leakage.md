---
name: target-leakage
description: Read-only audit for hidden evaluator / Builder-Breaker / filesystem leakage. Alias of /audit-target.
---

# /target-leakage

Read-only. Same workflow as `/audit-target`. Invoke `target-integrity-audit` for the target id or library path in the prompt.

Do not modify targets, manifests, or application source.

Cover manifest, runtime, visible/private files, evaluator/reference exposure, Builder/Breaker handoff, direct read, shell, Python, subprocess, absolute paths, symlinks, and public Git leakage.

Use synthetic markers only. Do not paste real hidden evaluator contents.

## Report

- Target id
- ISOLATED / LEAKED / UNVERIFIED
- Attack paths
- Recommended hermetic tests (`test_target_security.py`, `test_evaluator_isolation.py`)
