---
name: live-status-truth
description: Audit or fix LiveBattle / SSE / export so one Neon status and event_id contract is the truth.
---

# /live-status-truth

Invoke the `live-status-truth` skill.

Chain, in order:

1. `finalization-audit`
2. `realtime-execution-streaming`
3. `implementation-worker` for UI/SSE; `lead-engineer` if stored status writes change
4. `regression-gate`

SSE/event timing cannot determine authoritative outcome.

Do not dispatch Composer, Luna, Sol, Opus, or unrelated design/3D agents.
