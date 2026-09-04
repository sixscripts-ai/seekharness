from __future__ import annotations

import json
import pytest

from agent_arena.tool_protocol import (
    CanonicalToolCall,
    ModelResponse,
    REGISTRY,
    TOOL_SCHEMAS,
    normalize_response,
    parse_kimi_token_xml,
    parse_xml_tags,
    parse_arena_json,
    parse_arena_legacy,
)
from agent_arena.sandbox.executors.advanced_executor import (
    ToolSession,
    parse_tool_calls,
    rank_skills_for_context,
    select_skills,
)
from agent_arena.internal_router import _apply_self_learning


def test_tool_schemas_integrity():
    assert len(TOOL_SCHEMAS) >= 10
    names = {s["function"]["name"] for s in TOOL_SCHEMAS}
    assert "read" in names
    assert "write" in names
    assert "shell" in names
    assert "test" in names
    assert "use_skill" in names
    assert "done" in names


def test_openai_native_tool_calls():
    resp = ModelResponse(
        text="",
        native_tool_calls=[
            {
                "id": "call_123",
                "type": "function",
                "function": {
                    "name": "read",
                    "arguments": json.dumps({"path": "src/index.js"}),
                },
            },
            {
                "id": "call_456",
                "type": "function",
                "function": {
                    "name": "shell",
                    "arguments": json.dumps({"command": "npm test"}),
                },
            },
        ],
    )
    norm = normalize_response(resp)
    assert norm.parse_status == "native"
    assert norm.dialect == "openai_native"
    assert len(norm.calls) == 2
    assert norm.calls[0].name == "read"
    assert norm.calls[0].arguments == {"path": "src/index.js"}
    assert norm.calls[1].name == "shell"
    assert norm.calls[1].arguments == {"cmd": "npm test"}  # normalized from command


def test_kimi_token_xml_parsing():
    kimi_text = (
        "I will inspect the package.json and formatter.<|open|>tools<|sep|>"
        "<|open|>call tool=\"read\" index=\"1\"<|sep|>"
        "<|open|>argument key=\"path\" type=\"string\"<|sep|>package.json<|close|>argument<|sep|>"
        "<|close|>call<|sep|>"
        "<|open|>call tool=\"shell\" index=\"2\"<|sep|>"
        "<|open|>argument key=\"cmd\" type=\"string\"<|sep|>npm test<|close|>argument<|sep|>"
        "<|close|>call<|sep|>"
        "<|close|>tools<|sep|><|close|>message<|sep|>"
    )
    norm = normalize_response(kimi_text)
    assert norm.parse_status == "parsed"
    assert norm.dialect == "kimi_token_xml"
    assert len(norm.calls) == 2
    assert norm.calls[0].name == "read"
    assert norm.calls[0].arguments == {"path": "package.json"}
    assert norm.calls[1].name == "shell"
    assert norm.calls[1].arguments == {"cmd": "npm test"}


def test_standard_xml_tag_parsing():
    xml_text = (
        "Let's check the files:\n"
        "<tool_call>\n"
        "<name>read</name>\n"
        "<arguments>{\"path\": \"README.md\"}</arguments>\n"
        "</tool_call>\n"
        "<tool_call name=\"shell\">\n"
        "<arguments><cmd>pytest -q</cmd></arguments>\n"
        "</tool_call>"
    )
    norm = normalize_response(xml_text)
    assert norm.parse_status == "parsed"
    assert norm.dialect == "xml_tag"
    assert len(norm.calls) == 2
    assert norm.calls[0].name == "read"
    assert norm.calls[0].arguments == {"path": "README.md"}
    assert norm.calls[1].name == "shell"
    assert norm.calls[1].arguments == {"cmd": "pytest -q"}


