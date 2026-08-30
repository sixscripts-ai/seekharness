---
name: regression-gate
description: Run the Agent Arena hermetic test ladder from focused regression through Change Sets A/B/C and target security. Use before claiming a backend or frontend change is verified.
---

# Regression gate

Run the narrowest useful ladder, then expand. Do not set `ARENA_INTEGRATION_TESTS=1` unless the user explicitly asked for external integration.

Default backend command:

```text
backend/.venv/bin/python -m pytest --ignore=tests/evals
```

`pytest.ini` already deselects `modal`, `integration`, `postgres`, and `provider_eval`.

## Ladder

1. **Focused regression** — tests that fail if this change is wrong
2. **Affected subsystem** — neighboring module tests
3. **Change Set A** — execution kernel, tool protocol, tool-step accounting (`test_execution_kernel.py` and related). There is no file literally named "Change Set A"; use those kernel tests.
4. **Change Set B** — skill identity, memory provenance, ranking fairness (`test_skill_policy.py`, `test_memory_policy.py`, `test_change_set_b_probes.py`, `test_pg_memory_policy.py` when hermetic)
5. **Change Set C** — authoritative results and finalization (`test_authoritative_results.py`, `test_finalization_*.py`, `test_change_set_c_probes.py`)
6. **Target security if relevant** — `test_target_security.py`, `test_evaluator_isolation.py`, `test_hermetic_guard.py`
7. **Full hermetic backend** — `backend/.venv/bin/python -m pytest --ignore=tests/evals`
8. **Frontend checks if relevant** — `pnpm -C frontend check` and `pnpm -C frontend lint` (lint has known pre-existing errors)

## Do not

- Run `tests/evals` (DeepEval / OpenRouter at collection)
- Treat Python-lock tests as Postgres concurrency proof
- Claim "full regression" if a ladder step was skipped
- Mutate Appwrite, Neon, Modal, Vercel, or provider APIs

## Report

- Steps run and exact commands
- Pass / fail counts
- Steps skipped and why
- Remaining risk

## Examples

- Finalization-only change: focused `test_finalization_*.py` → Change Set C → full hermetic backend
- Target bundle change: target security → hermetic backend; skip frontend
