"""Shared policy and process primitives for sandbox tool execution.

The advanced executor exposes many tools, but all of them ultimately cross one
of two security boundaries: a child process or a network request.  Keeping the
policy and process lifecycle here prevents individual tool handlers from
silently acquiring different privileges or cleanup behavior.
"""

from __future__ import annotations

import ipaddress
import os
import signal
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Mapping
from urllib.parse import urlsplit

from ._command_guard import origin_key


_SECRET_EXACT = frozenset(
    {
        "FERNET_KEY",
        "FERNET_KEY_OLD",
        "INTERNAL_API_KEY",
        "BATTLE_TOKEN",
        "DATABASE_URL",
        "DATABASE_URL_UNPOOLED",
        "BATTLE_RO_DATABASE_URL",
        "ARENA_EVALUATOR_DIR",
        "ARENA_TRUSTED_TARGETS_DIR",
        "BATTLE_BOOTSTRAP_JSON",
    }
)
_SECRET_SUFFIXES = (
    "_KEY",
    "_SECRET",
    "_TOKEN",
    "_PASSWORD",
    "_PASS",
    "_PWD",
    "_CREDENTIAL",
    "_CREDENTIALS",
)


def strip_secret_env(env: Mapping[str, str]) -> dict[str, str]:
    """Return a child-safe copy of *env* without credentials or evaluator state."""

    out = dict(env)
    for name in list(out):
        upper = str(name).upper()
        if upper in _SECRET_EXACT or upper.endswith(_SECRET_SUFFIXES):
            out.pop(name, None)
    return out


_normalize_origin = origin_key


def _is_local_host(host: str) -> bool:
    host = (host or "").lower().rstrip(".")
    if host == "localhost" or "." not in host or host.endswith(".local"):
        return True
    try:
        address = ipaddress.ip_address(host.split("%", 1)[0])
    except ValueError:
        return False
    return bool(
        address.is_loopback
        or address.is_private
        or address.is_link_local
        or address.is_reserved
    )


@dataclass(frozen=True)
class SandboxPolicy:
    """Filesystem, child-environment, and network policy for one tool session."""

    workdir: Path
    root: Path | None = None
    allow_network: bool = False
    allowed_origins: Iterable[str] = field(default_factory=tuple)
    timeout: int | None = None
    output_cap: int | None = None

    def __post_init__(self) -> None:
        workdir = Path(self.workdir)
        root = Path(self.root) if self.root is not None else workdir
        origins = frozenset(
            origin
            for origin in (_normalize_origin(value) for value in self.allowed_origins)
            if origin
        )
        object.__setattr__(self, "workdir", workdir)
        object.__setattr__(self, "root", root)
        object.__setattr__(self, "allowed_origins", origins)

    def resolve_path(self, rel: str) -> Path:
        """Resolve a relative path inside the session's filesystem jail."""

        if not rel or rel == ".":
            return self.workdir
        path = Path(rel)
        if path.is_absolute():
            raise ValueError(f"ERROR: absolute path rejected: {rel}")
        if ".." in path.parts:
            raise ValueError(f"ERROR: path escape '..' rejected: {rel}")
        resolved = (self.workdir / path).resolve()
        workdir = self.workdir.resolve()
        if resolved != workdir and workdir not in resolved.parents:
            raise ValueError(f"ERROR: path escape rejected: {rel}")
        return resolved

    def cap_output(self, data: str) -> tuple[str, bool]:
        """Apply the configured UTF-8-safe output cap."""

        if self.output_cap is None:
            return data, False
        encoded = data.encode("utf-8")
        if len(encoded) <= self.output_cap:
            return data, False
        capped = (
            encoded[: self.output_cap].decode("utf-8", errors="ignore")
            + "\n[TRUNCATED]"
        )
        return capped, True

    def child_env(self, extra: Mapping[str, str] | None = None) -> dict[str, str]:
        """Build the environment used by every fighter-owned child process."""

        env = strip_secret_env(os.environ.copy())
        env.update(
            {
                "ARENA_ROOT": str(self.root),
                "ARENA_WORKDIR": str(self.workdir),
                "PYTHONDONTWRITEBYTECODE": "1",
                "PYTHONUNBUFFERED": "1",
            }
        )
        work = str(self.workdir.resolve())
        env["PYTHONPATH"] = work + os.pathsep + env.get("PYTHONPATH", "")
        if extra:
            safe_extra = {
                str(key): str(value) for key, value in extra.items()
            }
            env.update(strip_secret_env(safe_extra))
        return env

    def check_url(self, url: str) -> str | None:
        """Return a policy rejection reason, or ``None`` when the URL is allowed.

        Explicit origins are intended for local preview/service endpoints.  A
        configured origin is matched exactly by scheme, host, and port; paths
        do not broaden the allowlist.
        """

        raw = str(url or "").strip()
        parsed = urlsplit(raw)
        if parsed.username is not None or parsed.password is not None:
            return "URL credentials are not allowed"
        origin = _normalize_origin(raw)
        if not origin:
            return "unparseable URL (http/https required)"
        if origin in self.allowed_origins and _is_local_host(parsed.hostname or ""):
            return None
        if not self.allow_network:
            return "network access is disabled"
        from ._command_guard import _fetch_url_blocked

        return _fetch_url_blocked(raw)

    def check_command(self, command: str) -> str | None:
        """Apply the command jail and this session's network policy together."""

        from ._command_guard import command_block_reason

        local_origins = tuple(
            origin
            for origin in self.allowed_origins
            if _is_local_host(urlsplit(origin).hostname or "")
        )
        return command_block_reason(
            command,
            allow_network=self.allow_network,
            allowed_origins=local_origins,
        )