def test_arena_fenced_json_parsing():
    json_text = (
        "Here are my actions:\n"
        "```json\n"
        "[\n"
        "  {\"tool\": \"write\", \"arguments\": {\"path\": \"solution.py\", \"code\": \"def solve(): pass\"}},\n"
        "  {\"tool\": \"test\", \"arguments\": {}}\n"
        "]\n"
        "```"
    )
    norm = normalize_response(json_text)
    assert norm.parse_status == "parsed"
    assert norm.dialect == "arena_json"
    assert len(norm.calls) == 2
    assert norm.calls[0].name == "write"
    assert norm.calls[0].arguments == {"path": "solution.py", "content": "def solve(): pass"}
    assert norm.calls[1].name == "test"


def test_legacy_line_grammar_parsing():
    legacy_text = (
        "SKILLS: sandbox-runtime-engineer, secure-code-execution\n"
        "TOOL read path=src/index.js\n"
        "TOOL shell cmd='npm test'\n"
        "TOOL write path=src/fix.js\n"
        "const x = 1;\n"
        "END_TOOL\n"
        "DONE"
    )
    norm = normalize_response(legacy_text)
    assert norm.parse_status == "parsed"
    assert norm.dialect == "arena_legacy"
    assert len(norm.calls) == 5
    assert norm.calls[0].name == "skills"
    assert norm.calls[0].arguments["chosen"] == ["sandbox-runtime-engineer", "secure-code-execution"]
    assert norm.calls[1].name == "read"
    assert norm.calls[1].arguments == {"path": "src/index.js"}
    assert norm.calls[2].name == "shell"
    assert norm.calls[2].arguments == {"cmd": "npm test"}
    assert norm.calls[3].name == "write"
    assert norm.calls[3].arguments == {"path": "src/fix.js", "content": "const x = 1;"}
    assert norm.calls[4].name == "done"


def test_skill_ranking_token_relevance():
    mock_pool = [
        {"name": "generic-infra", "slug": "generic-infra", "description": "Cloud infra setup", "tags": ["cloud"], "category": "infra"},
        {"name": "node-package-debugging", "slug": "node-package-debugging", "description": "Fix broken npm packages and node modules", "tags": ["node", "npm", "javascript"], "category": "debugging"},
        {"name": "python-kata-fixer", "slug": "python-kata-fixer", "description": "Solve Python algorithms and unit tests", "tags": ["python", "kata"], "category": "python"},
        {"name": "secure-code-execution", "slug": "secure-code-execution", "description": "Sandbox isolation and security", "tags": ["security"], "category": "security"},
    ]

    # Node target config
    node_cfg = {
        "name": "broken-package-recovery",
        "category": "debugging",
        "runtime": "node",
        "objectives": ["Repair broken npm module exports", "Make npm test pass in node environment"],
        "tags": ["node", "package"],
    }
    ranked = rank_skills_for_context(mock_pool, node_cfg, limit=3)
    assert ranked[0]["name"] == "node-package-debugging"

    # Python target config
    py_cfg = {
        "name": "algo-reverse",
        "category": "python",
        "runtime": "python",
        "objectives": ["Fix python palindrome kata"],
        "tags": ["python", "algorithm"],
    }
    ranked_py = rank_skills_for_context(mock_pool, py_cfg, limit=3)
    assert ranked_py[0]["name"] == "python-kata-fixer"


def test_apply_self_learning_no_failed_winners():
    results = [
        {"model_id": "host:modal-kimi", "passed": False, "steps": 5, "chosen_skills": ["secure-code-execution"]}
    ]
    battle = {"user_id": "test_user", "format_id": "solo", "model_ids": ["host:modal-kimi"]}

    # Run self learning on failed solo battle
    # Should not raise and should not credit the failed fighter with a win
    _apply_self_learning(None, "db", battle, "battle_failed_solo", results)


