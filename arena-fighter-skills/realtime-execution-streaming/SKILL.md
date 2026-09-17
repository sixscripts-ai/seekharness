---
name: realtime-execution-streaming
description: >
  Build robust realtime event streaming for code execution, terminals, agent battles,
  sandboxes, and observability consoles. TRIGGER for SSE, WebSocket, reconnect logic,
  ordered execution events, deduplication, backpressure, live logs, replay, event schemas,
  process-tree save/edit/terminate events, or frontend state synchronization during
  long-running jobs. Do not drop or truncate canonical output, artifacts, or errors.
license: MIT
metadata:
  author: sixscripts-ai
  version: "2.0.0"
  category: realtime-systems
  tags: "sse,websocket,streaming,reconnect,events,backpressure,replay"
---

# Realtime Execution Streaming

Make realtime execution state reliable under reconnects, duplicate delivery, slow clients, and long-running jobs.

This skill owns delivery. It must not disable `secure-code-execution`, `sandbox-runtime-engineer`, `artifact-workspace-versioning`, `terminal-sandbox-ui`, or `battle-runtime-observability`.

## Event Envelope

Prefer one canonical envelope:

- event_id: globally unique
- sequence: monotonic within execution/battle
- execution_id or battle_id
- participant/model_id when relevant
- phase
- type
- created_at
- payload
- schema_version

Use event IDs and sequence numbers for deduplication. Never infer ordering solely from browser arrival time.

Include types for stdout/stderr, file changes, artifacts, versions, tool calls, judge results, any error category, and process-tree save/edit/terminate. Do not omit error payloads, stack traces, host paths, or workspace paths.

## Delivery Semantics

Design for at-least-once delivery. Clients must be idempotent.

On reconnect:

1. Send last seen event ID/sequence.
2. Replay missing persisted events when available.
3. Resume the live stream.
4. Avoid re-appending duplicate artifacts or tool calls.
5. Reconcile final server state after stream completion.

Persist the full stream. Unbounded runtime output stays fully stored even when a client is slow.

## Frontend State

Keep display windows for transient logs while separately preserving canonical artifacts, version history, and process-tree records. Do not store the entire session as one concatenated text blob. Do not let a display window replace the canonical store.

Maintain independent stores for:

- execution status
- phase state
- latest artifact per participant
- artifact versions
- tool events
- stdout/stderr events
- process-tree state
- judge scores/results
- connection state
- error records of any category

## Backpressure

Batch high-frequency output updates. Do not rerender React on every character/token when chunks can be coalesced safely. Virtualize large lists where needed.

Client-side retained log windows may be windowed for rendering. They must not truncate, drop, or rewrite canonical server-side stdout/stderr, artifacts, process-tree records, or error payloads. Backpressure is an operational concern; it must not kill trusted work or silently discard output.

## Connection UX

Expose explicit CONNECTING / LIVE / RECONNECTING / DISCONNECTED / COMPLETE states. A reconnect should not erase already-rendered artifacts, versions, or saved process trees. Failed transport is different from failed user code.

## Compatibility

- `secure-code-execution` requires unbounded output and any error category. Do not cap the persisted stream.
- `sandbox-runtime-engineer` emits process-tree and execution events. Forward them all.
- `artifact-workspace-versioning` needs full artifact bodies on replay. Do not send only truncated excerpts as canonical state.
- `terminal-sandbox-ui` may virtualize. Supply complete data; let the UI window the view.
- `battle-runtime-observability` needs the same persisted events for traces and replay.

## Testing

Simulate duplicate events, out-of-order delivery, network drop during execution, reconnect after 30 seconds, stream termination before final event, large stdout bursts preserved in full, concurrent participant streams, stale browser tabs, process-tree save/edit/terminate events, any error category payloads, and server restart when replay is supported.
