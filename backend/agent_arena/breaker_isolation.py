"""Run untrusted Breaker artifacts outside the trusted evaluator container.

The production verifier owns the private evaluator Volume. Breaker code must
never run in that process because a read-only mount is still readable. Modal
verification uses a short-lived Sandbox with no evaluator Volume. Local tests
use a sanitized subprocess only when the private production mount is absent.
"""

from __future__ import annotations

import os
import pathlib
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from typing import Mapping


MAX_OUTPUT_BYTES = 32 * 1024
PRIVATE_EVALUATOR_MOUNT = pathlib.Path("/opt/arena-evaluators")


@dataclass(frozen=True)
class BreakerExecution:
    started: bool = False
    completed: bool = False
    return_code: int | None = None
    stdout: str = ""
    stderr: str = ""
    error: str = ""


def _safe_relative_path(path: str) -> pathlib.PurePosixPath | None:
    clean = str(path).replace("\\", "/").strip()
    if not clean or clean.startswith("/"):
        return None
    parts = tuple(part for part in clean.split("/") if part not in ("", "."))
    if not parts or any(part == ".." for part in parts):
        return None
    if parts[0].lower() in {"tests", "reference"}:
        return None
    return pathlib.PurePosixPath(*parts)


def _as_bytes(value: bytes | str) -> bytes:
    return value if isinstance(value, bytes) else str(value).encode("utf-8")


def _materialize(root: pathlib.Path, files: Mapping[str, bytes | str]) -> None:
    for rel, value in files.items():
        safe = _safe_relative_path(str(rel))
        if safe is None:
            continue
        destination = (root / pathlib.Path(*safe.parts)).resolve()
        if root.resolve() not in destination.parents:
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(_as_bytes(value))


def _command_argv(command: str, *, remote: bool = False) -> tuple[str, ...] | None:
    if command == "python3 exploit.py":
        return ("python3" if remote else sys.executable, "exploit.py")
    if command == "bash exploit.sh":
        return ("bash", "exploit.sh")
    if command == "node exploit.js":
        return ("node", "exploit.js")
    return None


def _bounded(value: str) -> tuple[str, bool]:
    encoded = str(value or "").encode("utf-8", errors="replace")
    if len(encoded) > MAX_OUTPUT_BYTES:
        return encoded[:MAX_OUTPUT_BYTES].decode("utf-8", errors="replace"), True
    return encoded.decode("utf-8", errors="replace"), False


def _clean_env(workdir: str, *, path: str = "") -> dict[str, str]:
    return {
        "PATH": path or os.environ.get("PATH", ""),
        "HOME": workdir,
        "TMPDIR": workdir,
        "PYTHONPATH": workdir,
        "PYTHONNOUSERSITE": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONSAFEPATH": "1",
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
    }


