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
from .battle_plan import (
    parse_battle_plan,
    restore_protected,
    snapshot_handoff,
    write_allowed_file,
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
    _EXACT = {"FERNET_KEY", "FERNET_KEY_OLD", "INTERNAL_API_KEY", "BATTLE_TOKEN"}
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


def rank_skills_for_context(
    pool: list[dict],
    format_config: dict | None = None,
    limit: int = 5,
) -> list[dict]:
    """Rank skills using tokenized relevance across target objectives, runtime, tags, and category."""
    cfg = format_config or {}
    recommended = set(cfg.get("recommended_skills") or [])

    objectives = cfg.get("objectives") or []
    target_name = str(cfg.get("name") or cfg.get("target_id") or "")
    category = str(cfg.get("category") or "")
    runtime = str(cfg.get("runtime") or "")
    tags = cfg.get("tags") or []

    context_text = f"{target_name} {category} {runtime} {' '.join(objectives)} {' '.join(tags)}".lower()
    tokens = set(re.findall(r"[a-z0-9_-]{3,}", context_text))

    scored_skills = []
    for skill in pool:
        score = 0.0
        name = skill["name"].lower()
        slug = skill["slug"].lower()
        desc = skill.get("description", "").lower()
        skill_tags = [t.lower() for t in skill.get("tags", [])]
        skill_cat = skill.get("category", "").lower()

        if skill["name"] in recommended or skill["slug"] in recommended:
            score += 100.0

        for tok in tokens:
            if tok in name or tok in slug:
                score += 5.0
            if tok in skill_tags:
                score += 4.0
            if tok in skill_cat:
                score += 3.0
            if tok in desc:
                score += 1.0

        if runtime and (runtime.lower() in name or runtime.lower() in desc):
            score += 4.0
        if category and category.lower() in skill_cat:
            score += 3.0

        scored_skills.append((score, skill))

    scored_skills.sort(key=lambda x: (x[0], -len(x[1]["name"])), reverse=True)
    return [s for score, s in scored_skills[:limit]]


def select_skills(
    format_config: dict | None = None, pool: list[dict] | None = None
) -> list[dict]:
    """Selection protocol: curate a relevant shortlist of 4-6 candidate skills
    via recommended_skills or tokenized keyword relevance, resolve prerequisites,
    and return the candidate pool for the battle.
    """
    pool = pool if pool is not None else (load_skill_pool() or SKILL_POOL)
    ranked = rank_skills_for_context(pool, format_config, limit=5)

    ordered: list[dict] = []
    seen: set[str] = set()

    for s in ranked:
        if s["name"] not in seen:
            seen.add(s["name"])
            ordered.append(s)

    by_name = {s["name"]: s for s in pool}
    by_slug = {s["slug"]: s for s in pool}
    for prereq in resolve_prerequisites(ordered, pool):
        prereq_skill = by_name.get(prereq) or by_slug.get(prereq.lower())
        if prereq_skill and prereq_skill["name"] not in seen:
            seen.add(prereq_skill["name"])
            ordered.append(prereq_skill)

    return ordered or pool[:5]


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
    "cmd", "command", "content", "code", "name", "id", "path", "pattern",
    "query", "q", "url", "src", "source", "from", "dst", "dest", "to",
    "tail", "skills", "chosen", "list",
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
            args.get("content") if args.get("content") is not None else args.get("code", "")
        )
        call["cmd"] = args.get("cmd") or args.get("command") or ""
        call["name"] = args.get("name") or args.get("id") or ""
    if tool == "fetch":
        call["url"] = args.get("url") or ""
    if tool == "grep":
        call["pattern"] = args.get("pattern") or args.get("query") or ""
        call["path"] = args.get("path") or "."
    if tool == "skills":
        call["chosen"] = list(args.get("chosen") or args.get("skills") or [])
        if args.get("list"):
            call["list"] = True
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

    def _maybe_cap(self, data: str) -> str:
        if self._max_output is None:
            return data
        encoded = data.encode("utf-8")
        if len(encoded) <= self._max_output:
            return data
        return (
            encoded[: self._max_output].decode("utf-8", errors="ignore")
            + "\n[TRUNCATED]"
        )

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

    def write(self, path: str, content: str) -> str:
        try:
            if path.endswith(".py"):
                from ._harness import extract_python_source

                extracted = extract_python_source(content)
                if extracted:
                    content = extracted
            t = self._resolve(path)
            t.parent.mkdir(parents=True, exist_ok=True)
            t.write_text(content, encoding="utf-8")
            self.steps += 1
            return f"WROTE {path} {len(content)} bytes"
        except Exception as exc:
            return f"ERROR: {exc}"

    def read(self, path: str) -> str:
        try:
            t = self._resolve(path)
            if not t.exists():
                return f"ERROR: not found {path}"
            if t.is_dir():
                return f"ERROR: {path} is a directory, use ls"
            data = t.read_text(encoding="utf-8", errors="ignore")
            data = self._maybe_cap(data)
            self.steps += 1
            try:
                rel = str(t.relative_to(self.workdir.resolve()))
            except Exception:
                rel = str(t)
            if rel.startswith(".agents/skills/") and t.name == "SKILL.md":
                self.skill_reads.add(t.parent.name)
            return data
        except Exception as exc:
            return f"ERROR: {exc}"

    def ls(self, path: str = ".", *, count_step: bool = True) -> str:
        try:
            t = self._resolve(path)
            if not t.exists():
                return f"ERROR: not found {path}"
            if t.is_file():
                return f"FILE {t.name} {t.stat().st_size}b"
            items = []
            for child in sorted(t.iterdir(), key=lambda x: x.name):
                typ = "DIR" if child.is_dir() else "FILE"
                try:
                    sz = child.stat().st_size
                except Exception:
                    sz = 0
                items.append(f"{typ} {child.name} {sz}b")
            if count_step:
                self.steps += 1
            return "\n".join(items) if items else "(empty)"
        except Exception as exc:
            return f"ERROR: {exc}"

    def clean(self, path: str) -> str:
        try:
            t = self._resolve(path)
            if not t.exists():
                return f"ERROR: not found {path}"
            if t.is_dir():
                return f"ERROR: {path} is a dir, not cleaned (use rm -rf manually)"
            t.unlink()
            self.steps += 1
            return f"CLEANED {path}"
        except Exception as exc:
            return f"ERROR: {exc}"

    def run(self, path: str | None = None, inline: str | None = None) -> str:
        try:
            env = _strip_secret_env(os.environ.copy())
            env["ARENA_ROOT"] = str(self.root)
            env["ARENA_WORKDIR"] = str(self.workdir)
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
                return "ERROR: run needs path"
            try:
                out, err = proc.communicate(timeout=self.tool_timeout)
                out = self._maybe_cap(out or "")
                err = self._maybe_cap(err or "")
                self.steps += 1
                return f"STDOUT:\n{out}\nSTDERR:\n{err}\nrc={proc.returncode}"
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                except Exception:
                    pass
                return f"ERROR: timeout after {self.tool_timeout}s"
        except Exception as exc:
            return f"ERROR: {exc}"

    def test(self, path: str) -> str:
        if self.test_cmd and (not path or path in {".", "tests/test_target.py", "test"}):
            out = self._run_command(self.test_cmd)
            self.steps += 1
            rc_m = re.search(r"rc=(-?\d+)\s*$", out.strip())
            rc = int(rc_m.group(1)) if rc_m else 1
            passed = rc == 0 or "TEST_PASS" in out
            fail = rc != 0 or "TEST_FAIL" in out
            if passed and rc == 0:
                return f"TEST_PASS {self.test_cmd}\n{out}"
            if fail:
                return f"TEST_FAIL {self.test_cmd}\n{out}"
            return f"TEST_UNKNOWN {self.test_cmd}\n{out}"

        harness = self.workdir / "tests" / "test_target.py"
        run_path = path
        if harness.exists() and (
            not path or path in {".", "tests/test_target.py", "test"}
        ):
            run_path = "tests/test_target.py"
        out = self.run(run_path)
        rc_m = re.search(r"rc=(-?\d+)\s*$", out.strip())
        rc = int(rc_m.group(1)) if rc_m else 1
        passed = rc == 0 or "TEST_PASS" in out
        fail = rc != 0 or "TEST_FAIL" in out
        # `run()` already counted this step; don't double-charge the budget.
        if passed and rc == 0:
            return f"TEST_PASS {run_path}\n{out}"
        if fail:
            return f"TEST_FAIL {run_path}\n{out}"
        return f"TEST_UNKNOWN {run_path}\n{out}"

    def _run_command(self, command: str, timeout: int | None = None) -> str:
        blocked = _shell_command_blocked(
            command, allow_network=self.allow_network
        )
        if blocked:
            self.steps += 1
            return f"ERROR: {blocked}"
        env = _strip_secret_env(os.environ.copy())
        env["ARENA_ROOT"] = str(self.root)
        env["ARENA_WORKDIR"] = str(self.workdir)
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
                return f"ERROR: timeout after {cmd_timeout}s"
            out = self._maybe_cap(out or "")
            err = self._maybe_cap(err or "")
            self.steps += 1
            return f"STDOUT:\n{out}\nSTDERR:\n{err}\nrc={proc.returncode}"
        except Exception as exc:
            return f"ERROR: {exc}"

    def shell(self, command: str) -> str:
        return self._run_command(command)

    def install(self, command: str) -> str:
        return self._run_command(command, timeout=self.tool_timeout or 300)

    def grep(self, pattern: str, path: str = ".") -> str:
        try:
            t = self._resolve(path)
            if not t.exists():
                return f"ERROR: not found {path}"
            rx = re.compile(pattern)
            matches: list[str] = []
            skip = {".arena_bg", ".git", "__pycache__", "node_modules", ".venv"}
            for p in sorted(t.rglob("*")):
                if p.is_dir() or any(part in skip for part in p.parts):
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
            self.steps += 1
            return "\n".join(matches) if matches else f"(no matches for {pattern!r})"
        except Exception as exc:
            return f"ERROR: {exc}"

    def tree(self, path: str = ".") -> str:
        try:
            t = self._resolve(path)
            if not t.exists():
                return f"ERROR: not found {path}"
            if t.is_file():
                return f"FILE {t.name} {t.stat().st_size}b"
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
            self.steps += 1
            return "\n".join(lines) if lines else "(empty)"
        except Exception as exc:
            return f"ERROR: {exc}"

    def cp(self, src: str, dst: str) -> str:
        try:
            s = self._resolve(src)
            d = self._resolve(dst)
            if not s.exists():
                return f"ERROR: not found {src}"
            if d.exists() and d.is_dir() and not s.is_dir():
                d = d / s.name
            if s.is_dir():
                shutil.copytree(s, d, dirs_exist_ok=True)
            else:
                shutil.copy2(s, d)
            self.steps += 1
            return f"COPIED {src} -> {dst}"
        except Exception as exc:
            return f"ERROR: {exc}"

    def mv(self, src: str, dst: str) -> str:
        try:
            s = self._resolve(src)
            d = self._resolve(dst)
            if not s.exists():
                return f"ERROR: not found {src}"
            if d.exists() and d.is_dir():
                d = d / s.name
            shutil.move(str(s), str(d))
            self.steps += 1
            return f"MOVED {src} -> {dst}"
        except Exception as exc:
            return f"ERROR: {exc}"

    def rm(self, path: str) -> str:
        try:
            t = self._resolve(path)
            if not t.exists():
                return f"ERROR: not found {path}"
            if t.is_dir():
                shutil.rmtree(t)
            else:
                t.unlink()
            self.steps += 1
            return f"REMOVED {path}"
        except Exception as exc:
            return f"ERROR: {exc}"

    def fetch(self, url: str) -> str:
        blocked = _fetch_url_blocked(url)
        if blocked:
            self.steps += 1
            return f"ERROR: fetch blocked ({blocked})"
        try:
            import httpx

            # Disable redirects: a public URL could 3xx to an internal address,
            # bypassing the pre-flight SSRF check above.
            resp = httpx.get(url, timeout=20, follow_redirects=False)
            if resp.is_redirect:
                self.steps += 1
                location = resp.headers.get("location", "")
                return f"ERROR: fetch blocked (redirect to {location[:200]} not followed)"
            body = self._maybe_cap(resp.text[:20000])
            self.steps += 1
            return f"STATUS {resp.status_code}\n{body}"
        except Exception as exc:
            return f"ERROR: {exc}"

    def search(self, query: str) -> str:
        self.steps += 1
        return (
            "SEARCH has no external key configured. Use TOOL FETCH url=<known endpoint> "
            f"to pull specific pages, and read TARGET.md + tests/test_target.py first. "
            f"(query ignored: {query[:200]})"
        )

    def bg(self, name: str, content: str) -> str:
        blocked = _shell_command_blocked(
            content or "", allow_network=self.allow_network
        )
        if blocked:
            self.steps += 1
            return f"ERROR: {blocked}"
        try:
            mgr = self.procs.start(
                name, content or "", env=_strip_secret_env(os.environ.copy())
            )
            self.steps += 1
            return f"BG STARTED {mgr.name} pid={mgr.proc.pid}"
        except Exception as exc:
            return f"ERROR: {exc}"

    def ps(self) -> str:
        self.steps += 1
        return self.procs.list()

    def kill(self, name: str) -> str:
        res = self.procs.kill(name)
        self.steps += 1
        return res

    def logs(self, name: str, tail: str = "8000") -> str:
        try:
            n = int(tail)
        except Exception:
            n = 8000
        res = self.procs.logs(name, n)
        self.steps += 1
        return res

    def use_skill(self, name: str) -> str:
        try:
            if name in self.skill_reads:
                return f"SKILL_ALREADY_LOADED {name}"
            skill_path = self.workdir / ".agents" / "skills" / name / "SKILL.md"
            if not skill_path.is_file():
                return f"ERROR: skill not mounted: {name}"
            body = self._maybe_cap(
                skill_path.read_text(encoding="utf-8", errors="ignore")
            )
            self.skill_reads.add(name)
            self.steps += 1
            return body
        except Exception as exc:
            return f"ERROR: {exc}"

    def list_skills(self) -> str:
        skills_dir = self.workdir / ".agents" / "skills"
        if not skills_dir.is_dir():
            return "(no skills mounted)"
        names = sorted(
            d.name for d in skills_dir.iterdir() if (d / "SKILL.md").is_file()
        )
        return "\n".join(names) if names else "(no skills mounted)"

    def exec_tool(self, call: dict) -> str:
        tool = call.get("tool")
        if tool == "write":
            return self.write(call.get("path", ""), call.get("content", ""))
        if tool == "read":
            return self.read(call.get("path", ""))
        if tool == "ls":
            return self.ls(call.get("path", "."))
        if tool == "clean":
            return self.clean(call.get("path", ""))
        if tool == "run":
            if call.get("content"):
                tmp = f"_tmp_run_{int(time.time() * 1000)}.py"
                self.write(tmp, call.get("content", ""))
                res = self.run(tmp)
                self.clean(tmp)
                return res
            return self.run(call.get("path", ""))
        if tool == "test":
            return self.test(call.get("path", ""))
        if tool == "shell":
            return self.shell(call.get("cmd") or call.get("content", ""))
        if tool == "install":
            return self.install(call.get("content", "") or call.get("cmd", ""))
        if tool == "grep":
            return self.grep(call.get("pattern", ""), call.get("path", "."))
        if tool == "tree":
            return self.tree(call.get("path", "."))
        if tool == "cp":
            return self.cp(call.get("src", ""), call.get("dst", ""))
        if tool == "mv":
            return self.mv(call.get("src", ""), call.get("dst", ""))
        if tool == "rm":
            return self.rm(call.get("path", ""))
        if tool == "fetch":
            return self.fetch(call.get("url", ""))
        if tool == "search":
            return self.search(call.get("query", ""))
        if tool == "bg":
            return self.bg(call.get("name", ""), call.get("content", ""))
        if tool == "ps":
            return self.ps()
        if tool == "kill":
            return self.kill(call.get("name", ""))
        if tool == "logs":
            return self.logs(call.get("name", ""), call.get("tail", "8000"))
        if tool == "use_skill":
            return self.use_skill(call.get("name", ""))
        if tool == "skills":
            if call.get("list"):
                return self.list_skills()
            return f"SKILLS_CHOSEN {','.join(call.get('chosen', []))}"
        if tool == "done":
            return "DONE"
        if tool == "error":
            return call.get("error", "ERROR")
        return f"ERROR: unknown tool {tool}"


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
    def _harness_passed(test_res: str | None) -> bool:
        text = test_res or ""
        return "TEST_PASS" in text and "rc=0" in text

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
        canonical_test_code: str | None = None,
        required_artifacts: list[str] | None = None,
        phase_type: str | None = None,
        emit_action=None,
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
                else ((format_config or {}).get("artifacts") or {}).get("required") or []
            )
            artifact_checks = {
                "required": list(required_artifacts),
                "present": [r for r in required_artifacts if r in files],
                "missing": [r for r in required_artifacts if r not in files],
            }
            outcome = "JUDGE_ONLY"
            if budget_exceeded:
                outcome = "STEP_BUDGET_EXCEEDED"
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
                "outcome": outcome,
                "passed": None,
                "steps": sess.steps,
                "tool_errors": tool_errors,
                "parse_errors": parse_errors,
                "artifact_checks": artifact_checks,
                "policy": {"status": "clean", "violations": []},
                "chosen_skills": chosen_skills,
                "theory": theory[:2000],
                "skill_read_ok": bool(chosen_skills) and set(chosen_skills).issubset(
                    sess.skill_reads
                ),
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
                    "steps": sess.steps,
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
        canonical_hash = hashlib.sha256(
            canonical_test_code.encode("utf-8")
        ).hexdigest()
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
        test_res = sess.test("")
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
            from agent_arena.target_library import get_target_library
            from agent_arena.target_verifier import verify_target_submission

            bundle = get_target_library().get_target(target_id)
            if bundle is None:
                target_verification_error = f"Target '{target_id}' not found in target library"
            else:
                # Immutable hash validation: verify loaded bundle matches frozen battle spec
                frozen_manifest = (format_config or {}).get("manifest_hash")
                frozen_hidden = (format_config or {}).get("hidden_hash")
                if frozen_manifest and bundle.manifest_hash != frozen_manifest:
                    target_verification_error = (
                        f"Target manifest hash mismatch: loaded {bundle.manifest_hash[:12]} != frozen {frozen_manifest[:12]}"
                    )
                elif frozen_hidden and bundle.hidden_hash != frozen_hidden:
                    target_verification_error = (
                        f"Target hidden hash mismatch: loaded {bundle.hidden_hash[:12]} != frozen {frozen_hidden[:12]}"
                    )
                else:
                    try:
                        ev = verify_target_submission(
                            bundle,
                            files,
                            run_visible=True,
                            run_hidden=True,
                        )
                        target_evidence = {
                            "target_id": ev.target_id,
                            "target_version": ev.target_version,
                            "manifest_hash": ev.manifest_hash,
                            "passed": ev.passed,
                            "visible_passed": ev.visible_passed,
                            "hidden_passed": ev.hidden_passed,
                            "visible_exit_code": ev.visible_exit_code,
                            "hidden_exit_code": ev.hidden_exit_code,
                            "duration_seconds": ev.duration_seconds,
                        }
                        passed = ev.passed
                    except Exception as exc:
                        target_verification_error = f"Verifier execution error: {exc}"

        if target_id and not is_builder_breaker(format_config):
            # FAIL-CLOSED: if target verification was required but errored/unavailable, FAIL CLOSED
            if target_verification_error:
                outcome = "VERIFY_ERROR"
                passed = False
            elif target_evidence:
                if target_evidence["passed"]:
                    outcome = "TEST_PASS"
                elif budget_exceeded:
                    outcome = "STEP_BUDGET_EXCEEDED"
                else:
                    outcome = "TEST_FAIL"
            else:
                outcome = "VERIFY_ERROR"
                passed = False
        elif passed:
            outcome = "TEST_PASS"
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
            "outcome": outcome,
            "passed": passed,
            "steps": sess.steps,
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
            "preview_url": preview_url,
            "spec_hash": str((format_config or {}).get("spec_hash") or ""),
            "evaluation_mode": str((format_config or {}).get("evaluation_mode") or ""),
        }
        if target_evidence:
            result["target_id"] = target_evidence["target_id"]
            result["target_version"] = target_evidence["target_version"]
            result["target_verification"] = target_evidence
        elif target_verification_error:
            result["target_id"] = target_id
            result["target_verification_error"] = target_verification_error
        files_json = json.dumps(
            {
                "files": files,
                "chosen_skills": chosen_skills,
                "theory": theory,
                "outcome": outcome,
                "steps": sess.steps,
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

        def _budget(key, default):
            val = format_config.get(key)
            if val is None:
                val = limits.get(key)
            return val if val is not None else default

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
        max_turns = int(_budget("max_tool_turns", 6))
        max_steps = int(_budget("max_tool_steps", 14))
        raw_timeout = _budget("tool_timeout", None)
        tool_timeout = int(raw_timeout) if raw_timeout else None
        pick_n = int(_budget("pick_per_battle", 3))
        race_tokens = int(_budget("race_max_tokens", RACE_MAX_TOKENS) or RACE_MAX_TOKENS)
        pool = select_skills(format_config) or load_skill_pool() or SKILL_POOL
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
                client.round(
                    battle_id,
                    action_phase,
                    model_id,
                    json.dumps(payload),
                    event_type="action_log",
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

        skill_list_text = "\n".join(
            [
                f"{i + 1}. {s['name']} (elo {s['elo']}): {s['desc']}"
                for i, s in enumerate(pool)
            ]
        )
        opponent_info = (
            f"Opponent also picks {pick_n} from the same pool. "
            f"Counter their likely picks for format {format_config.get('name')}."
        )

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
            test_code = fighter_test_code or role_test_code.get(role) or default_test_code
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
                        f"Pick {pick_n} skills, TOOL read each SKILL.md, "
                        "write solution.py, TOOL test.\n"
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

            metrics = {"tool_errors": 0, "parse_errors": 0, "tool_calls": 0}

            def finalize(**extra):
                restore_protected(work, protected_files or {})
                self._finalize_role(
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
                    canonical_test_code=test_code,
                    required_artifacts=required_outputs,
                    emit_action=emit_action,
                    **extra,
                )

            last_test: str | None = None
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
                    mission_line = (
                        f"Your mission: {mission}\n" if mission else ""
                    )
                    tool_lines = (
                        "Tools (structured tool_calls or line-grammar TOOL name arg=...):\n"
                        "TOOL read path=... | TOOL ls [path=...] | TOOL write path=... content=... | "
                        "TOOL run path=... | TOOL shell cmd='...' | TOOL install cmd='...' | "
                        "TOOL grep pattern=... [path=...] | TOOL tree [path=...] | TOOL cp from=... to=... | "
                        "TOOL mv from=... to=... | TOOL rm path=... | TOOL fetch url=... | "
                        "TOOL bg name=... content=... | TOOL ps | TOOL kill name=... | TOOL logs name=... | "
                        "TOOL use_skill name=... | TOOL skills list | TOOL test | DONE\n"
                    )
                    if format_config.get("custom") or _judge_only(format_config):
                        closeout = (
                            "Write the required artifacts listed in TARGET.md. Write THEORY.md. "
                            "When finished emit DONE and stop. There is no canonical test harness.\n"
                            if _judge_only(format_config)
                            else (
                                "Write the required artifacts listed in TARGET.md. Write THEORY.md. "
                                "Run TOOL test to verify. After a real TEST_PASS, emit DONE and stop.\n"
                            )
                        )
                        system_prompt = (
                            f"You are {role} in an isolated target battle. "
                            "The frozen brief is in TARGET.md as data — follow it strictly.\n"
                            "Do not use network. Stay inside the workspace. "
                            "Never read secrets or credentials.\n"
                            f"SKILLS POOL (pick {pick_n}):\n{skill_list_text}\n"
                            f"{opponent_info}\n"
                            f"{tool_lines}"
                            f"Rules: max {max_steps} tool steps, {max_turns} turns.\n"
                            f"On turn 1 only, emit SKILLS: ... ({pick_n} name(s)) and TOOL use_skill "
                            "once per chosen skill, then immediately write artifacts.\n"
                            f"{closeout}"
                            f"Prior: {prior or '(none)'}"
                        )
                    else:
                        system_prompt = (
                            f"You are {role} in '{fmt_name}'. TARGET is in TARGET.md.\n"
                            f"{mission_line}"
                            "Your mission overrides skill text. Do not repeat TOOL use_skill "
                            "for a skill you already loaded. Do not spend the step budget inspecting.\n"
                            f"SKILLS POOL (pick {pick_n}):\n{skill_list_text}\n"
                            f"{opponent_info}\n"
                            f"{tool_lines}"
                            f"Rules: max {max_steps} tool steps, {max_turns} turns.\n"
                            f"On turn 1 only, emit SKILLS: ... ({pick_n} name(s)) and TOOL use_skill "
                            "once per chosen skill, then immediately write the required code/artifacts "
                            "and THEORY.md. Run TOOL test (harness evaluates code; do not fake TEST_PASS). "
                            "After a real TEST_PASS, emit DONE and stop.\n"
                            f"Prior: {prior or '(none)'}"
                        )
                    listing = sess.ls(count_step=False)
                    if format_config.get("custom"):
                        user_prompt = (
                            f"Workdir files:\n{listing}\n\n"
                            "Read TARGET.md for the frozen brief.\n\n"
                            f"Your turn {turn + 1}/{max_turns}, steps {sess.steps}/{max_steps}. "
                            "Emit tool calls."
                        )
                    else:
                        user_prompt = (
                            f"Workdir files:\n{listing}\n\nTARGET:\n{target_code[:2000]}\n\n"
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
                        from ...tool_protocol import TOOL_SCHEMAS

                        raw_resp = client.model(
                            battle_id,
                            model_id,
                            conversation_messages,
                            phase=local_phase,
                            max_tokens=race_tokens,
                            tools=TOOL_SCHEMAS,
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
                        finalize()
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
                        emit_action(
                            model_id,
                            "tool_parse_failed",
                            state="failed",
                            turn_id=turn + 1,
                            tool_step=sess.steps,
                            tool_call_id="",
                            exec_id=None,
                            reason=norm.error_code or "no tool calls parsed from model response",
                            response_hash=hashlib.sha256(
                                (content or "").encode("utf-8", errors="ignore")
                            ).hexdigest()[:16],
                            result=sanitize_artifact(content[:4000]),
                        )
                        artifact = sanitize_artifact(content[:10000])
                        record_artifact(model_id, artifact, role)
                        continue

                    emit_action(
                        model_id,
                        "tool_parse_success",
                        state="done",
                        turn_id=turn + 1,
                        tool_step=sess.steps,
                        tool_call_id="",
                        exec_id=None,
                        result=f"parsed {len(calls)} calls (dialect: {norm.dialect}, status: {norm.parse_status})",
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
                            finalize(budget_exceeded=True)
                            break

                        if call.get("tool") == "skills":
                            chosen_skills = call.get("chosen", [])[:pick_n]
                            pool_names = {s["name"] for s in pool}
                            chosen_skills = [
                                c for c in chosen_skills if c in pool_names
                            ][:pick_n]
                            res = sess.exec_tool(call)
                            record_artifact(
                                model_id, sanitize_artifact(f"{res}"), role
                            )
                            turn_tool_outputs.append(f"[SKILLS]: {res}")
                            continue

                        if call.get("tool") == "done":
                            finalize(retest=True)
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
                            command_now = f"pytest {test_target}".strip() if test_target else "pytest -q"
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
                            "shell", "install", "run", "test", "bg",
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

                        exec_res = sess.exec_tool(call)
                        failed = isinstance(exec_res, str) and exec_res.startswith("ERROR")
                        if failed:
                            metrics["tool_errors"] += 1
                        exec_ms = int((time.time() - exec_start) * 1000)
                        exec_res_sanitized = sanitize_artifact(exec_res[:10000])
                        turn_tool_outputs.append(f"[{tool_name_now} {target_now or command_now}]:\n{exec_res_sanitized[:3000]}")
                        emit_action(
                            model_id,
                            tool_name_now,
                            target=target_now,
                            command=command_now,
                            state="failed" if failed else "done",
                            duration_ms=exec_ms,
                            result=exec_res_sanitized[:4000],
                            turn_id=turn + 1,
                            tool_step=step_before + 1,
                            tool_call_id=tool_call_id,
                            exec_id=exec_id,
                            role=role,
                            workspace=work.name,
                        )
                        record_artifact(model_id, exec_res_sanitized, role)

                        tool_name = call.get("tool")
                        run_path = str(call.get("path") or "").replace("\\", "/")
                        if run_path.startswith("./"):
                            run_path = run_path[2:]
                        harness_like = tool_name == "test" or (
                            tool_name == "run"
                            and run_path
                            in {"tests/test_target.py", "test_target.py"}
                        )
                        if harness_like:
                            last_test = exec_res_sanitized
                            if self._harness_passed(exec_res_sanitized):
                                finalize()
                                break

                    if turn_tool_outputs:
                        conversation_messages.append({"role": "assistant", "content": content or json.dumps(calls)})
                        tool_feedback_text = "\n\n".join(turn_tool_outputs)
                        listing_after = sess.ls(count_step=False)
                        conversation_messages.append({
                            "role": "user",
                            "content": (
                                f"Tool Output (Turn {turn + 1}/{max_turns}, step {sess.steps}/{max_steps}):\n"
                                f"{tool_feedback_text[:4000]}\n\n"
                                f"Workdir files:\n{listing_after}\n\n"
                                "Emit your next TOOL calls or DONE."
                            ),
                        })

                    if role_recorded(model_id, record_token):
                        break

                if not role_recorded(model_id, record_token):
                    finalize()
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
                        self.emit_result(
                            client, battle_id, phase.phase_id, result
                        )
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
                            "manifest": [{"path": rel, "missing": True} for rel in missing],
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
                    if work.exists():
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
                    bb_evidence = None
                    bb_error = None
                    try:
                        from agent_arena.target_library import get_target_library
                        from agent_arena.target_verifier import (
                            verify_builder_breaker_submission,
                        )

                        bundle = get_target_library().get_target(target_id)
                        if bundle is None:
                            bb_error = f"Target '{target_id}' not found in target library"
                        else:
                            bb_ev = verify_builder_breaker_submission(
                                bundle, builder_files, breaker_files
                            )
                            bb_evidence = {
                                "target_id": bb_ev.target_id,
                                "target_version": bb_ev.target_version,
                                "manifest_hash": bb_ev.manifest_hash,
                                "builder_functional_passed": bb_ev.builder_functional_passed,
                                "builder_hidden_passed": bb_ev.builder_hidden_passed,
                                "breaker_exploit_passed": bb_ev.breaker_exploit_passed,
                                "builder_passed": bb_ev.builder_passed,
                                "breaker_passed": bb_ev.breaker_passed,
                                "duration_seconds": bb_ev.duration_seconds,
                            }
                    except Exception as exc:
                        bb_error = f"Builder/breaker verifier execution error: {exc}"

                    # Re-emit the per-role results with the asymmetric verdict so
                    # the persisted EXECUTOR_RESULT stream (which downstream
                    # evidence/scoring parse) reflects builder vs breaker outcomes.
                    for r in list(results):
                        if r.get("role") not in ("builder", "breaker"):
                            continue
                        corrected = dict(r)
                        corrected["builder_breaker_verification"] = (
                            bb_evidence.copy() if bb_evidence else None
                        )
                        if bb_error:
                            corrected["outcome"] = "VERIFY_ERROR"
                            corrected["passed"] = False
                            corrected["builder_breaker_verification_error"] = bb_error
                            corrected.setdefault("policy", {})["status"] = "invalid"
                            corrected.setdefault("policy", {}).setdefault("violations", [])
                            corrected["policy"]["violations"].append("target-verifier-error")
                        elif bb_evidence:
                            role_passed = (
                                bb_evidence["builder_passed"]
                                if r.get("role") == "builder"
                                else bb_evidence["breaker_passed"]
                            )
                            corrected["outcome"] = "TEST_PASS" if role_passed else "TEST_FAIL"
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

        # In-memory skill Elo nudge. A fighter only "wins" if it actually passed
        # the harness; when nobody passes there is no winner, so a lower-step
        # failure is never rewarded. Durable self-learning (Appwrite memory +
        # skill registry) happens once on the backend in /internal/finalize,
        # which re-parses the persisted EXECUTOR_RESULT events — so we do not
        # write to Appwrite here (the sandbox has no credentials anyway).
        try:
            passed_results = [
                r
                for r in results
                if r.get("passed")
                and (r.get("policy") or {}).get("status") != "invalid"
            ]
            winner = (
                min(passed_results, key=lambda x: x.get("steps", 999))
                if passed_results
                else None
            )
            for r in results:
                delta = 5 if (winner is not None and r is winner) else -5
                for chosen in r.get("chosen_skills", [])[:5]:
                    for s in SKILL_POOL:
                        if s["name"] == chosen:
                            s["elo"] = max(800, min(2000, s["elo"] + delta))
        except Exception:
            pass

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
