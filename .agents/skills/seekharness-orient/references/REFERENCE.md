# SeekHarness Architecture & Lifecycle Boundary Reference

## 1. Five Core Architectural Boundaries

SeekHarness evaluates AI combatants across five deterministic architectural boundaries:

1. **`semantic_verification`**: Target verifier command guard, AST inspection, and builder/breaker semantic tests.
   - Key modules: `backend/agent_arena/target_verifier.py`, `backend/agent_arena/target_verifier/_command_guard.py`
   - Key test: `backend/tests/test_builder_breaker_semantic_verification.py`

2. **`battle_db`**: Ephemeral Neon PostgreSQL branch isolation for live multi-turn battles.
   - Key module: `backend/agent_arena/neon_branch_manager.py`
   - Key test: `backend/tests/test_battle_database_lifecycle.py`

3. **`service_lifecycle`**: Process management, sandbox runner, reaper, and port allocation.
   - Key modules: `backend/agent_arena/reaper.py`, `backend/agent_arena/sandbox/executors/battle_plan.py`
   - Key test: `backend/tests/test_battle_plan.py`

4. **`breaker_handoff`**: Frozen artifact transfer and fighter network isolation policy.
   - Key module: `backend/agent_arena/sandbox/executors/fighter_network_policy.py`
   - Key test: `backend/tests/test_fighter_tool_boundaries.py`

5. **`trusted_completion`**: Transactional finalization audit and cryptographic/deterministic scoring verification.
   - Key module: `backend/agent_arena/finalization.py`
   - Key test: `backend/tests/test_finalization_transactional_audit.py`

## 2. Preflight Health Invariants

Before any code modification or battle dispatch, verify:
- Python backend virtualenv is located at `backend/.venv`
- Frontend dependencies exist at `frontend/node_modules`
- No untracked migration conflicts exist in `backend/alembic/versions`
- Target working tree state is checked via `seekharness-dev preflight --json`

## 3. Boundary Progression Strategy

Never proceed to a subsequent boundary until all preceding boundaries report `VERIFIED` with zero failing tests. If any check fails, resolve it within the current boundary slice.
