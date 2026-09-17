"""Trusted destination policy for Fighter-initiated HTTP requests.

Fighter input chooses a request, never its authority.  The runtime registers
exact origins that were authorized by validated Battle/Format/Target state.
Every request and redirect must continue to match one of those origins.
"""

from __future__ import annotations

from dataclasses import dataclass
import ipaddress
import os
import re
import socket
import ssl
from collections.abc import Callable, Iterable, Mapping
from urllib.parse import urlsplit, urlunsplit

import httpcore
import httpx


Resolver = Callable[[str, int], Iterable[str]]

_MAX_URL_LENGTH = 4096
_DEFAULT_PORTS = {"http": 80, "https": 443}
_METADATA_HOSTS = frozenset(
    {
        "metadata",
        "metadata.google.internal",
        "instance-data",
    }
)
_METADATA_NETWORKS = tuple(
    ipaddress.ip_network(value)
    for value in (
        "169.254.169.254/32",  # AWS/GCP/OpenStack metadata
        "169.254.170.2/32",  # ECS task metadata
        "100.100.100.200/32",  # Alibaba metadata
        "fd00:ec2::254/128",  # AWS IPv6 metadata
    )
)
_PROTECTED_HEADER_NAMES = frozenset(
    {
        "connection",
        "content-length",
        "forwarded",
        "host",
        "proxy-authorization",
        "proxy-connection",
        "te",
        "trailer",
        "transfer-encoding",
        "upgrade",
        "x-forwarded-for",
        "x-forwarded-host",
        "x-forwarded-port",
        "x-forwarded-proto",
        "x-internal-key",
        "x-sandbox-token",
    }
)
_SECRET_ENV_EXACT = frozenset(
    {
        "APPWRITE_API_KEY",
        "BATTLE_DATABASE_URL",
        "BATTLE_RO_DATABASE_URL",
        "BATTLE_TOKEN",
        "DATABASE_URL",
        "DATABASE_URL_UNPOOLED",
        "FERNET_KEY",
        "FERNET_KEY_OLD",
        "INTERNAL_API_KEY",
        "MODAL_TOKEN_ID",
        "MODAL_TOKEN_SECRET",
        "NEON_API_KEY",
    }
)
_CONTROL_PLANE_URL_ENV = (
    "BACKEND_PUBLIC_URL",
    "INTERNAL_BASE_URL",
    "APPWRITE_ENDPOINT",
    "NEON_API_BASE",
)


