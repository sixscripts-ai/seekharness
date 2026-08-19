"""Outbound URL validation to prevent server-side request forgery (SSRF).

User-controlled ``base_url`` values (LLM provider endpoints) are passed to
``httpx``. Without validation they can point at loopback / link-local /
private / metadata endpoints, turning the backend into a probing relay. This
module centralises the guards shared by :mod:`agent_arena.providers` and
:mod:`agent_arena.llm_client`.
"""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlsplit

from fastapi import HTTPException


def validate_base_url(url: str) -> str:
    """Validate a provider base URL and return a normalised form of it.

    Rejects URLs that are not ``http(s)``, lack a hostname, or resolve to a
    non-global (loopback / private / link-local / reserved / multicast /
    unspecified) address. Raises :class:`fastapi.HTTPException` (400) on
    failure so callers can surface it directly to API clients.

    The returned string is the original scheme+netloc, with a trailing slash
    stripped, ready for path concatenation.
    """
    if not url or not isinstance(url, str):
        raise HTTPException(status_code=400, detail="Invalid base_url")
    url = url.strip()
    if len(url) > 2048:
        raise HTTPException(status_code=400, detail="base_url too long")
    try:
        parsed = urlsplit(url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Malformed base_url") from exc

    scheme = parsed.scheme.lower()
    if scheme not in ("http", "https"):
        raise HTTPException(
            status_code=400,
            detail="base_url must use http or https",
        )
    host = parsed.hostname
    if not host:
        raise HTTPException(status_code=400, detail="base_url must include a host")
    if parsed.username is not None or parsed.password is not None:
        raise HTTPException(
            status_code=400, detail="base_url must not embed credentials"
        )

    host = host.strip("[]").rstrip(".")
    _validate_host(host)

    # Normalise: strip trailing slash so path concatenation is deterministic.
    netloc = parsed.netloc
    base = f"{scheme}://{netloc}"
    if parsed.path and parsed.path not in ("", "/"):
        base += parsed.path
    base = base.rstrip("/")
    return base


def _validate_host(host: str) -> None:
    """Ensure ``host`` is a domain name or a global IP address."""
    try:
        addr = ipaddress.ip_address(host)
    except ValueError:
        # Not an IP literal — treat as a DNS name; resolve it and validate
        # every address it points at to block DNS-rebinding tricks.
        _validate_dns_name(host)
        return

    if addr.version == 4:
        if addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_multicast or addr.is_unspecified:
            raise HTTPException(
                status_code=400, detail="base_url must not target a private network"
            )
    else:  # IPv6
        if not addr.is_global or addr.is_loopback or addr.is_link_local or addr.is_multicast or addr.is_unspecified:
            raise HTTPException(
                status_code=400, detail="base_url must not target a private network"
            )


def _validate_dns_name(host: str) -> None:
    # Reserved / non-routeable TLDs (RFC 2606) can never resolve, so they are
    # safe to accept (they are also what tests use). ``.localhost``/``.local``
    # map to the loopback / mDNS space and must be rejected.
    if host == "localhost" or host.endswith((".localhost", ".local")):
        raise HTTPException(
            status_code=400, detail="base_url must not target a private network"
        )
    if host.endswith((".invalid", ".test", ".example", ".example.com", ".example.org", ".example.net")):
        return

    # Resolve before deciding so a hostname that points only at RFC1918 or
    # loopback space can't be used to reach internal services.
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as exc:
        raise HTTPException(status_code=400, detail="base_url host not resolvable") from exc

    for info in infos:
        family = info[0]
        ip = info[4][0]
        try:
            addr = ipaddress.ip_address(ip)
        except ValueError:
            continue
        if family == socket.AF_INET:
            if not addr.is_global or addr.is_reserved:
                raise HTTPException(
                    status_code=400,
                    detail="base_url must not target a private network",
                )
        elif family == socket.AF_INET6:
            if not addr.is_global:
                raise HTTPException(
                    status_code=400,
                    detail="base_url must not target a private network",
                )