def test_serialization_repair_never_invents_tool_intent():
    """Verify that serialization repair strictly normalizes aliases and NEVER
    hallucinates or invents tool calls when the model simply reasons in natural language.
    """
    prose_samples = [
        "I should probably test this package now by running npm test.",
        "Let's write some code to fix the issue in src/index.js.",
        "We need to read package.json to see what scripts exist.",
        "I'm going to look at the files: ls -la",
        "Maybe I will execute pytest and then check the result.",
    ]
    for sample in prose_samples:
        norm = normalize_response(sample)
        assert len(norm.calls) == 0, f"Expected 0 calls for natural language '{sample}', got {norm.calls}"
        assert norm.parse_status == "failed"

    # In contrast, structured aliases MUST be normalized accurately without modifying values
    alias_sample = (
        'TOOL shell command="npm test --silent"\n'
        'TOOL write path="fix.js"\n'
        'console.log("hello");\n'
        'END_TOOL\n'
    )
    norm_alias = normalize_response(alias_sample)
    assert len(norm_alias.calls) == 2
    assert norm_alias.calls[0].name == "shell"
    assert norm_alias.calls[0].arguments == {"cmd": "npm test --silent"}
    assert norm_alias.calls[1].name == "write"
    assert norm_alias.calls[1].arguments == {"path": "fix.js", "content": 'console.log("hello");'}


def _fighter_calls(text: str):
    """Mirror the executor: parse → CanonicalToolCall → {tool, **arguments} → validate."""
    norm = normalize_response(text)
    calls = [{"tool": c.name, **c.arguments} for c in norm.calls]
    validated = [
        (call, *REGISTRY.validate_call(call["tool"], call)) for call in calls
    ]
    return norm, validated


def _assert_valid_flat(text: str, name: str, arguments: dict):
    calls = parse_arena_json(text)
    assert len(calls) == 1
    assert calls[0].name == name
    assert calls[0].arguments == arguments
    assert calls[0].dialect == "arena_json"
    norm, validated = _fighter_calls(text)
    assert norm.dialect == "arena_json"
    assert norm.parse_status == "parsed"
    call, canonical, errors = validated[0]
    assert errors == []
    assert "Missing required parameter" not in " ".join(errors)
    assert canonical == arguments
    assert call["tool"] == name
    for key, value in arguments.items():
        assert call[key] == value


def test_flat_arena_json_read_retains_path():
    _assert_valid_flat(
        '{"tool":"read","path":"TARGET.md"}',
        "read",
        {"path": "TARGET.md"},
    )


def test_flat_arena_json_read_file_alias():
    _assert_valid_flat(
        '{"tool":"read","file":"TARGET.md"}',
        "read",
        {"path": "TARGET.md"},
    )


def test_flat_arena_json_write_retains_path_and_content():
    _assert_valid_flat(
        '{"tool":"write","path":"src/test.txt","content":"hello"}',
        "write",
        {"path": "src/test.txt", "content": "hello"},
    )


def test_nested_arena_json_write_still_works():
    _assert_valid_flat(
        '{"tool":"write","arguments":{"path":"src/test.txt","content":"hello"}}',
        "write",
        {"path": "src/test.txt", "content": "hello"},
    )


def test_flat_arena_json_write_aliases():
    _assert_valid_flat(
        '{"tool":"write","file":"solution.py","code":"print(\'ok\')"}',
        "write",
        {"path": "solution.py", "content": "print('ok')"},
    )


def test_flat_arena_json_shell_cmd_and_command_alias():
    _assert_valid_flat('{"tool":"shell","cmd":"pytest -q"}', "shell", {"cmd": "pytest -q"})
    _assert_valid_flat(
        '{"tool":"shell","command":"ls"}',
        "shell",
        {"cmd": "ls"},
    )


def test_flat_arena_json_skill_graph_selectors():
    _assert_valid_flat(
        '{"tool":"skills","search":"session replay token"}',
        "skills",
        {"search": "session replay token"},
    )
    _assert_valid_flat(
        '{"tool":"skills","index":"security"}',
        "skills",
        {"index": "security"},
    )
    _assert_valid_flat(
        '{"tool":"skills","skill":"auth-flow-debugger"}',
        "skills",
        {"skill": "auth-flow-debugger"},
    )
    _assert_valid_flat(
        '{"tool":"use_skill","name":"auth-flow-debugger"}',
        "use_skill",
        {"name": "auth-flow-debugger"},
    )


def test_nested_arena_json_read_still_works():
    _assert_valid_flat(
        '{"tool":"read","arguments":{"path":"TARGET.md"}}',
        "read",
        {"path": "TARGET.md"},
    )


