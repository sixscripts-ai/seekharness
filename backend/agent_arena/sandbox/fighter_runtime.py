"""Secretless raw-process runtime for untrusted Fighter tools.

The trusted Arena process owns credentials and lifecycle decisions.  This
module is a deliberately small JSON-lines RPC boundary: every raw Fighter
process is a descendant of a network-denied helper that receives only a
minimal, non-secret environment.
"""

from __future__ import annotations

import argparse
import json
import os
import select
import shutil
import signal
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any

from .executors.procs import ProcessManager


class FighterRuntimeError(RuntimeError):
    """A runtime protocol or containment failure."""


class FighterRuntimeUnavailable(FighterRuntimeError):
    """The host cannot create the required contained Fighter runtime."""


_ENV_EXACT = {
    "APPWRITE_ENDPOINT",
    "LANG",
    "LC_ALL",
    "LC_CTYPE",
    "PATH",
    "PYTEST_ADDOPTS",
    "PYTEST_DISABLE_PLUGIN_AUTOLOAD",
    "TERM",
    "TZ",
}
_RUNTIME_ENV_EXACT = {
    "ARENA_BG_NAME",
    "ARENA_ROOT",
    "ARENA_WORKDIR",
    "HOME",
    "PYTHONDONTWRITEBYTECODE",
    "PYTHONPATH",
    "PYTHONUNBUFFERED",
    "TMPDIR",
}


def _backend_root() -> Path:
    return Path(__file__).resolve().parents[2]


def secretless_environment(source: dict[str, str], workdir: Path) -> dict[str, str]:
    """Build the only environment visible to the Fighter runtime.

    This is intentionally an allowlist rather than a denylist.  The sole
    retained service setting is the existing non-credential endpoint setting;
    raw processes have no network route to use it.
    """

    work = Path(workdir).resolve()
    tmpdir = work / ".arena_tmp"
    tmpdir.mkdir(parents=True, exist_ok=True)
    env = {
        name: str(value)
        for name, value in source.items()
        if name.upper() in _ENV_EXACT and str(value)
    }
    env["PATH"] = env.get("PATH") or os.defpath
    env["HOME"] = str(work)
    env["TMPDIR"] = str(tmpdir)
    env["ARENA_ROOT"] = str(work)
    env["ARENA_WORKDIR"] = str(work)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTHONPATH"] = os.pathsep.join((str(work), str(_backend_root())))
    return env


def _kill_process_group(proc: subprocess.Popen) -> None:
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


