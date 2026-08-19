"""Universal toolbelt executor: one agent loop for all formats.

Full toolbelt: WRITE/READ/LS/CLEAN/RUN/TEST + SHELL/GREP/TREE/CP/MV/RM/FETCH/
SEARCH/INSTALL/BG/PS/KILL/LOGS/SKILLS/USE_SKILL. Every tool call streams as an
`action_log` event. Skill pick-n competitive race, file-tree artifacts,
THEORY.md, preview servers per fighter, Appwrite skill Elo + memory.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import signal
import subprocess
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from .base import Executor
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


def _fetch_url_blocked(url: str) -> str | None:
    """Return a rejection reason if `url` must not be fetched, else None.

    Mitigates SSRF from the model-driven toolbelt: only http/https to public
    hosts are allowed. Loopback, private, link-local, and metadata endpoints
    (e.g. cloud 169.254.169.254) are blocked so a fighter cannot pivot to the
    internal network or credential endpoints.
    """
    import ipaddress
    import socket
    from urllib.parse import urlparse

    try:
        parsed = urlparse(url.strip())
    except Exception:
        return "unparseable URL"
    scheme = (parsed.scheme or "").lower()
    if scheme not in {"http", "https"}:
        return f"scheme '{scheme or '(none)'}' not allowed (http/https only)"
    host = parsed.hostname
    if not host:
        return "missing host"
    if host.lower() in {"localhost", "metadata", "metadata.google.internal"}:
        return "host not allowed"
    try:
        infos = socket.getaddrinfo(host, parsed.port or (443 if scheme == "https" else 80))
    except Exception as exc:
        return f"DNS resolution failed: {exc}"
    for info in infos:
        addr = info[4][0]
        try:
            ip = ipaddress.ip_address(addr.split("%")[0])
        except ValueError:
            continue
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        ):
            return f"host resolves to non-public address {ip}"
    return None


_URL_IN_TEXT = re.compile(r"(?:[a-z][a-z0-9+.-]*)://[^\s\"'<>]+", re.I)
_FETCH_BIN = re.compile(
    r"(?:^|[\s;&|`(\n])(?:sudo\s+)?(?:[A-Za-z0-9._/-]+/)?(?:curl|wget)\b",
    re.I,
)
_ABS_PATH_IN_CMD = re.compile(r"(?:^|[\s=<>|&;`'\"(])(/[^\s;|&<>`'\"\)]*)")
_DOTDOT_IN_CMD = re.compile(r"(?:^|[\s=<>|&;`'\"(/])\.\.(?:/|[\s;|&<>`'\"\)]|$)")
_HOME_PATH_IN_CMD = re.compile(r"(?:^|[\s=<>|&;`'\"(])~(?:/|$)")


def _looks_like_fetch_target(token: str) -> bool:
    t = token.strip().strip("'\"")
    if not t:
        return False
    if "://" in t:
        return True
    host = t.split("/")[0].split(":")[0].lower()
    if host in {"localhost", "metadata", "metadata.google.internal"}:
        return True
    if re.fullmatch(r"(?:\d{1,3}\.){3}\d{1,3}(?::\d+)?(?:/.*)?", t):
        return True
    if re.fullmatch(r"[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+", host):
        return True
    return False


def _normalize_fetch_url(token: str) -> str:
    t = token.strip().strip("'\"")
    if "://" in t:
        return t
    return "http://" + t


def _fetch_targets_in_command(command: str) -> list[str]:
    found: list[str] = []
    for match in _URL_IN_TEXT.finditer(command):
        found.append(match.group(0).rstrip(".,;)]}"))
    if _FETCH_BIN.search(command):
        for match in re.finditer(
            r"(?:^|[\s;&|`(\n])(?:sudo\s+)?(?:[A-Za-z0-9._/-]+/)?(?:curl|wget)\b(.*)",
            command,
            re.I | re.S,
        ):
            tokens = match.group(1).replace("\n", " ").split()
            idx = 0
            while idx < len(tokens):
                tok = tokens[idx]
                if tok.startswith("--url="):
                    found.append(tok.split("=", 1)[1])
                    break
                if tok == "--url" and idx + 1 < len(tokens):
                    found.append(tokens[idx + 1])
                    break
                if tok.startswith("-"):
                    idx += 1
                    continue
                if _looks_like_fetch_target(tok):
                    found.append(tok)
                break
    out: list[str] = []
    seen: set[str] = set()
    for raw in found:
        if raw and raw not in seen:
            seen.add(raw)
            out.append(raw)
    return out


def _shell_command_blocked(command: str, *, allow_network: bool) -> str | None:
    """Reject shell/install commands that escape the workdir jail or bypass fetch SSRF."""
    if command is None or not str(command).strip():
        return "empty command"
    text = str(command)
    if _DOTDOT_IN_CMD.search(text):
        return "path escape '..' rejected"
    if _HOME_PATH_IN_CMD.search(text):
        return "home path '~' rejected"
    abs_match = _ABS_PATH_IN_CMD.search(text)
    if abs_match:
        return f"absolute path rejected: {abs_match.group(1)}"
    has_fetch_bin = bool(_FETCH_BIN.search(text))
    targets = _fetch_targets_in_command(text)
    if (has_fetch_bin or targets) and not allow_network:
        return "network fetch blocked (format environment.network is false)"
    for raw in targets:
        reason = _fetch_url_blocked(_normalize_fetch_url(raw))
        if reason:
            return f"fetch blocked ({reason})"
    return None


def select_skills(
    format_config: dict | None = None, pool: list[dict] | None = None
) -> list[dict]:
    """Selection protocol (C10): curate 2-3 skills per format via recommended_skills
    or objective-keyword tags, resolve prerequisites, prune anything not available,
    and return the progressive-disclosure subset (only these are mounted).

    Order: recommended_skills first (kept in listed order), then keyword-tag
    matches from objectives, capped at MAX_SELECTED_SKILLS + prereqs.
    """
    pool = pool if pool is not None else (load_skill_pool() or SKILL_POOL)
    cfg = format_config or {}
    by_name = {s["name"]: s for s in pool}
    by_slug = {s["slug"]: s for s in pool}

    ordered: list[dict] = []
    seen: set[str] = set()

    def add(skill: dict | None) -> None:
        if skill and skill["name"] not in seen:
            seen.add(skill["name"])
            ordered.append(skill)

    for rec in cfg.get("recommended_skills") or []:
        add(by_name.get(rec) or by_slug.get(str(rec).lower()))

    keywords = (
        " ".join(cfg.get("objectives") or []) + " " + str(cfg.get("name") or "")
    ).strip()
    if keywords:
        for tag_hit in filter_skills(keywords, root=None)[:MAX_SELECTED_SKILLS]:
            # filter_skills scans the default root; map back onto pool by name
            add(by_name.get(tag_hit["name"]) or by_slug.get(tag_hit["slug"]))

    if not ordered:
        ordered = pool[:MAX_SELECTED_SKILLS]

    for prereq in resolve_prerequisites(ordered[:MAX_SELECTED_SKILLS], pool):
        add(by_name.get(prereq) or by_slug.get(prereq.lower()))
    return ordered


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


def parse_tool_calls(text: str) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []
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
            env = os.environ.copy()
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
        env = os.environ.copy()
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
            mgr = self.procs.start(name, content or "")
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
    ) -> dict:
        """Collect workspace + score the harness. Credits TEST_PASS even if the
        step budget was later burned by extra tool calls.
        """
        files, theory = self._collect_workspace(work)
        if retest or last_test is None:
            test_res = sess.test("")
        else:
            test_res = last_test
        passed = self._harness_passed(test_res)
        skill_read_ok = bool(chosen_skills) and set(chosen_skills).issubset(
            sess.skill_reads
        )
        if passed:
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
        result = {
            "model_id": model_id,
            "role": role,
            "outcome": outcome,
            "passed": passed,
            "steps": sess.steps,
            "files": files,
            "chosen_skills": chosen_skills,
            "theory": theory,
            "skill_read_ok": skill_read_ok,
            "preview_url": preview_url,
        }
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

        target_code = format_config.get("target_code") or "# TASK: Fix is_palindrome\n"
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
            model_id, action, target="", state="", duration_ms=0, result=""
        ):
            with io_lock:
                seq["n"] += 1
                client.round(
                    battle_id,
                    phase_name,
                    model_id,
                    json.dumps(
                        {
                            "action": action,
                            "target": target,
                            "state": state,
                            "duration_ms": int(duration_ms),
                            "result": (result or "")[:4000],
                        }
                    ),
                    event_type="action_log",
                    sequence=seq["n"],
                )

        def record_artifact(model_id, artifact, role):
            with io_lock:
                seq["n"] += 1
                client.round(
                    battle_id,
                    phase_name,
                    model_id,
                    artifact,
                    sequence=seq["n"],
                )
                history.append(
                    {
                        "phase": phase_name,
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

        def role_recorded(model_id):
            with io_lock:
                return any(r["model_id"] == model_id for r in results)

        def visible_for(role):
            with io_lock:
                if round_visibility == "isolated":
                    return [a for a in history if a.get("role") == role]
                return list(history)

        def run_fighter(role_idx, role):
            halted = halted_now()
            if halted:
                mark_halted(halted)
                return
            model_id = role_to_model.get(role)
            if not model_id:
                return

            work = root / f"work_{role}"
            work.mkdir(exist_ok=True)
            mount_skills(work, pool)
            (work / "TARGET.md").write_text(target_code, encoding="utf-8")
            tests_dir = work / "tests"
            tests_dir.mkdir(exist_ok=True)
            test_code = role_test_code.get(role) or default_test_code
            (tests_dir / "test_target.py").write_text(test_code, encoding="utf-8")
            mission = str(role_missions.get(role) or "").strip()
            if role in seed_solution_roles:
                (work / "solution.py").write_text(target_code, encoding="utf-8")
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
            sess = ToolSession(
                work,
                root=work,
                tool_timeout=tool_timeout,
                allow_network=bool(env_cfg.get("network")),
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
                phase_name,
                model_id,
                f"phase_start:{role} workdir {work.name}"
                + (f" preview {preview_url}" if preview_url else ""),
                "phase_start",
            )

            chosen_skills: list[str] = []
            last_test = ""

            def finalize(**extra):
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
                    phase=phase_name,
                    lock=io_lock,
                    **extra,
                )

            try:
                for turn in range(max_turns):
                    halted = halted_now()
                    if halted:
                        mark_halted(halted)
                        break
                    visible_history = visible_for(role)
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
                    system_prompt = (
                        f"You are {role} in '{fmt_name}'. TARGET is in TARGET.md.\n"
                        f"{mission_line}"
                        "Your mission overrides skill text. Do not repeat TOOL use_skill "
                        "for a skill you already loaded. Do not spend the step budget inspecting.\n"
                        f"SKILLS POOL (pick {pick_n}):\n{skill_list_text}\n"
                        f"{opponent_info}\n"
                        "Tools (one per line, body tools need END_TOOL):\n"
                        "TOOL read path=... | TOOL ls [path=...] | TOOL write path=... END_TOOL | "
                        "TOOL run path=... END_TOOL | TOOL shell cmd='...' | TOOL install cmd='...' | "
                        "TOOL grep pattern=... [path=...] | TOOL tree [path=...] | TOOL cp from=... to=... | "
                        "TOOL mv from=... to=... | TOOL rm path=... | TOOL fetch url=... | "
                        "TOOL bg name=... END_TOOL | TOOL ps | TOOL kill name=... | TOOL logs name=... | "
                        "TOOL use_skill name=... | TOOL skills list | TOOL test | DONE\n"
                        f"Rules: max {max_steps} tool steps, {max_turns} turns.\n"
                        f"On turn 1 only, emit SKILLS: ... ({pick_n} name(s)) and TOOL use_skill "
                        "once per chosen skill, then immediately write the artifacts your mission "
                        "requires (exploit.py and/or solution.py). Write THEORY.md. Run TOOL test "
                        "(harness is tests/test_target.py; do not fake TEST_PASS). "
                        "After a real TEST_PASS, emit DONE and stop.\n"
                        f"Prior: {prior or '(none)'}"
                    )
                    listing = sess.ls(count_step=False)
                    user_prompt = (
                        f"Workdir files:\n{listing}\n\nTARGET:\n{target_code[:2000]}\n\n"
                        f"Your turn {turn + 1}/{max_turns}, steps {sess.steps}/{max_steps}. "
                        "Emit TOOL calls."
                    )

                    messages = [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ]
                    t0 = time.time()
                    try:
                        content = client.model(
                            battle_id,
                            model_id,
                            messages,
                            phase=phase_name,
                            max_tokens=race_tokens,
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
                    content = (content or "").strip()

                    calls = parse_tool_calls(content)
                    if not calls:
                        artifact = sanitize_artifact(content[:10000])
                        record_artifact(model_id, artifact, role)
                        continue

                    for call in calls:
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
                            continue

                        if call.get("tool") == "done":
                            finalize(retest=True)
                            break

                        exec_start = time.time()
                        exec_res = sess.exec_tool(call)
                        exec_ms = int((time.time() - exec_start) * 1000)
                        exec_res_sanitized = sanitize_artifact(exec_res[:10000])
                        emit_action(
                            model_id,
                            call.get("tool", "?"),
                            target=call.get("path")
                            or call.get("name")
                            or call.get("url")
                            or "",
                            state="done",
                            duration_ms=exec_ms,
                            result=exec_res_sanitized[:4000],
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

                    if role_recorded(model_id):
                        break

                if not role_recorded(model_id):
                    finalize()
            finally:
                if preview_server is not None:
                    try:
                        preview_server.stop()
                    except Exception:
                        pass

        with tempfile.TemporaryDirectory(prefix="arena-adv-") as tmp:
            root = Path(tmp)
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
            passed_results = [r for r in results if r.get("passed")]
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
                    "phase": phase_name,
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
