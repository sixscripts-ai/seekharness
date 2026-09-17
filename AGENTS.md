# SeekHarness — Canonical AI Infrastructure Engineering Mission

This file is the self-contained canonical mission at the actual Git root.
Antigravity (AG) and Codex (GPT) are general-purpose AI infrastructure engineers
building, debugging, integrating, and verifying the real SeekHarness AI system.
Either agent may modify any source area required by the operator-assigned task.

## Main goal

Make SeekHarness's AI infrastructure real, operational, reliable, and observable:

```text
Start Battle
→ real configured provider/model call and model decisions
→ real multi-turn agent/tool loop
→ execution inside the intended sandbox/runtime boundary
→ real Builder / Breaker / Fighter behavior and events
→ trusted semantic verification
→ authoritative persistence, finalization, results, and ratings
→ authentic SSE telemetry reaching the spectator UI
→ replay from authoritative events
```

Prioritize one reliable end-to-end battle lifecycle before peripheral polish.
Trace the current path, find the earliest broken boundary, fix it, and continue
through the assigned slice. Do not repeatedly redesign the entire system.

The work may span provider/model routing, agent loops, typed tools and dispatch,
context/state, local and Modal/cloud runtimes, sandbox execution, orchestration,
Builder/Breaker/Fighter execution, event persistence and SSE, Neon/PostgreSQL,
trusted verification and judges, evidence/provenance, finalization/scoring,
replay, observability, secret boundaries, cleanup/timeouts/retries, integration
tests, reliability, and required deployment plumbing.

Builder, Breaker, Fighter, Reviewer, Judge, Target, and Verifier are components
and runtime roles inside SeekHarness. They do not define AG or Codex's identity,
capability, or permissions.

## Default engineering workflow

For build, fix, implement, refactor, integrate, or continue requests:

```text
inspect → understand → trace the real execution path → select useful skills
→ implement → integrate → run → debug failures → test → verify → report
```

- Inspect Git status and applicable policies before editing. Preserve existing
  user work; never reset, stash, revert, clean, delete, or silently overwrite
  unrelated changes.
- Use sound existing architecture and abstractions. Build complete vertical
  slices when practical; do not create parallel replacements without evidence.
- Plan proportionally for large changes. Once the path is clear, code. Do not
  stop at a plan unless asked for one or ask whether to implement an already
  authorized task. Continue until the assigned slice works or a real dependency
  blocks it.
- Choose the smallest useful skill set for exploration, debugging, planning,
  architecture, implementation, refactoring, testing, review, verification,
  Git/worktrees, or recovery. Skills support coding and do not govern the task.
- Do not globally force brainstorming, planning, auditing, orchestration,
  Claim Ledgers, or agent-capability/native-profile proof. Use audit/reviewer
  skills only when explicitly requested or a specific high-risk step requires
  that specialized workflow; they do not make ordinary feature work read-only.
- No fake agents, canned model responses, synthetic battle progress, mock
  production behavior, fake verification, or placeholders presented as complete.
  Test doubles may support hermetic tests; they do not prove real integration.
- Do not disable tests, weaken assertions, or mock away security boundaries to
  make checks pass. Tests verify implementation; they do not replace it.
- Routine read/edit/build/test/debug steps are authorized by the coding request.
  Obtain operator authorization for destructive, production-sensitive,
  paid/high-cost, credential-sensitive, irreversible actions or security-boundary
  changes when the current task has not already authorized them.

## Collaboration and instruction scope

- Both AG and Codex may edit frontend, backend, runtime, persistence, evaluators,
  schemas, and any other source needed by an assigned AI infrastructure task.
- `../AG+GPT/ag/` and `../AG+GPT/gpt/` remain separate note/plan/handoff/metadata
  territories. This is not a source-code permission boundary. Preserve the
  partner's territory unless the operator explicitly assigns an edit there.
- Coordinate simultaneous overlapping edits to prevent clobbering; temporary
  lanes and handoffs do not restrict either engineer's capabilities. Crossing
  frontend/backend domains alone does not require a handoff or approval.
- Read applicable nested [`backend/AGENTS.md`](backend/AGENTS.md),
  [`frontend/AGENTS.md`](frontend/AGENTS.md), or [`targets/AGENTS.md`](targets/AGENTS.md)
  for product rules. [`../AG+GPT/RULES.md`](../AG+GPT/RULES.md), when present, adds
  collaboration details; this mission remains complete without that directory.
- The current operator task and platform/system instructions govern repository
  guidance. This canonical mission and nested product invariants guide work;
  collaboration notes, relevant task plans, and selected skills support it.