class _FighterRuntimeServer:
    """Runs inside the network-denied, secretless helper process."""

    def __init__(self, workdir: Path):
        self.workdir = Path(workdir).resolve()
        self.workdir.mkdir(parents=True, exist_ok=True)
        self._base_env = secretless_environment(dict(os.environ), self.workdir)
        self._procs = ProcessManager(self.workdir)

    def _command_env(self, request_env: object) -> dict[str, str]:
        if not isinstance(request_env, dict):
            return dict(self._base_env)
        # The request is trusted-side input, but filter it again at the boundary.
        supplied = {str(k): str(v) for k, v in request_env.items()}
        allowed = secretless_environment(supplied, self.workdir)
        for name in _RUNTIME_ENV_EXACT:
            if name in self._base_env:
                allowed[name] = self._base_env[name]
        return allowed

    def _require_workdir(self, raw: object) -> None:
        if Path(str(raw or self.workdir)).resolve() != self.workdir:
            raise FighterRuntimeError("fighter runtime rejected a non-workdir cwd")

    @staticmethod
    def _argv(raw: object) -> list[str]:
        if not isinstance(raw, list) or not raw or not all(
            isinstance(item, str) and item for item in raw
        ):
            raise FighterRuntimeError("fighter runtime requires a non-empty argv")
        return raw

    @staticmethod
    def _timeout(raw: object) -> float | None:
        if raw is None:
            return None
        try:
            timeout = float(raw)
        except (TypeError, ValueError) as exc:
            raise FighterRuntimeError("fighter runtime timeout is invalid") from exc
        if timeout <= 0:
            raise FighterRuntimeError("fighter runtime timeout must be positive")
        return timeout

    def _exec(self, request: dict[str, Any]) -> dict[str, Any]:
        self._require_workdir(request.get("cwd"))
        proc = subprocess.Popen(
            self._argv(request.get("argv")),
            cwd=str(self.workdir),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,
            env=self._command_env(request.get("env")),
        )
        try:
            stdout, stderr = proc.communicate(
                timeout=self._timeout(request.get("process_timeout"))
            )
        except subprocess.TimeoutExpired:
            _kill_process_group(proc)
            return {"exit_code": 124, "stdout": "", "stderr": "", "timed_out": True}
        return {
            "exit_code": int(proc.returncode or 0),
            "stdout": stdout or "",
            "stderr": stderr or "",
            "timed_out": False,
        }

    def _start_bg(self, request: dict[str, Any]) -> dict[str, Any]:
        self._require_workdir(request.get("cwd"))
        name = str(request.get("name") or "").strip()
        command = request.get("command")
        if not isinstance(command, str) or not command:
            raise FighterRuntimeError("fighter runtime background command is required")
        managed = self._procs.start(
            name,
            command,
            env=self._command_env(request.get("env")),
        )
        return {"name": managed.name, "pid": managed.proc.pid}

    def dispatch(self, request: dict[str, Any]) -> tuple[dict[str, Any], bool]:
        op = request.get("op")
        if op == "exec":
            return self._exec(request), False
        if op == "bg":
            return self._start_bg(request), False
        if op == "ps":
            return {"output": self._procs.list()}, False
        if op == "kill":
            return {"output": self._procs.kill(str(request.get("name") or ""))}, False
        if op == "logs":
            try:
                tail = int(request.get("tail", 8000))
            except (TypeError, ValueError):
                tail = 8000
            return {"output": self._procs.logs(str(request.get("name") or ""), tail)}, False
        if op == "close":
            self._procs.killall()
            return {"closed": True}, True
        raise FighterRuntimeError("fighter runtime operation is not allowed")

    def serve(self) -> int:
        print(json.dumps({"ready": True}), flush=True)
        try:
            for raw_line in sys.stdin:
                request: object = None
                try:
                    request = json.loads(raw_line)
                    if not isinstance(request, dict):
                        raise FighterRuntimeError("fighter runtime request must be an object")
                    result, should_close = self.dispatch(request)
                    response = {"id": request.get("id"), "ok": True, "result": result}
                except Exception as exc:
                    response = {
                        "id": request.get("id") if isinstance(request, dict) else None,
                        "ok": False,
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                    should_close = False
                print(json.dumps(response, separators=(",", ":")), flush=True)
                if should_close:
                    return 0
        finally:
            self._procs.killall()
        return 0


class FighterRuntimeClient:
    """Trusted-side client for the one-purpose Fighter execution protocol."""

    def __init__(self, workdir: Path, env: dict[str, str]):
        self.workdir = Path(workdir).resolve()
        self._env = secretless_environment(env, self.workdir)
        self._proc: subprocess.Popen[str] | None = None
        self._lock = threading.Lock()
        self._next_id = 0
        self._closed = False

    def _command(self) -> list[str]:
        module = "agent_arena.sandbox.fighter_runtime"
        server_args = [sys.executable, "-m", module, "--serve", "--workdir", str(self.workdir)]
        if sys.platform == "darwin":
            sandbox_exec = shutil.which("sandbox-exec")
            if not sandbox_exec:
                raise FighterRuntimeUnavailable("sandbox-exec is unavailable for Fighter containment")
            return [
                sandbox_exec,
                "-p",
                "(version 1) (deny network*) (allow default)",
                *server_args,
            ]
        if sys.platform.startswith("linux"):
            unshare = shutil.which("unshare")
            if not unshare:
                raise FighterRuntimeUnavailable("unshare is unavailable for Fighter containment")
            return [
                unshare,
                "--user",
                "--map-root-user",
                "--net",
                "--pid",
                "--fork",
                "--mount-proc",
                *server_args,
            ]
        raise FighterRuntimeUnavailable("no supported Fighter containment runtime on this host")

    def start(self) -> None:
        if self._proc is not None:
            return
        try:
            self._proc = subprocess.Popen(
                self._command(),
                cwd=str(self.workdir),
                env=self._env,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                start_new_session=True,
            )
            ready = self._read_message(timeout=5)
            if ready.get("ready") is not True:
                raise FighterRuntimeUnavailable("Fighter runtime did not acknowledge readiness")
        except FighterRuntimeError:
            self._terminate()
            raise
        except Exception as exc:
            self._terminate()
            raise FighterRuntimeUnavailable(f"Fighter runtime failed to start: {exc}") from exc

    def _read_message(self, timeout: float) -> dict[str, Any]:
        if self._proc is None or self._proc.stdout is None:
            raise FighterRuntimeError("Fighter runtime is not running")
        ready, _, _ = select.select([self._proc.stdout], [], [], timeout)
        if not ready:
            raise FighterRuntimeUnavailable("Fighter runtime protocol timed out")
        line = self._proc.stdout.readline()
        if not line:
            stderr = ""
            if self._proc.stderr is not None:
                try:
                    stderr = self._proc.stderr.read(2000)
                except Exception:
                    pass
            raise FighterRuntimeUnavailable(
                f"Fighter runtime exited before response: {stderr.strip()[:500]}"
            )
        try:
            response = json.loads(line)
        except json.JSONDecodeError as exc:
            raise FighterRuntimeError("Fighter runtime returned invalid protocol data") from exc
        if not isinstance(response, dict):
            raise FighterRuntimeError("Fighter runtime returned an invalid protocol object")
        return response

    def request(self, op: str, *, timeout: float = 10, **payload: Any) -> dict[str, Any]:
        with self._lock:
            if self._closed or self._proc is None or self._proc.poll() is not None:
                raise FighterRuntimeUnavailable("Fighter runtime is unavailable")
            if self._proc.stdin is None:
                raise FighterRuntimeUnavailable("Fighter runtime input is unavailable")
            self._next_id += 1
            request = {"id": self._next_id, "op": op, **payload}
            try:
                self._proc.stdin.write(json.dumps(request, separators=(",", ":")) + "\n")
                self._proc.stdin.flush()
                response = self._read_message(timeout)
            except FighterRuntimeError:
                raise
            except Exception as exc:
                raise FighterRuntimeUnavailable(f"Fighter runtime request failed: {exc}") from exc
            if response.get("id") != self._next_id:
                raise FighterRuntimeError("Fighter runtime response id mismatch")
            if response.get("ok") is not True:
                raise FighterRuntimeError(str(response.get("error") or "Fighter runtime rejected request"))
            result = response.get("result")
            if not isinstance(result, dict):
                raise FighterRuntimeError("Fighter runtime response missing result")
            return result

    def exec(self, argv: list[str], *, env: dict[str, str], timeout: int | None) -> dict[str, Any]:
        # `run` historically had no timeout when the session did not configure
        # one, so the protocol wait must not invent a short command deadline.
        request_timeout = float(timeout + 5) if timeout is not None else 86400.0
        return self.request(
            "exec",
            timeout=request_timeout,
            argv=argv,
            cwd=str(self.workdir),
            env=env,
            process_timeout=timeout,
        )

    def bg(self, name: str, command: str, *, env: dict[str, str]) -> dict[str, Any]:
        return self.request(
            "bg", name=name, command=command, cwd=str(self.workdir), env=env
        )

    def ps(self) -> str:
        return str(self.request("ps").get("output") or "")

    def kill(self, name: str) -> str:
        return str(self.request("kill", name=name).get("output") or "")

    def logs(self, name: str, tail: int) -> str:
        return str(self.request("logs", name=name, tail=tail).get("output") or "")

    def close(self) -> None:
        if self._closed:
            return
        try:
            if self._proc is not None and self._proc.poll() is None:
                self.request("close", timeout=3)
        except Exception:
            pass
        self._closed = True
        self._terminate()

    def _terminate(self) -> None:
        proc = self._proc
        if proc is None:
            return
        if proc.poll() is None:
            _kill_process_group(proc)
        try:
            proc.wait(timeout=2)
        except Exception:
            pass


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--serve", action="store_true")
    parser.add_argument("--workdir", required=True)
    args = parser.parse_args()
    if not args.serve:
        raise SystemExit("fighter runtime requires --serve")
    return _FighterRuntimeServer(Path(args.workdir)).serve()


if __name__ == "__main__":
    raise SystemExit(main())