class FighterNetworkPolicyError(RuntimeError):
    """A Fighter request failed trusted network authorization."""

    def __init__(self, message: str, *, code: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class ValidatedHttpDestination:
    url: str
    origin: str
    scheme: str
    host: str
    port: int
    addresses: frozenset[str]
    scope: str


@dataclass(frozen=True)
class _AuthorizedOrigin:
    origin: str
    scheme: str
    host: str
    port: int
    addresses: frozenset[str]
    scope: str


@dataclass(frozen=True)
class _ParsedUrl:
    url: str
    origin: str
    scheme: str
    host: str
    port: int


def control_plane_urls_from_env(
    env: Mapping[str, str] | None = None,
) -> tuple[str, ...]:
    source = os.environ if env is None else env
    return tuple(
        value.strip()
        for name in _CONTROL_PLANE_URL_ENV
        if (value := str(source.get(name) or "").strip())
    )


def protected_secret_values_from_env(
    env: Mapping[str, str] | None = None,
) -> tuple[str, ...]:
    """Return secret values for equality/containment checks without logging them."""

    source = os.environ if env is None else env
    values: set[str] = set()
    for name, raw in source.items():
        upper = str(name).upper()
        if not (
            upper in _SECRET_ENV_EXACT
            or upper.endswith(("_KEY", "_SECRET", "_TOKEN", "_PASSWORD"))
            or upper.endswith("_DATABASE_URL")
        ):
            continue
        value = str(raw or "")
        if len(value) >= 8:
            values.add(value)
    return tuple(values)


def _system_resolver(host: str, port: int) -> tuple[str, ...]:
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise FighterNetworkPolicyError(
            "authorized destination DNS resolution failed",
            code="dns_resolution_failed",
        ) from exc
    addresses = {str(info[4][0]).split("%", 1)[0] for info in infos}
    if not addresses:
        raise FighterNetworkPolicyError(
            "authorized destination produced no usable addresses",
            code="dns_resolution_failed",
        )
    return tuple(sorted(addresses))


def _canonical_host(raw_host: str) -> str:
    host = str(raw_host or "").strip().strip("[]").rstrip(".")
    if not host or len(host) > 253:
        raise FighterNetworkPolicyError("invalid HTTP hostname", code="invalid_url")
    if any(ch.isspace() or ord(ch) < 32 for ch in host) or any(
        ch in host for ch in ("\\", "/", "@", "%")
    ):
        raise FighterNetworkPolicyError("invalid HTTP hostname", code="invalid_url")
    try:
        return str(ipaddress.ip_address(host))
    except ValueError:
        lowered = host.lower()
        # Reject legacy decimal/octal/hex IP spellings that URL stacks may
        # reinterpret as an address after a string-only policy comparison.
        if re.fullmatch(r"(?:0x[0-9a-f]+|[0-9]+|[0-9.]+)", lowered):
            raise FighterNetworkPolicyError(
                "non-canonical numeric address rejected",
                code="alternate_address_rejected",
            )
        try:
            return lowered.encode("idna").decode("ascii")
        except UnicodeError as exc:
            raise FighterNetworkPolicyError(
                "invalid HTTP hostname", code="invalid_url"
            ) from exc


def _format_origin(scheme: str, host: str, port: int) -> str:
    rendered_host = f"[{host}]" if ":" in host else host
    return f"{scheme}://{rendered_host}:{port}"


def _parse_url(url: str, *, origin_only: bool = False) -> _ParsedUrl:
    if not isinstance(url, str) or not url.strip():
        raise FighterNetworkPolicyError("missing HTTP URL", code="invalid_url")
    raw = url.strip()
    if len(raw) > _MAX_URL_LENGTH:
        raise FighterNetworkPolicyError("HTTP URL is too long", code="invalid_url")
    if "\\" in raw or any(ch.isspace() or ord(ch) < 32 for ch in raw):
        raise FighterNetworkPolicyError("malformed HTTP URL", code="invalid_url")
    try:
        parsed = urlsplit(raw)
        scheme = parsed.scheme.lower()
        if scheme not in _DEFAULT_PORTS:
            raise FighterNetworkPolicyError(
                "HTTP policy permits only http and https",
                code="scheme_not_allowed",
            )
        if parsed.username is not None or parsed.password is not None:
            raise FighterNetworkPolicyError(
                "embedded URL credentials are forbidden",
                code="embedded_credentials",
            )
        if not parsed.hostname:
            raise FighterNetworkPolicyError("HTTP URL has no host", code="invalid_url")
        host = _canonical_host(parsed.hostname)
        port = parsed.port or _DEFAULT_PORTS[scheme]
    except FighterNetworkPolicyError:
        raise
    except (TypeError, ValueError) as exc:
        raise FighterNetworkPolicyError("malformed HTTP URL", code="invalid_url") from exc
    if not 1 <= port <= 65535:
        raise FighterNetworkPolicyError("invalid HTTP port", code="invalid_url")
    if origin_only and (parsed.path not in ("", "/") or parsed.query or parsed.fragment):
        raise FighterNetworkPolicyError(
            "authorized destinations must be exact origins",
            code="invalid_authorized_origin",
        )
    origin = _format_origin(scheme, host, port)
    rendered_host = f"[{host}]" if ":" in host else host
    netloc = rendered_host
    if port != _DEFAULT_PORTS[scheme]:
        netloc = f"{rendered_host}:{port}"
    normalized = urlunsplit(
        (scheme, netloc, parsed.path or "/", parsed.query, "")
    )
    return _ParsedUrl(normalized, origin, scheme, host, port)


def _addresses_for(host: str, port: int, resolver: Resolver) -> frozenset[str]:
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        try:
            raw_addresses = resolver(host, port)
        except FighterNetworkPolicyError:
            raise
        except OSError as exc:
            raise FighterNetworkPolicyError(
                "authorized destination DNS resolution failed",
                code="dns_resolution_failed",
            ) from exc
    else:
        raw_addresses = (str(literal),)

    addresses: set[str] = set()
    for raw in raw_addresses:
        try:
            addresses.add(str(ipaddress.ip_address(str(raw).split("%", 1)[0])))
        except ValueError as exc:
            raise FighterNetworkPolicyError(
                "resolver returned a non-IP address",
                code="dns_resolution_failed",
            ) from exc
    if not addresses:
        raise FighterNetworkPolicyError(
            "authorized destination produced no usable addresses",
            code="dns_resolution_failed",
        )
    return frozenset(addresses)


def _always_forbidden_address(address: str) -> bool:
    addr = ipaddress.ip_address(address)
    if any(addr in network for network in _METADATA_NETWORKS):
        return True
    return bool(
        addr.is_link_local
        or addr.is_multicast
        or addr.is_unspecified
        or addr.is_reserved
    )


class FighterNetworkPolicy:
    """Exact-origin policy constructed and mutated only by trusted runtime code."""

    def __init__(
        self,
        *,
        allow_external: bool = False,
        resolver: Resolver | None = None,
        control_plane_urls: Iterable[str] = (),
    ):
        self.allow_external = bool(allow_external)
        self._resolver = resolver or _system_resolver
        self._authorized: dict[str, _AuthorizedOrigin] = {}
        self._control_plane_origins: set[str] = set()
        self._control_plane_endpoints: set[tuple[str, int]] = set()
        for url in control_plane_urls:
            self._register_control_plane(url)

    @property
    def has_authorized_origins(self) -> bool:
        return bool(self._authorized)

    def _register_control_plane(self, url: str) -> None:
        try:
            parsed = _parse_url(url)
        except FighterNetworkPolicyError:
            return
        self._control_plane_origins.add(parsed.origin)
        try:
            self._control_plane_endpoints.update(
                (address, parsed.port)
                for address in _addresses_for(
                    parsed.host, parsed.port, self._resolver
                )
            )
        except FighterNetworkPolicyError:
            # Exact-host blocking remains active if DNS is unavailable.
            pass

    def _reject_forbidden(
        self, parsed: _ParsedUrl, addresses: frozenset[str]
    ) -> None:
        if parsed.host in _METADATA_HOSTS or any(
            _always_forbidden_address(address) for address in addresses
        ):
            raise FighterNetworkPolicyError(
                "cloud metadata or non-routable destination blocked",
                code="metadata_destination_blocked",
            )
        if parsed.origin in self._control_plane_origins or any(
            (address, parsed.port) in self._control_plane_endpoints
            for address in addresses
        ):
            raise FighterNetworkPolicyError(
                "Arena control-plane destination blocked",
                code="control_plane_destination_blocked",
            )

    def _authorize(self, origin: str, *, scope: str) -> ValidatedHttpDestination:
        parsed = _parse_url(origin, origin_only=True)
        if scope == "external" and not self.allow_external:
            raise FighterNetworkPolicyError(
                "Target/Format network permission is disabled",
                code="network_disabled",
            )
        addresses = _addresses_for(parsed.host, parsed.port, self._resolver)
        self._reject_forbidden(parsed, addresses)
        if scope == "external" and any(
            not ipaddress.ip_address(address).is_global for address in addresses
        ):
            raise FighterNetworkPolicyError(
                "external authorization cannot designate an internal address",
                code="invalid_external_destination",
            )
        if scope == "battle-local" and any(
            ipaddress.ip_address(address).is_global for address in addresses
        ):
            raise FighterNetworkPolicyError(
                "Battle-local authorization cannot designate an external address",
                code="invalid_battle_local_destination",
            )
        authorized = _AuthorizedOrigin(
            parsed.origin,
            parsed.scheme,
            parsed.host,
            parsed.port,
            addresses,
            scope,
        )
        self._authorized[parsed.origin] = authorized
        return ValidatedHttpDestination(
            parsed.url,
            parsed.origin,
            parsed.scheme,
            parsed.host,
            parsed.port,
            addresses,
            scope,
        )

    def authorize_battle_local(self, origin: str) -> ValidatedHttpDestination:
        """Register one exact trusted Battle-local origin, including its port."""

        return self._authorize(origin, scope="battle-local")

    def authorize_external(self, origin: str) -> ValidatedHttpDestination:
        """Register an exact external origin when Target network policy permits it."""

        return self._authorize(origin, scope="external")

    def validate_url(self, url: str) -> ValidatedHttpDestination:
        parsed = _parse_url(url)
        if parsed.host in _METADATA_HOSTS:
            raise FighterNetworkPolicyError(
                "cloud metadata destination blocked",
                code="metadata_destination_blocked",
            )
        if parsed.origin in self._control_plane_origins:
            raise FighterNetworkPolicyError(
                "Arena control-plane destination blocked",
                code="control_plane_destination_blocked",
            )
        authorized = self._authorized.get(parsed.origin)
        if authorized is None:
            raise FighterNetworkPolicyError(
                "destination is not authorized for this Battle",
                code="destination_not_allowed",
            )
        addresses = _addresses_for(parsed.host, parsed.port, self._resolver)
        self._reject_forbidden(parsed, addresses)
        if not addresses.issubset(authorized.addresses):
            raise FighterNetworkPolicyError(
                "authorized destination DNS addresses changed",
                code="dns_rebinding_blocked",
            )
        return ValidatedHttpDestination(
            parsed.url,
            parsed.origin,
            parsed.scheme,
            parsed.host,
            parsed.port,
            addresses,
            authorized.scope,
        )

    def connection_addresses(self, host: str | bytes, port: int) -> tuple[str, ...]:
        """Resolve and revalidate immediately before the socket is opened."""

        raw_host = host.decode("ascii") if isinstance(host, bytes) else str(host)
        canonical = _canonical_host(raw_host)
        candidates = [
            authorized
            for authorized in self._authorized.values()
            if authorized.host == canonical and authorized.port == int(port)
        ]
        if not candidates:
            raise FighterNetworkPolicyError(
                "socket destination is not authorized for this Battle",
                code="destination_not_allowed",
            )
        addresses = _addresses_for(canonical, int(port), self._resolver)
        parsed = _ParsedUrl(
            candidates[0].origin,
            candidates[0].origin,
            candidates[0].scheme,
            canonical,
            int(port),
        )
        self._reject_forbidden(parsed, addresses)
        if not any(addresses.issubset(item.addresses) for item in candidates):
            raise FighterNetworkPolicyError(
                "authorized destination DNS addresses changed before connect",
                code="dns_rebinding_blocked",
            )
        return tuple(
            sorted(
                addresses,
                key=lambda value: (
                    ipaddress.ip_address(value).version,
                    int(ipaddress.ip_address(value)),
                ),
            )
        )

    def sanitize_headers(
        self,
        headers: Mapping[str, str] | None,
        *,
        protected_values: Iterable[str] = (),
    ) -> dict[str, str]:
        if headers is None:
            return {}
        if not isinstance(headers, Mapping):
            raise FighterNetworkPolicyError(
                "HTTP headers must be an object",
                code="invalid_headers",
            )
        secrets = tuple(value for value in protected_values if len(value) >= 8)
        clean: dict[str, str] = {}
        for raw_name, raw_value in headers.items():
            if not isinstance(raw_name, str) or not isinstance(raw_value, str):
                raise FighterNetworkPolicyError(
                    "HTTP header names and values must be strings",
                    code="invalid_headers",
                )
            name = raw_name.strip()
            value = raw_value.strip()
            lowered = name.lower()
            if (
                not name
                or lowered in _PROTECTED_HEADER_NAMES
                or lowered.startswith("x-forwarded-")
            ):
                raise FighterNetworkPolicyError(
                    f"protected HTTP header rejected: {name or '(empty)'}",
                    code="protected_header_rejected",
                )
            if any(ch in name or ch in value for ch in ("\r", "\n", "\x00")):
                raise FighterNetworkPolicyError(
                    "malformed HTTP header rejected",
                    code="invalid_headers",
                )
            if any(secret in value for secret in secrets):
                raise FighterNetworkPolicyError(
                    f"protected credential value rejected in header: {name}",
                    code="protected_credential_rejected",
                )
            clean[name] = value
        return clean

    def reject_protected_values(
        self,
        *values: str,
        protected_values: Iterable[str] = (),
    ) -> None:
        """Reject direct forwarding of a host credential without echoing it."""

        secrets = tuple(value for value in protected_values if len(value) >= 8)
        if any(secret in str(value) for secret in secrets for value in values):
            raise FighterNetworkPolicyError(
                "protected credential value rejected in HTTP request",
                code="protected_credential_rejected",
            )


class _PinnedNetworkBackend(httpcore.NetworkBackend):
    """httpcore backend that connects only to policy-validated IP addresses."""

    def __init__(self, policy: FighterNetworkPolicy):
        self._policy = policy
        self._backend = httpcore.SyncBackend()

    def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options=None,
    ):
        last_error: Exception | None = None
        for address in self._policy.connection_addresses(host, port):
            try:
                return self._backend.connect_tcp(
                    address,
                    port,
                    timeout=timeout,
                    local_address=local_address,
                    socket_options=socket_options,
                )
            except Exception as exc:
                last_error = exc
        if last_error is not None:
            raise last_error
        raise FighterNetworkPolicyError(
            "authorized destination had no connectable address",
            code="dns_resolution_failed",
        )

    def connect_unix_socket(
        self,
        path: str,
        timeout: float | None = None,
        socket_options=None,
    ):
        del path, timeout, socket_options
        raise FighterNetworkPolicyError(
            "Unix socket transport is forbidden for Fighter HTTP",
            code="scheme_not_allowed",
        )

    def sleep(self, seconds: float) -> None:
        self._backend.sleep(seconds)


