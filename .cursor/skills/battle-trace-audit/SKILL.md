---
name: battle-trace-audit
description: Reconstruct an Agent Arena battle from JSON, events, and traces and classify the failure. Use when auditing a battle, live telemetry, SSE events, or a failed run.
---

# Battle trace audit

Reconstruct the battle from stored JSON, events, and code. Do not treat UI timing as truth.

## Reconstruct

Walk these in order, citing evidence for each:

1. Battle identity and status
2. Target and format
3. Phases
4. Model turns
5. Parser dialect
6. Tools requested vs tools executed
7. Tool-step accounting (failed attempts still cost a step)
8. Skill lifecycle
9. Filesystem changes
10. Builder handoff (if Builder/Breaker)
11. Verification
12. Finalization

Arena may normalize serialization. Do not invent fighter intent.

## Classify

Assign exactly one primary class:

| Class | Meaning |
| --- | --- |
| `MODEL_FAILURE` | Fighter strategy, code, or stopping was wrong |
| `TOOL_INTERFACE_FAILURE` | Valid intent, bad tool schema/parse/dispatch |
| `TARGET_RUNTIME_FAILURE` | Declared runtime/harness could not run the work |
| `TARGET_BUNDLE_FAILURE` | Manifest, files, or hashes are wrong |
| `SANDBOX_FAILURE` | Isolation, exec, timeout, or I/O platform fault |
| `VERIFIER_FAILURE` | Trusted verifier command/result is wrong |
| `FINALIZATION_FAILURE` | Authority, identity, transaction, or idempotency fault |
| `PRESENTATION_ONLY` | Stored outcome is correct; UI/SSE/display is wrong |

Sandbox/runtime output is evidence, not the verdict.

## Report

- Primary class
- Evidence paths
- What Arena owned vs what the fighter owned
- Whether finalization agrees with verification
- Recommended regression (file + assertion)

## Examples

- SSE shows a winner before finalize → likely `PRESENTATION_ONLY` unless the stored result matches the stream.
- Tool parse failed and no step was charged → `TOOL_INTERFACE_FAILURE` plus kernel accounting.
- Hidden evaluator path appears in fighter listing → stop and run `target-integrity-audit`.
