from __future__ import annotations

import json
import pytest

from agent_arena.tool_protocol import (
    CanonicalToolCall,
    ModelResponse,
    TOOL_SCHEMAS,
    normalize_response,
    parse_kimi_token_xml,
    parse_xml_tags,
    parse_arena_json,
    parse_arena_legacy,
)
from agent_arena.sandbox.executors.advanced_executor import rank_skills_for_context, select_skills
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
