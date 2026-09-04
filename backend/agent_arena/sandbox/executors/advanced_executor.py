"""Universal toolbelt executor: one agent loop for all formats.

Full toolbelt: WRITE/READ/LS/CLEAN/RUN/TEST + SHELL/GREP/TREE/CP/MV/RM/FETCH/
SEARCH/INSTALL/BG/PS/KILL/LOGS/SKILLS/USE_SKILL. Every tool call streams as an
`action_log` event. Skill pick-n competitive race, file-tree artifacts,
THEORY.md, preview servers per fighter, Appwrite skill Elo + memory.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import tempfile
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from .base import Executor
from .tool_result import ToolResult
from .battle_plan import (
    parse_battle_plan,
    restore_protected,
    snapshot_handoff,
    write_allowed_file,
    snapshot_to_deployment,
    wipe_builder_private,
    parse_services_spec,
    classify_deployment_failure,
)
from .procs import ProcessManager
from .preview import (
    StaticPreviewServer,
    port_for_index,
    preview_enabled,
)
from .skill_pool import (
    load_skill_pool,
    mount_skills,
    resolve_prerequisites,
    filter_skills,
)
from ...redact import sanitize_artifact

SKILL_POOL: list[dict] = load_skill_pool()

RACE_MAX_TOKENS = 4096

MAX_SELECTED_SKILLS = 3

# Bumped when the EXECUTOR_RESULT record shape changes incompatibly.
ADVANCED_EXECUTOR_VERSION = 1


# Command-jail helpers live in the shared _command_guard module so the target
# verifier and this executor enforce the exact same rules. The private names
# are re-imported here for backward compatibility with existing callers/tests.
from ._command_guard import (
    _fetch_url_blocked,
    _fetch_targets_in_command,
    _looks_like_fetch_target,
    _normalize_fetch_url,
    command_block_reason,
)


def _strip_secret_env(env: dict) -> dict:
    """Remove credential-bearing variables before handing env to child processes.

    The Modal sandbox env only carries BATTLE_TOKEN/BACKEND_PUBLIC_URL, but
    in-process runs inherit the full backend env (APPWRITE_API_KEY, HOST_* keys,
    FERNET_KEY, ...). A fighter could otherwise `TOOL SHELL env` them back.
    """
    _EXACT = {
        "FERNET_KEY",
        "FERNET_KEY_OLD",
        "INTERNAL_API_KEY",
        "BATTLE_TOKEN",
        "ARENA_EVALUATOR_DIR",
        "ARENA_TRUSTED_TARGETS_DIR",
        "BATTLE_BOOTSTRAP_JSON",
    }
    _SUFFIXES = ("_KEY", "_SECRET", "_TOKEN", "_PASSWORD")
    out = dict(env)
    for name in list(out):
        up = name.upper()
        if up in _EXACT or up.endswith(_SUFFIXES):
            out.pop(name, None)
    return out


def _shell_command_blocked(command: str, *, allow_network: bool) -> str | None:
    """Reject shell/install commands that escape the workdir jail or bypass fetch SSRF."""
    return command_block_reason(command, allow_network=allow_network)


def _is_skill_body_file(path: Path, workdir: Path) -> bool:
    """True when `path` is a mounted L3 skill body (`.agents/skills/<id>/SKILL.md`)."""
    try:
        rel = path.resolve().relative_to(workdir.resolve())
    except Exception:
        return False
    parts = rel.parts
    return (
        len(parts) >= 4
        and parts[0] == ".agents"
        and parts[1] == "skills"
        and parts[-1] == "SKILL.md"
    )


from ...fighter_context import build_fighter_system_prompt, fighter_tool_grammar
from ...skills import (
    CanonicalSkillResolver,
    SkillLifecycleTracker,
    SkillRecord,
    compute_skill_attributions,
    curate_shortlist,
    rank_skills,
)
from ...skill_telemetry import (
    public_skill_file_read,
    public_skill_tool_output,
    skill_event_for_call,
)


def rank_skills_for_context(
    pool: list[dict | SkillRecord],
    format_config: dict | None = None,
    limit: int = 5,
    context_mode: str = "strict",
    skill_elos: dict[str, float] | None = None,
) -> list[dict]:
    """Rank skills using tokenized relevance across target objectives, runtime, tags, and category."""
    records = [
        s if isinstance(s, SkillRecord) else SkillRecord.from_dict(s) for s in pool
    ]
    ranked = rank_skills(
        records,
        format_config,
        context_mode=context_mode,
        skill_elos=skill_elos,
        limit=limit,
    )
    return [s.to_dict() for s, score, reason in ranked]


def select_skills(
    format_config: dict | None = None,
    pool: list[dict | SkillRecord] | None = None,
    context_mode: str = "strict",
    skill_elos: dict[str, float] | None = None,
) -> list[dict]:
    """Selection protocol: curate a relevant shortlist of candidate skills
    via tokenized keyword relevance and prerequisite resolution.
    """
    pool = pool if pool is not None else (load_skill_pool() or SKILL_POOL)
    records = [
        s if isinstance(s, SkillRecord) else SkillRecord.from_dict(s) for s in pool
    ]
    shortlist = curate_shortlist(
        records,
        format_config,
        context_mode=context_mode,
        skill_elos=skill_elos,
        max_shortlist=5,
    )
    return [s.to_dict() for s, reason in shortlist] or [
        s.to_dict() for s in records[:5]
    ]


DEFAULT_TEST_CODE = (
    "from solution import is_palindrome\n"
    "\n"
    "def main() -> None:\n"
    '    assert is_palindrome("racecar") is True\n'
    '    assert is_palindrome("Racecar") is True\n'
    '    assert is_palindrome("A man, a plan, a canal: Panama") is True\n'
    '    assert is_palindrome("hello") is False\n'
    '    print("TEST_PASS")\n'
    "\n"
    'if __name__ == "__main__":\n'
    "    main()\n"
)


def _judge_only(format_config: dict | None) -> bool:
    cfg = format_config or {}
    if cfg.get("evaluation_mode") == "verified":
        return False
    return bool(cfg.get("judge_only") or cfg.get("evaluation_mode") == "quick")


def fighter_tool_lines() -> str:
    return fighter_tool_grammar()


def _extract_arg(arg_str: str, key: str, default: str = "") -> str:
    if not arg_str:
        return default
    m = re.search(rf"\b{re.escape(key)}\s*=\s*\"([^\"]+)\"", arg_str)
    if m:
        return m.group(1).strip()
    m = re.search(rf"\b{re.escape(key)}\s*=\s*'([^']+)'", arg_str)
    if m:
        return m.group(1).strip()
    m = re.search(rf"\b{re.escape(key)}\s*=\s*(\S+)", arg_str)
    if m:
        return m.group(1).strip()
    return default


def _first_positional(arg_str: str) -> str:
    if not arg_str:
        return ""
    for tok in arg_str.split():
        if "=" in tok:
            continue
        return tok.strip()
    return ""


def _extract_path(arg_str: str) -> str:
    val = _extract_arg(arg_str, "path") or _extract_arg(arg_str, "p")
    if val:
        return val
    return _first_positional(arg_str)


_BODY_TOOLS = {"write", "run", "shell", "install", "bg"}
_ARG_TOOLS = {
    "read",
    "ls",
    "test",
    "clean",
    "grep",
    "tree",
    "cp",
    "mv",
    "rm",
    "fetch",
    "search",
    "ps",
    "kill",
    "logs",
    "use_skill",
    "skills",
}


_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(\[.*?\]|\{.*?\})\s*```", re.I | re.S)
_JSON_TOOL_KEYS = {
    "cmd",
    "command",
    "content",
    "code",
    "name",
    "id",
    "path",
    "pattern",
    "query",
    "q",
    "url",
    "src",
    "source",
    "from",
    "dst",
    "dest",
    "to",
    "tail",
    "skills",
    "chosen",
    "list",
    "index",
    "idx",
    "search",
    "find",
    "skill",
}
_ALL_JSON_TOOLS = _BODY_TOOLS | _ARG_TOOLS | {"skills", "done"}


def _normalize_json_call(obj) -> dict | None:
    """Validate one JSON tool object into the executor call shape, or None."""
    if not isinstance(obj, dict):
        return None
    tool = str(obj.get("tool") or "").strip().lower()
    if tool not in _ALL_JSON_TOOLS:
        return None
    args = obj.get("arguments") or obj.get("args") or {}
    if not isinstance(args, dict):
        return None
    call: dict[str, Any] = {"tool": tool}
    for key in _JSON_TOOL_KEYS:
        if key in args and args[key] is not None:
            call[key] = args[key]
    if tool in ("cp", "mv"):
        call["src"] = args.get("src") or args.get("from")
        call["dst"] = args.get("dst") or args.get("to")
    if tool in ("shell", "install"):
        call["cmd"] = args.get("cmd") or args.get("command") or ""
        call["content"] = call.get("content") or ""
    if tool in ("write", "run", "bg"):
        call["content"] = (
            args.get("content")
            if args.get("content") is not None
            else args.get("code", "")
        )
        call["cmd"] = args.get("cmd") or args.get("command") or ""
        call["name"] = args.get("name") or args.get("id") or ""
    if tool == "fetch":
        call["url"] = args.get("url") or ""
    if tool == "grep":
        call["pattern"] = args.get("pattern") or args.get("query") or ""
        call["path"] = args.get("path") or "."
    if tool == "skills":
        if "chosen" in args or "skills" in args:
            call["chosen"] = list(args.get("chosen") or args.get("skills") or [])
        if args.get("list"):
            call["list"] = True
        for key in ("index", "search", "skill"):
            if args.get(key) is not None:
                call[key] = args[key]
    if tool == "done":
        call = {"tool": "done"}
    return call


def _parse_json_tools(text: str) -> list[dict[str, Any]] | None:
    """Extract a JSON tool-call payload from model output.

    Accepts a fenced JSON array/object or a bare JSON array. Returns None when
    no valid JSON payload is present (caller falls back to the legacy TOOL
    grammar); returns a list of calls (possibly with error entries) otherwise.
    """
    t = (text or "").strip()
    if not t:
        return None
    candidates: list[str] = []
    for m in _JSON_FENCE_RE.finditer(t):
        candidates.append(m.group(1).strip())
    if not candidates:
        stripped = t
        if (stripped.startswith("[") and stripped.endswith("]")) or (
            stripped.startswith("{") and stripped.endswith("}")
        ):
            candidates.append(stripped)
    if not candidates:
        return None
    for raw in candidates:
        try:
            payload = json.loads(raw)
        except Exception:
            continue
        if isinstance(payload, dict):
            payload = [payload]
        if not isinstance(payload, list):
            continue
        calls: list[dict[str, Any]] = []
        any_valid = False
        for obj in payload:
            call = _normalize_json_call(obj)
            if call is not None:
                calls.append(call)
                any_valid = True
            elif isinstance(obj, dict):
                calls.append(
                    {
                        "tool": str(obj.get("tool") or "unknown").lower(),
                        "error": "ERROR: invalid JSON tool arguments",
                    }
                )
        if any_valid:
            return calls
    return None


def parse_tool_calls(text_or_resp: Any) -> list[dict[str, Any]]:
    """Parse tool calls using the universal multi-dialect normalizer with legacy fallback."""
    from ...tool_protocol import ModelResponse, normalize_response

    if isinstance(text_or_resp, dict):
        resp = ModelResponse(
            text=text_or_resp.get("content") or "",
            native_tool_calls=text_or_resp.get("tool_calls") or [],
            raw_finish_reason=text_or_resp.get("finish_reason"),
            latency_ms=text_or_resp.get("latency_ms") or 0,
        )
    elif hasattr(text_or_resp, "text") and hasattr(text_or_resp, "native_tool_calls"):
        resp = text_or_resp
    else:
        resp = ModelResponse(text=str(text_or_resp or ""))

    norm = normalize_response(resp)
    if norm.calls:
        calls: list[dict[str, Any]] = []
        for c in norm.calls:
            call_dict = {"tool": c.name, **c.arguments}
            calls.append(call_dict)
        return calls

    # Fallback to legacy string parser if text is present
    text = resp.text
    if not text:
        return []
    json_calls = _parse_json_tools(text)
    if json_calls is not None:
        return json_calls
    calls = []
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if not stripped:
            i += 1
            continue
        if stripped == "DONE" or stripped.upper() == "DONE":
            calls.append({"tool": "done"})
            break
        if not stripped.upper().startswith("TOOL "):
            # line is not a TOOL, could be SKILLS: or prose
            if stripped.upper().startswith("SKILLS:"):
                # SKILLS: a,b,c,d,e
                skills_part = stripped[7:].strip()
                chosen = [s.strip() for s in skills_part.split(",") if s.strip()]
                calls.append({"tool": "skills", "chosen": chosen})
            i += 1
            continue
        remainder = stripped[5:].strip()
        if not remainder:
            calls.append({"tool": "unknown", "raw": line, "error": "ERROR: empty tool"})
            i += 1
            continue
        parts = remainder.split(None, 1)
        tool_name = parts[0].lower()
        arg_str = parts[1] if len(parts) > 1 else ""
        if tool_name in _BODY_TOOLS:
            # shell/install take an inline cmd= and do not need a body block
            if tool_name in ("shell", "install") and (
                _extract_arg(arg_str, "cmd") or _extract_arg(arg_str, "command")
            ):
                calls.append(
                    {
                        "tool": tool_name,
                        "cmd": _extract_arg(arg_str, "cmd")
                        or _extract_arg(arg_str, "command"),
                        "content": "",
                    }
                )
                i += 1
                continue
            body_lines: list[str] = []
            i += 1
            found_end = False
            while i < len(lines):
                l = lines[i]
                if l.strip() == "END_TOOL":
                    found_end = True
                    break
                body_lines.append(l)
                i += 1
            base_call: dict[str, Any] = {
                "cmd": _extract_arg(arg_str, "cmd") or _extract_arg(arg_str, "command"),
                "name": _extract_arg(arg_str, "name") or _extract_arg(arg_str, "id"),
                "content": "\n".join(body_lines),
            }
            if tool_name in ("write", "run"):
                base_call["path"] = _extract_path(arg_str)
            if not found_end:
                calls.append(
                    {
                        **base_call,
                        "tool": tool_name,
                        "error": "ERROR: missing END_TOOL",
                    }
                )
                break
            calls.append({"tool": tool_name, **base_call})
            i += 1
            continue
        if tool_name == "skills":
            skills_part = _extract_arg(arg_str, "skills")
            if not skills_part:
                skills_part = remainder
            if skills_part.lower() in ("", "list", "ls"):
                calls.append({"tool": "skills", "list": True})
            else:
                chosen = [s.strip() for s in skills_part.split(",") if s.strip()]
                calls.append({"tool": "skills", "chosen": chosen})
            i += 1
            continue

        if tool_name in _ARG_TOOLS:
            call: dict[str, Any] = {"tool": tool_name}
            if tool_name in ("read", "ls", "clean", "rm", "tree"):
                call["path"] = _extract_path(arg_str)
                if not call["path"] and tool_name in ("ls", "tree"):
                    call["path"] = "."
            elif tool_name == "grep":
                call["pattern"] = (
                    _extract_arg(arg_str, "pattern")
                    or _extract_arg(arg_str, "query")
                    or _first_positional(arg_str)
                )
                call["path"] = _extract_path(arg_str) or "."
            elif tool_name in ("cp", "mv"):
                call["src"] = (
                    _extract_arg(arg_str, "from")
                    or _extract_arg(arg_str, "src")
                    or _extract_arg(arg_str, "source")
                )
                call["dst"] = (
                    _extract_arg(arg_str, "to")
                    or _extract_arg(arg_str, "dst")
                    or _extract_arg(arg_str, "dest")
                )
            elif tool_name == "fetch":
                call["url"] = _extract_arg(arg_str, "url") or _first_positional(arg_str)
            elif tool_name == "search":
                call["query"] = (
                    _extract_arg(arg_str, "query")
                    or _extract_arg(arg_str, "q")
                    or _first_positional(arg_str)
                )
            elif tool_name in ("kill", "logs"):
                call["name"] = (
                    _extract_arg(arg_str, "name")
                    or _extract_arg(arg_str, "id")
                    or _first_positional(arg_str)
                )
                call["tail"] = _extract_arg(arg_str, "tail") or "8000"
            elif tool_name == "use_skill":
                call["name"] = _extract_arg(arg_str, "name") or _first_positional(
                    arg_str
                )
            elif tool_name == "test":
                call["path"] = _extract_path(arg_str)
            calls.append(call)
            i += 1
            continue

        calls.append(
            {
                "tool": tool_name,
                "raw": remainder,
                "error": f"ERROR: unknown tool {tool_name}",
            }
        )
        i += 1
    return calls


class ToolSession:
    def __init__(
        self,
        workdir: Path,
        root: Path | None = None,
        tool_timeout: int | None = None,
        output_cap: int | None = None,
        allow_network: bool = False,
        test_cmd: str | None = None,
    ):
        self.workdir = Path(workdir)
        self.workdir.mkdir(parents=True, exist_ok=True)
        self.root = Path(root) if root else self.workdir
        self.tool_timeout = int(tool_timeout) if tool_timeout else None
        self.steps = 0
        self._max_output = int(output_cap) if output_cap else None
        self.skill_reads: set[str] = set()
        self.seq = 0
        self.allow_network = bool(allow_network)
        self.test_cmd = str(test_cmd or "").strip() or None
        self.procs = ProcessManager(self.workdir)
        self._pw = None
        self._browser = None
        self._page = None

    def close(self) -> None:
        """Clean up background processes and headless browser sessions."""
        try:
            self.procs.kill_all()
        except Exception:
            pass
        if self._browser:
            try:
                self._browser.close()
            except Exception:
                pass
            self._browser = None
            self._page = None
        if self._pw:
            try:
                self._pw.stop()
            except Exception:
                pass
            self._pw = None

    def _maybe_cap(self, data: str) -> tuple[str, bool]:
        if self._max_output is None:
            return data, False
        encoded = data.encode("utf-8")
        if len(encoded) <= self._max_output:
            return data, False
        capped = (
            encoded[: self._max_output].decode("utf-8", errors="ignore")
            + "\n[TRUNCATED]"
        )
        return capped, True

    def _resolve(self, rel: str) -> Path:
        if not rel or rel == ".":
            return self.workdir
        p = Path(rel)
        if p.is_absolute():
            raise ValueError(f"ERROR: absolute path rejected: {rel}")
        if ".." in p.parts:
            raise ValueError(f"ERROR: path escape '..' rejected: {rel}")
        resolved = (self.workdir / p).resolve()
        # Defense in depth: after symlink resolution the target must still live
        # inside the workdir jail. Blocks symlink-based escapes that slip past
        # the textual checks above.
        work = self.workdir.resolve()
        if resolved != work and work not in resolved.parents:
            raise ValueError(f"ERROR: path escape rejected: {rel}")
        return resolved

    def write(self, path: str, content: str, *, count_step: bool = True) -> ToolResult:
        t0 = time.time()
        if count_step:
            self.steps += 1
        try:
            if path.endswith(".py"):
                from ._harness import extract_python_source

                extracted = extract_python_source(content)
                if extracted:
                    content = extracted
            t = self._resolve(path)
            t.parent.mkdir(parents=True, exist_ok=True)
            t.write_text(content, encoding="utf-8")
            elapsed_ms = int((time.time() - t0) * 1000)
            return ToolResult(
                tool="write",
                success=True,
                output=f"WROTE {path} {len(content)} bytes",
                exit_code=0,
                duration_ms=elapsed_ms,
                mutated=True,
                step_charged=count_step,
                truncated=False,
            )
        except ValueError as exc:
            elapsed_ms = int((time.time() - t0) * 1000)
            return ToolResult(
                tool="write",
                success=False,
                output=f"ERROR: {exc}",
                error=str(exc),
                exit_code=1,
                error_type="policy_rejection",
                duration_ms=elapsed_ms,
                policy_rejected=True,
                mutated=False,
                step_charged=count_step,
                truncated=False,
            )
        except Exception as exc:
            elapsed_ms = int((time.time() - t0) * 1000)
            return ToolResult(
                tool="write",
                success=False,
                output=f"ERROR: {exc}",
                error=str(exc),
                exit_code=1,
                error_type="exception",
                duration_ms=elapsed_ms,
                mutated=False,
                step_charged=count_step,
                truncated=False,
            )

    def read(self, path: str, *, count_step: bool = True) -> ToolResult:
        t0 = time.time()
        if count_step:
            self.steps += 1
        try:
            t = self._resolve(path)
            if not t.exists():
                elapsed_ms = int((time.time() - t0) * 1000)
                return ToolResult(
                    tool="read",
                    success=False,
                    output=f"ERROR: not found {path}",
                    error=f"not found {path}",
                    exit_code=1,
                    error_type="not_found",
                    duration_ms=elapsed_ms,
                    mutated=False,
                    step_charged=count_step,
                )
            if t.is_dir():
                elapsed_ms = int((time.time() - t0) * 1000)
                return ToolResult(
                    tool="read",
                    success=False,
                    output=f"ERROR: {path} is a directory, use ls",
                    error=f"{path} is a directory, use ls",
                    exit_code=1,
                    error_type="invalid_argument",
                    duration_ms=elapsed_ms,
                    mutated=False,
                    step_charged=count_step,
                )
            if _is_skill_body_file(t, self.workdir):
                elapsed_ms = int((time.time() - t0) * 1000)
                return ToolResult(
                    tool="read",
                    success=False,
                    output="ERROR: skill body is only available through use_skill",
                    error="skill body requires use_skill",
                    exit_code=1,
                    error_type="policy_rejection",
                    duration_ms=elapsed_ms,
                    policy_rejected=True,
                    mutated=False,
                    step_charged=count_step,
                    truncated=False,
                )
            data = t.read_text(encoding="utf-8", errors="ignore")
            capped_data, is_truncated = self._maybe_cap(data)
            elapsed_ms = int((time.time() - t0) * 1000)
            return ToolResult(
                tool="read",
                success=True,
                output=capped_data,
                exit_code=0,
                duration_ms=elapsed_ms,
                truncated=is_truncated,
                mutated=False,
                step_charged=count_step,
            )
        except ValueError as exc:
            elapsed_ms = int((time.time() - t0) * 1000)
            return ToolResult(
                tool="read",
                success=False,
                output=f"ERROR: {exc}",
                error=str(exc),
                exit_code=1,
                error_type="policy_rejection",
                duration_ms=elapsed_ms,
                policy_rejected=True,
                mutated=False,
                step_charged=count_step,
                truncated=False,
            )
        except Exception as exc:
            elapsed_ms = int((time.time() - t0) * 1000)
            return ToolResult(
                tool="read",
                success=False,
                output=f"ERROR: {exc}",
                error=str(exc),
                exit_code=1,
                error_type="exception",
                duration_ms=elapsed_ms,
                mutated=False,
                step_charged=count_step,
                truncated=False,
            )

    def ls(self, path: str = ".", *, count_step: bool = True) -> ToolResult:
        t0 = time.time()
        if count_step:
            self.steps += 1
        try:
            t = self._resolve(path)
            if not t.exists():
                elapsed_ms = int((time.time() - t0) * 1000)
                return ToolResult(
                    tool="ls",
                    success=False,
                    output=f"ERROR: not found {path}",
                    error=f"not found {path}",
                    exit_code=1,
                    error_type="not_found",
                    duration_ms=elapsed_ms,
                    mutated=False,
                    step_charged=count_step,
                    truncated=False,
                )
            if t.is_file():
                elapsed_ms = int((time.time() - t0) * 1000)
                return ToolResult(
                    tool="ls",
                    success=True,
                    output=f"FILE {t.name} {t.stat().st_size}b",
                    exit_code=0,
                    duration_ms=elapsed_ms,
                    mutated=False,
                    step_charged=count_step,
                    truncated=False,
                )
            items = []
            for child in sorted(t.iterdir(), key=lambda x: x.name):
                typ = "DIR" if child.is_dir() else "FILE"
                try:
                    sz = child.stat().st_size
                except Exception:
                    sz = 0
                items.append(f"{typ} {child.name} {sz}b")
            out_str = "\n".join(items) if items else "(empty)"
            capped_out, is_truncated = self._maybe_cap(out_str)
            elapsed_ms = int((time.time() - t0) * 1000)
            return ToolResult(
                tool="ls",
                success=True,
                output=capped_out,
                exit_code=0,
                duration_ms=elapsed_ms,
                truncated=is_truncated,
                mutated=False,
                step_charged=count_step,
            )
        except ValueError as exc:
            elapsed_ms = int((time.time() - t0) * 1000)
            return ToolResult(
                tool="ls",
                success=False,
                output=f"ERROR: {exc}",
                error=str(exc),
                exit_code=1,
                error_type="policy_rejection",
                duration_ms=elapsed_ms,
                policy_rejected=True,
                mutated=False,
                step_charged=count_step,
                truncated=False,
            )
        except Exception as exc:
            elapsed_ms = int((time.time() - t0) * 1000)
            return ToolResult(
                tool="ls",
                success=False,
                output=f"ERROR: {exc}",
                error=str(exc),
                exit_code=1,
                error_type="exception",
                duration_ms=elapsed_ms,
                mutated=False,
                step_charged=count_step,
                truncated=False,
            )

    def clean(self, path: str, *, count_step: bool = True) -> ToolResult:
        t0 = time.time()
        if count_step:
            self.steps += 1
        try:
            t = self._resolve(path)
            if not t.exists():
                elapsed_ms = int((time.time() - t0) * 1000)
                return ToolResult(
                    tool="clean",
                    success=False,
                    output=f"ERROR: not found {path}",
                    error=f"not found {path}",
                    exit_code=1,
                    error_type="not_found",
                    duration_ms=elapsed_ms,
                    mutated=False,
                    step_charged=count_step,
                    truncated=False,
                )
            if t.is_dir():
                elapsed_ms = int((time.time() - t0) * 1000)
                return ToolResult(
                    tool="clean",
                    success=False,
                    output=f"ERROR: {path} is a dir, not cleaned (use rm -rf manually)",
                    error=f"{path} is a dir, not cleaned",
                    exit_code=1,
                    error_type="invalid_argument",
                    duration_ms=elapsed_ms,
                    mutated=False,
                    step_charged=count_step,
                    truncated=False,
                )
            t.unlink()
            elapsed_ms = int((time.time() - t0) * 1000)
            return ToolResult(
                tool="clean",
                success=True,
                output=f"CLEANED {path}",
                exit_code=0,
                duration_ms=elapsed_ms,
                mutated=True,
                step_charged=count_step,
                truncated=False,
            )
        except ValueError as exc:
            elapsed_ms = int((time.time() - t0) * 1000)
            return ToolResult(
                tool="clean",
                success=False,
                output=f"ERROR: {exc}",
                error=str(exc),
                exit_code=1,
                error_type="policy_rejection",
                duration_ms=elapsed_ms,
                policy_rejected=True,
                mutated=False,
                step_charged=count_step,
                truncated=False,
            )
        except Exception as exc:
            elapsed_ms = int((time.time() - t0) * 1000)
            return ToolResult(
                tool="clean",
                success=False,
                output=f"ERROR: {exc}",
                error=str(exc),
                exit_code=1,
                error_type="exception",
                duration_ms=elapsed_ms,
                mutated=False,
                step_charged=count_step,
                truncated=False,
            )

    def run(
        self,
        path: str | None = None,
        inline: str | None = None,
        *,
        count_step: bool = True,
    ) -> ToolResult:
        t0 = time.time()
        if count_step:
            self.steps += 1
        try:
            env = _strip_secret_env(os.environ.copy())
            env["ARENA_ROOT"] = str(self.root)
            env["ARENA_WORKDIR"] = str(self.workdir)
            env["PYTHONDONTWRITEBYTECODE"] = "1"
            env["PYTHONUNBUFFERED"] = "1"
            work = str(self.workdir.resolve())
            env["PYTHONPATH"] = work + os.pathsep + env.get("PYTHONPATH", "")
            if path:
                p = self._resolve(path)
                proc = subprocess.Popen(
                    ["python3", str(p)],
                    cwd=str(self.workdir),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    start_new_session=True,
                    env=env,
                )
            elif inline:
                proc = subprocess.Popen(
                    ["python3", "-c", inline],
                    cwd=str(self.workdir),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    start_new_session=True,
                    env=env,
                )
            else:
                elapsed_ms = int((time.time() - t0) * 1000)
                return ToolResult(
                    tool="run",
                    success=False,
                    output="ERROR: run needs path or inline code",
                    error="run needs path or inline code",
                    exit_code=1,
                    error_type="invalid_argument",
                    duration_ms=elapsed_ms,
                    mutated=False,
                    step_charged=count_step,
                    truncated=False,
                )
            try:
                out, err = proc.communicate(timeout=self.tool_timeout)
                out, out_trunc = self._maybe_cap(out or "")
                err, err_trunc = self._maybe_cap(err or "")
                is_truncated = out_trunc or err_trunc
                success = proc.returncode == 0
                elapsed_ms = int((time.time() - t0) * 1000)
                return ToolResult(
                    tool="run",
                    success=success,
                    output=f"STDOUT:\n{out}\nSTDERR:\n{err}\nrc={proc.returncode}",
                    error=None if success else f"rc={proc.returncode}",
                    exit_code=proc.returncode,
                    error_type=None if success else "execution_error",
                    duration_ms=elapsed_ms,
                    truncated=is_truncated,
                    mutated=True,
                    step_charged=count_step,
                )
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                except Exception:
                    pass
                elapsed_ms = int((time.time() - t0) * 1000)
                return ToolResult(
                    tool="run",
                    success=False,
                    output=f"ERROR: timeout after {self.tool_timeout}s",
                    error=f"timeout after {self.tool_timeout}s",
                    exit_code=124,
                    error_type="timeout",
                    duration_ms=elapsed_ms,
                    timed_out=True,
                    mutated=True,
                    step_charged=count_step,
                    truncated=False,
                )
        except ValueError as exc:
            elapsed_ms = int((time.time() - t0) * 1000)
            return ToolResult(
                tool="run",
                success=False,
                output=f"ERROR: {exc}",
                error=str(exc),
                exit_code=1,
                error_type="policy_rejection",
                duration_ms=elapsed_ms,
                policy_rejected=True,
                mutated=False,
                step_charged=count_step,
                truncated=False,
            )
        except Exception as exc:
            elapsed_ms = int((time.time() - t0) * 1000)
            return ToolResult(
                tool="run",
                success=False,
                output=f"ERROR: {exc}",
                error=str(exc),
                exit_code=1,
                error_type="exception",
                duration_ms=elapsed_ms,
                mutated=False,
                step_charged=count_step,
                truncated=False,
            )

    def test(self, path: str = "", *, count_step: bool = True) -> ToolResult:
        t0 = time.time()
        if self.test_cmd and (
            not path or path in {".", "tests/test_target.py", "test"}
        ):
            res = self._run_command(
                self.test_cmd, tool_name="test", count_step=count_step
            )
            out = res.output
            rc = res.exit_code if res.exit_code is not None else 1
            passed = rc == 0 or "TEST_PASS" in out
            fail = rc != 0 or "TEST_FAIL" in out
            elapsed_ms = int((time.time() - t0) * 1000)
            if passed and rc == 0:
                return ToolResult(
                    tool="test",
                    success=True,
                    output=f"TEST_PASS {self.test_cmd}\n{out}",
                    exit_code=0,
                    duration_ms=elapsed_ms,
                    truncated=res.truncated,
                    mutated=False,
                    step_charged=count_step,
                )
            if fail:
                return ToolResult(
                    tool="test",
                    success=False,
                    output=f"TEST_FAIL {self.test_cmd}\n{out}",
                    error="test failed",
                    exit_code=rc,
                    error_type="test_failed",
                    duration_ms=elapsed_ms,
                    truncated=res.truncated,
                    mutated=False,
                    step_charged=count_step,
                )
            return ToolResult(
                tool="test",
                success=False,
                output=f"TEST_UNKNOWN {self.test_cmd}\n{out}",
                error="test unknown outcome",
                exit_code=rc,
                error_type="test_failed",
                duration_ms=elapsed_ms,
                truncated=res.truncated,
                mutated=False,
                step_charged=count_step,
            )

        harness = self.workdir / "tests" / "test_target.py"
        run_path = path
        if harness.exists() and (
            not path or path in {".", "tests/test_target.py", "test"}
        ):
            run_path = "tests/test_target.py"
        if not run_path:
            elapsed_ms = int((time.time() - t0) * 1000)
            return ToolResult(
                tool="test",
                success=False,
                output="ERROR: no test harness available. Write a test file or use a target with a test command.",
                error="no test harness configured",
                exit_code=1,
                error_type="no_harness",
                duration_ms=elapsed_ms,
                mutated=False,
                step_charged=count_step,
                truncated=False,
            )
        run_res = self.run(run_path, count_step=count_step)
        out = run_res.output
        rc = run_res.exit_code if run_res.exit_code is not None else 1
        passed = rc == 0 or "TEST_PASS" in out
        fail = rc != 0 or "TEST_FAIL" in out
        elapsed_ms = int((time.time() - t0) * 1000)
        if passed and rc == 0:
            return ToolResult(
                tool="test",
                success=True,
                output=f"TEST_PASS {run_path}\n{out}",
                exit_code=0,
                duration_ms=elapsed_ms,
                truncated=run_res.truncated,
                mutated=False,
                step_charged=count_step,
            )
        if fail:
            return ToolResult(
                tool="test",
                success=False,
                output=f"TEST_FAIL {run_path}\n{out}",
                error="test failed",
                exit_code=rc,
                error_type="test_failed",
                duration_ms=elapsed_ms,
                truncated=run_res.truncated,
                mutated=False,
                step_charged=count_step,
            )
        return ToolResult(
            tool="test",
            success=False,
            output=f"TEST_UNKNOWN {run_path}\n{out}",
            error="test unknown outcome",
            exit_code=rc,
            error_type="test_failed",
            duration_ms=elapsed_ms,
            truncated=run_res.truncated,
            mutated=False,
            step_charged=count_step,
        )

    def _run_command(
        self,
        command: str,
        timeout: int | None = None,
        tool_name: str = "shell",
        *,
        count_step: bool = True,
    ) -> ToolResult:
        t0 = time.time()
        if count_step:
            self.steps += 1
        blocked = _shell_command_blocked(command, allow_network=self.allow_network)
        if blocked:
            elapsed_ms = int((time.time() - t0) * 1000)
            return ToolResult(
                tool=tool_name,
                success=False,
                output=f"ERROR: {blocked}",
                error=blocked,
                exit_code=1,
                error_type="policy_rejection",
                duration_ms=elapsed_ms,
                policy_rejected=True,
                mutated=False,
                step_charged=count_step,
                truncated=False,
            )
        env = _strip_secret_env(os.environ.copy())
        env["ARENA_ROOT"] = str(self.root)
        env["ARENA_WORKDIR"] = str(self.workdir)
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        env["PYTHONUNBUFFERED"] = "1"
        work = str(self.workdir.resolve())
        env["PYTHONPATH"] = work + os.pathsep + env.get("PYTHONPATH", "")
        cmd_timeout = timeout or self.tool_timeout or 90
        try:
            proc = subprocess.Popen(
                ["bash", "-c", command],
                cwd=str(self.workdir),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                start_new_session=True,
                env=env,
            )
            try:
                out, err = proc.communicate(timeout=cmd_timeout)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                except Exception:
                    pass
                elapsed_ms = int((time.time() - t0) * 1000)
                return ToolResult(
                    tool=tool_name,
                    success=False,
                    output=f"ERROR: timeout after {cmd_timeout}s",
                    error=f"timeout after {cmd_timeout}s",
                    exit_code=124,
                    error_type="timeout",
                    duration_ms=elapsed_ms,
                    timed_out=True,
                    mutated=True,
                    step_charged=count_step,
                    truncated=False,
                )
            out, out_trunc = self._maybe_cap(out or "")
            err, err_trunc = self._maybe_cap(err or "")
            is_truncated = out_trunc or err_trunc
            success = proc.returncode == 0
            elapsed_ms = int((time.time() - t0) * 1000)
            return ToolResult(
                tool=tool_name,
                success=success,
                output=f"STDOUT:\n{out}\nSTDERR:\n{err}\nrc={proc.returncode}",
                error=None if success else f"rc={proc.returncode}",
                exit_code=proc.returncode,
                error_type=None if success else "execution_error",
                duration_ms=elapsed_ms,
                truncated=is_truncated,
                mutated=True,
                step_charged=count_step,
            )
        except Exception as exc:
            elapsed_ms = int((time.time() - t0) * 1000)
            return ToolResult(
                tool=tool_name,
                success=False,
                output=f"ERROR: {exc}",
                error=str(exc),
                exit_code=1,
                error_type="exception",
                duration_ms=elapsed_ms,
                mutated=False,
                step_charged=count_step,
                truncated=False,
            )

    def shell(self, command: str, *, count_step: bool = True) -> ToolResult:
        return self._run_command(command, tool_name="shell", count_step=count_step)

    def install(self, command: str, *, count_step: bool = True) -> ToolResult:
        return self._run_command(
            command,
            timeout=self.tool_timeout or 300,
            tool_name="install",
            count_step=count_step,
        )

    def grep(
        self, pattern: str, path: str = ".", *, count_step: bool = True
    ) -> ToolResult:
        t0 = time.time()
        if count_step:
            self.steps += 1
        try:
            t = self._resolve(path)
            if not t.exists():
                elapsed_ms = int((time.time() - t0) * 1000)
                return ToolResult(
                    tool="grep",
                    success=False,
                    output=f"ERROR: not found {path}",
                    error=f"not found {path}",
                    exit_code=1,
                    error_type="not_found",
                    duration_ms=elapsed_ms,
                    mutated=False,
                    step_charged=count_step,
                )
            rx = re.compile(pattern)
            matches: list[str] = []
            skip = {".arena_bg", ".git", "__pycache__", "node_modules", ".venv"}
            for p in sorted(t.rglob("*")):
                if p.is_dir() or any(part in skip for part in p.parts):
                    continue
                if _is_skill_body_file(p, self.workdir):
                    continue
                try:
                    if p.stat().st_size > 200_000:
                        continue
                except Exception:
                    continue
                try:
                    lines = p.read_text(encoding="utf-8", errors="ignore").splitlines()
                except Exception:
                    continue
                for lineno, text in enumerate(lines, 1):
                    if rx.search(text):
                        try:
                            rel = str(p.relative_to(self.workdir.resolve()))
                        except Exception:
                            rel = str(p)
                        matches.append(f"{rel}:{lineno}:{text[:240]}")
                        if len(matches) >= 200:
                            break
                if len(matches) >= 200:
                    break
            out_str = "\n".join(matches) if matches else f"(no matches for {pattern!r})"
            capped_out, is_truncated = self._maybe_cap(out_str)
            elapsed_ms = int((time.time() - t0) * 1000)
            return ToolResult(
                tool="grep",
                success=True,
                output=capped_out,
                exit_code=0,
                duration_ms=elapsed_ms,
                truncated=is_truncated,
                mutated=False,
                step_charged=count_step,
            )
        except ValueError as exc:
            elapsed_ms = int((time.time() - t0) * 1000)
            return ToolResult(
                tool="grep",
                success=False,
                output=f"ERROR: {exc}",
                error=str(exc),
                exit_code=1,
                error_type="policy_rejection",
                duration_ms=elapsed_ms,
                policy_rejected=True,
                mutated=False,
                step_charged=count_step,
                truncated=False,
            )
        except Exception as exc:
            elapsed_ms = int((time.time() - t0) * 1000)
            return ToolResult(
                tool="grep",
                success=False,
                output=f"ERROR: {exc}",
                error=str(exc),
                exit_code=1,
                error_type="exception",
                duration_ms=elapsed_ms,
                mutated=False,
                step_charged=count_step,
                truncated=False,
            )

    def tree(self, path: str = ".", *, count_step: bool = True) -> ToolResult:
        t0 = time.time()
        if count_step:
            self.steps += 1
        try:
            t = self._resolve(path)
            if not t.exists():
                elapsed_ms = int((time.time() - t0) * 1000)
                return ToolResult(
                    tool="tree",
                    success=False,
                    output=f"ERROR: not found {path}",
                    error=f"not found {path}",
                    exit_code=1,
                    error_type="not_found",
                    duration_ms=elapsed_ms,
                    mutated=False,
                    step_charged=count_step,
                    truncated=False,
                )
            if t.is_file():
                elapsed_ms = int((time.time() - t0) * 1000)
                return ToolResult(
                    tool="tree",
                    success=True,
                    output=f"FILE {t.name} {t.stat().st_size}b",
                    exit_code=0,
                    duration_ms=elapsed_ms,
                    mutated=False,
                    step_charged=count_step,
                    truncated=False,
                )
            lines: list[str] = []
            skip = {".arena_bg", ".git", "__pycache__", "node_modules", ".venv"}

            def walk(d: Path, prefix: str, depth: int) -> None:
                if depth > 4 or len(lines) > 300:
                    return
                children = sorted(
                    (c for c in d.iterdir() if c.name not in skip),
                    key=lambda c: (c.is_file(), c.name),
                )
                for child in children:
                    marker = "" if child.is_dir() else f" {child.stat().st_size}b"
                    lines.append(f"{prefix}{child.name}{marker}")
                    if child.is_dir():
                        walk(child, prefix + "  ", depth + 1)

            walk(t, "", 0)
            out_str = "\n".join(lines) if lines else "(empty)"
            capped_out, is_truncated = self._maybe_cap(out_str)
            elapsed_ms = int((time.time() - t0) * 1000)
            return ToolResult(
                tool="tree",
                success=True,
                output=capped_out,
                exit_code=0,
                duration_ms=elapsed_ms,
                truncated=is_truncated,
                mutated=False,
                step_charged=count_step,
            )
        except ValueError as exc:
            elapsed_ms = int((time.time() - t0) * 1000)
            return ToolResult(
                tool="tree",
                success=False,
                output=f"ERROR: {exc}",
                error=str(exc),
                exit_code=1,
                error_type="policy_rejection",
                duration_ms=elapsed_ms,
                policy_rejected=True,
                mutated=False,
                step_charged=count_step,
                truncated=False,
            )
        except Exception as exc:
            elapsed_ms = int((time.time() - t0) * 1000)
            return ToolResult(
                tool="tree",
                success=False,
                output=f"ERROR: {exc}",
                error=str(exc),
                exit_code=1,
                error_type="exception",
                duration_ms=elapsed_ms,
                mutated=False,
                step_charged=count_step,
                truncated=False,
            )

    def cp(self, src: str, dst: str, *, count_step: bool = True) -> ToolResult:
        t0 = time.time()
        if count_step:
            self.steps += 1
        try:
            s = self._resolve(src)
            d = self._resolve(dst)
            if not s.exists():
                elapsed_ms = int((time.time() - t0) * 1000)
                return ToolResult(
                    tool="cp",
                    success=False,
                    output=f"ERROR: not found {src}",
                    error=f"not found {src}",
                    exit_code=1,
                    error_type="not_found",
                    duration_ms=elapsed_ms,
                    mutated=False,
                    step_charged=count_step,
                    truncated=False,
                )
            if _is_skill_body_file(s, self.workdir):
                elapsed_ms = int((time.time() - t0) * 1000)
                return ToolResult(
                    tool="cp",
                    success=False,
                    output="ERROR: skill body is only available through use_skill",
                    error="skill body requires use_skill",
                    exit_code=1,
                    error_type="policy_rejection",
                    duration_ms=elapsed_ms,
                    policy_rejected=True,
                    mutated=False,
                    step_charged=count_step,
                    truncated=False,
                )
            if d.exists() and d.is_dir() and not s.is_dir():
                d = d / s.name
            if s.is_dir():
                shutil.copytree(s, d, dirs_exist_ok=True)
            else:
                shutil.copy2(s, d)
            elapsed_ms = int((time.time() - t0) * 1000)
            return ToolResult(
                tool="cp",
                success=True,
                output=f"COPIED {src} -> {dst}",
                exit_code=0,
                duration_ms=elapsed_ms,
                mutated=True,
                step_charged=count_step,
                truncated=False,
            )
        except ValueError as exc:
            elapsed_ms = int((time.time() - t0) * 1000)
            return ToolResult(
                tool="cp",
                success=False,
                output=f"ERROR: {exc}",
                error=str(exc),
                exit_code=1,
                error_type="policy_rejection",
                duration_ms=elapsed_ms,
                policy_rejected=True,
                mutated=False,
                step_charged=count_step,
                truncated=False,
            )
        except Exception as exc:
            elapsed_ms = int((time.time() - t0) * 1000)
            return ToolResult(
                tool="cp",
                success=False,
                output=f"ERROR: {exc}",
                error=str(exc),
                exit_code=1,
                error_type="exception",
                duration_ms=elapsed_ms,
                mutated=False,
                step_charged=count_step,
                truncated=False,
            )

    def mv(self, src: str, dst: str, *, count_step: bool = True) -> ToolResult:
        t0 = time.time()
        if count_step:
            self.steps += 1
        try:
            s = self._resolve(src)
            d = self._resolve(dst)
            if not s.exists():
                elapsed_ms = int((time.time() - t0) * 1000)
                return ToolResult(
                    tool="mv",
                    success=False,
                    output=f"ERROR: not found {src}",
                    error=f"not found {src}",
                    exit_code=1,
                    error_type="not_found",
                    duration_ms=elapsed_ms,
                    mutated=False,
                    step_charged=count_step,
                    truncated=False,
                )
            if _is_skill_body_file(s, self.workdir):
                elapsed_ms = int((time.time() - t0) * 1000)
                return ToolResult(
                    tool="mv",
                    success=False,
                    output="ERROR: skill body is only available through use_skill",
                    error="skill body requires use_skill",
                    exit_code=1,
                    error_type="policy_rejection",
                    duration_ms=elapsed_ms,
                    policy_rejected=True,
                    mutated=False,
                    step_charged=count_step,
                    truncated=False,
                )
            if d.exists() and d.is_dir():
                d = d / s.name
            shutil.move(str(s), str(d))
            elapsed_ms = int((time.time() - t0) * 1000)
            return ToolResult(
                tool="mv",
                success=True,
                output=f"MOVED {src} -> {dst}",
                exit_code=0,
                duration_ms=elapsed_ms,
                mutated=True,
                step_charged=count_step,
                truncated=False,
            )
        except ValueError as exc:
            elapsed_ms = int((time.time() - t0) * 1000)
            return ToolResult(
                tool="mv",
                success=False,
                output=f"ERROR: {exc}",
                error=str(exc),
                exit_code=1,
                error_type="policy_rejection",
                duration_ms=elapsed_ms,
                policy_rejected=True,
                mutated=False,
                step_charged=count_step,
                truncated=False,
            )
        except Exception as exc:
            elapsed_ms = int((time.time() - t0) * 1000)
            return ToolResult(
                tool="mv",
                success=False,
                output=f"ERROR: {exc}",
                error=str(exc),
                exit_code=1,
                error_type="exception",
                duration_ms=elapsed_ms,
                mutated=False,
                step_charged=count_step,
                truncated=False,
            )

    def rm(self, path: str, *, count_step: bool = True) -> ToolResult:
        t0 = time.time()
        if count_step:
            self.steps += 1
        try:
            t = self._resolve(path)
            if not t.exists():
                elapsed_ms = int((time.time() - t0) * 1000)
                return ToolResult(
                    tool="rm",
                    success=False,
                    output=f"ERROR: not found {path}",
                    error=f"not found {path}",
                    exit_code=1,
                    error_type="not_found",
                    duration_ms=elapsed_ms,
                    mutated=False,
                    step_charged=count_step,
                    truncated=False,
                )
            if t.is_dir():
                shutil.rmtree(t)
            else:
                t.unlink()
            elapsed_ms = int((time.time() - t0) * 1000)
            return ToolResult(
                tool="rm",
                success=True,
                output=f"REMOVED {path}",
                exit_code=0,
                duration_ms=elapsed_ms,
                mutated=True,
                step_charged=count_step,
                truncated=False,
            )
        except ValueError as exc:
            elapsed_ms = int((time.time() - t0) * 1000)
            return ToolResult(
                tool="rm",
                success=False,
                output=f"ERROR: {exc}",
                error=str(exc),
                exit_code=1,
                error_type="policy_rejection",
                duration_ms=elapsed_ms,
                policy_rejected=True,
                mutated=False,
                step_charged=count_step,
                truncated=False,
            )
        except Exception as exc:
            elapsed_ms = int((time.time() - t0) * 1000)
            return ToolResult(
                tool="rm",
                success=False,
                output=f"ERROR: {exc}",
                error=str(exc),
                exit_code=1,
                error_type="exception",
                duration_ms=elapsed_ms,
                mutated=False,
                step_charged=count_step,
                truncated=False,
            )

    def fetch(self, url: str, *, count_step: bool = True) -> ToolResult:
        t0 = time.time()
        if count_step:
            self.steps += 1
        if not self.allow_network:
            elapsed_ms = int((time.time() - t0) * 1000)
            return ToolResult(
                tool="fetch",
                success=False,
                output="ERROR: network fetch blocked (target network is false)",
                error="network fetch blocked (target network is false)",
                exit_code=1,
                error_type="policy_rejection",
                duration_ms=elapsed_ms,
                policy_rejected=True,
                mutated=False,
                step_charged=count_step,
                truncated=False,
            )
        blocked = _fetch_url_blocked(url)
        if blocked:
            elapsed_ms = int((time.time() - t0) * 1000)
            return ToolResult(
                tool="fetch",
                success=False,
                output=f"ERROR: fetch blocked ({blocked})",
                error=blocked,
                exit_code=1,
                error_type="policy_rejection",
                duration_ms=elapsed_ms,
                policy_rejected=True,
                mutated=False,
                step_charged=count_step,
                truncated=False,
            )
        try:
            import httpx

            resp = httpx.get(url, timeout=20, follow_redirects=False)
            if resp.is_redirect:
                elapsed_ms = int((time.time() - t0) * 1000)
                return ToolResult(
                    tool="fetch",
                    success=False,
                    output="ERROR: fetch blocked (redirect not followed)",
                    error="redirect not followed",
                    exit_code=1,
                    error_type="policy_rejection",
                    duration_ms=elapsed_ms,
                    policy_rejected=True,
                    mutated=False,
                    step_charged=count_step,
                    truncated=False,
                )
            body, is_truncated = self._maybe_cap(resp.text[:20000])
            success = resp.status_code == 200
            elapsed_ms = int((time.time() - t0) * 1000)
            return ToolResult(
                tool="fetch",
                success=success,
                output=f"STATUS {resp.status_code}\n{body}",
                error=None if success else f"status {resp.status_code}",
                exit_code=0 if success else 1,
                error_type=None if success else "execution_error",
                duration_ms=elapsed_ms,
                truncated=is_truncated,
                mutated=False,
                step_charged=count_step,
            )
        except Exception as exc:
            elapsed_ms = int((time.time() - t0) * 1000)
            return ToolResult(
                tool="fetch",
                success=False,
                output=f"ERROR: {exc}",
                error=str(exc),
                exit_code=1,
                error_type="exception",
                duration_ms=elapsed_ms,
                mutated=False,
                step_charged=count_step,
                truncated=False,
            )

    def search(self, query: str, *, count_step: bool = True) -> ToolResult:
        if count_step:
            self.steps += 1
        return ToolResult(
            tool="search",
            success=True,
            output=(
                "SEARCH has no external key configured. Use TOOL FETCH url=<known endpoint> "
                f"to pull specific pages, and read TARGET.md + tests/test_target.py first. "
                f"(query ignored: {query[:200]})"
            ),
            exit_code=0,
            duration_ms=0,
            mutated=False,
            step_charged=count_step,
            truncated=False,
        )

    def bg(self, name: str, content: str, *, count_step: bool = True) -> ToolResult:
        t0 = time.time()
        if count_step:
            self.steps += 1
        blocked = _shell_command_blocked(
            content or "", allow_network=self.allow_network
        )
        if blocked:
            elapsed_ms = int((time.time() - t0) * 1000)
            return ToolResult(
                tool="bg",
                success=False,
                output=f"ERROR: {blocked}",
                error=blocked,
                exit_code=1,
                error_type="policy_rejection",
                duration_ms=elapsed_ms,
                policy_rejected=True,
                mutated=False,
                step_charged=count_step,
                truncated=False,
            )
        try:
            mgr = self.procs.start(
                name, content or "", env=_strip_secret_env(os.environ.copy())
            )
            elapsed_ms = int((time.time() - t0) * 1000)
            return ToolResult(
                tool="bg",
                success=True,
                output=f"BG STARTED {mgr.name} pid={mgr.proc.pid}",
                exit_code=0,
                duration_ms=elapsed_ms,
                mutated=True,
                step_charged=count_step,
                truncated=False,
            )
        except Exception as exc:
            elapsed_ms = int((time.time() - t0) * 1000)
            return ToolResult(
                tool="bg",
                success=False,
                output=f"ERROR: {exc}",
                error=str(exc),
                exit_code=1,
                error_type="exception",
                duration_ms=elapsed_ms,
                mutated=False,
                step_charged=count_step,
                truncated=False,
            )

    def ps(self, *, count_step: bool = True) -> ToolResult:
        if count_step:
            self.steps += 1
        out_str, is_truncated = self._maybe_cap(self.procs.list())
        return ToolResult(
            tool="ps",
            success=True,
            output=out_str,
            exit_code=0,
            duration_ms=0,
            mutated=False,
            step_charged=count_step,
            truncated=is_truncated,
        )

    def kill(self, name: str, *, count_step: bool = True) -> ToolResult:
        t0 = time.time()
        if count_step:
            self.steps += 1
        res = self.procs.kill(name)
        success = not res.startswith("ERROR")
        elapsed_ms = int((time.time() - t0) * 1000)
        return ToolResult(
            tool="kill",
            success=success,
            output=res,
            error=None if success else res,
            exit_code=0 if success else 1,
            error_type=None if success else "execution_error",
            duration_ms=elapsed_ms,
            mutated=True,
            step_charged=count_step,
            truncated=False,
        )

    def logs(
        self, name: str, tail: str = "8000", *, count_step: bool = True
    ) -> ToolResult:
        t0 = time.time()
        if count_step:
            self.steps += 1
        try:
            n = int(tail)
        except Exception:
            n = 8000
        res = self.procs.logs(name, n)
        res_capped, is_truncated = self._maybe_cap(res)
        success = not res.startswith("ERROR")
        elapsed_ms = int((time.time() - t0) * 1000)
        return ToolResult(
            tool="logs",
            success=success,
            output=res_capped,
            error=None if success else res,
            exit_code=0 if success else 1,
            error_type=None if success else "execution_error",
            duration_ms=elapsed_ms,
            truncated=is_truncated,
            mutated=False,
            step_charged=count_step,
        )

    def use_skill(self, name: str, *, count_step: bool = True) -> ToolResult:
        t0 = time.time()
        try:
            if count_step:
                self.steps += 1
            if name in self.skill_reads:
                return ToolResult(
                    tool="use_skill",
                    success=True,
                    output=f"SKILL_ALREADY_LOADED {name}",
                    exit_code=0,
                    duration_ms=0,
                    mutated=False,
                    step_charged=count_step,
                    truncated=False,
                )
            skill_path = self.workdir / ".agents" / "skills" / name / "SKILL.md"
            if skill_path.is_file():
                body, is_truncated = self._maybe_cap(
                    skill_path.read_text(encoding="utf-8", errors="ignore")
                )
                self.skill_reads.add(name)
                elapsed_ms = int((time.time() - t0) * 1000)
                return ToolResult(
                    tool="use_skill",
                    success=True,
                    output=body,
                    exit_code=0,
                    duration_ms=elapsed_ms,
                    truncated=is_truncated,
                    mutated=False,
                    step_charged=count_step,
                )
            from .skill_pool import skills_root

            source_path = skills_root() / name / "SKILL.md"
            if not source_path.is_file():
                elapsed_ms = int((time.time() - t0) * 1000)
                return ToolResult(
                    tool="use_skill",
                    success=False,
                    output=f"ERROR: skill not mounted: {name}",
                    error=f"skill not mounted: {name}",
                    exit_code=1,
                    error_type="not_found",
                    duration_ms=elapsed_ms,
                    mutated=False,
                    step_charged=count_step,
                    truncated=False,
                )
            body, is_truncated = self._maybe_cap(
                source_path.read_text(encoding="utf-8", errors="ignore")
            )
            self.skill_reads.add(name)
            elapsed_ms = int((time.time() - t0) * 1000)
            return ToolResult(
                tool="use_skill",
                success=True,
                output=body,
                exit_code=0,
                duration_ms=elapsed_ms,
                truncated=is_truncated,
                mutated=False,
                step_charged=count_step,
            )
        except Exception as exc:
            elapsed_ms = int((time.time() - t0) * 1000)
            return ToolResult(
                tool="use_skill",
                success=False,
                output=f"ERROR: {exc}",
                error=str(exc),
                exit_code=1,
                error_type="exception",
                duration_ms=elapsed_ms,
                mutated=False,
                step_charged=count_step,
                truncated=False,
            )

    def list_skills(self, *, count_step: bool = True) -> ToolResult:
        if count_step:
            self.steps += 1
        skills_dir = self.workdir / ".agents" / "skills"
        if not skills_dir.is_dir():
            return ToolResult(
                tool="skills",
                success=True,
                output="(no skills mounted)",
                exit_code=0,
                duration_ms=0,
                mutated=False,
                step_charged=count_step,
                truncated=False,
            )
        names = sorted(
            d.name for d in skills_dir.iterdir() if (d / "SKILL.md").is_file()
        )
        out_text = "\n".join(names) if names else "(no skills mounted)"
        capped_out, is_truncated = self._maybe_cap(out_text)
        return ToolResult(
            tool="skills",
            success=True,
            output=capped_out,
            exit_code=0,
            duration_ms=0,
            mutated=False,
            step_charged=count_step,
            truncated=is_truncated,
        )

    def skills(
        self,
        chosen: list[str] | None = None,
        *,
        index: str | None = None,
        search: str | None = None,
        skill: str | None = None,
        list: bool = False,
        count_step: bool = True,
    ) -> ToolResult:
        if list and any(value is not None for value in (index, search, skill)):
            if count_step:
                self.steps += 1
            return ToolResult(
                tool="skills",
                success=False,
                output="ERROR [invalid_request]: list cannot be combined with index, search, or skill",
                error="list cannot be combined with index, search, or skill",
                error_type="invalid_request",
                exit_code=1,
                duration_ms=0,
                mutated=False,
                step_charged=count_step,
                truncated=False,
            )
        if chosen and any(value is not None for value in (index, search, skill)):
            if count_step:
                self.steps += 1
            return ToolResult(
                tool="skills",
                success=False,
                output="ERROR [invalid_request]: chosen cannot be combined with discovery selectors",
                error="chosen cannot be combined with discovery selectors",
                error_type="invalid_request",
                exit_code=1,
                duration_ms=0,
                mutated=False,
                step_charged=count_step,
                truncated=False,
            )
        if list:
            return self.list_skills(count_step=count_step)
        if count_step:
            self.steps += 1
        if (
            index is not None
            or search is not None
            or skill is not None
            or chosen is None
        ):
            from ...skills import (
                DiscoveryErrorView,
                DiscoveryRequestError,
                UnknownIndexError,
                UnknownSkillError,
                discover_skills,
                format_discovery_text,
            )

            try:
                view = discover_skills(
                    index=index,
                    search=search,
                    skill=skill,
                )
                output = format_discovery_text(view)
                return ToolResult(
                    tool="skills",
                    success=True,
                    output=output,
                    exit_code=0,
                    duration_ms=0,
                    mutated=False,
                    step_charged=count_step,
                    truncated=False,
                )
            except (DiscoveryRequestError, UnknownIndexError, UnknownSkillError) as exc:
                if isinstance(exc, DiscoveryRequestError):
                    error_type = "invalid_request"
                elif isinstance(exc, UnknownIndexError):
                    error_type = "unknown_index"
                else:
                    error_type = "unknown_skill"
                error_view = DiscoveryErrorView(
                    error=str(exc),
                    error_type=error_type,
                    requested=str(index or search or skill or ""),
                )
                return ToolResult(
                    tool="skills",
                    success=False,
                    output=format_discovery_text(error_view),
                    error=str(exc),
                    error_type=error_type,
                    exit_code=1,
                    duration_ms=0,
                    mutated=False,
                    step_charged=count_step,
                    truncated=False,
                )
        chosen_list = chosen or []
        return ToolResult(
            tool="skills",
            success=True,
            output=f"SKILLS_CHOSEN {','.join(chosen_list)}",
            exit_code=0,
            duration_ms=0,
            mutated=False,
            step_charged=count_step,
            truncated=False,
        )

    def _ensure_page(self):
        if self._page is not None:
            return self._page
        try:
            from playwright.sync_api import sync_playwright

            self._pw = sync_playwright().start()
            self._browser = self._pw.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                ],
            )
            self._page = self._browser.new_page()
            return self._page
        except Exception:
            return None

    def playwright_navigate(self, url: str, *, count_step: bool = True) -> ToolResult:
        t0 = time.time()
        if count_step:
            self.steps += 1
        page = self._ensure_page()
        if page is not None:
            try:
                resp = page.goto(url, timeout=10000)
                status = resp.status if resp else 200
                title = page.title()
                elapsed_ms = int((time.time() - t0) * 1000)
                return ToolResult(
                    tool="playwright_navigate",
                    success=True,
                    output=f"NAVIGATED to {url} [status: {status}, title: '{title}']",
                    exit_code=0,
                    duration_ms=elapsed_ms,
                    mutated=False,
                    step_charged=count_step,
                    truncated=False,
                )
            except Exception as exc:
                elapsed_ms = int((time.time() - t0) * 1000)
                return ToolResult(
                    tool="playwright_navigate",
                    success=False,
                    output=f"ERROR navigating to {url}: {exc}",
                    error=str(exc),
                    exit_code=1,
                    error_type="browser_error",
                    duration_ms=elapsed_ms,
                    mutated=False,
                    step_charged=count_step,
                    truncated=False,
                )
        try:
            import httpx

            with httpx.Client(timeout=5.0) as client:
                res = client.get(url)
                elapsed_ms = int((time.time() - t0) * 1000)
                return ToolResult(
                    tool="playwright_navigate",
                    success=res.status_code < 400,
                    output=f"NAVIGATED (HTTP probe) to {url} [status: {res.status_code}]",
                    exit_code=0 if res.status_code < 400 else 1,
                    duration_ms=elapsed_ms,
                    mutated=False,
                    step_charged=count_step,
                    truncated=False,
                )
        except Exception as exc:
            elapsed_ms = int((time.time() - t0) * 1000)
            return ToolResult(
                tool="playwright_navigate",
                success=False,
                output=f"ERROR navigating to {url}: {exc}",
                error=str(exc),
                exit_code=1,
                error_type="browser_error",
                duration_ms=elapsed_ms,
                mutated=False,
                step_charged=count_step,
                truncated=False,
            )

    def playwright_click(
        self, selector: str, *, count_step: bool = True
    ) -> ToolResult:
        t0 = time.time()
        if count_step:
            self.steps += 1
        page = self._ensure_page()
        if page is not None:
            try:
                page.click(selector, timeout=5000)
                elapsed_ms = int((time.time() - t0) * 1000)
                return ToolResult(
                    tool="playwright_click",
                    success=True,
                    output=f"CLICKED selector '{selector}'",
                    exit_code=0,
                    duration_ms=elapsed_ms,
                    mutated=False,
                    step_charged=count_step,
                    truncated=False,
                )
            except Exception as exc:
                elapsed_ms = int((time.time() - t0) * 1000)
                return ToolResult(
                    tool="playwright_click",
                    success=False,
                    output=f"ERROR clicking '{selector}': {exc}",
                    error=str(exc),
                    exit_code=1,
                    error_type="browser_error",
                    duration_ms=elapsed_ms,
                    mutated=False,
                    step_charged=count_step,
                    truncated=False,
                )
        elapsed_ms = int((time.time() - t0) * 1000)
        return ToolResult(
            tool="playwright_click",
            success=True,
            output=f"CLICKED selector '{selector}' (simulated)",
            exit_code=0,
            duration_ms=elapsed_ms,
            mutated=False,
            step_charged=count_step,
            truncated=False,
        )

    def playwright_fill(
        self, selector: str, text: str, *, count_step: bool = True
    ) -> ToolResult:
        t0 = time.time()
        if count_step:
            self.steps += 1
        page = self._ensure_page()
        if page is not None:
            try:
                page.fill(selector, text, timeout=5000)
                elapsed_ms = int((time.time() - t0) * 1000)
                return ToolResult(
                    tool="playwright_fill",
                    success=True,
                    output=f"FILLED selector '{selector}' with {len(text)} characters",
                    exit_code=0,
                    duration_ms=elapsed_ms,
                    mutated=False,
                    step_charged=count_step,
                    truncated=False,
                )
            except Exception as exc:
                elapsed_ms = int((time.time() - t0) * 1000)
                return ToolResult(
                    tool="playwright_fill",
                    success=False,
                    output=f"ERROR filling '{selector}': {exc}",
                    error=str(exc),
                    exit_code=1,
                    error_type="browser_error",
                    duration_ms=elapsed_ms,
                    mutated=False,
                    step_charged=count_step,
                    truncated=False,
                )
        elapsed_ms = int((time.time() - t0) * 1000)
        return ToolResult(
            tool="playwright_fill",
            success=True,
            output=f"FILLED selector '{selector}' (simulated)",
            exit_code=0,
            duration_ms=elapsed_ms,
            mutated=False,
            step_charged=count_step,
            truncated=False,
        )

    def playwright_screenshot(
        self, path: str = "", *, count_step: bool = True
    ) -> ToolResult:
        t0 = time.time()
        if count_step:
            self.steps += 1
        target_path = path or f"screenshot_{int(time.time() * 1000)}.png"
        p = self._resolve(target_path)
        page = self._ensure_page()
        if page is not None:
            try:
                page.screenshot(path=str(p))
                elapsed_ms = int((time.time() - t0) * 1000)
                return ToolResult(
                    tool="playwright_screenshot",
                    success=True,
                    output=f"SCREENSHOT saved to {target_path} ({p.stat().st_size} bytes)",
                    exit_code=0,
                    duration_ms=elapsed_ms,
                    mutated=True,
                    step_charged=count_step,
                    truncated=False,
                )
            except Exception as exc:
                elapsed_ms = int((time.time() - t0) * 1000)
                return ToolResult(
                    tool="playwright_screenshot",
                    success=False,
                    output=f"ERROR capturing screenshot: {exc}",
                    error=str(exc),
                    exit_code=1,
                    error_type="browser_error",
                    duration_ms=elapsed_ms,
                    mutated=False,
                    step_charged=count_step,
                    truncated=False,
                )
        p.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDRmock_screenshot")
        elapsed_ms = int((time.time() - t0) * 1000)
        return ToolResult(
            tool="playwright_screenshot",
            success=True,
            output=f"SCREENSHOT saved to {target_path} (mock screenshot)",
            exit_code=0,
            duration_ms=elapsed_ms,
            mutated=True,
            step_charged=count_step,
            truncated=False,
        )

    def playwright_read(
        self, selector: str = "body", *, count_step: bool = True
    ) -> ToolResult:
        t0 = time.time()
        if count_step:
            self.steps += 1
        target_sel = selector or "body"
        page = self._ensure_page()
        if page is not None:
            try:
                el = page.query_selector(target_sel)
                if not el:
                    elapsed_ms = int((time.time() - t0) * 1000)
                    return ToolResult(
                        tool="playwright_read",
                        success=False,
                        output=f"ERROR: selector '{target_sel}' not found in DOM",
                        exit_code=1,
                        duration_ms=elapsed_ms,
                        mutated=False,
                        step_charged=count_step,
                        truncated=False,
                    )
                text = el.inner_text()
                elapsed_ms = int((time.time() - t0) * 1000)
                return ToolResult(
                    tool="playwright_read",
                    success=True,
                    output=f"DOM TEXT ({target_sel}):\n{text[:4000]}",
                    exit_code=0,
                    duration_ms=elapsed_ms,
                    mutated=False,
                    step_charged=count_step,
                    truncated=len(text) > 4000,
                )
            except Exception as exc:
                elapsed_ms = int((time.time() - t0) * 1000)
                return ToolResult(
                    tool="playwright_read",
                    success=False,
                    output=f"ERROR reading '{target_sel}': {exc}",
                    error=str(exc),
                    exit_code=1,
                    error_type="browser_error",
                    duration_ms=elapsed_ms,
                    mutated=False,
                    step_charged=count_step,
                    truncated=False,
                )
        elapsed_ms = int((time.time() - t0) * 1000)
        return ToolResult(
            tool="playwright_read",
            success=True,
            output=f"DOM TEXT ({target_sel}):\n(simulated page text for {target_sel})",
            exit_code=0,
            duration_ms=elapsed_ms,
            mutated=False,
            step_charged=count_step,
            truncated=False,
        )

    def playwright_wait(
        self, selector: str, timeout_ms: int = 5000, *, count_step: bool = True
    ) -> ToolResult:
        t0 = time.time()
        if count_step:
            self.steps += 1
        page = self._ensure_page()
        if page is not None:
            try:
                page.wait_for_selector(selector, timeout=timeout_ms or 5000)
                elapsed_ms = int((time.time() - t0) * 1000)
                return ToolResult(
                    tool="playwright_wait",
                    success=True,
                    output=f"WAIT_SUCCESS: selector '{selector}' appeared",
                    exit_code=0,
                    duration_ms=elapsed_ms,
                    mutated=False,
                    step_charged=count_step,
                    truncated=False,
                )
            except Exception as exc:
                elapsed_ms = int((time.time() - t0) * 1000)
                return ToolResult(
                    tool="playwright_wait",
                    success=False,
                    output=f"WAIT_TIMEOUT: selector '{selector}' not found within {timeout_ms}ms: {exc}",
                    error=str(exc),
                    exit_code=1,
                    error_type="browser_timeout",
                    duration_ms=elapsed_ms,
                    mutated=False,
                    step_charged=count_step,
                    truncated=False,
                )
        elapsed_ms = int((time.time() - t0) * 1000)
        return ToolResult(
            tool="playwright_wait",
            success=True,
            output=f"WAIT_SUCCESS: selector '{selector}' appeared (simulated)",
            exit_code=0,
            duration_ms=elapsed_ms,
            mutated=False,
            step_charged=count_step,
            truncated=False,
        )

    def http_request(
        self,
        method: str,
        url: str,
        headers: dict | None = None,
        body: str = "",
        *,
        count_step: bool = True,
    ) -> ToolResult:
        t0 = time.time()
        if count_step:
            self.steps += 1
        try:
            import httpx

            with httpx.Client(timeout=15.0) as client:
                res = client.request(
                    method=method.upper(),
                    url=url,
                    headers=headers,
                    content=body.encode("utf-8") if body else None,
                )
                elapsed_ms = int((time.time() - t0) * 1000)
                resp_preview = res.text[:3000]
                return ToolResult(
                    tool="http_request",
                    success=res.status_code < 400,
                    output=f"HTTP {res.status_code} {res.reason_phrase}\n{resp_preview}",
                    exit_code=0 if res.status_code < 400 else 1,
                    duration_ms=elapsed_ms,
                    mutated=False,
                    step_charged=count_step,
                    truncated=len(res.text) > 3000,
                )
        except Exception as exc:
            elapsed_ms = int((time.time() - t0) * 1000)
            return ToolResult(
                tool="http_request",
                success=False,
                output=f"ERROR: HTTP request failed: {exc}",
                error=str(exc),
                exit_code=1,
                error_type="network_error",
                duration_ms=elapsed_ms,
                mutated=False,
                step_charged=count_step,
                truncated=False,
            )

    def sql_query(self, query: str, *, count_step: bool = True) -> ToolResult:
        t0 = time.time()
        if count_step:
            self.steps += 1
        # Explicitly reject attempts to query evaluator/trusted schemas directly
        if "arena_trusted" in query.lower():
            elapsed_ms = int((time.time() - t0) * 1000)
            return ToolResult(
                tool="sql_query",
                success=False,
                output="ERROR: permission denied for schema 'arena_trusted' (restricted to app_public)",
                error="permission denied for schema 'arena_trusted'",
                exit_code=1,
                error_type="database_permission_denied",
                duration_ms=elapsed_ms,
                mutated=False,
                step_charged=count_step,
                truncated=False,
            )
        ro_url = os.environ.get("BATTLE_RO_DATABASE_URL") or os.environ.get(
            "DATABASE_URL"
        )
        if not ro_url or "mock" in ro_url or os.environ.get("ARENA_HERMETIC") == "1":
            elapsed_ms = int((time.time() - t0) * 1000)
            return ToolResult(
                tool="sql_query",
                success=True,
                output="SQL_QUERY (mock):\nRows returned: 1\n[('1', 'alice', 'public_profile')]",
                exit_code=0,
                duration_ms=elapsed_ms,
                mutated=False,
                step_charged=count_step,
                truncated=False,
            )
        try:
            import psycopg

            # Enforce read-only AND app_public search path
            options = "-cdefault_transaction_read_only=on -csearch_path=app_public"
            conn_url = (
                ro_url
                if "default_transaction_read_only" in ro_url
                else (
                    f"{ro_url}&options={options}"
                    if "?" in ro_url
                    else f"{ro_url}?options={options}"
                )
            )
            with psycopg.connect(conn_url, autocommit=True) as conn:
                with conn.cursor() as cur:
                    cur.execute(query)
                    if cur.description:
                        rows = cur.fetchall()
                        cols = [d.name for d in cur.description]
                        elapsed_ms = int((time.time() - t0) * 1000)
                        return ToolResult(
                            tool="sql_query",
                            success=True,
                            output=f"COLUMNS: {cols}\nROWS ({len(rows)}):\n{rows[:50]}",
                            exit_code=0,
                            duration_ms=elapsed_ms,
                            mutated=False,
                            step_charged=count_step,
                            truncated=len(rows) > 50,
                        )
                    elapsed_ms = int((time.time() - t0) * 1000)
                    return ToolResult(
                        tool="sql_query",
                        success=True,
                        output="SQL_QUERY: executed (no rows returned)",
                        exit_code=0,
                        duration_ms=elapsed_ms,
                        mutated=False,
                        step_charged=count_step,
                        truncated=False,
                    )
        except Exception as exc:
            elapsed_ms = int((time.time() - t0) * 1000)
            return ToolResult(
                tool="sql_query",
                success=False,
                output=f"ERROR: SQL query failed (read-only enforced): {exc}",
                error=str(exc),
                exit_code=1,
                error_type="database_error",
                duration_ms=elapsed_ms,
                mutated=False,
                step_charged=count_step,
                truncated=False,
            )

    def exec_tool(self, call: dict, *, count_step: bool = True) -> ToolResult:
        tool = str(call.get("tool") or "").strip().lower()
        if tool == "write":
            return self.write(
                call.get("path", ""), call.get("content", ""), count_step=count_step
            )
        if tool == "read":
            return self.read(call.get("path", ""), count_step=count_step)
        if tool == "ls":
            return self.ls(call.get("path", "."), count_step=count_step)
        if tool == "clean":
            return self.clean(call.get("path", ""), count_step=count_step)
        if tool == "run":
            if call.get("content"):
                tmp = f"_tmp_run_{int(time.time() * 1000)}.py"
                self.write(tmp, call.get("content", ""), count_step=False)
                res = self.run(tmp, count_step=count_step)
                self.clean(tmp, count_step=False)
                return res
            return self.run(call.get("path", ""), count_step=count_step)
        if tool == "test":
            return self.test(call.get("path", ""), count_step=count_step)
        if tool == "shell":
            return self.shell(
                call.get("cmd") or call.get("content", ""), count_step=count_step
            )
        if tool == "install":
            return self.install(
                call.get("content", "") or call.get("cmd", ""), count_step=count_step
            )
        if tool == "grep":
            return self.grep(
                call.get("pattern", ""), call.get("path", "."), count_step=count_step
            )
        if tool == "tree":
            return self.tree(call.get("path", "."), count_step=count_step)
        if tool == "cp":
            return self.cp(
                call.get("src", ""), call.get("dst", ""), count_step=count_step
            )
        if tool == "mv":
            return self.mv(
                call.get("src", ""), call.get("dst", ""), count_step=count_step
            )
        if tool == "rm":
            return self.rm(call.get("path", ""), count_step=count_step)
        if tool == "fetch":
            return self.fetch(call.get("url", ""), count_step=count_step)
        if tool == "search":
            return self.search(call.get("query", ""), count_step=count_step)
        if tool == "bg":
            return self.bg(
                call.get("name", ""), call.get("content", ""), count_step=count_step
            )
        if tool == "ps":
            return self.ps(count_step=count_step)
        if tool == "kill":
            return self.kill(call.get("name", ""), count_step=count_step)
        if tool == "logs":
            return self.logs(
                call.get("name", ""), call.get("tail", "8000"), count_step=count_step
            )
        if tool == "use_skill":
            return self.use_skill(call.get("name", ""), count_step=count_step)
        if tool == "skills":
            return self.skills(
                call.get("chosen"),
                index=call.get("index"),
                search=call.get("search"),
                skill=call.get("skill"),
                list=bool(call.get("list")),
                count_step=count_step,
            )
        if tool == "playwright_navigate":
            return self.playwright_navigate(call.get("url", ""), count_step=count_step)
        if tool == "playwright_click":
            return self.playwright_click(
                call.get("selector", ""), count_step=count_step
            )
        if tool == "playwright_fill":
            return self.playwright_fill(
                call.get("selector", ""), call.get("text", ""), count_step=count_step
            )
        if tool == "playwright_screenshot":
            return self.playwright_screenshot(
                call.get("path", ""), count_step=count_step
            )
        if tool == "playwright_read":
            return self.playwright_read(
                call.get("selector", "") or call.get("path", ""), count_step=count_step
            )
        if tool == "playwright_wait":
            return self.playwright_wait(
                call.get("selector", ""),
                timeout_ms=int(call.get("timeout_ms") or 5000),
                count_step=count_step,
            )
        if tool == "http_request":
            return self.http_request(
                call.get("method", "GET"),
                call.get("url", ""),
                headers=call.get("headers"),
                body=call.get("body", ""),
                count_step=count_step,
            )
        if tool == "sql_query":
            return self.sql_query(call.get("query", ""), count_step=count_step)
        if tool == "done":
            return ToolResult(
                tool="done",
                success=True,
                output="DONE",
                exit_code=0,
                duration_ms=0,
                mutated=False,
                step_charged=False,
                truncated=False,
            )
        if tool == "error":
            err = call.get("error", "ERROR")
            if count_step:
                self.steps += 1
            return ToolResult(
                tool="error",
                success=False,
                output=f"ERROR: {err}",
                error=str(err),
                exit_code=1,
                error_type="parse_error",
                duration_ms=0,
                mutated=False,
                step_charged=count_step,
                truncated=False,
            )
        if count_step:
            self.steps += 1
        return ToolResult(
            tool=tool,
            success=False,
            output=f"ERROR: unknown tool: '{tool}'",
            error=f"unknown tool: '{tool}'",
            exit_code=1,
            error_type="unknown_tool",
            duration_ms=0,
            mutated=False,
            step_charged=count_step,
            truncated=False,
        )


def fighter_roles(format_config: dict) -> list[str]:
    seen: list[str] = []
    for phase in format_config.get("phases") or []:
        for role in phase.get("participants") or []:
            if not role or role == "judge" or role in seen:
                continue
            seen.append(role)
    if seen:
        return seen
    return [r for r in (format_config.get("roles") or []) if r != "judge"]


def tool_phase_name(format_config: dict) -> str:
    for phase in format_config.get("phases") or []:
        parts = [p for p in (phase.get("participants") or []) if p != "judge"]
        if parts:
            return str(phase.get("name") or "race")
    return "race"


def is_builder_breaker(format_config: dict | None) -> bool:
    """True when the format is an asymmetric builder vs breaker target match.

    compile_target_to_battle_config emits `format == "builder_breaker"` together
    with a two-phase battle_plan (build -> break). These matches are verified
    asymmetrically via verify_builder_breaker_submission rather than the
    single-phase verify_target_submission path.
    """
    cfg = format_config or {}
    if str(cfg.get("format")) == "builder_breaker":
        return True
    actors = {str(p.get("actor")) for p in cfg.get("battle_plan", {}).get("phases", [])}
    return actors == {"builder", "breaker"}


class AdvancedExecutor(Executor):
    @staticmethod
    def _collect_workspace(work: Path) -> tuple[dict[str, str], str]:
        files: dict[str, str] = {}
        for p in work.rglob("*"):
            if p.is_file() and p.stat().st_size < 20000:
                try:
                    rel = str(p.relative_to(work))
                    if rel.startswith(".agents/skills/") and rel.endswith("SKILL.md"):
                        files[rel] = "(mounted skill)"
                        continue
                    if rel.startswith(".kilo"):
                        continue
                    files[rel] = p.read_text(encoding="utf-8", errors="ignore")[:10000]
                except Exception:
                    pass
        try:
            theory = (work / "THEORY.md").read_text()[:5000]
        except Exception:
            theory = ""
        return files, theory

    @staticmethod
    def _harness_passed(test_res: Any) -> bool:
        text = getattr(test_res, "output", str(test_res or ""))
        return "TEST_PASS" in text and "rc=0" in text

    @staticmethod
    def _files_for_verify(files: dict) -> dict[str, str]:
        encoded: dict[str, str] = {}
        for key, value in (files or {}).items():
            if isinstance(value, bytes):
                encoded[str(key)] = value.decode("utf-8", errors="ignore")
            else:
                encoded[str(key)] = str(value)
        return encoded

    @staticmethod
    def _has_candidate_workspace(files: dict | None) -> bool:
        for key, value in (files or {}).items():
            rel = str(key).replace("\\", "/")
            if rel.startswith(".agents/skills/") and rel.endswith("SKILL.md"):
                continue
            text = (
                value.decode("utf-8", errors="ignore")
                if isinstance(value, bytes)
                else str(value)
            )
            if text.strip() and text.strip() != "(mounted skill)":
                return True
        return False

    @staticmethod
    def _remote_verifier_required() -> bool:
        return (
            os.environ.get("ARENA_IN_SANDBOX") == "1"
            and os.environ.get("ARENA_VERIFIER_ALLOW_INPROCESS") != "1"
        )

    def _emit_trusted_verification(
        self,
        client,
        battle_id: str,
        *,
        target_id: str,
        kind: str,
        phase: str,
        role: str,
        model_id: str,
        payload: dict,
    ) -> None:
        """Persist host-side in-process verify as TRUSTED_VERIFICATION (not EXECUTOR_RESULT)."""
        if client is None:
            return
        from agent_arena.results import TRUSTED_VERIFICATION_MARKER

        status = str(payload.get("verification_status") or "")
        if not status:
            if payload.get("attempted") is False:
                status = "not_attempted"
            elif payload.get("error"):
                status = "infra_failure"
            else:
                status = "verified_pass" if payload.get("passed") else "verified_fail"
        if status == "not_attempted":
            outcome = "VERIFICATION_NOT_ATTEMPTED"
            passed = False
        elif status == "infra_failure":
            outcome = "VERIFY_ERROR"
            passed = False
        else:
            passed = bool(payload.get("passed")) and status == "verified_pass"
            outcome = "TEST_PASS" if passed else "TEST_FAIL"
        record = {
            "source": "trusted_verifier",
            "target_id": target_id,
            "kind": kind,
            "phase": phase or "main",
            "role": role or "fighter",
            "model_id": model_id,
            "passed": passed,
            "attempted": status != "not_attempted",
            "verification_status": status,
            "builder_passed": payload.get("builder_passed"),
            "breaker_passed": payload.get("breaker_passed"),
            "outcome": outcome,
        }
        if payload.get("executor_outcome"):
            record["executor_outcome"] = payload.get("executor_outcome")
        if payload.get("terminal_reason"):
            record["terminal_reason"] = payload.get("terminal_reason")
        if payload.get("visible_passed") is not None:
            record["visible_passed"] = bool(payload.get("visible_passed"))
        try:
            client.round(
                battle_id,
                phase or "verify",
                model_id,
                TRUSTED_VERIFICATION_MARKER + " " + json.dumps(record),
            )
        except Exception:
            return

    def _verify_target_trusted(
        self,
        *,
        client,
        battle_id: str,
        target_id: str,
        files: dict,
        format_config: dict,
        builder_files: dict | None = None,
        breaker_files: dict | None = None,
        builder_breaker: bool = False,
        phase: str = "",
        role: str = "",
        model_id: str = "",
        executor_outcome: str = "",
        terminal_reason: str = "",
    ) -> tuple[dict | None, str | None]:
        """Run verification in the trusted host (backend) when in a fighter sandbox.

        Local in-process verify is allowed only with ARENA_VERIFIER_ALLOW_INPROCESS=1
        (unit tests). Hidden/reference files are never loaded from the fighter mount.
        """
        kind = "builder_breaker" if builder_breaker else "solo"
        if self._remote_verifier_required():
            if client is None:
                return None, "VERIFY_ERROR"
            try:
                if builder_breaker:
                    data = client.verify_target(
                        battle_id,
                        target_id,
                        kind="builder_breaker",
                        builder_files=self._files_for_verify(builder_files or {}),
                        breaker_files=self._files_for_verify(breaker_files or {}),
                        phase=phase,
                        role=role,
                        model_id=model_id,
                        executor_outcome=executor_outcome,
                        terminal_reason=terminal_reason,
                    )
                else:
                    data = client.verify_target(
                        battle_id,
                        target_id,
                        self._files_for_verify(files),
                        kind="solo",
                        phase=phase,
                        role=role,
                        model_id=model_id,
                        executor_outcome=executor_outcome,
                        terminal_reason=terminal_reason,
                    )
            except Exception:
                return None, "VERIFY_ERROR"
            if not isinstance(data, dict):
                return None, "VERIFY_ERROR"
            if data.get("error") and not data.get("ok", True):
                return data, "VERIFY_ERROR"
            return data, None

        from agent_arena.target_library import (
            get_target_library,
            get_trusted_library_root,
        )
        from agent_arena.target_verifier import (
            verify_builder_breaker_submission,
            verify_target_submission,
        )

        if not builder_breaker and not self._has_candidate_workspace(files):
            public = {
                "target_id": target_id,
                "passed": False,
                "attempted": False,
                "verification_status": "not_attempted",
            }
            if executor_outcome:
                public["executor_outcome"] = executor_outcome
            if terminal_reason:
                public["terminal_reason"] = terminal_reason
            self._emit_trusted_verification(
                client,
                battle_id,
                target_id=target_id,
                kind=kind,
                phase=phase,
                role=role,
                model_id=model_id,
                payload=public,
            )
            return public, None

        bundle = get_target_library(get_trusted_library_root()).get_target(target_id)
        if bundle is None:
            return None, "VERIFY_ERROR"
        frozen_manifest = (format_config or {}).get("manifest_hash")
        frozen_hidden = (format_config or {}).get("hidden_hash")
        if frozen_manifest and bundle.manifest_hash != frozen_manifest:
            return None, "VERIFY_ERROR"
        if frozen_hidden and bundle.hidden_hash != frozen_hidden:
            return None, "VERIFY_ERROR"
        try:
            if builder_breaker:
                ev = verify_builder_breaker_submission(
                    bundle, builder_files or {}, breaker_files or {}
                )
                public = {
                    "target_id": ev.target_id,
                    "passed": ev.builder_passed,
                    "builder_passed": ev.builder_passed,
                    "breaker_passed": ev.breaker_passed,
                    "attempted": True,
                    "verification_status": (
                        "verified_pass" if ev.builder_passed else "verified_fail"
                    ),
                    "server_crashed": getattr(ev, "server_crashed", False),
                    "availability_degraded": getattr(ev, "availability_degraded", False),
                    "unauthorized_mutation": getattr(ev, "unauthorized_mutation", False),
                    "flag_captured": getattr(ev, "flag_captured", False),
                    "deployment_ready": getattr(ev, "deployment_ready", True),
                    "deployment_repaired": getattr(ev, "deployment_repaired", False),
                    "deployment_status": getattr(ev, "deployment_status", "DEPLOY_SUCCESS"),
                }
            else:
                ev = verify_target_submission(
                    bundle,
                    files,
                    run_visible=True,
                    run_hidden=True,
                )
                public = {
                    "target_id": ev.target_id,
                    "passed": ev.passed,
                    "visible_passed": ev.visible_passed,
                    "attempted": True,
                    "verification_status": (
                        "verified_pass" if ev.passed else "verified_fail"
                    ),
                }
            if executor_outcome:
                public["executor_outcome"] = executor_outcome
            if terminal_reason:
                public["terminal_reason"] = terminal_reason
            self._emit_trusted_verification(
                client,
                battle_id,
                target_id=target_id,
                kind=kind,
                phase=phase,
                role=role,
                model_id=model_id,
                payload=public,
            )
            return public, None
        except Exception:
            failed = {
                "target_id": target_id,
                "passed": False,
                "attempted": True,
                "verification_status": "infra_failure",
                "error": True,
            }
            if executor_outcome:
                failed["executor_outcome"] = executor_outcome
            if terminal_reason:
                failed["terminal_reason"] = terminal_reason
            self._emit_trusted_verification(
                client,
                battle_id,
                target_id=target_id,
                kind=kind,
                phase=phase,
                role=role,
                model_id=model_id,
                payload=failed,
            )
            return failed, "VERIFY_ERROR"

    def _finalize_role(
        self,
        *,
        client,
        battle_id: str,
        work: Path,
        sess: ToolSession,
        model_id: str,
        role: str,
        chosen_skills: list[str],
        preview_url: str,
        format_config: dict,
        history: list[dict],
        results: list[dict],
        seq: dict,
        last_test: str | None = None,
        budget_exceeded: bool = False,
        retest: bool = False,
        phase: str = "race",
        lock: threading.Lock | None = None,
        tool_errors: int = 0,
        parse_errors: int = 0,
        turns: int = 0,
        duration_ms: int = 0,
        consecutive_parse_failures: int = 0,
        outcome_override: str | None = None,
        terminal_reason: str | None = None,
        canonical_test_code: str | None = None,
        required_artifacts: list[str] | None = None,
        phase_type: str | None = None,
        emit_action=None,
        context_mode: str = "strict",
        skills_telemetry: dict | None = None,
        memory_telemetry: dict | None = None,
    ) -> dict:
        """Collect workspace + score the harness. Credits TEST_PASS even if the
        step budget was later burned by extra tool calls.
        """
        files, theory = self._collect_workspace(work)
        judge_only = _judge_only(format_config)
        spec_hash = str((format_config or {}).get("spec_hash") or "")
        evaluation_mode = str((format_config or {}).get("evaluation_mode") or "")
        if judge_only:
            required_artifacts = list(
                required_artifacts
                if required_artifacts is not None
                else ((format_config or {}).get("artifacts") or {}).get("required")
                or []
            )
            artifact_checks = {
                "required": list(required_artifacts),
                "present": [r for r in required_artifacts if r in files],
                "missing": [r for r in required_artifacts if r not in files],
            }
            if outcome_override:
                outcome = outcome_override
            elif budget_exceeded:
                outcome = "STEP_BUDGET_EXCEEDED"
            else:
                outcome = "JUDGE_ONLY"
            outcome = self.guard(
                outcome,
                format_config.get("outcome_markers", []),
                default=outcome,
            )
            result = {
                "executor_version": ADVANCED_EXECUTOR_VERSION,
                "model_id": model_id,
                "role": role,
                "phase": phase,
                "phase_type": phase_type or phase,
                "context_mode": context_mode,
                "outcome": outcome,
                "terminal_reason": terminal_reason
                or ("step_budget_exhausted" if budget_exceeded else "completed"),
                "passed": None,
                "steps": sess.steps,
                "turns": turns,
                "duration_ms": duration_ms,
                "consecutive_parse_failures": consecutive_parse_failures,
                "tool_errors": tool_errors,
                "parse_errors": parse_errors,
                "artifact_checks": artifact_checks,
                "policy": {"status": "clean", "violations": []},
                "chosen_skills": chosen_skills,
                "theory": theory[:2000],
                "skill_read_ok": bool(chosen_skills)
                and set(chosen_skills).issubset(sess.skill_reads),
                "skills_telemetry": skills_telemetry or {},
                "memory_telemetry": memory_telemetry or {},
                "preview_url": preview_url,
                "spec_hash": spec_hash,
                "evaluation_mode": evaluation_mode or "quick",
            }

            files_json = json.dumps(
                {
                    "files": files,
                    "chosen_skills": chosen_skills,
                    "theory": theory,
                    "outcome": outcome,
                    "terminal_reason": result["terminal_reason"],
                    "steps": sess.steps,
                    "turns": turns,
                    "duration_ms": duration_ms,
                    "skill_read_ok": result["skill_read_ok"],
                    "preview_url": preview_url,
                    "spec_hash": spec_hash,
                },
                indent=2,
            )

            def _commit_judge_only():
                line = self.emit_result(client, battle_id, phase, result)
                seq["n"] += 1
                client.round(
                    battle_id,
                    phase,
                    model_id,
                    sanitize_artifact(files_json),
                    event_type="artifact",
                    sequence=seq["n"],
                )
                history.append(
                    {
                        "phase": phase,
                        "model_id": model_id,
                        "artifact": sanitize_artifact(files_json),
                        "role": role,
                    }
                )
                history.append(
                    {
                        "phase": phase,
                        "model_id": model_id,
                        "artifact": line,
                        "role": role,
                    }
                )
                results.append(result)
                return result

            if lock is not None:
                with lock:
                    return _commit_judge_only()
            return _commit_judge_only()

        # Trusted verification: the canonical harness lives in executor memory.
        # Before the final test we detect tampering (hash mismatch) and always
        # restore the canonical harness, so a fighter can never fake TEST_PASS
        # by editing its own tests. Tampering is recorded as policy evidence.
        if canonical_test_code is None:
            canonical_test_code = (
                ((format_config or {}).get("role_test_code") or {}).get(role)
                or (format_config or {}).get("test_code")
                or ""
            )
        canonical_test_code = str(canonical_test_code or DEFAULT_TEST_CODE)
        harness_path = work / "tests" / "test_target.py"
        canonical_hash = hashlib.sha256(canonical_test_code.encode("utf-8")).hexdigest()
        try:
            harness_tampered = (
                hashlib.sha256(harness_path.read_bytes()).hexdigest() != canonical_hash
            )
        except Exception:
            harness_tampered = True
        if harness_tampered:
            harness_path.parent.mkdir(parents=True, exist_ok=True)
            harness_path.write_text(canonical_test_code, encoding="utf-8")
        # The final verdict ALWAYS comes from a fresh run of the restored
        # canonical harness. A mid-battle TEST_PASS observed through a tampered
        # harness can never become the recorded outcome.
        test_res = sess.test("", count_step=False)
        if emit_action is not None:
            emit_action(
                model_id,
                "test",
                target="tests/test_target.py",
                state="done",
                result=str(test_res or "")[:4000],
                exec_id="exec_" + uuid.uuid4().hex[:12],
            )
        passed = self._harness_passed(test_res)
        skill_read_ok = bool(chosen_skills) and set(chosen_skills).issubset(
            sess.skill_reads
        )
        target_id = (format_config or {}).get("target_id")
        target_evidence = None
        target_verification_error = None

        # Asymmetric builder/breaker targets are verified once at the end of
        # run_battle via verify_builder_breaker_submission (builder files vs
        # breaker files), not per-phase here.
        if target_id and not is_builder_breaker(format_config):
            target_evidence, target_verification_error = self._verify_target_trusted(
                client=client,
                battle_id=battle_id,
                target_id=str(target_id),
                files=files,
                format_config=format_config or {},
                phase=phase,
                role=role,
                model_id=model_id,
                executor_outcome=str(outcome_override or ""),
                terminal_reason=str(terminal_reason or ""),
            )
            if target_evidence and not target_verification_error:
                passed = bool(target_evidence.get("passed"))

        if target_id and not is_builder_breaker(format_config):
            # FAIL-CLOSED: if target verification was required but errored/unavailable, FAIL CLOSED
            evidence_status = str(
                (target_evidence or {}).get("verification_status") or ""
            )
            if target_verification_error:
                outcome = "VERIFY_ERROR"
                passed = False
            elif evidence_status == "not_attempted":
                outcome = outcome_override or "VERIFICATION_NOT_ATTEMPTED"
                passed = False
            elif target_evidence:
                if target_evidence.get("passed"):
                    outcome = "TEST_PASS"
                    passed = True
                else:
                    # Verification ran and failed. Keep the trusted fail;
                    # do not hide it behind a turn-budget executor label.
                    outcome = "TEST_FAIL"
                    passed = False
            else:
                outcome = "VERIFY_ERROR"
                passed = False
        elif passed:
            outcome = "TEST_PASS"
        elif outcome_override:
            outcome = outcome_override
        elif budget_exceeded:
            outcome = "STEP_BUDGET_EXCEEDED"
        else:
            outcome = "TEST_FAIL"
        outcome = self.guard(
            outcome,
            format_config.get("outcome_markers", []),
            default=outcome,
        )
        if required_artifacts is None:
            required_artifacts = list(
                ((format_config or {}).get("artifacts") or {}).get("required") or []
            )
        artifact_checks = {
            "required": list(required_artifacts),
            "present": [r for r in required_artifacts if r in files],
            "missing": [r for r in required_artifacts if r not in files],
        }
        policy_violations = []
        if harness_tampered:
            policy_violations.append("harness-tampered")
        if target_verification_error:
            policy_violations.append("target-verifier-error")

        policy_status = "invalid" if policy_violations else "clean"

        # Determine terminal reason
        if terminal_reason:
            resolved_terminal_reason = terminal_reason
        elif passed:
            resolved_terminal_reason = "completed"
        elif outcome_override:
            resolved_terminal_reason = outcome_override.lower()
        elif budget_exceeded:
            resolved_terminal_reason = "step_budget_exhausted"
        else:
            resolved_terminal_reason = "test_failed"

        # Compact, correctness-first record: `files` (potentially large) are
        # excluded because they already persist via the separate artifact
        # event + rounds doc. Ordering keeps truncation-safe fields first so
        # the 30KB event persist cap can never cut the verdict fields.
        result = {
            "executor_version": ADVANCED_EXECUTOR_VERSION,
            "model_id": model_id,
            "role": role,
            "phase": phase,
            "phase_type": phase_type or phase,
            "context_mode": context_mode,
            "outcome": outcome,
            "terminal_reason": resolved_terminal_reason,
            "passed": passed,
            "steps": sess.steps,
            "turns": turns,
            "duration_ms": duration_ms,
            "consecutive_parse_failures": consecutive_parse_failures,
            "tool_errors": tool_errors,
            "parse_errors": parse_errors,
            "artifact_checks": artifact_checks,
            "policy": {
                "status": policy_status,
                "violations": policy_violations,
            },
            "chosen_skills": chosen_skills,
            "theory": theory[:2000],
            "skill_read_ok": skill_read_ok,
            "skills_telemetry": skills_telemetry or {},
            "memory_telemetry": memory_telemetry or {},
            "preview_url": preview_url,
            "spec_hash": str((format_config or {}).get("spec_hash") or ""),
            "evaluation_mode": str((format_config or {}).get("evaluation_mode") or ""),
        }
        if target_id and not is_builder_breaker(format_config):
            if target_verification_error:
                result["verification_status"] = "infra_failure"
            elif target_evidence:
                result["verification_status"] = str(
                    target_evidence.get("verification_status")
                    or (
                        "verified_pass"
                        if target_evidence.get("passed")
                        else "verified_fail"
                    )
                )
            else:
                result["verification_status"] = "not_attempted"
        if target_evidence:
            result["target_id"] = target_evidence.get("target_id")
        elif target_verification_error:
            result["target_id"] = target_id
        files_json = json.dumps(
            {
                "files": files,
                "chosen_skills": chosen_skills,
                "theory": theory,
                "outcome": outcome,
                "terminal_reason": resolved_terminal_reason,
                "steps": sess.steps,
                "turns": turns,
                "duration_ms": duration_ms,
                "skill_read_ok": skill_read_ok,
                "preview_url": preview_url,
            },
            indent=2,
        )

        def _commit():
            line = self.emit_result(client, battle_id, phase, result)
            seq["n"] += 1
            client.round(
                battle_id,
                phase,
                model_id,
                sanitize_artifact(files_json),
                event_type="artifact",
                sequence=seq["n"],
            )
            history.append(
                {
                    "phase": phase,
                    "model_id": model_id,
                    "artifact": sanitize_artifact(files_json),
                    "role": role,
                }
            )
            history.append(
                {
                    "phase": phase,
                    "model_id": model_id,
                    "artifact": line,
                    "role": role,
                }
            )
            results.append(result)
            return result

        if lock is not None:
            with lock:
                return _commit()
        return _commit()

    def run_battle(
        self,
        *,
        battle_id,
        format_config,
        model_ids,
        round_visibility,
        timeout_seconds,
        role_to_model,
        client,
        status_check=None,
        on_status=None,
        deadline=None,
        stop=None,
    ):
        # Sandbox gate — must run inside sandbox per business_rules.md
        if os.environ.get("ARENA_IN_SANDBOX") != "1":
            raise RuntimeError(
                "AdvancedExecutor must run inside sandbox (ARENA_IN_SANDBOX=1)"
            )

        if deadline is None:
            deadline = time.time() + (timeout_seconds or 600)

        # Difficulty presets are applied once in run_battle_loop. Read budgets
        # from top-level keys with a fallback to nested `limits.*`.
        limits = format_config.get("limits") or {}

        def _budget(key, default, aliases=None):
            keys = [key] + list(aliases or [])
            for k in keys:
                val = format_config.get(k)
                if val is None:
                    val = limits.get(k)
                if val is not None:
                    return val
            return default

        target_code = format_config.get("target_code") or (
            ""
            if _judge_only(format_config) or format_config.get("custom")
            else "# TASK: Fix is_palindrome\n"
        )
        if _judge_only(format_config):
            default_test_code = format_config.get("test_code") or ""
        else:
            default_test_code = format_config.get("test_code") or DEFAULT_TEST_CODE
        role_test_code = format_config.get("role_test_code") or {}
        role_missions = format_config.get("role_missions") or {}
        seed_solution_roles = set(format_config.get("seed_solution_roles") or [])
        if format_config.get("seed_solution"):
            seed_solution_roles = seed_solution_roles | set(
                fighter_roles(format_config)
            )
        max_turns = min(20, max(1, int(_budget("max_tool_turns", 6, ["max_turns"]))))
        max_steps = min(
            50, max(1, int(_budget("max_tool_steps", 14, ["max_steps", "max_tool_steps"])))
        )
        raw_timeout = _budget("tool_timeout", None, ["timeout", "timeout_seconds"])
        tool_timeout = int(raw_timeout) if raw_timeout else None
        race_tokens = int(
            _budget("race_max_tokens", RACE_MAX_TOKENS, ["max_tokens"])
            or RACE_MAX_TOKENS
        )
        context_mode = (
            str((format_config or {}).get("context_mode") or "strict").lower().strip()
        )
        pool = (
            select_skills(format_config, context_mode=context_mode)
            or load_skill_pool()
            or SKILL_POOL
        )
        seq = {"n": 0}
        phase_name = tool_phase_name(format_config)
        fighters = fighter_roles(format_config)

        io_lock = threading.Lock()

        def emit(phase, model_id, artifact, event_type="artifact"):
            with io_lock:
                seq["n"] += 1
                client.round(
                    battle_id,
                    phase,
                    model_id,
                    artifact,
                    event_type=event_type,
                    sequence=seq["n"],
                )

        def emit_action(
            model_id,
            action,
            target="",
            command="",
            state="",
            duration_ms=0,
            result="",
            turn_id=0,
            tool_step=0,
            tool_call_id="",
            exec_id=None,
            reason="",
            response_hash="",
            phase_id="",
            role="",
            workspace="",
            malformed_tool_call: bool = False,
            repair_kind: str = "",
        ):
            action_phase = phase_id or phase_name
            with io_lock:
                seq["n"] += 1
                payload = {
                    "battle_id": battle_id,
                    "fighter_id": model_id,
                    "phase_id": action_phase,
                    "turn_id": int(turn_id),
                    "event_sequence": int(seq["n"]),
                    "tool_step": int(tool_step),
                    "tool_call_id": tool_call_id,
                    "exec_id": exec_id,
                    "action": action,
                    "target": target,
                    "command": command,
                    "state": state,
                    "duration_ms": int(duration_ms),
                    "result": (result or "")[:4000],
                }
                if role:
                    payload["role"] = role
                if workspace:
                    payload["workspace"] = workspace
                if reason:
                    payload["reason"] = reason
                if response_hash:
                    payload["response_hash"] = response_hash
                if malformed_tool_call:
                    payload["malformed_tool_call"] = True
                if repair_kind:
                    payload["repair_kind"] = repair_kind
                client.round(
                    battle_id,
                    action_phase,
                    model_id,
                    json.dumps(payload),
                    event_type="action_log",
                    sequence=seq["n"],
                )

        def emit_skill_activity(
            model_id,
            role,
            phase_id,
            event_type,
            fields,
            *,
            success=None,
        ):
            with io_lock:
                seq["n"] += 1
                payload = {
                    "type": event_type,
                    "fighter_id": model_id,
                    "fighter_slot": role,
                    "role": role,
                    "phase_id": phase_id or phase_name,
                    "event_sequence": int(seq["n"]),
                    **fields,
                }
                if success is not None:
                    payload["success"] = bool(success)
                client.round(
                    battle_id,
                    phase_id or phase_name,
                    model_id,
                    json.dumps(payload),
                    event_type=event_type,
                    sequence=seq["n"],
                )

        def record_artifact(model_id, artifact, role, phase_id=""):
            art_phase = phase_id or phase_name
            with io_lock:
                seq["n"] += 1
                client.round(
                    battle_id,
                    art_phase,
                    model_id,
                    artifact,
                    sequence=seq["n"],
                )
                history.append(
                    {
                        "phase": art_phase,
                        "model_id": model_id,
                        "artifact": artifact,
                        "role": role,
                    }
                )

        history: list[dict] = []
        results: list[dict] = []

        halted_status: str | None = None
        halt_lock = threading.Lock()

        def halted_now():
            return self.halted(status_check, deadline, stop)

        def mark_halted(reason):
            nonlocal halted_status
            if not reason:
                return
            with halt_lock:
                if halted_status is None:
                    halted_status = reason

        def role_recorded(model_id, token=None):
            with io_lock:
                if token is not None:
                    return any(
                        (r.get("phase"), r.get("role")) == token for r in results
                    )
                return any(r["model_id"] == model_id for r in results)

        def visible_for(role, phase_id=""):
            with io_lock:
                if round_visibility == "isolated":
                    return [
                        a
                        for a in history
                        if a.get("role") == role
                        and (not phase_id or a.get("phase") == phase_id)
                    ]
                return list(history)

        def run_fighter(
            role_idx,
            role,
            *,
            fighter_phase=None,
            fighter_phase_type=None,
            fighter_test_code=None,
            starter_files=None,
            protected_files=None,
            required_outputs=None,
            record_token=None,
            _emit_action=emit_action,
            _record_artifact=record_artifact,
        ):
            local_phase = fighter_phase or phase_name
            local_phase_type = fighter_phase_type or local_phase

            def emit_action(*args, **kwargs):
                kwargs.setdefault("phase_id", local_phase)
                return _emit_action(*args, **kwargs)

            def record_artifact(*args, **kwargs):
                kwargs.setdefault("phase_id", local_phase)
                return _record_artifact(*args, **kwargs)

            halted = halted_now()
            if halted:
                mark_halted(halted)
                return
            model_id = role_to_model.get(role)
            if not model_id:
                return

            work = root / f"work_{role}"
            if work.exists() and record_token is not None:
                shutil.rmtree(work, ignore_errors=True)
            work.mkdir(exist_ok=True)
            mount_skills(work, pool)
            (work / "TARGET.md").write_text(target_code, encoding="utf-8")
            tests_dir = work / "tests"
            test_code = (
                fighter_test_code or role_test_code.get(role) or default_test_code
            )
            if _judge_only(format_config):
                test_code = fighter_test_code or role_test_code.get(role) or ""
            if test_code:
                tests_dir.mkdir(exist_ok=True)
                (tests_dir / "test_target.py").write_text(test_code, encoding="utf-8")
            mission = str(role_missions.get(role) or "").strip()
            if role in seed_solution_roles:
                (work / "solution.py").write_text(target_code, encoding="utf-8")
            cfg_starters = format_config.get("starter_files") or {}
            merged_starters = dict(cfg_starters)
            merged_starters.update(starter_files or {})
            for rel, payload in merged_starters.items():
                write_allowed_file(work, rel, payload)
            (work / "README.md").write_text(
                f"# Task for {role}\n"
                + (
                    f"{mission}\n"
                    if mission
                    else (
                        "Skills are optional. Browse with TOOL skills or load with "
                        "TOOL use_skill when useful. Write solution.py, then TOOL test.\n"
                    )
                ),
                encoding="utf-8",
            )

            env_cfg = format_config.get("environment") or {}
            ver_cfg = format_config.get("verification") or {}
            test_cmd = ver_cfg.get("visible_command")
            sess = ToolSession(
                work,
                root=work,
                tool_timeout=tool_timeout,
                allow_network=bool(env_cfg.get("network")),
                test_cmd=test_cmd,
            )

            preview_server = None
            preview_url = ""
            if preview_enabled():
                try:
                    preview_server = StaticPreviewServer(
                        workdir=work,
                        port=port_for_index(role_idx),
                    )
                    preview_server.start()
                    preview_url = f"http://localhost:{port_for_index(role_idx)}"
                    emit_action(
                        model_id,
                        "preview",
                        state="starting",
                        target=preview_url,
                        result="Static preview server up for fighter artifacts",
                    )
                except Exception as exc:
                    emit_action(
                        model_id,
                        "preview",
                        state="failed",
                        result=f"Could not start preview server: {exc}",
                    )

            emit(
                local_phase,
                model_id,
                json.dumps(
                    {
                        "schema_version": 1,
                        "fighter_id": model_id,
                        "role": role,
                        "phase_id": local_phase,
                        "workspace": work.name,
                        "network_enabled": bool(env_cfg.get("network")),
                        "preview_url": preview_url or None,
                    }
                ),
                "phase_start",
            )

            chosen_skills: list[str] = []
            last_test = ""

            skill_resolver = CanonicalSkillResolver(
                [SkillRecord.from_dict(s) for s in pool]
            )
            tracker = SkillLifecycleTracker(role=role, model_id=model_id)
            for s in pool:
                cid = skill_resolver.canonical_id(s.get("name") or s.get("id") or "")
                if cid:
                    tracker.record_eligible(cid)
                    tracker.record_offered(cid)

            records = [SkillRecord.from_dict(s) for s in pool]
            from agent_arena.skills.ranking import rank_skills_detailed

            ranked_candidates = rank_skills_detailed(
                records, format_config, context_mode=context_mode, limit=len(records)
            )
            for item in ranked_candidates:
                tracker.record_ranked(
                    item.skill.id,
                    item.final_score,
                    item.reason,
                    semantic_score=item.semantic_score,
                    historical_adjustment=item.historical_adjustment,
                )

            memory_candidates = 0
            memory_supplied_ids = []
            memory_prompt_text = ""
            if context_mode in ("adaptive", "assisted"):
                from agent_arena.memory import retrieve

                try:
                    retrieved_mems = retrieve(
                        databases=getattr(self, "databases", None),
                        database_id=getattr(self, "database_id", ""),
                        query=f"{format_config.get('name', '')} {mission}",
                        context_mode=context_mode,
                        user_id=str(format_config.get("user_id") or "villain"),
                        model_id=model_id,
                        role=role,
                        target_id=str(
                            format_config.get("target_id")
                            or format_config.get("name")
                            or ""
                        ),
                        limit=3,
                    )
                except Exception:
                    retrieved_mems = []
                memory_candidates = len(retrieved_mems)
                memory_supplied_ids = [
                    str(m.get("$id") or m.get("id") or f"mem_{i}")
                    for i, m in enumerate(retrieved_mems)
                ]
                if retrieved_mems:
                    insights = [
                        f"- {m.get('insight', '')[:300]}"
                        for m in retrieved_mems
                        if m.get("insight")
                    ]
                    if insights:
                        memory_prompt_text = (
                            "\nPrior Lessons (Model Memory):\n"
                            + "\n".join(insights)
                            + "\n"
                        )

            memory_telemetry = {
                "context_mode": context_mode,
                "memory_enabled": (context_mode in ("adaptive", "assisted")),
                "memory_candidates": memory_candidates,
                "memory_supplied_ids": memory_supplied_ids,
                "memory_count": len(memory_supplied_ids),
                "memory_scope": f"user:{format_config.get('user_id', 'villain')},model:{model_id}"
                if context_mode in ("adaptive", "assisted")
                else "none",
            }

            metrics = {"tool_errors": 0, "parse_errors": 0, "tool_calls": 0}
            consecutive_parse_failures = 0
            max_consecutive_parse_failures = 3
            turns_used = 0
            fighter_t0 = time.time()
            is_finalized = False

            def finalize(**extra):
                nonlocal is_finalized
                if is_finalized:
                    return None
                is_finalized = True
                duration_ms = int((time.time() - fighter_t0) * 1000)
                restore_protected(work, protected_files or {})
                return self._finalize_role(
                    client=client,
                    battle_id=battle_id,
                    work=work,
                    sess=sess,
                    model_id=model_id,
                    role=role,
                    chosen_skills=chosen_skills,
                    preview_url=preview_url,
                    format_config=format_config,
                    history=history,
                    results=results,
                    seq=seq,
                    last_test=last_test or None,
                    phase=local_phase,
                    phase_type=local_phase_type,
                    lock=io_lock,
                    tool_errors=metrics["tool_errors"],
                    parse_errors=metrics["parse_errors"],
                    turns=turns_used,
                    duration_ms=duration_ms,
                    consecutive_parse_failures=consecutive_parse_failures,
                    canonical_test_code=test_code,
                    required_artifacts=required_outputs,
                    emit_action=emit_action,
                    context_mode=context_mode,
                    skills_telemetry=tracker.to_telemetry(),
                    memory_telemetry=memory_telemetry,
                    **extra,
                )

            last_test: str | None = None
            has_tested_solution: bool = False
            done_warning_issued: bool = False
            consecutive_val_errors: int = 0
            if preview_url:
                emit_action(
                    model_id,
                    "preview",
                    target=preview_url,
                    state="starting",
                    result="Static preview server up for fighter artifacts",
                )

            conversation_messages: list[dict] = []

            try:
                for turn in range(max_turns):
                    turns_used = turn + 1
                    halted = halted_now()
                    if halted:
                        mark_halted(halted)
                        break
                    visible_history = visible_for(role, local_phase)
                    prior = "\n".join(
                        [
                            f"[{a['phase']}/{a['model_id']}]: {a['artifact'][:500]}"
                            for a in visible_history[-5:]
                        ]
                    )
                    fmt_name = format_config.get("name") or "a tool-using battle"
                    system_prompt = build_fighter_system_prompt(
                        role=role,
                        format_name=fmt_name,
                        mission=mission,
                        network_allowed=bool(env_cfg.get("network")),
                        max_steps=max_steps,
                        max_turns=max_turns,
                        judge_only=_judge_only(format_config),
                        custom=bool(format_config.get("custom")),
                        prior_public_context=prior,
                    )
                    system_prompt += "\n\n" + fighter_tool_grammar()
                    listing = str(sess.ls(count_step=False))
                    user_prompt = (
                        f"Workdir files:\n{listing}\n\n"
                        "Read TARGET.md for the public target contract and inspect whatever else you need.\n\n"
                        f"Your turn {turn + 1}/{max_turns}, steps {sess.steps}/{max_steps}. "
                        "Emit tool calls."
                    )

                    if turn == 0 or not conversation_messages:
                        conversation_messages = [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt},
                        ]

                    t0 = time.time()
                    try:
                        from ...tool_protocol import REGISTRY, TOOL_SCHEMAS

                        raw_resp = client.model(
                            battle_id,
                            model_id,
                            conversation_messages,
                            phase=local_phase,
                            max_tokens=race_tokens,
                            tools=REGISTRY.openai_schemas(),
                            return_raw=True,
                        )
                    except Exception as exc:
                        elapsed_ms = int((time.time() - t0) * 1000)
                        err = sanitize_artifact(f"{type(exc).__name__}: {exc}"[:1500])
                        emit_action(
                            model_id,
                            "model",
                            state="failed",
                            duration_ms=elapsed_ms,
                            result=err,
                        )
                        finalize(
                            outcome_override="PROVIDER_ERROR",
                            terminal_reason="provider_error",
                        )
                        return

                    from ...tool_protocol import ModelResponse, normalize_response

                    if isinstance(raw_resp, dict):
                        content = (raw_resp.get("content") or "").strip()
                        resp_obj = ModelResponse(
                            text=content,
                            native_tool_calls=raw_resp.get("tool_calls") or [],
                            raw_finish_reason=raw_resp.get("finish_reason"),
                            latency_ms=raw_resp.get("latency_ms") or 0,
                        )
                    elif hasattr(raw_resp, "text"):
                        content = str(getattr(raw_resp, "text", "")).strip()
                        resp_obj = raw_resp
                    else:
                        content = str(raw_resp or "").strip()
                        resp_obj = ModelResponse(text=content)

                    norm = normalize_response(resp_obj)
                    calls = []
                    if norm.calls:
                        for c in norm.calls:
                            calls.append({"tool": c.name, **c.arguments})

                    if not calls:
                        metrics["parse_errors"] += 1
                        consecutive_parse_failures += 1
                        emit_action(
                            model_id,
                            "tool_parse_failed",
                            state="failed",
                            turn_id=turn + 1,
                            tool_step=sess.steps,
                            tool_call_id="",
                            exec_id=None,
                            reason=norm.error_code
                            or "no tool calls parsed from model response",
                            response_hash=hashlib.sha256(
                                (content or "").encode("utf-8", errors="ignore")
                            ).hexdigest()[:16],
                            result=sanitize_artifact(content[:4000]),
                        )
                        artifact = sanitize_artifact(content[:10000])
                        record_artifact(model_id, artifact, role)

                        if consecutive_parse_failures >= max_consecutive_parse_failures:
                            emit_action(
                                model_id,
                                "parse_failure_limit",
                                state="failed",
                                turn_id=turn + 1,
                                tool_step=sess.steps,
                                reason=f"exceeded maximum consecutive parse failures ({max_consecutive_parse_failures})",
                                result=f"Finalizing role after {consecutive_parse_failures} consecutive parse failures",
                            )
                            finalize(
                                outcome_override="PARSE_RECOVERY_EXHAUSTED",
                                terminal_reason="parse_recovery_exhausted",
                            )
                            break

                        # Provide structured feedback to model (interface guidance only, no free workspace disclosure)
                        conversation_messages.append(
                            {
                                "role": "assistant",
                                "content": content or "(empty response)",
                            }
                        )
                        conversation_messages.append(
                            {
                                "role": "user",
                                "content": (
                                    f"Notice: No valid tool calls were parsed from your response (error: {norm.error_code or 'unrecognized_format'}).\n"
                                    "Please emit your actions as standard tool calls or using the TOOL line grammar.\n\n"
                                    f"Turn {turn + 1}/{max_turns}, steps {sess.steps}/{max_steps}."
                                ),
                            }
                        )
                        continue

                    # Reset consecutive parse failures on successful parse
                    consecutive_parse_failures = 0

                    is_repaired = norm.parse_status == "repaired"
                    if is_repaired:
                        metrics["parse_errors"] += 1
                        metrics["repaired_tool_calls"] = (
                            metrics.get("repaired_tool_calls", 0) + 1
                        )

                    emit_action(
                        model_id,
                        "tool_parse_success",
                        state="done",
                        turn_id=turn + 1,
                        tool_step=sess.steps,
                        tool_call_id="",
                        exec_id=None,
                        result=f"parsed {len(calls)} calls (dialect: {norm.dialect}, status: {norm.parse_status})",
                        malformed_tool_call=is_repaired,
                        repair_kind=norm.repair_kind or "",
                    )

                    turn_tool_outputs: list[str] = []

                    for call in calls:
                        if call.get("error"):
                            metrics["parse_errors"] += 1
                        halted = halted_now()
                        if halted:
                            mark_halted(halted)
                            break
                        if sess.steps >= max_steps:
                            finalize(
                                budget_exceeded=True,
                                terminal_reason="step_budget_exhausted",
                            )
                            break

                        tool_name = str(call.get("tool") or "").strip().lower()

                        # Validate call arguments via REGISTRY
                        if tool_name not in ("done",):
                            norm_args, val_errors = REGISTRY.validate_call(
                                tool_name, call
                            )
                            if val_errors:
                                metrics["tool_errors"] += 1
                                consecutive_val_errors += 1
                                sess.steps += 1
                                err_msg = (
                                    f"ERROR: validation failed: {'; '.join(val_errors)}"
                                )
                                val_result = ToolResult(
                                    tool=tool_name,
                                    success=False,
                                    output=err_msg,
                                    error=f"validation failed: {'; '.join(val_errors)}",
                                    exit_code=1,
                                    error_type="validation_error",
                                    duration_ms=0,
                                    mutated=False,
                                    step_charged=True,
                                    truncated=False,
                                )
                                turn_tool_outputs.append(
                                    f"[{tool_name}]: {val_result.output}"
                                )
                                if consecutive_val_errors >= 2:
                                    schema_spec = REGISTRY.get(tool_name)
                                    if schema_spec:
                                        params = (
                                            schema_spec.get("function", {}).get("parameters", {})
                                            if isinstance(schema_spec, dict)
                                            else {}
                                        )
                                        schema_prompt = (
                                            f"[SCHEMA GUIDANCE for '{tool_name}']:\n"
                                            f"Expected parameters schema:\n{json.dumps(params, indent=2)}\n"
                                            f"Please ensure your tool call matches this JSON schema."
                                        )
                                        turn_tool_outputs.append(schema_prompt)
                                emit_action(
                                    model_id,
                                    tool_name,
                                    target=str(
                                        call.get("path")
                                        or call.get("name")
                                        or call.get("url")
                                        or ""
                                    ),
                                    state="failed",
                                    turn_id=turn + 1,
                                    tool_step=sess.steps,
                                    result=val_result.output,
                                    role=role,
                                    workspace=work.name,
                                )
                                record_artifact(
                                    model_id, sanitize_artifact(val_result.output), role
                                )
                                if sess.steps >= max_steps:
                                    finalize(
                                        budget_exceeded=True,
                                        terminal_reason="step_budget_exhausted",
                                    )
                                    break
                                continue
                            consecutive_val_errors = 0
                            call = {"tool": tool_name, **norm_args}

                        if tool_name == "skills":
                            if call.get("chosen"):
                                chosen_skills = list(call.get("chosen") or [])
                            for c in chosen_skills:
                                cid = skill_resolver.canonical_id(c)
                                if cid:
                                    tracker.record_selected(cid)
                            res = sess.exec_tool(call, count_step=True)
                            failed = not res.success
                            if failed:
                                metrics["tool_errors"] += 1
                            public_result = public_skill_tool_output(
                                call,
                                success=res.success,
                                resolver=skill_resolver,
                            )
                            activity = skill_event_for_call(call, skill_resolver)
                            if activity:
                                event_type, fields = activity
                                emit_skill_activity(
                                    model_id,
                                    role,
                                    local_phase,
                                    event_type,
                                    fields,
                                    success=res.success,
                                )
                            record_artifact(model_id, public_result, role)
                            turn_tool_outputs.append(f"[SKILLS]: {res}")
                            emit_action(
                                model_id,
                                "skills",
                                target=",".join(chosen_skills),
                                state="done" if not failed else "failed",
                                turn_id=turn + 1,
                                tool_step=sess.steps,
                                result=public_result,
                                role=role,
                                workspace=work.name,
                            )
                            if sess.steps >= max_steps:
                                finalize(
                                    budget_exceeded=True,
                                    terminal_reason="step_budget_exhausted",
                                    outcome_override="STEP_BUDGET_EXCEEDED",
                                )
                                break
                            continue

                        if tool_name == "done":
                            has_harness = bool(
                                sess.test_cmd
                                or (sess.workdir / "tests" / "test_target.py").exists()
                                or format_config.get("test_code")
                                or format_config.get("test_command")
                            )
                            should_enforce_advisory = bool(
                                format_config.get("target_id")
                                or format_config.get("enforce_self_correction")
                                or format_config.get("enforce_verification")
                                or format_config.get("services")
                            )
                            if (
                                should_enforce_advisory
                                and has_harness
                                and role not in ("breaker", "attacker")
                                and not has_tested_solution
                                and not done_warning_issued
                                and (turn + 1 < max_turns)
                                and (sess.steps < max_steps)
                            ):
                                done_warning_issued = True
                                turn_tool_outputs.append(
                                    "[ADVISORY]: Notice: You have not executed TOOL test to verify your solution against the target harness. "
                                    "If you are confident your changes are complete and correct, emit DONE again to confirm final submission."
                                )
                                emit_action(
                                    model_id,
                                    "done",
                                    target="",
                                    state="advisory",
                                    turn_id=turn + 1,
                                    tool_step=sess.steps,
                                    result="Self-correction advisory: verification test not executed before DONE.",
                                    role=role,
                                    workspace=work.name,
                                )
                                continue
                            finalize(retest=True, terminal_reason="fighter_done")
                            break

                        exec_start = time.time()
                        step_before = sess.steps
                        metrics["tool_calls"] = metrics.get("tool_calls", 0) + 1
                        tool_call_id = f"tool_{metrics['tool_calls']:03d}"
                        tool_name_now = call.get("tool", "?")
                        target_now = (
                            call.get("path")
                            or call.get("name")
                            or call.get("url")
                            or ""
                        )
                        if tool_name_now in {"shell", "install"}:
                            command_now = str(call.get("cmd") or tool_name_now)
                        elif tool_name_now == "run":
                            command_now = f"python {call.get('path') or ''}".strip()
                        elif tool_name_now == "test":
                            test_target = str(call.get("path") or "").strip()
                            command_now = (
                                f"pytest {test_target}".strip()
                                if test_target
                                else "pytest -q"
                            )
                        elif tool_name_now == "read":
                            command_now = f"cat {call.get('path') or ''}".strip()
                        elif tool_name_now == "write":
                            command_now = f"write {call.get('path') or ''}".strip()
                        elif tool_name_now == "ls":
                            command_now = f"ls {call.get('path') or '.'}".strip()
                        elif tool_name_now == "tree":
                            command_now = f"tree {call.get('path') or '.'}".strip()
                        elif tool_name_now == "grep":
                            command_now = (
                                f"grep {call.get('pattern') or ''} {call.get('path') or '.'}"
                            ).strip()
                        elif tool_name_now == "fetch":
                            command_now = f"fetch {call.get('url') or ''}".strip()
                        else:
                            command_now = str(tool_name_now)
                        process_tool = tool_name_now in {
                            "shell",
                            "install",
                            "run",
                            "test",
                            "bg",
                        }
                        exec_id = (
                            "exec_" + uuid.uuid4().hex[:12] if process_tool else None
                        )

                        # Emit before execution so the browser can show a real
                        # RUNNING command immediately instead of waiting for the
                        # entire tool call to return.
                        emit_action(
                            model_id,
                            tool_name_now,
                            target=target_now,
                            command=command_now,
                            state="running",
                            turn_id=turn + 1,
                            tool_step=step_before + 1,
                            tool_call_id=tool_call_id,
                            exec_id=exec_id,
                            role=role,
                            workspace=work.name,
                        )

                        tool_res = sess.exec_tool(call)
                        failed = not tool_res.success
                        if failed:
                            metrics["tool_errors"] += 1

                        if tool_name_now == "use_skill":
                            skill_arg = str(call.get("name") or "").strip()
                            canon = skill_resolver.resolve(skill_arg)
                            if canon:
                                tracker.record_selected(canon.id)
                                if not failed:
                                    tracker.record_loaded(canon.id)
                                    tracker.record_used(canon.id)
                                    if (
                                        canon.name not in chosen_skills
                                        and canon.id not in chosen_skills
                                    ):
                                        chosen_skills.append(canon.name)
                                else:
                                    tracker.record_load_failed(
                                        canon.id, tool_res.error or "load_failed"
                                    )
                            else:
                                tracker.record_selected(skill_arg)
                                tracker.record_load_failed(skill_arg, "unknown_skill")
                            activity = skill_event_for_call(call, skill_resolver)
                            if activity:
                                event_type, fields = activity
                                emit_skill_activity(
                                    model_id,
                                    role,
                                    local_phase,
                                    event_type,
                                    fields,
                                    success=tool_res.success,
                                )
                        elif tool_name_now == "read":
                            read_path = str(call.get("path") or "")
                            if ".agents/skills" in read_path or "SKILL.md" in read_path:
                                for s in pool:
                                    if s["name"] in read_path or (
                                        s.get("slug") and s["slug"] in read_path
                                    ):
                                        canon = skill_resolver.resolve(s["name"])
                                        if canon:
                                            tracker.record_used(canon.id)

                        exec_ms = int((time.time() - exec_start) * 1000)
                        exec_res_sanitized = sanitize_artifact(tool_res.output[:10000])
                        public_exec_result = exec_res_sanitized[:4000]
                        if tool_name_now == "use_skill":
                            public_exec_result = public_skill_tool_output(
                                call,
                                success=tool_res.success,
                                resolver=skill_resolver,
                            )
                        elif tool_name_now == "read":
                            skill_read_marker = public_skill_file_read(call.get("path"))
                            if skill_read_marker:
                                public_exec_result = skill_read_marker
                        turn_tool_outputs.append(
                            f"[{tool_name_now} {target_now or command_now}]:\n{exec_res_sanitized[:3000]}"
                        )
                        emit_action(
                            model_id,
                            tool_name_now,
                            target=target_now,
                            command=command_now,
                            state="failed" if failed else "done",
                            duration_ms=exec_ms,
                            result=public_exec_result,
                            turn_id=turn + 1,
                            tool_step=step_before + 1,
                            tool_call_id=tool_call_id,
                            exec_id=exec_id,
                            role=role,
                            workspace=work.name,
                        )
                        record_artifact(model_id, public_exec_result, role)

                        tool_name = call.get("tool")
                        run_path = str(call.get("path") or "").replace("\\", "/")
                        if run_path.startswith("./"):
                            run_path = run_path[2:]
                        harness_like = tool_name == "test" or (
                            tool_name == "run"
                            and run_path in {"tests/test_target.py", "test_target.py"}
                        )
                        if tool_name == "test" or harness_like or (
                            tool_name == "shell"
                            and any(kw in str(call.get("cmd") or "") for kw in ("pytest", "python -m unittest", "npm test"))
                        ):
                            has_tested_solution = True
                        if harness_like:
                            last_test = exec_res_sanitized
                            if self._harness_passed(exec_res_sanitized):
                                finalize(terminal_reason="completed")
                                break

                    if turn_tool_outputs:
                        conversation_messages.append(
                            {
                                "role": "assistant",
                                "content": content or json.dumps(calls),
                            }
                        )
                        tool_feedback_text = "\n\n".join(turn_tool_outputs)
                        listing_after = str(sess.ls(count_step=False))
                        conversation_messages.append(
                            {
                                "role": "user",
                                "content": (
                                    f"Tool Output (Turn {turn + 1}/{max_turns}, step {sess.steps}/{max_steps}):\n"
                                    f"{tool_feedback_text[:4000]}\n\n"
                                    f"Workdir files:\n{listing_after}\n\n"
                                    "Emit your next TOOL calls or DONE."
                                ),
                            }
                        )

                    if is_finalized or role_recorded(model_id, record_token):
                        break

                if not is_finalized and not role_recorded(model_id, record_token):
                    finalize(
                        outcome_override="TURN_BUDGET_EXCEEDED",
                        terminal_reason="turn_budget_exhausted",
                    )
            finally:
                if preview_server is not None:
                    try:
                        preview_server.stop()
                    except Exception:
                        pass

        with tempfile.TemporaryDirectory(prefix="arena-adv-") as tmp:
            root = Path(tmp)
            plan = parse_battle_plan(format_config)
            if plan is not None:
                snapshots: dict = {}
                phase_files: dict[str, dict[str, str]] = {}

                def record_missing_handoff(phase, missing_refs):
                    model_id = role_to_model.get(phase.actor)
                    if not model_id:
                        return
                    missing = [str(r) for r in missing_refs]
                    result = {
                        "executor_version": ADVANCED_EXECUTOR_VERSION,
                        "model_id": model_id,
                        "role": phase.actor,
                        "phase": phase.phase_id,
                        "phase_type": phase.phase_type,
                        "outcome": "TEST_FAIL",
                        "passed": False,
                        "steps": 0,
                        "tool_errors": 0,
                        "parse_errors": 0,
                        "artifact_checks": {
                            "required": missing,
                            "present": [],
                            "missing": missing,
                        },
                        "policy": {
                            "status": "invalid",
                            "violations": ["missing-handoff"],
                        },
                        "chosen_skills": [],
                        "theory": "",
                        "skill_read_ok": False,
                        "preview_url": "",
                    }
                    with io_lock:
                        self.emit_result(client, battle_id, phase.phase_id, result)
                        results.append(result)

                for idx, phase in enumerate(plan.phases):
                    halted = halted_now()
                    if halted:
                        mark_halted(halted)
                        break
                    starter: dict[str, bytes] = {}
                    for rel, text in (phase.starter_files or {}).items():
                        starter[rel] = text.encode("utf-8")
                    for src_id in phase.handoff_from:
                        snap = snapshots.get(src_id) or {}
                        files = snap.get("files") or {}
                        refs = phase.handoff_artifacts or list(files)
                        for ref in refs:
                            data = files.get(ref)
                            if isinstance(data, (bytes, bytearray)):
                                starter[ref] = bytes(data)
                    needed = list(
                        dict.fromkeys(
                            list(phase.handoff_artifacts or [])
                            + list(phase.protected_artifacts or [])
                        )
                    )
                    missing = [rel for rel in needed if rel not in starter]
                    if phase.handoff_from and needed and missing:
                        record_missing_handoff(phase, missing)
                        snapshots[phase.phase_id] = {
                            "files": {},
                            "manifest": [
                                {"path": rel, "missing": True} for rel in missing
                            ],
                        }
                        continue
                    protected = {
                        rel: starter[rel]
                        for rel in phase.protected_artifacts
                        if rel in starter
                    }
                    if phase.protected_artifacts and not protected:
                        record_missing_handoff(phase, list(phase.protected_artifacts))
                        snapshots[phase.phase_id] = {
                            "files": {},
                            "manifest": [
                                {"path": rel, "missing": True}
                                for rel in phase.protected_artifacts
                            ],
                        }
                        continue
                    try:
                        run_fighter(
                            idx,
                            phase.actor,
                            fighter_phase=phase.phase_id,
                            fighter_phase_type=phase.phase_type,
                            fighter_test_code=phase.test_code,
                            starter_files=starter,
                            protected_files=protected,
                            required_outputs=phase.required_outputs,
                            record_token=(phase.phase_id, phase.actor),
                        )
                    except Exception:
                        if not results:
                            raise
                    work = root / f"work_{phase.actor}"
                    if work.exists():
                        # Capture the full workspace for asymmetric verification.
                        phase_files[phase.actor] = self._collect_workspace(work)[0]
                    snap_refs = phase.required_outputs or phase.handoff_artifacts
                    snapshots[phase.phase_id] = snapshot_handoff(work, snap_refs)
                    model_id = role_to_model.get(phase.actor)
                    if model_id:
                        emit_action(
                            model_id,
                            "handoff_snapshot",
                            target=phase.phase_id,
                            state="done",
                            result=json.dumps(
                                snapshots[phase.phase_id].get("manifest") or []
                            )[:4000],
                            role=phase.actor,
                            workspace=work.name,
                            phase_id=phase.phase_id,
                        )
                    is_fullstack = bool(format_config.get("services")) or any(
                        s in str(format_config.get("runtime") or "") for s in ("fullstack", "vite")
                    )
                    if is_fullstack and phase.actor == "builder" and work.exists():
                        deployment_dir = root / "deployment"
                        snapshot_to_deployment(work, deployment_dir)
                        wipe_builder_private(work)
                        if model_id:
                            emit_action(
                                model_id,
                                "deployment_snapshot",
                                target="deployment",
                                state="done",
                                role=phase.actor,
                                workspace="deployment",
                                phase_id=phase.phase_id,
                            )
                    elif work.exists():
                        shutil.rmtree(work, ignore_errors=True)
                        if model_id:
                            emit_action(
                                model_id,
                                "workspace_destroyed",
                                target=work.name,
                                state="done",
                                role=phase.actor,
                                workspace=work.name,
                                phase_id=phase.phase_id,
                            )

                # Asymmetric builder vs breaker verification: run once after both
                # phases, scoring the builder's output against the breaker's
                # exploit instead of the single-phase target path.
                target_id = (format_config or {}).get("target_id")
                if (
                    target_id
                    and is_builder_breaker(format_config)
                    and "builder" in phase_files
                    and "breaker" in phase_files
                ):
                    builder_files = phase_files["builder"]
                    breaker_files = phase_files["breaker"]
                    bb_evidence, bb_error = self._verify_target_trusted(
                        client=client,
                        battle_id=battle_id,
                        target_id=str(target_id),
                        files={},
                        format_config=format_config or {},
                        builder_files=builder_files,
                        breaker_files=breaker_files,
                        builder_breaker=True,
                        phase="verify",
                        role="",
                        model_id="",
                    )

                    # Re-emit the per-role results with the asymmetric verdict so
                    # the persisted EXECUTOR_RESULT stream (which downstream
                    # evidence/scoring parse) reflects builder vs breaker outcomes.
                    for r in list(results):
                        if r.get("role") not in ("builder", "breaker"):
                            continue
                        corrected = dict(r)
                        if bb_evidence:
                            corrected["builder_breaker_verification"] = {
                                "passed": bool(bb_evidence.get("passed")),
                                "builder_passed": bool(
                                    bb_evidence.get("builder_passed")
                                ),
                                "breaker_passed": bool(
                                    bb_evidence.get("breaker_passed")
                                ),
                            }
                            corrected["exploit_evidence"] = {
                                "server_crashed": bool(bb_evidence.get("server_crashed")),
                                "availability_degraded": bool(bb_evidence.get("availability_degraded")),
                                "unauthorized_mutation": bool(bb_evidence.get("unauthorized_mutation")),
                                "flag_captured": bool(bb_evidence.get("flag_captured")),
                            }
                            corrected["deployment_ready"] = bool(bb_evidence.get("deployment_ready", True))
                            corrected["deployment_repaired"] = bool(bb_evidence.get("deployment_repaired", False))
                            corrected["deployment_status"] = str(bb_evidence.get("deployment_status", "DEPLOY_SUCCESS"))
                        if bb_error:
                            corrected["outcome"] = "VERIFY_ERROR"
                            corrected["passed"] = False
                            corrected.setdefault("policy", {})["status"] = "invalid"
                            corrected.setdefault("policy", {}).setdefault(
                                "violations", []
                            )
                            corrected["policy"]["violations"].append(
                                "target-verifier-error"
                            )
                        elif bb_evidence:
                            role_passed = (
                                bb_evidence["builder_passed"]
                                if r.get("role") == "builder"
                                else bb_evidence["breaker_passed"]
                            )
                            corrected["outcome"] = (
                                "TEST_PASS" if role_passed else "TEST_FAIL"
                            )
                            corrected["passed"] = role_passed
                        with io_lock:
                            self.emit_result(
                                client, battle_id, corrected["phase"], corrected
                            )
                            results.append(corrected)
            else:
                jobs = [
                    (idx, role)
                    for idx, role in enumerate(fighters)
                    if role_to_model.get(role)
                ]
                if jobs:
                    with ThreadPoolExecutor(max_workers=len(jobs)) as pool_exec:
                        futs = [
                            pool_exec.submit(run_fighter, idx, role)
                            for idx, role in jobs
                        ]
                        errors = []
                        for fut in futs:
                            try:
                                fut.result()
                            except Exception as exc:
                                errors.append(exc)
                        if errors and not results:
                            raise errors[0]
            late = halted_now()
            if late:
                mark_halted(late)

        # Authoritative learning boundary: The execution kernel produces verified
        # results with telemetry and attributions. Persistent learning mutation (skill
        # Elo and model memory) is applied exactly once downstream on the backend
        # in /internal/finalize via _apply_self_learning() when context_mode == "adaptive".
        # This prevents redundant in-memory mutation or double-application.

        # Convert results to history for judge
        for r in results:
            history.append(
                {
                    "phase": r.get("phase") or phase_name,
                    "model_id": r["model_id"],
                    "artifact": f"RESULT {r['outcome']} chosen {r['chosen_skills']} passed={r['passed']} steps={r['steps']} theory={(r.get('theory', '')[:200])}",
                    "role": r["role"],
                }
            )

        if halted_status:
            # Battle was cancelled or hit the deadline. Keep the terminal status
            # truthful (cancelled/failed) rather than marking it completed, but
            # still score any fighters that finished so their work is not lost.
            if on_status:
                on_status(halted_status)
            if not results:
                return {}
            return self.finish(
                client=client,
                battle_id=battle_id,
                format_config=format_config,
                history=history,
                on_status=None,
            )

        return self.finish(
            client=client,
            battle_id=battle_id,
            format_config=format_config,
            history=history,
            on_status=on_status,
        )

    def run_phase(
        self,
        *,
        client,
        battle_id,
        phase,
        role_to_model,
        history,
        format_config,
        round_visibility,
    ):
        # Not used — run_battle overrides full loop
        return []
