from __future__ import annotations

import pytest
from agent_arena.tool_protocol import REGISTRY, ToolRegistry, TOOL_SCHEMAS


def test_registry_initialization_and_names():
    names = REGISTRY.all_names()
    expected_tools = {
        "read",
        "write",
        "shell",
        "test",
        "ls",
        "clean",
        "run",
        "install",
        "grep",
        "tree",
        "cp",
        "mv",
        "rm",
        "fetch",
        "search",
        "bg",
        "ps",
        "kill",
        "logs",
        "use_skill",
        "skills",
        "done",
    }
    for tool in expected_tools:
        assert tool in names, f"Expected tool {tool} in registry"


def test_registry_get_schema():
    schema = REGISTRY.get("read")
    assert schema is not None
    assert schema["function"]["name"] == "read"
    assert "path" in schema["function"]["parameters"]["properties"]

    assert REGISTRY.get("non_existent_tool") is None


def test_registry_openai_schemas():
    schemas = REGISTRY.openai_schemas()
    assert len(schemas) == len(TOOL_SCHEMAS)
    assert all("type" in s and "function" in s for s in schemas)


def test_registry_validate_call_valid():
    # Valid call
    args, errors = REGISTRY.validate_call("read", {"path": "src/main.py"})
    assert errors == []
    assert args == {"path": "src/main.py"}

    # Valid with alias
    args, errors = REGISTRY.validate_call("read", {"file": "src/main.py"})
    assert errors == []
    assert args == {"path": "src/main.py"}

    # Valid shell with command alias
    args, errors = REGISTRY.validate_call("shell", {"command": "echo hello"})
    assert errors == []
    assert args == {"cmd": "echo hello"}

    # Valid cp with from/to aliases
    args, errors = REGISTRY.validate_call("cp", {"from": "a.txt", "to": "b.txt"})
    assert errors == []
    assert args == {"src": "a.txt", "dst": "b.txt"}


def test_registry_validate_call_missing_required():
    # Missing required 'path' for read
    args, errors = REGISTRY.validate_call("read", {})
    assert len(errors) == 1
    assert "Missing required parameter 'path'" in errors[0]

    # Missing required 'cmd' for shell
    args, errors = REGISTRY.validate_call("shell", {})
    assert len(errors) == 1
    assert "Missing required parameter 'cmd'" in errors[0]

    # Missing required 'src' or 'dst' for mv
    args, errors = REGISTRY.validate_call("mv", {"src": "a.txt"})
    assert len(errors) == 1
    assert "Missing required parameter 'dst'" in errors[0]


def test_registry_validate_call_unknown_tool():
    args, errors = REGISTRY.validate_call("magic_wand", {"target": "all"})
    assert len(errors) == 1
    assert "Unknown tool" in errors[0]


def test_registry_validate_call_typed_rejections():
    """Gap 1: typed JSON-schema validations rejecting wrong types before handler execution."""
    # 1. read with integer path instead of string
    args, errors = REGISTRY.validate_call("read", {"path": 123})
    assert len(errors) > 0
    assert any("Invalid type for parameter 'path'" in e for e in errors)

    # 2. shell with list cmd instead of string
    args, errors = REGISTRY.validate_call("shell", {"cmd": ["echo", "hi"]})
    assert len(errors) > 0
    assert any("Invalid type for parameter 'cmd'" in e for e in errors)

    # 3. skills with string chosen instead of array
    args, errors = REGISTRY.validate_call("skills", {"chosen": "not-a-list"})
    assert len(errors) > 0
    assert any("Invalid type for parameter 'chosen'" in e for e in errors)

    # 4. logs with dict tail instead of string
    args, errors = REGISTRY.validate_call("logs", {"name": "server", "tail": {"bad": 1}})
    assert len(errors) > 0
    assert any("Invalid type for parameter 'tail'" in e for e in errors)

    # 5. additionalProperties: false rejects unexpected parameters
    args, errors = REGISTRY.validate_call("read", {"path": "main.py", "unexpected_extra": True})
    assert len(errors) > 0
    assert any("Unexpected parameter 'unexpected_extra'" in e for e in errors)

    # 6. array item type validation (chosen must be array of strings)
    args, errors = REGISTRY.validate_call("skills", {"chosen": [123, 456]})
    assert len(errors) > 0
    assert any("Invalid item type" in e for e in errors)


def test_registry_and_executor_consistency():
    """Gap 6: verify every advertised tool has metadata, handler mapping, and implementation in ToolSession."""
    from agent_arena.sandbox.executors.advanced_executor import ToolSession

    all_tools = REGISTRY.all_names()
    assert len(all_tools) == 22

    for name in all_tools:
        meta = REGISTRY.get_metadata(name)
        assert meta is not None, f"Tool '{name}' must have metadata defined"
        assert "classification" in meta, f"Tool '{name}' must have classification"
        assert meta["classification"] in ("executable", "context", "control")
        assert "handler" in meta, f"Tool '{name}' must have handler defined"
        assert "default_step_cost" in meta, f"Tool '{name}' must have default_step_cost defined"

        handler = meta["handler"]
        if meta["classification"] in ("executable", "context"):
            # Must exist as a method on ToolSession
            assert hasattr(ToolSession, handler), f"ToolSession missing handler method: {handler}"
        elif meta["classification"] == "control":
            assert name == "done"
            assert meta["default_step_cost"] == 0

