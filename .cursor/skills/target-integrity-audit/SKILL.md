---
name: target-integrity-audit
description: Audit a target bundle for public/private isolation, hidden evaluator exposure, Builder/Breaker handoff, and escape paths. Use when reviewing targets, verifier, or sandbox filesystem boundaries.
---

# Target integrity audit

Audit one target (or the library loader) as an isolation problem. Path allowlists are not enough.

## Audit

1. **Manifest** — `target.yaml` id, format, runtime, limits, commands
2. **Runtime** — declared runtime matches harness
3. **Visible / private files** — starter and visible tests vs hidden tests and reference
4. **Evaluator / reference exposure** — hidden material absent from fighter filesystem
5. **Builder / Breaker handoff** — Builder workspace gone before Breaker; only allowlisted artifacts
6. **Direct read** — fighter read tools cannot open private paths
7. **Shell** — shell cannot `cat`/`ls` into hidden/reference
8. **Python** — `open()`, imports, and runtime file APIs cannot pierce the partition
9. **Subprocess** — spawned processes inherit the same boundary
10. **Absolute paths** — rejected or confined
11. **Symlinks** — no escape from the public tree
12. **Public Git leakage** — private files not committed, published, or streamed to fighters

Use synthetic markers in hidden/reference files. Do not copy real evaluator secrets into chat.

## Verdict

- ISOLATED / LEAKED / UNVERIFIED
- Attack path (if any)
- Whether path guards were the only control
- Recommended regression in `test_target_security.py` / `test_evaluator_isolation.py`

## Examples

- Hidden file present in fighter materialize → LEAKED
- Symlink from starter to `tests/hidden` → LEAKED
- Only `_SAFE_PATH_REGEX` checked, no Python/subprocess cases → UNVERIFIED
