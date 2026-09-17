# Trusted Breaker Evaluator Dispatch and Skill Packaging Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make target-owned Breaker evaluation a trusted, persisted-runtime capability and make every Fighter sandbox load the canonical `arena-fighter-skills` package without exposing evaluator material.

**Architecture:** Keep the existing `TargetBundle` → `AdvancedExecutor` → `ToolSession` → trusted verifier pipeline as the only execution engine. A target manifest names a private evaluator entrypoint; the host verifier runs that entrypoint in a separate, sanitized subprocess using a versioned JSON protocol, then constructs host-owned `TrustedBreakerSemanticEvidence`. Skill bodies resolve through one shared packaging helper and are mounted into the Fighter image at `/opt/arena-skills`; `.agents/skills` remains only the participant workspace mount used by the existing skill tools.

**Tech Stack:** Python 3.11, FastAPI, Modal image/Volume packaging, `subprocess`, JSON protocol, Pydantic agent configuration, pytest, Neon/PostgreSQL persistence, existing SSE/event/replay layers.

**Spec:** `../AG+GPT/shared/handoffs/2026-09-16-breaker-ecosystem-and-verifier-handoff.md` plus the operator-provided Antigravity report `llm_client keeps content + tool_calls only`.

## Global Constraints

- Neon/PostgreSQL remains authoritative for Battle status, events, official results, and ratings.
- Hidden tests, reference solutions, evaluator source, evaluator stdout/stderr, and semantic diagnostics stay on the trusted host/evaluator boundary.
- Fighter/model/public/SSE/replay payloads contain only sanitized public mission data and allowlisted semantic finding names; never hidden content or verifier process output.
- A Breaker win requires a valid `exploit.py`, execution started and completed, process return code `0`, and a target-owned evaluator result with `condition_checked=True` and `condition_passed=True`.
- Missing, malformed, timed-out, or failed evaluators are infrastructure failures, never Breaker losses or wins.
- A model claim, stdout marker, `rc=0` by itself, judge prose, or canned benchmark output is not semantic evidence.
- Preserve the configured AgentConfig/registry layer and the existing runtime; do not create a parallel runner or redesign agent selection.
- Do not trigger `modal deploy` in this work; Cursor owns the deployment gate after the scoped changes are committed and verified.
- Keep ignored private evaluator bodies out of public Git; only manifests, protocol code, and hermetic synthetic fixtures belong in the repository.
- Preserve unrelated AG/user edits in the dirty worktree; stage only reviewed files for the scoped commit.

## Current Repository Findings (baseline for execution)

- The worktree is intentionally dirty on `main`, with broad AG runtime/config/UI/database changes, tracked `.agents/skills` removals, and an untracked `arena-fighter-skills/` tree. No reset, stash, cleanup, or overwrite is allowed.
- `target_verifier.py` already contains a partial `_run_breaker_evaluator()` implementation, but it assumes every evaluator consumes stdin JSON and emits exactly one JSON object. The synthetic Builder/Breaker fixture does not create such a harness, while several ignored full-stack harnesses still inspect `BREAKER_OUTPUT` markers.
- `verify_builder_breaker_submission()` now dispatches only after a completed Breaker process with return code `0`; `_semantic_record()` also requires a valid artifact, started/completed execution, trusted evidence IDs, and allowlisted findings. Existing tests still include one explicit trusted-evidence case with return code `7`, which must be made consistent with the required conjunction.
- `TargetVerificationConfig.breaker_evaluator` currently defaults for every target, including solo targets. The compiled config carries `evaluator_hash`, while Fighter-visible config strips it. This needs a format-aware contract and tests for absent/mismatched private evaluators.
- `runtime_packaging.py`, `modal_entry.py`, `sandbox_launcher.py`, and `skill_pool.py` have a partial canonical-root reconciliation. The source helper must be tested, and the distinction between host source `arena-fighter-skills` and participant workspace `.agents/skills` must remain explicit.
- The focused command `./.venv/bin/python -m pytest tests/test_builder_breaker_semantic_verification.py tests/test_target_executor_e2e.py tests/test_runtime_packaging.py -q` currently reports `26 passed`; those tests do not yet prove an automatically dispatched evaluator can turn a real `rc=0` exploit into a Breaker win.
- The report’s model-loop concerns are confirmed: `ModelResponse` retains text/native tool calls but no reasoning field; the executor appends flattened assistant/user tool feedback; the system prompt is rebuilt each turn; and tool feedback is clipped. Those are a follow-up runtime milestone after the verifier/packaging gate, not a reason to replace the current engine now.

