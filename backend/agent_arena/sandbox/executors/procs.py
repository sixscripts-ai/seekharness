"""Process manager for the universal toolbelt: background procs with ring-buffered logs."""

from __future__ import annotations

import os
import subprocess
import threading
import time
from collections import deque
from pathlib import Path

from .tool_runtime import ProcessRunner, strip_secret_env

_DEFAULT_MAX_LOG_BYTES = 64_000


class _LogRing:
    def __init__(self, max_bytes: int = _DEFAULT_MAX_LOG_BYTES):
        self._chunks: deque[str] = deque()
        self._bytes = 0
        self._max = max_bytes
        self._lock = threading.Lock()

    def append(self, text: str) -> None:
        if not text:
            return
        with self._lock:
            self._chunks.append(text)
            self._bytes += len(text.encode("utf-8", errors="ignore"))
            while self._bytes > self._max and self._chunks:
                dropped = self._chunks.popleft()
                self._bytes -= len(dropped.encode("utf-8", errors="ignore"))

    def tail(self, max_chars: int = 8000) -> str:
        with self._lock:
            out = "".join(self._chunks)
        return out[-max_chars:] if max_chars and len(out) > max_chars else out


class ManagedProcess:
    def __init__(self, name: str, proc: subprocess.Popen, workdir: Path):
        self.name = name
        self.proc = proc
        self.workdir = workdir
        self.stdout_log = _LogRing()
        self.stderr_log = _LogRing()
        self.started = time.time()
        self._readers: list[threading.Thread] = []

    def spawn_readers(self) -> None:
        def pump(stream, ring):
            try:
                for raw in iter(stream.readline, ""):
                    if not raw:
                        break
                    ring.append(raw)
            except Exception:
                pass
            finally:
                try:
                    stream.close()
                except Exception:
                    pass

        if self.proc.stdout is not None:
            t = threading.Thread(
                target=pump, args=(self.proc.stdout, self.stdout_log), daemon=True
            )
            t.start()
            self._readers.append(t)
        if self.proc.stderr is not None:
            t = threading.Thread(
                target=pump, args=(self.proc.stderr, self.stderr_log), daemon=True
            )
            t.start()
            self._readers.append(t)

    def alive(self) -> bool:
        return self.proc.poll() is None

    def status(self) -> str:
        if self.alive():
            return "running"
        return f"exit {self.proc.returncode}"

    def join_readers(self, timeout: float = 1.0) -> None:
        deadline = time.time() + max(0.05, timeout)
        for reader in self._readers:
            remaining = max(0.0, deadline - time.time())
            reader.join(remaining)


class ProcessManager:
    def __init__(self, workdir: Path):
        self.workdir = Path(workdir)
        self._procs: dict[str, ManagedProcess] = {}
        self._lock = threading.Lock()
        self._seq = 0

    def start(self, name: str, command: str, env: dict | None = None) -> ManagedProcess:
        name = (name or f"bg{self._seq + 1}").strip()
        with self._lock:
            if name in self._procs and self._procs[name].alive():
                raise RuntimeError(f"background process already running: {name}")
            self._seq += 1
            bg_dir = self.workdir / ".arena_bg"
            bg_dir.mkdir(parents=True, exist_ok=True)
            script = bg_dir / f"{name}.sh"
            script.write_text(command, encoding="utf-8")
            script.chmod(0o755)
            env = strip_secret_env(env if env is not None else os.environ.copy())
            env["ARENA_BG_NAME"] = name
            try:
                proc = ProcessRunner.start(
                    ["bash", str(script)],
                    cwd=self.workdir,
                    env=env,
                )
            except Exception as exc:
                raise RuntimeError(f"failed to start bg {name}: {exc}") from exc
            mgr = ManagedProcess(name, proc, self.workdir)
            mgr.spawn_readers()
            self._procs[name] = mgr
            return mgr

    def list(self) -> str:
        lines = []
        for name, mp in sorted(self._procs.items()):
            try:
                out_bytes = len(mp.stdout_log.tail(10**9))
            except Exception:
                out_bytes = 0
            lines.append(
                f"{name} pid={mp.proc.pid} {mp.status()} stdout={out_bytes}b "
                f"started={time.strftime('%H:%M:%S', time.localtime(mp.started))}"
            )
        return "\n".join(lines) if lines else "(no background processes)"

    def kill(self, name: str) -> str:
        mp = self._procs.get(name)
        if not mp:
            return f"ERROR: no background process {name}"
        if mp.alive():
            ProcessRunner.terminate_background(mp.proc)
        mp.join_readers()
        return f"KILLED {name} {mp.status()}"

    def logs(self, name: str, tail_chars: int = 8000) -> str:
        mp = self._procs.get(name)
        if not mp:
            return f"ERROR: no background process {name}"
        out = mp.stdout_log.tail(tail_chars)
        err = mp.stderr_log.tail(tail_chars)
        if out and err:
            return f"STDOUT:\n{out}\nSTDERR:\n{err}"
        return out or err or "(no logs yet)"

    def kill_all(self) -> None:
        for name in list(self._procs):
            try:
                self.kill(name)
            except Exception:
                pass

    # Compatibility alias for callers that used the original spelling.
    def killall(self) -> None:
        self.kill_all()
