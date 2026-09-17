---
name: live-battle-telemetry-synthesizer
description: >
  Orchestrate and analyze live AI battle executions and Target Library evaluations across web and API. Use this skill when the user asks to run a battle, evaluate a target, extract live battle telemetry, diagnose sandbox execution failures, or brainstorm product enhancements based on real agent performance data. Also activate when investigating 502/429 model errors, analyzing verifier logs, or inspecting multi-turn microVM action streams.
license: MIT
compatibility: Python 3.10+, PostgreSQL (Neon), Playwright / Browser Subagent, Modal
metadata:
  author: villain
  version: "1.0"
allowed-tools: Bash Read Write
---

# Live Battle Telemetry Synthesizer

## Overview

The **Live Battle Telemetry Synthesizer** automates the workflow of executing live agent duels and Target Library benchmarks, capturing granular microVM execution telemetry, querying the underlying database (Neon PostgreSQL / Appwrite) for raw deterministic evidence, and synthesizing the resulting data into high-value product opportunities and architectural insights.

---

## Instructions

When executing or analyzing a live battle or target evaluation, follow this 4-phase procedure:

### Phase 1: Environment Preflight & Model Health
1. **Verify Host Models**: Run `scripts/extract_battle_telemetry.py` or inspect active models in `backend/agent_arena/providers.py`.
2. **Ensure Clean Auth**: Ensure the target test user is authenticated via Appwrite.

### Phase 2: Live Battle Execution
1. **Launch Duel or Target Battle**:
   - For standard format duels: Navigate to `/battles/new`, select format (e.g., `debugging-race`, `pwn-exploit-race`), and pick two healthy fighters.
   - For target evaluation: Navigate to `/targets`, select a target (e.g., `broken-package-recovery`, `authentication-gate`), and launch via `/battles/new?target=<id>`.
2. **Observe Real-Time Stream**: Monitor SSE event stream on `/battles/:id` for `action_log`, `artifact`, `use_skill`, and `battle_status`.

### Phase 3: Raw Telemetry Extraction
1. **Extract Execution Records**:
   Run the bundled extraction script:
   ```bash
   python scripts/extract_battle_telemetry.py <battle_id>
   ```
2. **Audit Telemetry Markers**:
   - Check **Skill Selection**: Identify which skills from `.agents/skills` the agent loaded.
   - Check **Tool Dialect**: Verify if model tool calls adhered to JSON or XML structures.
   - Check **Verifier Output**: Extract exact `TEST_PASS` / `TEST_FAIL` stdout, stderr, and exit codes.
   - Check **Durable Scores & Elo**: Inspect deterministic score allocations in `scores` table.

### Phase 4: Data Synthesis & Opportunity Brainstorming
1. **Group Insights**:
   - **Model Behavior & Tool Dialects**: Note where the model succeeded or tripped on tool formats.
   - **Verifier Precision**: Note whether the target verifier caught the exact edge case.
   - **UX & Spectator Flow**: Evaluate terminal latency, step scrubbing, and score clarity.
2. **Deliver Actionable Opportunities**: Structure findings into concrete product, prompt, or architectural recommendations.

---

## Available Scripts

- **`scripts/extract_battle_telemetry.py`** — Connects to Neon PostgreSQL and extracts battle metadata, participants, skill loadouts, verifier logs, and raw chronological events into structured JSON or formatted summaries.

---

## Gotchas

- **Branch Matching**: Production Modal backend runs on the `main` Neon branch (`br-floral-fog-a6bpjm9i`). Ensure `DATABASE_URL` matches the deployed instance when querying historical battles.
- **Zero Fake Data**: Never synthesize mock scores or fallbacks. If a verifier reports `TEST_FAIL`, the battle must be reported as a genuine failure with exact `stderr`.
- **Dialect Variations**: Frontier models (Kimi, DeepSeek, Qwen) may emit raw token separators (`<|open|>tools<|sep|>`) when tool prompting varies.

---

## Examples

- Read [`examples/sample_telemetry_report.md`](examples/sample_telemetry_report.md) for a complete example of a battle telemetry synthesis report.

---

## References

- Read [`references/REFERENCE.md`](references/REFERENCE.md) for complete event schemas, scoring engine versions, and action log payload structures.
