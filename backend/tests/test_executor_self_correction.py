from agent_arena.tool_protocol import REGISTRY
import json

def test_tool_registry_schema_retrieval():
    write_spec = REGISTRY.get("write")
    assert write_spec is not None
    assert write_spec.get("type") == "function"
    fn = write_spec.get("function", {})
    assert fn.get("name") == "write"
    params = fn.get("parameters", {})
    assert "properties" in params
    assert "path" in params["properties"]
    assert "content" in params["properties"]

def test_tool_registry_validation_failure():
    # Calling write without content or path
    norm_args, val_errors = REGISTRY.validate_call("write", {"tool": "write"})
    assert len(val_errors) > 0
    assert any("path" in err for err in val_errors)
