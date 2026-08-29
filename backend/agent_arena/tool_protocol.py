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
                "properties": {},
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
            "name": "grep",
            "description": "Search for a regex or string pattern within workspace files.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": "Search pattern or regex"},
                    "path": {"type": "string", "description": "Directory or file to search"},
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
    for k, v in raw_args.items():
        canonical_k = _ARG_ALIASES.get(k.lower(), k.lower())
        args[canonical_k] = v

    if tool_name in ("shell", "install") and "content" in args and not args.get("cmd"):
        args["cmd"] = args.pop("content")
    if tool_name in ("write", "run", "bg") and "cmd" in args and not args.get("content"):
        args["content"] = args.pop("cmd")
    return args


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