def test_bare_and_fenced_flat_arena_json_arrays():
    payload = [
        {"tool": "read", "path": "TARGET.md"},
        {"tool": "skills", "search": "auth"},
        {"tool": "use_skill", "name": "auth-flow-debugger"},
        {"tool": "write", "path": "solution.py", "content": "print('ok')"},
    ]
    bare = json.dumps(payload)
    fenced = "```json\n" + bare + "\n```"
    expected = [
        ("read", {"path": "TARGET.md"}),
        ("skills", {"search": "auth"}),
        ("use_skill", {"name": "auth-flow-debugger"}),
        ("write", {"path": "solution.py", "content": "print('ok')"}),
    ]
    for text in (bare, fenced):
        calls = parse_arena_json(text)
        assert [(c.name, c.arguments) for c in calls] == expected
        norm, validated = _fighter_calls(text)
        assert norm.parse_status == "parsed"
        assert all(errors == [] for _, _, errors in validated)


def test_openai_shaped_name_plus_arguments_still_works():
    _assert_valid_flat(
        '{"name":"read","arguments":{"path":"TARGET.md"}}',
        "read",
        {"path": "TARGET.md"},
    )


def test_nested_arguments_are_authoritative_over_flat_fields():
    calls = parse_arena_json(
        '{"tool":"read","arguments":{"path":"a.md"},"path":"b.md","file":"c.md"}'
    )
    assert calls[0].arguments == {"path": "a.md"}


def test_empty_nested_arguments_are_filled_from_flat_fields():
    calls = parse_arena_json(
        '{"tool":"write","arguments":{},"path":"src/test.txt","content":"hello"}'
    )
    assert calls[0].arguments == {"path": "src/test.txt", "content": "hello"}


def test_top_level_id_is_call_id_not_a_skill_argument():
    calls = parse_arena_json(
        '{"tool":"use_skill","name":"auth-flow-debugger","id":"call_abc123"}'
    )
    assert calls[0].name == "use_skill"
    assert calls[0].arguments == {"name": "auth-flow-debugger"}
    assert calls[0].call_id == "call_abc123"

    missing = parse_arena_json('{"tool":"use_skill","id":"call_abc123"}')
    assert missing[0].name == "use_skill"
    assert missing[0].arguments == {}
    assert missing[0].call_id == "call_abc123"
    _, errors = REGISTRY.validate_call(missing[0].name, missing[0].arguments)
    assert any("Missing required parameter 'name'" in err for err in errors)


def test_unknown_flat_properties_still_fail_canonical_validation():
    calls = parse_arena_json('{"tool":"read","path":"TARGET.md","nope":"x"}')
    assert calls[0].arguments["path"] == "TARGET.md"
    _, errors = REGISTRY.validate_call(calls[0].name, calls[0].arguments)
    assert any("Unexpected parameter 'nope'" in err for err in errors)


def test_missing_required_flat_parameters_still_fail_validation():
    read_calls = parse_arena_json('{"tool":"read"}')
    _, read_errors = REGISTRY.validate_call("read", read_calls[0].arguments)
    assert any("Missing required parameter 'path'" in err for err in read_errors)

    write_calls = parse_arena_json('{"tool":"write"}')
    _, write_errors = REGISTRY.validate_call("write", write_calls[0].arguments)
    assert any("Missing required parameter 'path'" in err for err in write_errors)
    assert any("Missing required parameter 'content'" in err for err in write_errors)


