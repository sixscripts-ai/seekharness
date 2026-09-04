---
name: first-token-watchdog
description: >
  Fail a battle that never produces a first model or tool event within a deadline.
  Use when a fight stays queued/running with only preview/phase_start, or when
  adding halt-on-silence. Chain: battle-trace-audit → battle-runtime-observability
  → lead-engineer → regression-gate.
---

# First-token watchdog

A battle that never reaches a model result or a parsed tool call is an Arena
timeout, not a fighter strategy failure. Classify before coding.

## Chain (load in order, one at a time)

1. `battle-trace-audit` — reconstruct identity, phases, model turns, tools, status. Primary class is usually `SANDBOX_FAILURE` or `TOOL_INTERFACE_FAILURE`, not `MODEL_FAILURE`, when there are zero model/tool events.
2. `battle-runtime-observability` (`.agents/skills/battle-runtime-observability`) — define the first-token event and the clock.
3. `lead-engineer` — implement halt + persist `failed` with a reason. Do not invent fighter intent.
4. `regression-gate` — focused tests, then hermetic backend. No `tests/evals`.

## First token (canonical)

The watchdog clock starts at phase start (or battle `started_at`, else `created_at`).
The first token is the earliest of:

- a persisted model result / completion event
- a native `tool_parse_success` (or equivalent parsed tool call)

Not first token: SSE `preview`, `phase_start`, artifact listings, heartbeat, UI "EXECUTING".

If that event is missing after `timeout` (or a shorter first-token budget), fail the battle. Sandbox JSON does not choose the outcome.

## Code to inspect

- `backend/agent_arena/sandbox/executors/advanced_executor.py` — `halted()`, model deadline, halt after model return
- `backend/agent_arena/reaper.py` — whole-battle stale fail; watchdog is earlier and more specific
- `backend/agent_arena/event_bus.py` — durable events
- Replay JSON / Neon `battle_events` — evidence, not authority

## Do not

- Treat SSE arrival time as the stored outcome
- Dual-write to Appwrite
- Weaken Builder/Breaker or hidden-evaluator isolation
- Charge a model failure when the transport never returned

## Report

- Trace class from step 1
- Clock start, budget, first-token event (or none)
- Code path that should halt
- Tests run (`regression-gate` ladder)