## File Map

**Trusted target contract and verifier**

- Modify `backend/agent_arena/target_library.py` — format-aware evaluator path validation, evaluator hash calculation, frozen-config fields, and Fighter stripping.
- Modify `backend/agent_arena/target_verifier.py` — private evaluator subprocess protocol, strict result validation, process/evaluator conjunction, and host-only diagnostics.
- Modify `backend/agent_arena/finalization.py` — defense-in-depth promotion of only valid trusted Breaker evidence.
- Modify `backend/agent_arena/internal_router.py` and `backend/agent_arena/sandbox/executors/advanced_executor.py` — verify the frozen evaluator hash before trusted verification executes.
- Modify `backend/agent_arena/battle_public.py` if needed — keep evaluator hashes, paths, and all verifier output private in owner, SSE, and replay payloads.

**Hermetic private evaluator fixture and regression tests**

- Modify `backend/tests/eval_fixtures.py` — create a protocol-compatible synthetic private Breaker evaluator that checks a target postcondition, not a Fighter stdout marker.
- Modify `backend/tests/test_builder_breaker_semantic_verification.py` — cover automatic dispatch, pass/fail conditions, process return-code gating, evaluator failures, and no-leak behavior.
- Modify `backend/tests/test_target_executor_e2e.py` — prove the normal in-process executor’s Builder/Breaker phase records trusted semantic evidence without using `FakeTransport` as production behavior.
- Modify `backend/tests/test_evaluator_secrecy.py` and `backend/tests/test_target_security.py` — assert private evaluator metadata/output never crosses Fighter/public boundaries.

**Skill packaging**

- Modify `backend/agent_arena/runtime_packaging.py` — one resolver for `ARENA_SKILLS_ROOT`, `/opt/arena-skills`, and the committed `arena-fighter-skills` fallback; fail closed when empty; one image attachment helper.
- Modify `backend/modal_entry.py` and `backend/agent_arena/sandbox_launcher.py` — attach the canonical source through the helper after Python sources and keep the evaluator Volume private.
- Modify `backend/agent_arena/sandbox/executors/skill_pool.py` — resolve source bodies through the shared helper; keep participant workspace mounting at `.agents/skills`.
- Modify `backend/tests/test_runtime_packaging.py` — assert canonical source selection, image mount destination, legacy-path absence, and missing-root failure.

**Later report-driven runtime milestone (separate gate)**

- Modify `backend/agent_arena/tool_protocol.py`, `backend/agent_arena/llm_client.py`, `backend/agent_arena/sandbox/client.py`, and `backend/agent_arena/sandbox/executors/advanced_executor.py` only after the evaluator gate: preserve provider-native assistant/tool messages and reasoning metadata, avoid treating reasoning-only turns as parse failures, and compact old tool reads without changing security policy.
- Modify `backend/agent_arena/fighter_context.py` and agent profiles only with target-specific tests: keep generic Builder/Fighter guidance general, move auth-specific coaching to specialized profiles, and make persona prose subordinate to runtime policy.

---

### Task 1: Lock the trusted evaluator protocol with failing tests

**Files:**
- Modify: `backend/tests/eval_fixtures.py`
- Modify: `backend/tests/test_builder_breaker_semantic_verification.py`
- Modify: `backend/tests/test_evaluator_secrecy.py`

**Interfaces:**
- The private evaluator entrypoint is a Python file under the evaluator package, selected by `TargetVerificationConfig.breaker_evaluator`.
- Input is one JSON object on stdin:

```json
{
  "schema_version": 1,
  "target_id": "synthetic-bb-reference",
  "manifest_hash": "...",
  "evaluator_hash": "...",
  "builder_files": {"app.py": "..."},
  "breaker_files": {"exploit.py": "..."}
}
```

- Output must be exactly one JSON object with these keys and no others:

```json
{
  "schema_version": 1,
  "condition_checked": true,
  "condition_passed": true,
  "findings": ["unauthorized_mutation"]
}
```

- `findings` is limited to `server_crashed`, `availability_degraded`, `unauthorized_mutation`, and `flag_captured`; a passing result must include at least one finding and a failing result must include none.