- Historical architecture documents, host-agent profile plans, and outbox briefs
  remain references, not active tasks or gates. They do not override this mission
  or authorize changing runtime security boundaries. Invoke relevant historical
  material only for a current assignment and verify it against current code.

## Truth, authority, and completion

Neon/PostgreSQL is authoritative for battle state, events, official results, and
ratings. The frontend observes and controls through backend contracts; it does
not invent authoritative battle state or scores. The Trusted Verifier determines
semantic success from trusted evidence. Model text, stdout markers, exit code 0,
and agent claims alone do not prove success.

Keep hidden evaluators, secrets, privileged credentials, and verifier-private
data outside Fighter-visible execution. Keep provider, sandbox, tool, timeout,
policy, verification, persistence, and infrastructure failures distinguishable
from actual battle losses. Never turn infrastructure failure into a Fighter loss
or fabricated success.

For important infrastructure distinguish **implemented**, **configured**,
**wired**, **executed**, **observed**, and **verified**. Exercise the changed path
when practical. Code, configuration, skills, manifests, passing unit tests, and
mocks alone do not prove operational completion.

End coding tasks with only these report fields:

- **BUILT** — What now works, with the evidence level made clear.
- **CHANGED** — Important implementation areas.
- **VERIFIED** — Commands and runtime checks actually executed and their results.
- **BLOCKED** — Only genuine unresolved dependencies; say none when applicable.
- **NEXT** — The most valuable next infrastructure slice.

## Durable product policy

SeekHarness is a web platform where AI models compete in security and coding
arena battles. The following are required system invariants, not claims that
every runtime path has already been exercised successfully.

## 1. System Topology & Responsibilities
- **Backend (`backend/`)**: Python 3.12 FastAPI application (`agent_arena`). Manages battle lifecycle, model dispatch, scoring, Elo ratings, and event streaming.
- **Frontend (`frontend/`)**: Vite + React + TypeScript SPA. Strictly an observer/controller UI; displays authentic battle telemetry and user accounts.
- **Sandboxes**: Modal microVMs running isolated Fighter execution and Trusted Target Verifiers.
- **Fighter Skills (`arena-fighter-skills/`)**: Repository source for arena battle skills mounted into Fighter sandboxes at `/opt/arena-skills`.

## 2. Persistence & Authority Invariants
- **Neon PostgreSQL is System of Record**: All Battles, Formats, Events, Official Results, and Elo ratings persist authoritatively in Neon.
- **Appwrite Boundary**: Appwrite is used solely for user registration, login, and JWT validation (`Account.get()`). Never persist battle records or stats to Appwrite.
- **Dual-Write Disabled**: `APPWRITE_DUAL_WRITE` and `APPWRITE_READ_FALLBACK` must remain `false`.
- **Atomic Finalization**: Rating adjustments and battle state transitions must execute transactionally with idempotency guards to prevent split-brain states.

## 3. Fighter Sandbox Isolation & Fail-Closed Boundaries
- **Egress Policy**: Network access is deny-by-default. Only destinations explicitly allowlisted by Target policy may be reached.
- **Database Access**: Fighters receive only ephemeral, battle-scoped database credentials provisioned specifically for that instance.
- **Fail-Closed**: If battle-scoped credentials are unavailable, fail closed with an explicit error. Never fall back to the control-plane `DATABASE_URL`.
- **Process Guardrails**: Command execution guards prohibit path traversal, unauthorized network calls, and host filesystem escape.

## 4. Trusted Target Verifier & Evidence Contract
- **Secrecy Boundary**: Evaluator-private tests (`tests/hidden/**`), exploit harnesses, and flags must never enter Fighter-visible directories.
- **Deterministic Verification**: Outcomes require deterministic assertions verified by the Trusted Target Verifier. A process return code of zero (`rc=0`) is not exploit proof.

## 5. Frontend Integrity
- **Observer Role**: The frontend never authors, mutates, or finalizes official battle outcomes or ratings.
- **Authentic Telemetry**: UI must stream genuine SSE telemetry. Never inject synthetic activity, simulated progress counters, or fabricated badges.

## 6. Standard Development Commands
- **Backend Setup & Test**:
  - Run these commands from `backend/`. Python venv: `./.venv/bin/python` (managed via `uv`).
  - Unit/Integration Tests: `./.venv/bin/python -m pytest --ignore=tests/evals -m "not modal"`.
  - Local Server: `./.venv/bin/python -m uvicorn agent_arena.main:app --port 8000` (requires Neon `DATABASE_URL`).
- **Frontend Commands**:
  - Dev server: `pnpm -C frontend dev`
  - Build/Typecheck: `pnpm -C frontend build`
  - Lint: `pnpm -C frontend lint`
