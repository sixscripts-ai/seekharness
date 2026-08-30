"""Canonical tool protocol: typed models, canonical schemas, and multi-dialect parser.

Unifies OpenAI-native tool_calls, Anthropic tool_use blocks, Kimi token XML,
DeepSeek XML tags, Arena fenced/bare JSON, and legacy line grammar into
CanonicalToolCall objects for the execution sandbox.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Literal

ToolDialect = Literal[
    "openai_native",
    "anthropic_native",
    "kimi_token_xml",
    "xml_tag",
    "arena_json",
    "arena_legacy",
    "none",
]


@dataclass(frozen=True)
class CanonicalToolCall:
    name: str
    arguments: dict[str, Any]
    call_id: str = ""
    dialect: ToolDialect = "none"


@dataclass
class ModelResponse:
    text: str = ""
    native_tool_calls: list[dict[str, Any]] = field(default_factory=list)
    provider: str = ""
    model: str = ""
    raw_finish_reason: str | None = None
    latency_ms: int = 0


@dataclass
class NormalizedToolResponse:
    calls: list[CanonicalToolCall]
    dialect: ToolDialect
    parse_status: Literal["native", "parsed", "repaired", "failed"]
    repair_kind: str | None = None
    error_code: str | None = None


# Single source of truth for all microVM tools.
TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "read",
            "description": "Read the text contents of a file in the workspace.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string", "description": "Relative path to file"}},
                "required": ["path"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write",
            "description": "Write or overwrite a file with the given text content.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Relative path to file"},
                    "content": {"type": "string", "description": "Full file content to write"},
                },
                "required": ["path", "content"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "shell",
            "description": "Execute a shell command inside the workspace microVM.",
            "parameters": {
                "type": "object",
                "properties": {
                    "cmd": {"type": "string", "description": "The shell command to execute"}
                },
                "required": ["cmd"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "test",
            "description": "Run the task's authoritative test suite or verification script.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Optional test file or command path"}
                },
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "ls",
            "description": "List files and directories at the given path.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Directory path (defaults to .)"}
                },
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "clean",
            "description": "Delete a specific file in the workspace.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Relative path to file to remove"}
                },
                "required": ["path"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run",
            "description": "Run a python script by path or execute inline python code in the microVM workspace.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Relative path to python script"},
                    "content": {"type": "string", "description": "Inline python code to execute"},
                },
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "install",
            "description": "Run a package installation command (e.g. pip install / npm install).",
            "parameters": {
                "type": "object",
                "properties": {
                    "cmd": {"type": "string", "description": "The installation command"}
                },
                "required": ["cmd"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "grep",
            "description": "Search for a regex or string pattern within workspace files.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": "Search pattern or regex"},
                    "path": {"type": "string", "description": "Directory or file to search (defaults to .)"},
                },
                "required": ["pattern"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "tree",
            "description": "Display a recursive tree structure of workspace directories.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Directory path (defaults to .)"}
                },
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "cp",
            "description": "Copy a file or directory from src to dst.",
            "parameters": {
                "type": "object",
                "properties": {
                    "src": {"type": "string", "description": "Source path"},
                    "dst": {"type": "string", "description": "Destination path"},
                },
                "required": ["src", "dst"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "mv",
            "description": "Move or rename a file or directory from src to dst.",
            "parameters": {
                "type": "object",
                "properties": {
                    "src": {"type": "string", "description": "Source path"},
                    "dst": {"type": "string", "description": "Destination path"},
                },
                "required": ["src", "dst"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "rm",
            "description": "Delete a file or directory in the workspace.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string", "description": "Path to delete"}},
                "required": ["path"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fetch",
            "description": "Fetch URL contents via HTTP GET.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "HTTP/HTTPS URL to fetch"}
                },
                "required": ["url"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search",
            "description": "Search documentation or endpoints.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"}
                },
                "required": ["query"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "bg",
            "description": "Start a long-running background process in the workspace.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Identifier name for background process"},
                    "content": {"type": "string", "description": "Shell command to run in background"},
                },
                "required": ["name", "content"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "ps",
            "description": "List currently running background processes in the workspace.",
            "parameters": {
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "kill",
            "description": "Kill a running background process by name or ID.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Process name or ID to terminate"}
                },
                "required": ["name"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "logs",
            "description": "Fetch stdout/stderr logs from a background process.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Process name or ID"},
                    "tail": {"type": "string", "description": "Number of bytes to tail (default 8000)"},
                },
                "required": ["name"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "use_skill",
            "description": "Load a selected agent skill's instructions into active context.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Name of the skill to activate"}
                },
                "required": ["name"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "skills",
            "description": "List available skills or select skills for the battle.",
            "parameters": {
                "type": "object",
                "properties": {
                    "list": {"type": "boolean", "description": "If true, list available skills"},
                    "chosen": {"type": "array", "items": {"type": "string"}, "description": "List of skill names to select"},
                },
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "done",
            "description": "Signal that task implementation is complete and ready for final verification.",
            "parameters": {
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
        },
    },
]

TOOL_METADATA: dict[str, dict[str, Any]] = {
    "read": {"classification": "executable", "handler": "read", "default_step_cost": 1},
    "write": {"classification": "executable", "handler": "write", "default_step_cost": 1},
    "shell": {"classification": "executable", "handler": "shell", "default_step_cost": 1},
    "test": {"classification": "executable", "handler": "test", "default_step_cost": 1},
    "ls": {"classification": "executable", "handler": "ls", "default_step_cost": 1},
    "clean": {"classification": "executable", "handler": "clean", "default_step_cost": 1},
    "run": {"classification": "executable", "handler": "run", "default_step_cost": 1},
    "install": {"classification": "executable", "handler": "install", "default_step_cost": 1},
    "grep": {"classification": "executable", "handler": "grep", "default_step_cost": 1},
    "tree": {"classification": "executable", "handler": "tree", "default_step_cost": 1},
    "cp": {"classification": "executable", "handler": "cp", "default_step_cost": 1},
    "mv": {"classification": "executable", "handler": "mv", "default_step_cost": 1},
    "rm": {"classification": "executable", "handler": "rm", "default_step_cost": 1},
    "fetch": {"classification": "executable", "handler": "fetch", "default_step_cost": 1},
    "search": {"classification": "executable", "handler": "search", "default_step_cost": 1},
    "bg": {"classification": "executable", "handler": "bg", "default_step_cost": 1},
    "ps": {"classification": "executable", "handler": "ps", "default_step_cost": 1},
    "kill": {"classification": "executable", "handler": "kill", "default_step_cost": 1},
    "logs": {"classification": "executable", "handler": "logs", "default_step_cost": 1},
    "use_skill": {"classification": "context", "handler": "use_skill", "default_step_cost": 1},
    "skills": {"classification": "context", "handler": "skills", "default_step_cost": 1},
    "done": {
        "classification": "control",
        "handler": "done",
        "default_step_cost": 0,
        "description": "Control/finalization signal to trigger final authoritative verification. Zero fighter step cost.",
    },
}

_ARG_ALIASES: dict[str, str] = {
    "command": "cmd",
    "code": "content",
    "file": "path",
    "filepath": "path",
    "filename": "path",
    "p": "path",
    "from": "src",
    "source": "src",
    "to": "dst",
    "dest": "dst",
    "destination": "dst",
    "query": "pattern",
    "q": "pattern",
}


def _normalize_args(tool_name: str, raw_args: dict[str, Any]) -> dict[str, Any]:
    args: dict[str, Any] = {}
    tool = str(tool_name or "").lower().strip()
    for k, v in raw_args.items():
        lk = str(k).lower().strip()
        if lk in ("tool", "call_id", "command_id"):
            continue
        if tool == "search" and lk in ("q", "query"):
            args["query"] = v
        elif tool == "grep" and lk in ("q", "query", "pattern"):
            args["pattern"] = v
        elif tool in ("kill", "logs", "use_skill") and lk in ("id", "name", "skill"):
            args["name"] = v
        elif tool == "skills" and lk in ("skills", "chosen"):
            args["chosen"] = v
        else:
            canonical_k = _ARG_ALIASES.get(lk, lk)
            args[canonical_k] = v

    if tool in ("shell", "install") and "content" in args and not args.get("cmd"):
        args["cmd"] = args.pop("content")
    if tool in ("write", "run", "bg") and "cmd" in args and not args.get("content"):
        args["content"] = args.pop("cmd")
    return args


def _validate_json_type(val: Any, expected_type: str) -> bool:
    """Validate python value against JSON Schema primitive types."""
    if expected_type == "string":
        return isinstance(val, str)
    if expected_type == "integer":
        return isinstance(val, int) and not isinstance(val, bool)
    if expected_type == "number":
        return isinstance(val, (int, float)) and not isinstance(val, bool)
    if expected_type == "boolean":
        return isinstance(val, bool)
    if expected_type == "array":
        return isinstance(val, (list, tuple))
    if expected_type == "object":
        return isinstance(val, dict)
    return True


class ToolRegistry:
    """Canonical protocol and schema registry for microVM tools."""

    def __init__(
        self,
        schemas: list[dict[str, Any]] | None = None,
        metadata: dict[str, dict[str, Any]] | None = None,
    ):
        self._schemas: list[dict[str, Any]] = list(schemas or [])
        self._by_name: dict[str, dict[str, Any]] = {}
        for s in self._schemas:
            func = s.get("function") or {}
            name = str(func.get("name") or "").strip().lower()
            if name:
                self._by_name[name] = s
        self._metadata: dict[str, dict[str, Any]] = dict(metadata or TOOL_METADATA)

    def get(self, name: str) -> dict[str, Any] | None:
        return self._by_name.get(str(name or "").strip().lower())

    def get_metadata(self, name: str) -> dict[str, Any] | None:
        return self._metadata.get(str(name or "").strip().lower())

    def get_handler_name(self, name: str) -> str | None:
        meta = self.get_metadata(name)
        return meta.get("handler") if meta else None

    def is_control_tool(self, name: str) -> bool:
        meta = self.get_metadata(name)
        return bool(meta and meta.get("classification") == "control")

    def step_cost(self, name: str) -> int:
        meta = self.get_metadata(name)
        if not meta:
            return 1
        return int(meta.get("default_step_cost", 1))

    def all_names(self) -> set[str]:
        return set(self._by_name.keys())

    def openai_schemas(self) -> list[dict[str, Any]]:
        return list(self._schemas)

    def validate_call(self, name: str, args: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
        """Validate and normalize tool arguments against canonical typed schema.

        Enforces:
        - Required properties (present and non-empty for strings)
        - Strict types (string, integer, number, boolean, array, object)
        - Array item types (e.g. array of string)
        - Enums (if present)
        - additionalProperties: false (unexpected properties rejected)

        Returns:
            (canonical_args, errors_list)
        """
        canonical_name = str(name or "").strip().lower()
        schema = self.get(canonical_name)
        if not schema:
            return {}, [f"Unknown tool: '{name}'"]

        if not isinstance(args, dict):
            return {}, [f"Tool arguments for '{canonical_name}' must be an object/dict, got {type(args).__name__}"]

        norm_args = _normalize_args(canonical_name, dict(args))
        func = schema.get("function") or {}
        params = func.get("parameters") or {}
        properties = params.get("properties") or {}
        required = set(params.get("required") or [])
        additional_allowed = params.get("additionalProperties", True)

        errors: list[str] = []

        # 1. Reject unexpected properties when additionalProperties is False
        if not additional_allowed:
            for k in list(norm_args.keys()):
                if k not in properties:
                    errors.append(f"Unexpected parameter '{k}' for tool '{canonical_name}'")

        # 2. Check required parameters
        for req in required:
            if req not in norm_args or norm_args[req] is None:
                errors.append(f"Missing required parameter '{req}' for tool '{canonical_name}'")
            elif isinstance(norm_args[req], str) and not norm_args[req].strip():
                errors.append(f"Missing required parameter '{req}' (empty string) for tool '{canonical_name}'")

        # 3. Check property types, item types, and enums
        for k, val in norm_args.items():
            if k not in properties:
                continue
            prop_schema = properties[k]
            expected_type = prop_schema.get("type")
            if val is not None and expected_type:
                if not _validate_json_type(val, expected_type):
                    errors.append(
                        f"Invalid type for parameter '{k}' in tool '{canonical_name}': "
                        f"expected {expected_type}, got {type(val).__name__}"
                    )
                elif expected_type == "array" and "items" in prop_schema:
                    item_type = prop_schema["items"].get("type")
                    if item_type and isinstance(val, (list, tuple)):
                        for idx, item in enumerate(val):
                            if not _validate_json_type(item, item_type):
                                errors.append(
                                    f"Invalid item type at index {idx} for parameter '{k}' in tool '{canonical_name}': "
                                    f"expected {item_type}, got {type(item).__name__}"
                                )
                if "enum" in prop_schema and val not in prop_schema["enum"]:
                    errors.append(
                        f"Invalid value for parameter '{k}' in tool '{canonical_name}': "
                        f"expected one of {prop_schema['enum']}, got {val!r}"
                    )

        return norm_args, errors


REGISTRY: ToolRegistry = ToolRegistry(TOOL_SCHEMAS, TOOL_METADATA)


# --- Dialect Parsers ---

# 1. Kimi / Moonshot Token Separator XML: <|open|>tools<|sep|><|open|>call tool="..."...
_KIMI_TOKEN_RE = re.compile(
    r"<\|open\|>call\s+tool=[\"']?([a-zA-Z0-9_-]+)[\"']?[^>]*<\|sep\|>(.*?)<\|close\|>call",
    re.DOTALL,
)
_KIMI_ARG_RE = re.compile(
    r"<\|open\|>argument\s+key=[\"']?([a-zA-Z0-9_-]+)[\"']?[^>]*<\|sep\|>(.*?)<\|close\|>argument",
    re.DOTALL,
)


def parse_kimi_token_xml(text: str) -> list[CanonicalToolCall]:
    calls: list[CanonicalToolCall] = []
    for call_match in _KIMI_TOKEN_RE.finditer(text):
        tool_name = call_match.group(1).strip().lower()
        body = call_match.group(2)
        raw_args: dict[str, Any] = {}
        for arg_match in _KIMI_ARG_RE.finditer(body):
            key = arg_match.group(1).strip()
            val = arg_match.group(2).strip()
            raw_args[key] = val
        args = _normalize_args(tool_name, raw_args)
        calls.append(CanonicalToolCall(name=tool_name, arguments=args, dialect="kimi_token_xml"))
    return calls


# 2. Standard XML Tags: <tool_call><name>shell</name><arguments>{"cmd": "..."}</arguments></tool_call>
_XML_TAG_RE = re.compile(
    r"<(?:tool_call|invoke|function_call)(?:\s+name=[\"']([a-zA-Z0-9_-]+)[\"'])?[^>]*>(.*?)</(?:tool_call|invoke|function_call)>",
    re.DOTALL | re.IGNORECASE,
)
_XML_NAME_RE = re.compile(r"<(?:name|tool_name|tool)>([a-zA-Z0-9_-]+)</(?:name|tool_name|tool)>", re.I)
_XML_ARGS_RE = re.compile(r"<(?:arguments|parameters|args)>(.*?)</(?:arguments|parameters|args)>", re.DOTALL | re.I)


def parse_xml_tags(text: str) -> list[CanonicalToolCall]:
    calls: list[CanonicalToolCall] = []
    for m in _XML_TAG_RE.finditer(text):
        tool_name = m.group(1)
        body = m.group(2)
        if not tool_name:
            nm = _XML_NAME_RE.search(body)
            if nm:
                tool_name = nm.group(1)
        if not tool_name:
            continue
        tool_name = tool_name.strip().lower()
        raw_args: dict[str, Any] = {}
        args_match = _XML_ARGS_RE.search(body)
        if args_match:
            raw_content = args_match.group(1).strip()
            try:
                raw_args = json.loads(raw_content)
            except Exception:
                # Fallback: key-value extraction
                for kv in re.finditer(r"<([a-zA-Z0-9_-]+)>(.*?)</\1>", raw_content, re.DOTALL):
                    raw_args[kv.group(1)] = kv.group(2).strip()
        args = _normalize_args(tool_name, raw_args if isinstance(raw_args, dict) else {})
        calls.append(CanonicalToolCall(name=tool_name, arguments=args, dialect="xml_tag"))
    return calls


# 3. Fenced / Bare JSON Tools: [{"tool": "shell", "arguments": {"cmd": "..."}}] or {"name": "..."}
_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(\[.*?\]|\{.*?\})\s*```", re.I | re.S)


def parse_arena_json(text: str) -> list[CanonicalToolCall]:
    t = (text or "").strip()
    if not t:
        return []
    candidates: list[str] = []
    for m in _JSON_FENCE_RE.finditer(t):
        candidates.append(m.group(1).strip())
    if not candidates:
        if (t.startswith("[") and t.endswith("]")) or (t.startswith("{") and t.endswith("}")):
            candidates.append(t)
    calls: list[CanonicalToolCall] = []
    for raw in candidates:
        try:
            payload = json.loads(raw)
        except Exception:
            continue
        if isinstance(payload, dict):
            payload = [payload]
        if not isinstance(payload, list):
            continue
        for obj in payload:
            if not isinstance(obj, dict):
                continue
            name = str(obj.get("name") or obj.get("tool") or obj.get("action") or "").strip().lower()
            if not name:
                continue
            raw_args = obj.get("arguments") or obj.get("parameters") or obj.get("args") or obj.get("action_input") or {}
            if not isinstance(raw_args, dict):
                raw_args = {k: v for k, v in obj.items() if k not in ("name", "tool", "action", "type", "call_id", "id")}
            args = _normalize_args(name, raw_args)
            call_id = str(obj.get("call_id") or obj.get("id") or "")
            calls.append(CanonicalToolCall(name=name, arguments=args, call_id=call_id, dialect="arena_json"))
    return calls


# 4. Legacy Line-Based Parser: TOOL shell cmd='...' / TOOL read path=... / SKILLS: a, b
def parse_arena_legacy(text: str) -> list[CanonicalToolCall]:
    calls: list[CanonicalToolCall] = []
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if not line:
            i += 1
            continue
        if line.upper() == "DONE":
            calls.append(CanonicalToolCall(name="done", arguments={}, dialect="arena_legacy"))
            break
        if line.upper().startswith("SKILLS:"):
            skills_part = line[7:].strip()
            chosen = [s.strip() for s in skills_part.replace(",", " ").split() if s.strip()]
            calls.append(CanonicalToolCall(name="skills", arguments={"chosen": chosen}, dialect="arena_legacy"))
            i += 1
            continue
        if line.upper().startswith("TOOL "):
            remainder = line[5:].strip()
            parts = remainder.split(None, 1)
            name = parts[0].lower()
            arg_str = parts[1] if len(parts) > 1 else ""
            raw_args: dict[str, Any] = {}
            # Check key=value extraction
            for m in re.finditer(r"\b([a-zA-Z0-9_-]+)=(['\"])(.*?)\2", arg_str):
                raw_args[m.group(1)] = m.group(3)
            for m in re.finditer(r"\b([a-zA-Z0-9_-]+)=([^\s'\"]+)", arg_str):
                if m.group(1) not in raw_args:
                    raw_args[m.group(1)] = m.group(2)
            if not raw_args and arg_str:
                # Positional argument fallback
                if name in ("read", "rm", "tree", "ls", "use_skill"):
                    raw_args["path" if name != "use_skill" else "name"] = arg_str.strip()
                elif name in ("shell", "install"):
                    raw_args["cmd"] = arg_str.strip()
            # Body tool continuation check (e.g. write path=... until END_TOOL)
            if name in ("write", "run", "bg") and not raw_args.get("content"):
                body_lines = []
                found_end = False
                i += 1
                while i < len(lines):
                    if lines[i].strip().upper() == "END_TOOL":
                        found_end = True
                        break
                    body_lines.append(lines[i])
                    i += 1
                raw_args["content"] = "\n".join(body_lines)
                if not found_end:
                    raw_args["error"] = "ERROR: missing END_TOOL"
            args = _normalize_args(name, raw_args)
            if raw_args.get("error"):
                args["error"] = raw_args["error"]
            calls.append(CanonicalToolCall(name=name, arguments=args, dialect="arena_legacy"))
        i += 1
    return calls


def normalize_response(
    response: ModelResponse | str,
    provider_family: str = "openai",
) -> NormalizedToolResponse:
    """Universal normalizer: transforms provider-native calls or text into CanonicalToolCalls."""
    if isinstance(response, str):
        response = ModelResponse(text=response, provider=provider_family)

    # 1. Native structured tool_calls (highest priority)
    if response.native_tool_calls:
        calls: list[CanonicalToolCall] = []
        for tc in response.native_tool_calls:
            func = tc.get("function", {})
            name = str(func.get("name") or tc.get("name") or "").strip().lower()
            raw_args_str = func.get("arguments") or tc.get("arguments") or "{}"
            if isinstance(raw_args_str, str):
                try:
                    raw_args = json.loads(raw_args_str)
                except Exception:
                    raw_args = {"cmd": raw_args_str} if name == "shell" else {"raw": raw_args_str}
            elif isinstance(raw_args_str, dict):
                raw_args = raw_args_str
            else:
                raw_args = {}
            args = _normalize_args(name, raw_args)
            call_id = str(tc.get("id") or tc.get("call_id") or "")
            calls.append(CanonicalToolCall(name=name, arguments=args, call_id=call_id, dialect="openai_native"))
        if calls:
            return NormalizedToolResponse(calls=calls, dialect="openai_native", parse_status="native")

    text = response.text or ""

    # 2. Moonshot / Kimi Token XML
    kimi_calls = parse_kimi_token_xml(text)
    if kimi_calls:
        return NormalizedToolResponse(calls=kimi_calls, dialect="kimi_token_xml", parse_status="parsed")

    # 3. Standard XML tags (<tool_call>, <invoke>)
    xml_calls = parse_xml_tags(text)
    if xml_calls:
        return NormalizedToolResponse(calls=xml_calls, dialect="xml_tag", parse_status="parsed")

    # 4. Arena Fenced / Bare JSON
    json_calls = parse_arena_json(text)
    if json_calls:
        return NormalizedToolResponse(calls=json_calls, dialect="arena_json", parse_status="parsed")

    # 5. Legacy TOOL line grammar
    legacy_calls = parse_arena_legacy(text)
    if legacy_calls:
        return NormalizedToolResponse(calls=legacy_calls, dialect="arena_legacy", parse_status="parsed")

    # 6. Deterministic syntax repairs
    # Attempt to wrap bare JSON without fences
    if "{" in text and "}" in text and '"tool"' in text:
        m = re.search(r"(\{[^{}]*\"tool\"\s*:[^{}]*\})", text)
        if m:
            repaired = parse_arena_json(m.group(1))
            if repaired:
                return NormalizedToolResponse(
                    calls=repaired, dialect="arena_json", parse_status="repaired", repair_kind="json_substring_extraction"
                )

    return NormalizedToolResponse(calls=[], dialect="none", parse_status="failed", error_code="no_valid_tool_invocation")