- [ ] Add a synthetic private harness to `write_builder_breaker_reference_target()` that materializes the submitted `app.py`/`exploit.py` snapshots in its own temporary directory, executes the exploit against the target-owned application, and checks a structured target postcondition. It must not read `BREAKER_OUTPUT`, model prose, or an attacker-controlled marker as proof.
- [ ] Add a test with a vulnerable starter Builder and a valid `rc=0` exploit that calls `verify_builder_breaker_submission()` without injected trusted evidence. Expect `breaker_semantic_evidence.trusted_condition_checked is True`, `trusted_condition_passed is True`, a non-empty `evidence_ids` list, `findings == ["unauthorized_mutation"]`, and `breaker_passed is True`.
- [ ] Add the hardened-reference Builder case. The same executable exploit must yield `condition_checked=True`, `condition_passed=False`, `breaker_passed=False`, and `builder_passed=True` when visible and hidden Builder tests pass.
- [ ] Add tests proving exploit stdout such as `FLAG{attacker-claim}`, `BREAKER_EXPLOIT_SUCCESS`, or JSON claiming success does not create trusted evidence when the evaluator reports false or is absent.
- [ ] Add a secrecy assertion that hidden test text, reference source, evaluator source, evaluator stdout, and evaluator stderr are absent from all `client.round()`/public payload fields generated by the verification path.
- [ ] Run the new tests before implementation:

```bash
cd backend
PYTHONPATH=. .venv/bin/pytest tests/test_builder_breaker_semantic_verification.py -q
```

Expected result: the new automatic-dispatch assertions fail because the current fixture has no protocol-compatible harness and the current fallback returns no trusted evidence.

### Task 2: Make the target manifest and hash contract format-aware

**Files:**
- Modify: `backend/agent_arena/target_library.py`
- Modify: `backend/tests/test_target_security.py`
- Modify: `backend/tests/test_evaluator_secrecy.py`
- Modify: `backend/tests/test_target_executor_e2e.py`

**Interfaces:**
- `TargetVerificationConfig.breaker_evaluator` is an empty string for non-Builder/Breaker formats and resolves to the target’s declared path (with backwards-compatible `tests/breaker_harness.py` default only for `format: builder_breaker`).
- `TargetBundle.evaluator_hash` is deterministic over private evaluator programs/fixtures, while `hidden_hash` remains the hidden-test hash.
- `compile_target_to_battle_config()` includes `evaluator_hash` and the trusted evaluator path; `fighter_visible_battle_config()` removes both.

- [ ] Parse `verification` as a mapping and validate `breaker_evaluator` only when non-empty: normalize with `_validate_safe_relative_path()`, require `tests/` prefix, require `.py`, and reject wildcards or traversal.
- [ ] Reject a Builder/Breaker bundle whose private overlay has no configured evaluator entrypoint. Keep solo targets valid without a Breaker evaluator.
- [ ] Compute evaluator hash from the evaluator entrypoint and non-hidden/private support files in a stable sorted order; do not expose private file contents or hashes in public target details.
- [ ] Include the evaluator path/hash in the frozen internal config and validate the hash in `internal_router.internal_verify()` and `AdvancedExecutor._verify_target_trusted()` before running verification.
- [ ] Add tests for safe-path rejection, solo-without-evaluator acceptance, Builder/Breaker missing-evaluator failure, frozen hash mismatch failure, and Fighter/public stripping.
- [ ] Run:

```bash
cd backend
PYTHONPATH=. .venv/bin/pytest tests/test_target_security.py tests/test_evaluator_secrecy.py tests/test_target_executor_e2e.py -q
```

### Task 3: Implement isolated target-owned evaluator dispatch

**Files:**
- Modify: `backend/agent_arena/target_verifier.py`
- Modify: `backend/tests/test_builder_breaker_semantic_verification.py`

**Interfaces:**
- Keep `_run_breaker_evaluator(bundle, builder_files, breaker_files, *, timeout_seconds)` as the single dispatch helper returning `TrustedBreakerSemanticEvidence | None`.
- The helper writes private fixtures into a temporary trusted directory, runs `[sys.executable, "-I", evaluator_path]`, sends the canonical JSON request, and returns only structured semantic fields.

