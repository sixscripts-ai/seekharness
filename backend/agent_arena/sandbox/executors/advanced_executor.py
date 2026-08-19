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
import time
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
    ):
        self.workdir = Path(workdir)
        self.workdir.mkdir(parents=True, exist_ok=True)
        self.root = Path(root) if root else self.workdir
        self.tool_timeout = int(tool_timeout) if tool_timeout else None
        self.steps = 0
        self._max_output = int(output_cap) if output_cap else None
        self.skill_reads: set[str] = set()
        self.seq = 0
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
        if ".." in p.parts:
            raise ValueError(f"ERROR: path escape '..' rejected: {rel}")
        if p.is_absolute():
            return p
        return (self.workdir / p).resolve()

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

    def ls(self, path: str = ".") -> str:
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
        self.steps += 1
        if passed and rc == 0:
            return f"TEST_PASS {run_path}\n{out}"
        if fail:
            return f"TEST_FAIL {run_path}\n{out}"
        return f"TEST_UNKNOWN {run_path}\n{out}"

    def _run_command(self, command: str, timeout: int | None = None) -> str:
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
        try:
            import httpx

            resp = httpx.get(url, timeout=20, follow_redirects=True)
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
        if not skill_read_ok:
            passed = False
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
        line = self.emit_result(client, battle_id, phase, result)
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

        target_code = format_config.get("target_code") or "# TASK: Fix is_palindrome\n"
        default_test_code = format_config.get("test_code") or DEFAULT_TEST_CODE
        role_test_code = format_config.get("role_test_code") or {}
        role_missions = format_config.get("role_missions") or {}
        seed_solution_roles = set(format_config.get("seed_solution_roles") or [])
        if format_config.get("seed_solution"):
            seed_solution_roles = seed_solution_roles | set(
                fighter_roles(format_config)
            )
        max_turns = int(format_config.get("max_tool_turns", 6))
        max_steps = int(format_config.get("max_tool_steps", 14))
        raw_timeout = format_config.get("tool_timeout")
        tool_timeout = int(raw_timeout) if raw_timeout else None
        pick_n = int(format_config.get("pick_per_battle", 3))
        race_tokens = int(format_config.get("race_max_tokens") or RACE_MAX_TOKENS)
        pool = select_skills(format_config) or load_skill_pool() or SKILL_POOL
        seq = {"n": 0}
        phase_name = tool_phase_name(format_config)
        fighters = fighter_roles(format_config)

        def emit(phase, model_id, artifact, event_type="artifact"):
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

        with tempfile.TemporaryDirectory(prefix="arena-adv-") as tmp:
            root = Path(tmp)

            for role_idx, role in enumerate(fighters):
                halted = self.halted(status_check, deadline)
                if halted:
                    if on_status:
                        on_status(halted)
                    return {}
                model_id = role_to_model.get(role)
                if not model_id:
                    continue

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

                sess = ToolSession(work, root=work, tool_timeout=tool_timeout)

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

                for turn in range(max_turns):
                    halted = self.halted(status_check, deadline)
                    if halted:
                        break
                    # Build prompt with skill pool + competitive context
                    prior = "\n".join(
                        [
                            f"[{a['phase']}/{a['model_id']}]: {a['artifact'][:500]}"
                            for a in history[-5:]
                        ]
                    )
                    fmt_name = format_config.get("name") or "a tool-using battle"
                    mission_line = (
                        f"Your mission: {mission}\n" if mission else ""
                    )
                    system_prompt = (
                        f"You are {role} in '{fmt_name}'. TARGET is in TARGET.md.\n"
                        f"{mission_line}"
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
                        f"You MUST emit SKILLS: a,b,... ({pick_n} names) then TOOL use_skill "
                        "name=<skill> for each chosen skill before writing solution.py.\n"
                        "Write THEORY.md explaining the pick. Write required artifacts. Run TOOL test "
                        "(harness is tests/test_target.py; do not fake TEST_PASS). "
                        "After a real TEST_PASS, emit DONE and stop.\n"
                        f"Prior: {prior or '(none)'}"
                    )
                    user_prompt = f"Workdir files:\n{sess.ls()}\n\nTARGET:\n{target_code[:2000]}\n\nYour turn {turn + 1}/{max_turns}, steps {sess.steps}/{max_steps}. Emit TOOL calls."

                    messages = [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ]
                    content = client.model(
                        battle_id,
                        model_id,
                        messages,
                        phase=phase_name,
                        max_tokens=race_tokens,
                    )
                    content = content.strip()

                    calls = parse_tool_calls(content)
                    if not calls:
                        # If no TOOL, treat whole content as artifact (fallback)
                        artifact = sanitize_artifact(content[:10000])
                        history.append(
                            {
                                "phase": phase_name,
                                "model_id": model_id,
                                "artifact": artifact,
                                "role": role,
                            }
                        )
                        client.round(
                            battle_id, phase_name, model_id, artifact, sequence=seq["n"] + 1
                        )
                        seq["n"] += 1
                        continue

                    for call in calls:
                        if sess.steps >= max_steps:
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
                                budget_exceeded=True,
                                phase=phase_name,
                            )
                            break

                        if call.get("tool") == "skills":
                            chosen_skills = call.get("chosen", [])[:5]
                            # Validate chosen skills are in pool
                            pool_names = {s["name"] for s in pool}
                            chosen_skills = [
                                c for c in chosen_skills if c in pool_names
                            ][:5]
                            res = sess.exec_tool(call)
                            history.append(
                                {
                                    "phase": phase_name,
                                    "model_id": model_id,
                                    "artifact": sanitize_artifact(f"{res}"),
                                    "role": role,
                                }
                            )
                            client.round(
                                battle_id,
                                phase_name,
                                model_id,
                                sanitize_artifact(res),
                                sequence=seq["n"] + 1,
                            )
                            seq["n"] += 1
                            continue

                        if call.get("tool") == "done":
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
                                retest=True,
                                phase=phase_name,
                            )
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
                        history.append(
                            {
                                "phase": phase_name,
                                "model_id": model_id,
                                "artifact": exec_res_sanitized,
                                "role": role,
                            }
                        )
                        client.round(
                            battle_id,
                            phase_name,
                            model_id,
                            exec_res_sanitized,
                            sequence=seq["n"] + 1,
                        )
                        seq["n"] += 1

                        if call.get("tool") == "test":
                            last_test = exec_res_sanitized
                            if self._harness_passed(exec_res_sanitized):
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
                                    last_test=exec_res_sanitized,
                                    phase=phase_name,
                                )
                                break

                    # Check if result already recorded for this role (DONE / TEST_PASS / budget)
                    if any(r["model_id"] == model_id for r in results):
                        break

                # If no result recorded (no DONE / TEST_PASS), score from workspace
                if not any(r["model_id"] == model_id for r in results):
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
                    )

                if preview_server is not None:
                    try:
                        preview_server.stop()
                    except Exception:
                        pass

        # Self-learning: Appwrite memory push + skill Elo update (competitive pick 5 to beat opponent)
        # Determine winner by passed + steps (fewer steps better if tie)
        try:
            winner = None
            if results:
                # sort by passed desc, steps asc
                sorted_res = sorted(
                    results,
                    key=lambda x: (x.get("passed", False), -x.get("steps", 999)),
                    reverse=True,
                )
                winner = sorted_res[0] if sorted_res else None
                # Update SKILL_POOL Elo in-memory (+5 winner, -5 loser)
                for r in results:
                    delta = 5 if r == winner else -5
                    for chosen in r.get("chosen_skills", [])[:5]:
                        for s in SKILL_POOL:
                            if s["name"] == chosen:
                                s["elo"] = max(800, min(2000, s["elo"] + delta))
                # Best-effort Appwrite memory + skill registry write (no crash on failure)
                try:
                    from ... import db as _db
                    from ...memory import maybe_remember
                    from ...skills_registry import record_outcome

                    databases = _db.get_databases()
                    database_id = _db.get_database_id()
                    if winner:
                        maybe_remember(
                            databases,
                            database_id,
                            insight=(
                                f"Battle {battle_id} format {format_config.get('name')} "
                                f"winner {winner.get('model_id')} chose {winner.get('chosen_skills')} "
                                f"theory {winner.get('theory', '')[:300]} beat opponent picks "
                                f"{[r.get('chosen_skills') for r in results if r != winner]}. "
                                "Skills to beat opponent technique emerged."
                            ),
                            battle_id=battle_id,
                            model_id=winner.get("model_id", ""),
                            format_name=format_config.get("name", ""),
                            chosen_skills=winner.get("chosen_skills") or [],
                            theory=winner.get("theory", ""),
                            outcome=winner.get("outcome", ""),
                        )
                    for r in results:
                        for chosen in r.get("chosen_skills", [])[:5]:
                            try:
                                record_outcome(
                                    databases,
                                    database_id,
                                    chosen,
                                    outcome="win" if r == winner else "loss",
                                    tier="general",
                                )
                            except Exception:
                                pass
                except Exception:
                    pass
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