class ProcessRunner:
    """Create, terminate, and reap process groups used by tool handlers."""

    @staticmethod
    def start(
        args: list[str],
        *,
        cwd: Path,
        env: Mapping[str, str],
    ) -> subprocess.Popen:
        return subprocess.Popen(
            args,
            cwd=str(cwd),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,
            env=dict(env),
        )

    @staticmethod
    def _signal_group(proc: subprocess.Popen, sig: int) -> None:
        try:
            os.killpg(os.getpgid(proc.pid), sig)
        except Exception:
            try:
                if sig == signal.SIGKILL:
                    proc.kill()
                else:
                    proc.terminate()
            except Exception:
                pass

    @classmethod
    def kill_and_reap(
        cls,
        proc: subprocess.Popen,
        *,
        signal_to_send: int = signal.SIGKILL,
        grace_seconds: float = 1.0,
    ) -> tuple[str, str]:
        """Kill a process group and drain/reap its parent process.

        The first ``communicate`` call normally times out in the caller.  A
        second bounded call after the group is killed is intentional: it drains
        captured pipes and updates ``returncode`` instead of leaving a zombie.
        """

        cls._signal_group(proc, signal_to_send)
        try:
            return proc.communicate(timeout=max(0.05, grace_seconds))
        except subprocess.TimeoutExpired:
            cls._signal_group(proc, signal.SIGKILL)
            try:
                return proc.communicate(timeout=max(0.05, grace_seconds))
            except subprocess.TimeoutExpired:
                try:
                    proc.wait()
                except Exception:
                    pass
                return "", ""
        except Exception:
            try:
                proc.wait(timeout=max(0.05, grace_seconds))
            except Exception:
                pass
            return "", ""

    @classmethod
    def communicate_with_timeout(
        cls,
        proc: subprocess.Popen,
        *,
        timeout: int | float | None,
    ) -> tuple[str, str, bool]:
        """Drain a foreground process, reaping its group on timeout."""

        try:
            out, err = proc.communicate(timeout=timeout)
            return out or "", err or "", False
        except subprocess.TimeoutExpired:
            out, err = cls.kill_and_reap(proc)
            return out or "", err or "", True

    @classmethod
    def terminate_background(
        cls,
        proc: subprocess.Popen,
        *,
        grace_seconds: float = 1.0,
    ) -> None:
        """Terminate and reap a background process whose pipes have readers."""

        if proc.poll() is None:
            cls._signal_group(proc, signal.SIGTERM)
            try:
                proc.wait(timeout=max(0.05, grace_seconds))
            except subprocess.TimeoutExpired:
                cls._signal_group(proc, signal.SIGKILL)
                try:
                    proc.wait()
                except Exception:
                    pass
            except Exception:
                pass
        else:
            try:
                proc.wait(timeout=max(0.05, grace_seconds))
            except Exception:
                pass


__all__ = ["ProcessRunner", "SandboxPolicy", "strip_secret_env"]