- [ ] Validate the evaluator path again at dispatch time and refuse paths not present in `bundle.private_fixture_files`.
- [ ] Build evaluator input from sanitized text snapshots; exclude blocked submission paths and do not include hidden outputs, reference contents, host environment, control-plane URLs, or Fighter stdout/stderr.
- [ ] Run with a minimal allowlisted environment, a private `HOME`/`TMPDIR`, no `ARENA_FLAG`, no network permission, bounded stdout/stderr capture, and the configured timeout. Keep raw diagnostics in trusted host memory/logging only, truncated and never persisted to public events.
- [ ] Parse the exact result schema. Reject extra keys, wrong types, unknown findings, missing findings on a pass, findings on a fail, oversized output, non-zero evaluator return code, timeout, malformed JSON, and missing entrypoint with a stable `verifier_error`.
- [ ] Derive the evidence ID host-side from the canonical request plus evaluator hash; never accept an evidence ID supplied by the Fighter or evaluator as authority.
- [ ] Invoke the helper in `verify_builder_breaker_submission()` only after a valid Breaker artifact has started, completed, and returned `0`, unless trusted evidence was explicitly supplied by an already-trusted runtime.
- [ ] Preserve the same conjunction for explicit evidence: `valid_breaker_artifact AND execution_started AND execution_completed AND process_return_code == 0 AND trusted_condition_checked AND trusted_condition_passed AND non-empty evidence/findings`.
- [ ] Return `verification_status="infra_failure"` for evaluator infrastructure/protocol errors, and keep `breaker_passed=False`; never reinterpret those errors as a battle loss.
- [ ] Add tests for evaluator pass, evaluator false, evaluator timeout, evaluator non-zero exit, malformed output, unknown finding, oversized output, missing evaluator, and process `rc=7` with otherwise-true trusted evidence.
- [ ] Run:

```bash
cd backend
PYTHONPATH=. .venv/bin/pytest tests/test_builder_breaker_semantic_verification.py -q
```

### Task 4: Harden asymmetric scoring and public authority boundaries

**Files:**
- Modify: `backend/agent_arena/finalization.py`
- Modify: `backend/agent_arena/battle_public.py`
- Modify: `backend/agent_arena/internal_router.py`
- Modify: `backend/agent_arena/sandbox/executors/advanced_executor.py`
- Modify: `backend/tests/test_builder_breaker_semantic_verification.py`
- Modify: `backend/tests/test_live_battle_result_truth.py`
- Modify: `backend/tests/test_evaluator_secrecy.py`

**Interfaces:**
- Finalization consumes persisted trusted verification records and produces official role outcomes; it never consumes judge prose or model claims as authority.

- [ ] Keep `_trusted_breaker_semantic_passed()` fail-closed on missing/invalid evidence, non-zero process return code, missing evidence IDs, unknown findings, or `verifier_error`.
- [ ] Promote Breaker success only when the trusted semantic record passes; keep Builder success asymmetric (`visible_passed && hidden_passed && !trusted_breaker_passed`).
- [ ] Preserve `judge-v1` output as advisory scoring/justification only; do not let a judge score create semantic evidence or override infrastructure failure.
- [ ] Ensure verifier records retain only bounded trusted semantic fields in persisted results. Do not serialize `builder_output`, `hidden_output`, `visible_output`, `breaker_output`, evaluator source, or evaluator process output into public battle events, SSE, replay, owner API payloads, or Fighter context.
- [ ] Add regression assertions that a hidden marker placed in hidden tests or evaluator stderr cannot be found in `/internal/round` payloads, public battle JSON, SSE event data, or replay records.
- [ ] Run:

```bash
cd backend
PYTHONPATH=. .venv/bin/pytest tests/test_builder_breaker_semantic_verification.py tests/test_live_battle_result_truth.py tests/test_evaluator_secrecy.py -q
```

### Task 5: Prove the normal executor’s Builder/Breaker integration

**Files:**
- Modify: `backend/tests/test_target_executor_e2e.py`
- Inspect/modify only if a test demonstrates a defect: `backend/agent_arena/sandbox/executors/advanced_executor.py`, `backend/agent_arena/sandbox/client.py`

**Interfaces:**
- `compile_target_to_battle_config()` feeds the existing `AdvancedExecutor` battle plan; the `build` and `break` phases share only the configured handoff artifacts; the trusted verifier runs after the Breaker phase.

