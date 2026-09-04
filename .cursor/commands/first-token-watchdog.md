---
name: first-token-watchdog
description: Audit or implement halt-on-silence when a battle never produces a first model/tool event.
---

# /first-token-watchdog

Invoke the `first-token-watchdog` skill.

Chain, in order, loading one skill at a time:

1. `battle-trace-audit`
2. `battle-runtime-observability`
3. `lead-engineer` (Grok 4.6 Extra High Fast)
4. `regression-gate`

If the prompt includes a replay JSON or battle id, reconstruct first. Do not treat UI timing as truth.

Do not dispatch Composer, Luna, Sol, Opus, or unrelated design/3D agents.