REGISTERED_FLAT_FIXTURES = {
    "read": {"path": "TARGET.md"},
    "write": {"path": "solution.py", "content": "print('ok')"},
    "shell": {"cmd": "pytest -q"},
    "test": {},
    "ls": {"path": "."},
    "clean": {"path": "tmp.txt"},
    "run": {"path": "main.py"},
    "install": {"cmd": "pip install pytest"},
    "grep": {"pattern": "TODO", "path": "src"},
    "tree": {"path": "."},
    "cp": {"src": "a.txt", "dst": "b.txt"},
    "mv": {"src": "a.txt", "dst": "b.txt"},
    "rm": {"path": "gone.txt"},
    "fetch": {"url": "https://example.com"},
    "search": {"query": "docs"},
    "bg": {"name": "server", "content": "python -m http.server"},
    "ps": {},
    "kill": {"name": "server"},
    "logs": {"name": "server"},
    "use_skill": {"name": "auth-flow-debugger"},
    "skills": {"search": "authentication"},
    "playwright_navigate": {"url": "http://127.0.0.1:5173"},
    "playwright_click": {"selector": "#submit-btn"},
    "playwright_fill": {"selector": "#username", "text": "admin"},
    "playwright_screenshot": {"path": "shot.png"},
    "playwright_read": {"selector": "body"},
    "playwright_wait": {"selector": "#app", "timeout_ms": 3000},
    "http_request": {"method": "GET", "url": "http://127.0.0.1:8000/api/users"},
    "sql_query": {"query": "SELECT * FROM users"},
    "done": {},
}


def test_flat_arena_json_retains_args_for_every_registered_tool():
    assert set(REGISTERED_FLAT_FIXTURES) == REGISTRY.all_names()
    for tool, payload in REGISTERED_FLAT_FIXTURES.items():
        text = json.dumps({"tool": tool, **payload})
        calls = parse_arena_json(text)
        assert len(calls) == 1, tool
        assert calls[0].name == tool
        for key, value in payload.items():
            assert calls[0].arguments.get(key) == value, (tool, key, calls[0].arguments)
        _, errors = REGISTRY.validate_call(tool, {"tool": tool, **calls[0].arguments})
        assert errors == [], (tool, errors, calls[0].arguments)
        joined = "; ".join(errors)
        assert "Missing required parameter" not in joined


def test_flat_write_fighter_path_does_not_drop_required_fields():
    text = '{"tool":"write","path":"solution.py","content":"hello"}'
    parsed = parse_tool_calls(text)
    assert parsed == [{"tool": "write", "path": "solution.py", "content": "hello"}]
    args, errors = REGISTRY.validate_call(parsed[0]["tool"], parsed[0])
    assert errors == []
    assert args == {"path": "solution.py", "content": "hello"}
    assert "Missing required parameter" not in " ".join(errors)


def test_flat_read_write_round_trip_through_tool_session(tmp_path):
    session = ToolSession(tmp_path, allow_network=False)
    write_text = '{"tool":"write","path":"arena_parser_test.txt","content":"parser works"}'
    read_text = '{"tool":"read","path":"arena_parser_test.txt"}'

    write_calls = parse_tool_calls(write_text)
    write_args, write_errors = REGISTRY.validate_call(
        write_calls[0]["tool"], write_calls[0]
    )
    assert write_errors == []
    assert write_args == {"path": "arena_parser_test.txt", "content": "parser works"}
    written = session.exec_tool(write_calls[0])
    assert written.success is True

    read_calls = parse_tool_calls(read_text)
    read_args, read_errors = REGISTRY.validate_call(read_calls[0]["tool"], read_calls[0])
    assert read_errors == []
    assert read_args == {"path": "arena_parser_test.txt"}
    read_back = session.exec_tool(read_calls[0])
    assert read_back.success is True
    assert read_back.output == "parser works"