- [ ] Extend the synthetic normal executor test so the Breaker writes a valid exploit and the target-owned evaluator is automatically invoked through the same verifier call used by the phase finalization.
- [ ] Assert the result event contains only `breaker_semantic_evidence`’s allowlisted fields and role verdicts, not hidden output or evaluator diagnostics.
- [ ] Assert an evaluator failure produces an infrastructure terminal reason and does not award a Breaker win or mark the Builder as defeated by model behavior.
- [ ] Assert model tool schemas are filtered from the AgentConfig permission set and dispatch rejects a forged disallowed call; do not add a second execution loop.
- [ ] Run the requested integration suites:

```bash
cd backend
PYTHONPATH=. .venv/bin/pytest tests/test_target_executor_e2e.py -q
PYTHONPATH=. .venv/bin/pytest tests/test_builder_breaker_semantic_verification.py -q
```

### Task 6: Reconcile canonical Fighter skill packaging

**Files:**
- Modify: `backend/agent_arena/runtime_packaging.py`
- Modify: `backend/modal_entry.py`
- Modify: `backend/agent_arena/sandbox_launcher.py`
- Modify: `backend/agent_arena/sandbox/executors/skill_pool.py`
- Modify: `backend/tests/test_runtime_packaging.py`
- Modify: `backend/tests/test_agent_ecosystem.py`

**Interfaces:**
- `fighter_skill_directory() -> Path` resolves `ARENA_SKILLS_ROOT` when explicitly configured, `/opt/arena-skills` inside a Modal runtime, otherwise the committed repository `arena-fighter-skills` directory. A configured but missing/empty path fails closed.
- `attach_fighter_skills(image) -> image` mounts exactly that source at `/opt/arena-skills`.
- `mount_skills(workdir, pool)` continues to copy the permitted bundle into the participant’s workspace `.agents/skills`; that destination is not a host source lookup and must not be removed without a separate tool-contract change.

- [ ] Remove all host-source fallbacks from `backend/modal_entry.py`, `sandbox_launcher.py`, and `skill_pool.py` that point to `.agents/skills`.
- [ ] Keep canonical YAML attachment after `add_local_python_source("agent_arena")`; keep evaluator material on the read-only named Volume and never add it to Fighter images.
- [ ] Add a package-root test that `arena-fighter-skills/<skill>/SKILL.md` is selected when no env/mount exists, an env override is selected when valid, and a missing/empty env override raises `FileNotFoundError` during image attachment.
- [ ] Add an image fake recording `add_local_dir()` calls and assert the source is the canonical root and remote path is `/opt/arena-skills`.
- [ ] Add source scans asserting no legacy `.agents/skills` host lookup remains in packaging/Modal entry code while the intentional workspace destination remains in `mount_skills()` and its tests.
- [ ] Run:

```bash
cd backend
PYTHONPATH=. .venv/bin/pytest tests/test_runtime_packaging.py tests/test_agent_ecosystem.py -q
```

### Task 7: Re-verify the AgentConfig-to-runtime contract without redesign

**Files:**
- Modify tests first: `backend/tests/test_agent_ecosystem.py`, `backend/tests/test_fighter_tool_boundaries.py`, `backend/tests/test_fighter_runtime.py`
- Modify implementation only where a failing test identifies a concrete gap: `backend/agent_arena/sandbox/agent_runtime.py`, `backend/agent_arena/sandbox/executors/advanced_executor.py`, `backend/agent_arena/providers.py`, `backend/agent_arena/agents/models.py`

- [ ] Verify preferred/fallback model IDs resolve through the existing provider layer; provider-specific reasoning request fields remain in the provider layer, not in battle orchestration.
- [ ] Verify `AgentConfig.tool_permissions` filters advertised schemas and is enforced again at `ToolSession` dispatch, including `reviewer-security`’s read-only restriction.
- [ ] Verify every configured `skill_bundle` is loaded from the canonical root and an absent skill fails closed; no global skill pool widens a restricted agent.
- [ ] Verify role turn, tool-step, per-tool timeout, and total timeout budgets are min-capped against the battle budget and terminal states distinguish provider/runtime failures from fighter losses.
- [ ] Verify persona and target mission text cannot grant tools, reveal private metadata, or manufacture trusted verifier evidence; keep security instructions in runtime/tool/verifier code.
- [ ] Verify judge output remains advisory and cannot promote a result; verify model prose and stdout are never copied into trusted evidence records.
- [ ] Run:

```bash
cd backend
PYTHONPATH=. .venv/bin/pytest tests/test_agent_ecosystem.py tests/test_fighter_tool_boundaries.py tests/test_fighter_runtime.py tests/test_advanced_executor_hardening.py -q
```