def _run_local(
    command: str,
    files: Mapping[str, bytes | str],
    *,
    timeout_seconds: int,
    allow_network: bool,
) -> BreakerExecution:
    del allow_network  # The local test process is hermetic; production uses Modal.
    with tempfile.TemporaryDirectory(prefix="arena-breaker-isolated-") as temp:
        workdir = pathlib.Path(temp).resolve()
        _materialize(workdir, files)
        argv = _command_argv(command)
        if argv is None:
            return BreakerExecution(error="unsupported_breaker_command")
        try:
            result = subprocess.run(
                argv,
                cwd=workdir,
                env=_clean_env(str(workdir)),
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            out, _ = _bounded(exc.stdout or "")
            err, _ = _bounded(exc.stderr or "")
            return BreakerExecution(
                started=True,
                completed=False,
                stdout=out,
                stderr=err,
                error="breaker_isolation_timeout",
            )
        except OSError as exc:
            return BreakerExecution(error=f"breaker_isolation_unavailable:{type(exc).__name__}")
        stdout, oversized_out = _bounded(result.stdout or "")
        stderr, oversized_err = _bounded(result.stderr or "")
        if oversized_out or oversized_err:
            return BreakerExecution(
                started=True,
                completed=True,
                return_code=int(result.returncode),
                stdout=stdout,
                stderr=stderr,
                error="breaker_output_too_large",
            )
        return BreakerExecution(
            started=True,
            completed=True,
            return_code=int(result.returncode),
            stdout=stdout,
            stderr=stderr,
        )


def _run_modal(
    command: str,
    files: Mapping[str, bytes | str],
    *,
    timeout_seconds: int,
    allow_network: bool,
    runtime: str,
) -> BreakerExecution:
    """Run the artifact in a Modal Sandbox with no evaluator Volume attached."""
    try:
        import modal

        from .runtime_packaging import target_runtime_pip_packages

        app = modal.App.lookup("agent-arena-backend", create_if_missing=True)
        image = (
            modal.Image.debian_slim(python_version="3.11")
            .apt_install("bash", "nodejs", "npm", "ca-certificates")
        )
        packages = target_runtime_pip_packages(runtime)
        if packages:
            image = image.pip_install(*packages)
        sandbox = modal.Sandbox.create(
            "sh",
            "-c",
            "mkdir -p /workspace && sleep 900",
            app=app,
            image=image,
            timeout=max(int(timeout_seconds) + 30, 60),
            block_network=not allow_network,
            # Deliberately do not inherit the backend's evaluator Volume.
            volumes={},
        )
    except Exception as exc:
        return BreakerExecution(error=f"breaker_isolation_unavailable:{type(exc).__name__}")

    try:
        root = "/workspace"
        for rel, value in files.items():
            safe = _safe_relative_path(str(rel))
            if safe is None:
                continue
            remote = f"{root}/{safe.as_posix()}"
            parent = str(pathlib.PurePosixPath(remote).parent)
            mkdir = sandbox.exec("mkdir", "-p", parent, timeout=10)
            if mkdir.wait() != 0:
                return BreakerExecution(error="breaker_isolation_workspace_failed")
            handle = sandbox.open(remote, "wb")
            try:
                handle.write(_as_bytes(value))
            finally:
                handle.close()

        argv = _command_argv(command, remote=True)
        if argv is None:
            return BreakerExecution(error="unsupported_breaker_command")
        process = sandbox.exec(
            *argv,
            workdir=root,
            env=_clean_env(root, path="/usr/local/bin:/usr/bin:/bin"),
            timeout=timeout_seconds,
            text=True,
        )
        return_code = int(process.wait())
        stdout, oversized_out = _bounded(process.stdout.read() or "")
        stderr, oversized_err = _bounded(process.stderr.read() or "")
        if oversized_out or oversized_err:
            return BreakerExecution(
                started=True,
                completed=True,
                return_code=return_code,
                stdout=stdout,
                stderr=stderr,
                error="breaker_output_too_large",
            )
        return BreakerExecution(
            started=True,
            completed=True,
            return_code=return_code,
            stdout=stdout,
            stderr=stderr,
        )
    except Exception as exc:
        return BreakerExecution(
            started=True,
            completed=False,
            error=f"breaker_isolation_execution_failed:{type(exc).__name__}",
        )
    finally:
        try:
            sandbox.terminate()
        except Exception:
            pass


def run_breaker_isolated(
    command: str,
    files: Mapping[str, bytes | str],
    *,
    timeout_seconds: int,
    allow_network: bool,
    runtime: str,
) -> BreakerExecution:
    """Select the production boundary; refuse same-container execution there."""
    mode = os.environ.get("ARENA_BREAKER_EXECUTION_MODE", "local").strip().lower()
    if mode == "modal":
        return _run_modal(
            command,
            files,
            timeout_seconds=timeout_seconds,
            allow_network=allow_network,
            runtime=runtime,
        )
    if PRIVATE_EVALUATOR_MOUNT.is_dir():
        return BreakerExecution(error="breaker_isolation_required_private_mount_visible")
    return _run_local(
        command,
        files,
        timeout_seconds=timeout_seconds,
        allow_network=allow_network,
    )
