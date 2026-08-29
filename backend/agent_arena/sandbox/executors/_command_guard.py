"""Shared shell-command guard used by executors and the target verifier.

Single source of truth for blocking command strings that escape the workspace
jail, reach for host paths/env, or pivot the network (SSRF / egress). The
AdvancedExecutor toolbelt and the Trusted Target Verifier must apply the SAME
rules so a manifest-supplied verification command can never do what a fighter
tool call may not do.
"""

from __future__ import annotations

import ipaddress
import re
import socket
from urllib.parse import urlparse

_URL_IN_TEXT = re.compile(r"(?:[a-z][a-z0-9+.-]*)://[^\s\"'<>]+", re.I)
_FETCH_BIN = re.compile(
    r"(?:^|[\s;&|`(\n])(?:sudo\s+)?(?:[A-Za-z0-9._/-]+/)?(?:curl|wget)\b",
    re.I,
)
_ABS_PATH_IN_CMD = re.compile(r"(?:^|[\s=<>|&;`'\"(])(/[^\s;|&<>`'\"\)]*)")
_DOTDOT_IN_CMD = re.compile(r"(?:^|[\s=<>|&;`'\"(/])\.\.(?:/|[\s;|&<>`'\"\)]|$)")
_HOME_PATH_IN_CMD = re.compile(r"(?:^|[\s=<>|&;`'\"(])~(?:/|$)")
_ENV_HOME_IN_CMD = re.compile(r"(?:\$HOME|\$\{HOME\})(?![A-Za-z0-9_])")


def _fetch_url_blocked(url: str) -> str | None:
    """Return a rejection reason if `url` must not be fetched, else None.

    Only http/https to public hosts are allowed. Loopback, private, link-local,
    and metadata endpoints (e.g. cloud 169.254.169.254) are blocked so a
    verification command cannot pivot to the internal network or credential
    endpoints.
    """
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


def command_block_reason(command: str, *, allow_network: bool) -> str | None:
    """Return a rejection reason if `command` must not run, else None.

    Mirrors the executor's tool-call guard so verification commands (which run
    with shell=True from target manifests) get the exact same jail:
    - rejects '..', '~', '$HOME' and absolute-path escapes
    - blocks fetch binaries (curl/wget) and URL targets unless the target
      explicitly opts into network access
    - blocks SSRF-unsafe URLs (loopback/private/link-local/metadata) always
    """
    if command is None or not str(command).strip():
        return "empty command"
    text = str(command)
    if _DOTDOT_IN_CMD.search(text):
        return "path escape '..' rejected"
    if _HOME_PATH_IN_CMD.search(text):
        return "home path '~' rejected"
    if _ENV_HOME_IN_CMD.search(text):
        return "home env expansion '$HOME' rejected"
    abs_match = _ABS_PATH_IN_CMD.search(text)
    if abs_match:
        return f"absolute path rejected: {abs_match.group(1)}"
    has_fetch_bin = bool(_FETCH_BIN.search(text))
    targets = _fetch_targets_in_command(text)
    if (has_fetch_bin or targets) and not allow_network:
        return "network fetch blocked (target network is false)"
    for raw in targets:
        reason = _fetch_url_blocked(_normalize_fetch_url(raw))
        if reason:
            return f"fetch blocked ({reason})"
    return None