### Task 8: Address the report’s model-loop defects as a separately gated follow-up

**Files:**
- Modify: `backend/agent_arena/tool_protocol.py`
- Modify: `backend/agent_arena/llm_client.py`
- Modify: `backend/agent_arena/sandbox/client.py`
- Modify: `backend/agent_arena/sandbox/executors/advanced_executor.py`
- Modify: `backend/tests/test_tool_protocol.py`
- Modify: `backend/tests/test_advanced_executor.py`

- [ ] Extend the response model to preserve provider reasoning metadata separately from user-visible content and native tool calls; redacted reasoning may be persisted only where the existing trusted telemetry policy allows.
- [ ] Preserve the provider dialect: when a provider returns native `assistant.tool_calls`, append the native assistant message and matching `role=tool` messages with `tool_call_id`; use line grammar only as a fallback after a native parse miss.
- [ ] Treat a reasoning-only response as a recoverable non-action turn, not an automatic parse failure; retain the existing consecutive parse-failure limit for genuinely malformed action responses.
- [ ] Keep the system persona stable after turn 0 and refresh only dynamic budget/workspace/tool feedback; compact old read dumps with bounded deterministic summaries instead of repeatedly clipping arbitrary history at 4k.
- [ ] Add tests for reasoning-only responses, native tool-call round trips, tool-call IDs, parse-recovery counters, and bounded conversation size. Do not change verifier or permission semantics while doing this follow-up.

### Task 9: Verify the real persisted lifecycle and commit the scoped work

**Files:**
- No new production files; use the existing persistence/SSE/Modal entrypoints and the tests above.

- [ ] Run the complete required regression set from `backend/`:

```bash
PYTHONPATH=. .venv/bin/pytest tests/test_builder_breaker_semantic_verification.py
PYTHONPATH=. .venv/bin/pytest tests/test_target_executor_e2e.py
PYTHONPATH=. .venv/bin/pytest tests/test_runtime_packaging.py
PYTHONPATH=. .venv/bin/pytest tests/test_sandbox_boot_failure.py
PYTHONPATH=. .venv/bin/pytest tests/test_agent_ecosystem.py
```

- [ ] Run the broader hermetic backend suite with the repository’s configured exclusions:

```bash
./.venv/bin/python -m pytest --ignore=tests/evals -q
```

- [ ] Run `git diff --check` and source scans for hidden-output keys, evaluator paths, and legacy skill-source lookups. Review the complete staged diff for unrelated user/AG changes before staging.
- [ ] Commit the reviewed evaluator/packaging/runtime changes with a message such as `feat: dispatch trusted breaker evaluators`; do not include ignored evaluator bodies or accidentally stage unrelated WIP.
- [ ] Do not deploy in this task. After the commit, run one normal persisted Builder-v1 battle only when the deploy gate is opened. Use the real provider/runtime path, not `AgentBenchmarkHarness`, `FakeTransport`, `ARENA_ALLOW_DIRECT_BENCHMARK`, or verifier bypass flags.
- [ ] For that certification, record the earliest reached level exactly: `CONFIGURED`, `WIRED`, `REAL MODEL CALLED`, `REAL TOOL LOOP`, `REAL SANDBOX EXECUTION`, `TRUSTED VERIFIED`, or `PERSISTED FULL BATTLE`.
- [ ] Acceptance for `PERSISTED FULL BATTLE`: Neon shows authoritative status transition and terminal result, `started_at` is non-null after entering `running`, model/tool/phase events have ordered sequences, the evaluator evidence is present without private output, official finalization is authoritative, and SSE/replay expose the same sanitized lifecycle.

## Self-Review Checklist

- [ ] Every operator requirement maps to a task: evaluator dispatch (Tasks 1–5), skill packaging (Task 6), AgentConfig/runtime contract (Task 7), report findings (Task 8), and real persisted verification/deploy gate (Task 9).
- [ ] No task authorizes a benchmark shortcut, verifier bypass, private evaluator commit, or second runtime.
- [ ] All success paths require both execution telemetry and trusted target-owned semantics; all infrastructure failures remain distinct.
- [ ] The intentional `.agents/skills` participant workspace path is not confused with the removed host/deploy source path.
- [ ] Test commands are runnable from `backend/` and cover both positive and fail-closed cases.
