---
name: live-status-truth
description: >
  Make LiveBattle, SSE, and export JSON show one status and durable event identity.
  Use when replay nested status is running while the battle is cancelled/failed,
  or when the UI duplicates/drops events. Chain: finalization-audit +
  realtime-execution-streaming, then implementation-worker, then regression-gate.
---

# Live / export status truth

Authoritative status lives on the battle row in Neon. SSE and export are views.
They must not invent a second outcome.

## Chain (load in order)

1. `finalization-audit` — terminal state, caller authority, SSE cannot determine stored outcome
2. `realtime-execution-streaming` (`.agents/skills/realtime-execution-streaming`) — envelope, reconnect, dedupe
3. `implementation-worker` for UI/SSE glue; `lead-engineer` if finalize/status writes change
4. `regression-gate` — include `test_live_battle_result_truth.py` and frontend `utils.test.ts` when relevant

## Contract

One battle has one status: `queued` | `running` | `completed` | `failed` | `cancelled`.

Export JSON and the live page must use that status. Nested `battle.status: running` with top-level `cancelled` is a bug.

Events:

- `event_id` unique, used to dedupe
- `created_at` / `ts` for order fallback
- `sequence` and `event_sequence` mean the same thing; do not drop one in SSE

`mergeEvent` must key on `event_id`, not arrival order.

## Code to inspect

- `backend/agent_arena/battle_public.py` — public battle + event payload
- `backend/agent_arena/battles.py` — SSE stream
- `backend/agent_arena/event_bus.py` — persistence
- `frontend/src/pages/LiveBattle.tsx` — stream status → `battle.status`
- `frontend/src/components/battle/utils.ts` — `mergeEvent`
- `backend/tests/test_live_battle_result_truth.py`

## Do not

- Let sandbox or SSE choose winner/score
- Treat stream close as `completed`
- Read Appwrite for battle status (`PERSISTENCE_BACKEND=postgres`)

## Report

- Whether stored Neon status matches export and live UI
- Event identity gaps (`event_id` / sequence)
- Tests run
