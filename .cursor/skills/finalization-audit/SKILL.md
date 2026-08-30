---
name: finalization-audit
description: Audit battle finalization authority, idempotency, DB transactions, Elo/skill races, and memory provenance. Use when reviewing finalize, results, Elo, or concurrency claims.
---

# Finalization audit

Audit `finalization.py`, `results.py`, `scoring.py`, and persistence. Caller JSON is untrusted.

## Checklist

1. **Caller authority** — sandbox/API callers cannot choose score, winner, or pass/fail.
2. **Terminal transitions** — `completed` / `failed` / `cancelled` cannot be overwritten by a later finalize.
3. **Duplicate finalize** — second call returns existing state with zero extra Elo, skill, memory, or result writes.
4. **Result identity** — authoritative key is `(battle_id, phase, role, model_id)`.
5. **DB transaction boundaries** — result, scores, Elo, skill attribution, and memory learning commit together or not at all.
6. **Elo concurrency** — sorted row locks; no lost updates under concurrent finalize.
7. **First-row / missing-row races** — creating a missing leaderboard row is race-safe.
8. **Skill concurrency** — skill writes do not double-apply on retry.
9. **Memory provenance** — Change Set B policy; no raw winner inserts; strict mode gets no adaptive history.
10. **Rollback / retry** — rollback leaves no partial side effects; retry is idempotent.

## Proof bar

- Process-local locks are not a distributed correctness guarantee.
- Concurrency claims need real DB sessions (or an explicit gap).
- SSE/event timing cannot determine the stored outcome.

## Report

- Each checklist item: PASS / FAIL / UNVERIFIED
- Exact code path
- Missing test
- Whether the implementation claim is proven

## Examples

- Two concurrent finalize calls, one Elo increment → FAIL on Elo concurrency.
- Caller `scores` copied into `BattleResult` → FAIL on caller authority.
- In-process lock test only → UNVERIFIED for database-level concurrency.
