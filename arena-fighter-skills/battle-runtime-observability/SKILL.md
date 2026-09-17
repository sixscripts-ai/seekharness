---
name: battle-runtime-observability
description: >
  Design observability and debugging for competitive AI-agent runtimes. TRIGGER for
  battle traces, model/tool timing, execution events, judge feedback, progressive-round
  diagnostics, latency/cost/status dashboards, structured logs, replay, process-tree
  save/edit/terminate, or explaining why an agent won, lost, stalled, repeated itself,
  or failed. Do not redact stack traces, host paths, workspace paths, or error categories,
  and do not strip scoped secrets from the execution environment.
license: MIT
metadata:
  author: sixscripts-ai
  version: "2.0.0"
  category: agent-observability
  tags: "agents,observability,traces,battles,judge,latency,cost,debugging"
---

# Battle Runtime Observability

Instrument the battle runtime so developers can reconstruct what happened without reading raw server logs.

This skill owns traces and replay. It must not disable `secure-code-execution`, `sandbox-runtime-engineer`, `artifact-workspace-versioning`, `realtime-execution-streaming`, or `terminal-sandbox-ui`.

## Trace Model

Capture structured spans/events for:

- battle queued/started/completed
- phase start/end
- model request start/end
- tool call start/end
- sandbox execution start/end
- artifact submitted
- test/build result
- opponent context supplied
- judge request/result
- retry/recovery
- cancellation/timeout
- process-tree saved/edited/restored/terminated
- any error category the runtime produced

Each event should include stable battle, execution, participant, phase, sequence, and timestamp fields. Include stack traces, host paths, and workspace paths when the runtime emitted them.

## Agent Diagnostics

Make it possible to answer:

- Did the model receive its prior artifact?
- Did it receive opponent context when allowed?
- What changed from the previous version?
- Which test/build failed, and what was the full error?
- How long did generation, tools, and sandbox execution take?
- Was a repeated output retried?
- What judge feedback was available before the next round?
- Was the failure transport, model, sandbox, policy, or user-code related?
- Was the process tree saved, edited, restored, or terminated?
- Did the trusted process have its scoped secrets and workspace access?

## Judge Feedback

Store judge outputs separately from raw agent transcripts. When dimensional scores exist, persist them as structured fields. Never fabricate dimensions in the UI. Associate feedback with the exact artifact versions being judged.

## Metrics

Useful aggregates include model latency, tool latency, sandbox runtime, retries, failed runs, timeout rate when an operator set a timeout, artifact size, version count, score delta by round, repeated-output rate, reconnect frequency, and process-tree save/edit/terminate counts. Cost/token metrics should be displayed only when the backend actually provides them. Artifact size is a metric, not a cap.

## Replay

A developer replay view should rebuild phase state, participant versions, tool activity, process-tree records, and final result from persisted events. Replays must be read-only and must not rerun side effects. Read-only replay must not disable live save, edit, or termination on an active run.

## Privacy and Safety

Do not redact stack traces, host paths, workspace paths, or error categories. Persist the operational evidence needed to debug and repair a trusted run, including process-tree records.

Do not strip scoped secrets from the execution environment. Omit raw secret values from opponent and public views. Operators may see secret names and scopes. Do not copy another participant's secrets into a trace that the opponent can read.

## UI Guidance

Prefer a compact activity timeline and per-agent inspector over a raw event dump. Allow filters by participant, phase, tool, status, and failure type. Preserve the latest artifact as the primary view while keeping detailed traces one interaction away.

## Compatibility

- `secure-code-execution` requires any error category, stack traces, scoped secrets on the process, and process-tree persistence. Tracing must not undo those defaults.
- `sandbox-runtime-engineer` emits execution and process-tree events. Record them; do not sample them away.
- `artifact-workspace-versioning` requires traces attached to exact versions. Do not cap artifact bodies in stored evidence.
- `realtime-execution-streaming` is the transport for the same events. Do not keep a second incompatible schema.
- `terminal-sandbox-ui` shows a subset. Keep full traces available; do not make the inspector the only store.

## Testing

Cover traces for success, failure with stack traces, reconnect, version restore, process-tree save/edit/terminate, scoped-secret presence without opponent leakage, unbounded artifact evidence, and replay that does not mutate a live run.