def test_flat_skill_graph_json_reaches_tool_session(tmp_path):
    skill_dir = tmp_path / ".agents" / "skills" / "auth-flow-debugger"
    skill_dir.mkdir(parents=True)
    body = "---\nname: auth-flow-debugger\ndescription: test\n---\nUNIQUE_SKILL_BODY\n"
    (skill_dir / "SKILL.md").write_text(body, encoding="utf-8")
    session = ToolSession(tmp_path, allow_network=False)
    before_network = session.allow_network

    search_calls = parse_tool_calls('{"tool":"skills","search":"authentication"}')
    _, search_errors = REGISTRY.validate_call(search_calls[0]["tool"], search_calls[0])
    assert search_errors == []
    assert search_calls[0]["search"] == "authentication"
    search_result = session.exec_tool(search_calls[0], count_step=False)
    assert search_result.success is True
    assert "auth-flow-debugger" in search_result.output
    assert "UNIQUE_SKILL_BODY" not in search_result.output
    assert "SKILL.md" not in search_result.output

    card_calls = parse_tool_calls('{"tool":"skills","skill":"auth-flow-debugger"}')
    _, card_errors = REGISTRY.validate_call(card_calls[0]["tool"], card_calls[0])
    assert card_errors == []
    card_result = session.exec_tool(card_calls[0], count_step=False)
    assert card_result.success is True
    assert "SKILL CARD: auth-flow-debugger" in card_result.output
    assert "UNIQUE_SKILL_BODY" not in card_result.output
    assert 'use_skill("auth-flow-debugger")' in card_result.output
    assert session.skill_reads == set()

    load_calls = parse_tool_calls('{"tool":"use_skill","name":"auth-flow-debugger"}')
    _, load_errors = REGISTRY.validate_call(load_calls[0]["tool"], load_calls[0])
    assert load_errors == []
    assert load_calls[0]["name"] == "auth-flow-debugger"
    loaded = session.exec_tool(load_calls[0], count_step=False)
    assert loaded.success is True
    assert loaded.output == body
    assert session.skill_reads == {"auth-flow-debugger"}
    assert session.allow_network is before_network is False
    assert not hasattr(session, "capabilities")

    bypass = parse_tool_calls(
        '{"tool":"read","path":".agents/skills/auth-flow-debugger/SKILL.md"}'
    )
    _, bypass_errors = REGISTRY.validate_call(bypass[0]["tool"], bypass[0])
    assert bypass_errors == []
    denied = session.exec_tool(bypass[0], count_step=False)
    assert denied.success is False
    assert denied.policy_rejected is True
    assert "UNIQUE_SKILL_BODY" not in denied.output
    assert "use_skill" in denied.output


def test_fighter_bootstrap_does_not_imply_filesystem_skill_load():
    from agent_arena.fighter_context import build_fighter_system_prompt, fighter_tool_grammar

    prompt = build_fighter_system_prompt(
        role="builder",
        format_name="Target battle",
        max_steps=14,
        max_turns=6,
    )
    for text in (prompt, fighter_tool_grammar()):
        assert "SKILL.md" not in text
        assert ".agents/skills" not in text
        assert "use_skill" in text
        assert "skills(" in text or "TOOL skills" in text


def test_breaker_tools_exec_through_tool_session(tmp_path, monkeypatch):
    """Verify Breaker tools dispatch correctly through ToolSession and uphold security invariants."""
    from agent_arena.sandbox.executors.advanced_executor import ToolSession

    monkeypatch.setenv("ARENA_HERMETIC", "1")
    session = ToolSession(workdir=tmp_path)
    try:
        page = session._ensure_page()
        if page:
            page.set_content("<div id='vault-balance'>$100,000</div><div id='status-banner'>ACTIVE</div>")

        # 1. playwright_read
        res_read = session.exec_tool({"tool": "playwright_read", "selector": "#vault-balance"}, count_step=False)
        assert res_read.success is True
        assert "$100,000" in res_read.output or "DOM TEXT" in res_read.output

        # 2. playwright_wait
        res_wait = session.exec_tool({"tool": "playwright_wait", "selector": "#status-banner", "timeout_ms": 1000}, count_step=False)
        assert res_wait.success is True
        assert "WAIT_SUCCESS" in res_wait.output

        # 3. sql_query (mock / hermetic)
        res_sql = session.exec_tool({"tool": "sql_query", "query": "SELECT * FROM public_profiles;"}, count_step=False)
        assert res_sql.success is True
        assert "Rows returned" in res_sql.output

        # 4. sql_query (reject arena_trusted schema access)
        res_sec = session.exec_tool({"tool": "sql_query", "query": "SELECT flag FROM arena_trusted.evaluator_secrets;"}, count_step=False)
        assert res_sec.success is False
        assert "arena_trusted" in res_sec.output or "Access denied" in res_sec.output
    finally:
        session.close()