class _CoreResponseStream(httpx.SyncByteStream):
    def __init__(self, stream):
        self._stream = stream

    def __iter__(self):
        yield from self._stream

    def close(self) -> None:
        close = getattr(self._stream, "close", None)
        if close is not None:
            close()


class FighterHttpTransport(httpx.BaseTransport):
    """HTTPX transport whose TCP connection is pinned to trusted DNS results."""

    def __init__(self, policy: FighterNetworkPolicy):
        self._pool = httpcore.ConnectionPool(
            ssl_context=ssl.create_default_context(),
            network_backend=_PinnedNetworkBackend(policy),
            retries=0,
        )

    def __enter__(self):
        self._pool.__enter__()
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self._pool.__exit__(exc_type, exc_value, traceback)

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        core_request = httpcore.Request(
            method=request.method,
            url=httpcore.URL(
                scheme=request.url.raw_scheme,
                host=request.url.raw_host,
                port=request.url.port,
                target=request.url.raw_path,
            ),
            headers=request.headers.raw,
            content=request.stream,
            extensions=request.extensions,
        )
        response = self._pool.handle_request(core_request)
        return httpx.Response(
            status_code=response.status,
            headers=response.headers,
            stream=_CoreResponseStream(response.stream),
            extensions=response.extensions,
        )

    def close(self) -> None:
        self._pool.close()
