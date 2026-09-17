"""Adversarial regression coverage for Fighter HTTP and SQL trust boundaries."""

from __future__ import annotations

import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace

import httpx
import pytest

from agent_arena.sandbox.executors.advanced_executor import ToolSession, _strip_secret_env
from agent_arena.sandbox.executors.fighter_network_policy import (
    FighterNetworkPolicy,
    FighterNetworkPolicyError,
    _PinnedNetworkBackend,
)


class FakeResolver:
    """Deterministic resolver that preserves the real policy decision."""

    def __init__(self, answers: dict[str, list[str] | tuple[str, ...]]):
        self.answers = {host: list(values) for host, values in answers.items()}

    def __call__(self, host: str, port: int) -> tuple[str, ...]:
        del port
        values = self.answers.get(host)
        if not values:
            raise OSError(f"no deterministic DNS answer for {host}")
        return tuple(values)


class SequencedResolver:
    """Return a different answer on later lookups to exercise DNS rebinding."""

    def __init__(self, host: str, *answers: tuple[str, ...]):
        self.host = host
        self.answers = list(answers)

    def __call__(self, host: str, port: int) -> tuple[str, ...]:
        del port
        if host != self.host or not self.answers:
            raise OSError(f"no deterministic DNS answer for {host}")
        if len(self.answers) == 1:
            return self.answers[0]
        return self.answers.pop(0)


def _policy(
    *,
    resolver=None,
    allow_external: bool = False,
    control_plane_urls: tuple[str, ...] = (),
    battle_local_origins: tuple[str, ...] = (),
    external_origins: tuple[str, ...] = (),
) -> FighterNetworkPolicy:
    policy = FighterNetworkPolicy(
        allow_external=allow_external,
        resolver=resolver,
        control_plane_urls=control_plane_urls,
    )
    for origin in battle_local_origins:
        policy.authorize_battle_local(origin)
    for origin in external_origins:
        policy.authorize_external(origin)
    return policy


def _session(
    tmp_path,
    *,
    policy: FighterNetworkPolicy,
    handler,
    allow_network: bool = False,
) -> ToolSession:
    return ToolSession(
        tmp_path,
        allow_network=allow_network,
        network_policy=policy,
        http_transport=httpx.MockTransport(handler),
    )


def _request(session: ToolSession, url: str, *, headers: dict | None = None):
    return session.exec_tool(
        {
            "tool": "http_request",
            "method": "GET",
            "url": url,
            "headers": headers or {},
        },
        count_step=False,
    )


def test_http_network_disabled_and_no_battle_allowlist_rejects_before_transport(tmp_path):
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(200, text="unexpected")

    session = _session(
        tmp_path,
        policy=_policy(resolver=FakeResolver({"public.test": ["203.0.113.10"]})),
        handler=handler,
    )
    try:
        result = _request(session, "https://public.test/data")
    finally:
        session.close()

    assert result.success is False
    assert result.policy_rejected is True
    assert result.error_type == "network_policy_rejection"
    assert calls == []


def test_http_unapproved_external_destination_rejected_even_when_network_enabled(tmp_path):
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(200, text="unexpected")

    session = _session(
        tmp_path,
        allow_network=True,
        policy=_policy(
            allow_external=True,
            resolver=FakeResolver({"public.test": ["203.0.113.10"]}),
        ),
        handler=handler,
    )
    try:
        result = _request(session, "https://public.test/data")
    finally:
        session.close()

    assert result.success is False
    assert result.policy_rejected is True
    assert calls == []


def test_http_external_authorization_requires_target_format_network_permission():
    policy = _policy(
        resolver=FakeResolver({"external.test": ["1.1.1.1"]}),
    )

    with pytest.raises(FighterNetworkPolicyError) as exc:
        policy.authorize_external("https://external.test")

    assert exc.value.code == "network_disabled"


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1:8000/private",
        "http://[::1]:8000/private",
        "http://10.0.0.5:8000/private",
        "http://169.254.169.254/latest/meta-data",
        "http://[fd00:ec2::254]/latest/meta-data",
    ],
)
def test_http_unauthorized_internal_and_metadata_destinations_rejected(tmp_path, url):
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(200, text="unexpected")

    session = _session(tmp_path, policy=_policy(), handler=handler)
    try:
        result = _request(session, url)
    finally:
        session.close()

    assert result.success is False
    assert result.policy_rejected is True
    assert calls == []


def test_http_control_plane_destination_is_unconditionally_rejected(tmp_path):
    calls: list[str] = []
    resolver = FakeResolver({"arena-control.test": ["198.51.100.7"]})

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(200, text="unexpected")

    session = _session(
        tmp_path,
        policy=_policy(
            resolver=resolver,
            control_plane_urls=("https://arena-control.test",),
        ),
        handler=handler,
    )
    try:
        result = _request(session, "https://arena-control.test/internal/model")
    finally:
        session.close()

    assert result.success is False
    assert result.policy_rejected is True
    assert "control-plane" in result.output.lower()
    assert calls == []


def test_http_control_plane_resolved_ip_cannot_be_allowlisted_as_an_alias():
    resolver = FakeResolver({"arena-control.test": ["1.1.1.1"]})
    policy = _policy(
        resolver=resolver,
        control_plane_urls=("https://arena-control.test",),
    )

    with pytest.raises(FighterNetworkPolicyError) as exc:
        policy.authorize_battle_local("https://1.1.1.1")

    assert exc.value.code == "control_plane_destination_blocked"


def test_http_explicit_battle_local_origin_is_allowed_with_exact_port(tmp_path):
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(200, text="battle-local-ok")

    policy = _policy(battle_local_origins=("http://127.0.0.1:8000",))
    session = _session(tmp_path, policy=policy, handler=handler)
    try:
        allowed = _request(session, "http://127.0.0.1:8000/health")
        wrong_port = _request(session, "http://127.0.0.1:8001/health")
    finally:
        session.close()

    assert allowed.success is True
    assert "battle-local-ok" in allowed.output
    assert wrong_port.success is False
    assert wrong_port.policy_rejected is True
    assert calls == ["http://127.0.0.1:8000/health"]


def test_http_battle_local_authorization_cannot_smuggle_an_external_origin():
    policy = _policy(
        resolver=FakeResolver({"external.test": ["1.1.1.1"]}),
    )

    with pytest.raises(FighterNetworkPolicyError) as exc:
        policy.authorize_battle_local("https://external.test")

    assert exc.value.code == "invalid_battle_local_destination"


def test_http_redirect_from_allowed_origin_to_metadata_is_rejected(tmp_path):
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(
            302,
            headers={"Location": "http://169.254.169.254/latest/meta-data"},
        )

    session = _session(
        tmp_path,
        policy=_policy(battle_local_origins=("http://127.0.0.1:8000",)),
        handler=handler,
    )
    try:
        result = _request(session, "http://127.0.0.1:8000/start")
    finally:
        session.close()

    assert result.success is False
    assert result.policy_rejected is True
    assert "redirect" in result.output.lower()
    assert calls == ["http://127.0.0.1:8000/start"]


def test_http_cross_origin_redirect_strips_target_authorization_and_cookie(tmp_path):
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.url.port == 8000:
            return httpx.Response(
                302,
                headers={"Location": "http://127.0.0.1:8001/final"},
            )
        return httpx.Response(200, text="redirect-ok")

    session = _session(
        tmp_path,
        policy=_policy(
            battle_local_origins=(
                "http://127.0.0.1:8000",
                "http://127.0.0.1:8001",
            )
        ),
        handler=handler,
    )
    try:
        result = _request(
            session,
            "http://127.0.0.1:8000/start",
            headers={
                "Authorization": "Bearer target-user-token",
                "Cookie": "target_session=abc",
            },
        )
    finally:
        session.close()

    assert result.success is True
    assert len(calls) == 2
    assert "authorization" in calls[0].headers
    assert "cookie" in calls[0].headers
    assert "authorization" not in calls[1].headers
    assert "cookie" not in calls[1].headers


@pytest.mark.parametrize(
    "headers",
    [
        {"X-Sandbox-Token": "fighter-supplied"},
        {"X-Internal-Key": "fighter-supplied"},
        {"Host": "arena-control.test"},
        {"Proxy-Authorization": "Basic fighter-supplied"},
    ],
)
def test_http_caller_cannot_supply_protected_headers(tmp_path, headers):
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(200, text="unexpected")

    session = _session(
        tmp_path,
        policy=_policy(battle_local_origins=("http://127.0.0.1:8000",)),
        handler=handler,
    )
    try:
        result = _request(session, "http://127.0.0.1:8000/", headers=headers)
    finally:
        session.close()

    assert result.success is False
    assert result.policy_rejected is True
    assert calls == []


def test_http_caller_cannot_forward_a_host_secret_in_an_otherwise_allowed_header(
    tmp_path, monkeypatch
):
    calls: list[str] = []
    monkeypatch.setenv("BATTLE_TOKEN", "battle-secret-value-123")

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(200, text="unexpected")

    session = _session(
        tmp_path,
        policy=_policy(battle_local_origins=("http://127.0.0.1:8000",)),
        handler=handler,
    )
    try:
        result = _request(
            session,
            "http://127.0.0.1:8000/",
            headers={"Authorization": "Bearer battle-secret-value-123"},
        )
    finally:
        session.close()

    assert result.success is False
    assert result.policy_rejected is True
    assert calls == []


@pytest.mark.parametrize(
    ("url", "body"),
    [
        ("http://127.0.0.1:8000/?token=battle-secret-value-123", ""),
        ("http://127.0.0.1:8000/", '{"token":"battle-secret-value-123"}'),
    ],
)
def test_http_caller_cannot_forward_a_host_secret_in_url_or_body(
    tmp_path, monkeypatch, url, body
):
    calls: list[str] = []
    monkeypatch.setenv("BATTLE_TOKEN", "battle-secret-value-123")

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(200, text="unexpected")

    session = _session(
        tmp_path,
        policy=_policy(battle_local_origins=("http://127.0.0.1:8000",)),
        handler=handler,
    )
    try:
        result = session.exec_tool(
            {"tool": "http_request", "method": "POST", "url": url, "body": body},
            count_step=False,
        )
    finally:
        session.close()

    assert result.success is False
    assert result.policy_rejected is True
    assert result.metadata["policy_code"] == "protected_credential_rejected"
    assert "battle-secret-value-123" not in result.output
    assert calls == []


@pytest.mark.parametrize(
    "alternate",
    [
        "http://2130706433:8000/",
        "http://0x7f000001:8000/",
        "http://0177.0.0.1:8000/",
        "http://[::ffff:127.0.0.1]:8000/",
    ],
)
def test_http_alternate_loopback_forms_do_not_match_allowed_origin(tmp_path, alternate):
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(200, text="unexpected")

    session = _session(
        tmp_path,
        policy=_policy(battle_local_origins=("http://127.0.0.1:8000",)),
        handler=handler,
    )
    try:
        result = _request(session, alternate)
    finally:
        session.close()

    assert result.success is False
    assert result.policy_rejected is True
    assert calls == []


def test_http_dns_rebinding_to_a_new_address_is_rejected_before_transport(tmp_path):
    calls: list[str] = []
    resolver = SequencedResolver(
        "service.battle.test",
        ("10.0.0.20",),
        ("169.254.169.254",),
    )

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(200, text="unexpected")

    session = _session(
        tmp_path,
        policy=_policy(
            resolver=resolver,
            battle_local_origins=("http://service.battle.test:8000",),
        ),
        handler=handler,
    )
    try:
        result = _request(session, "http://service.battle.test:8000/")
    finally:
        session.close()

    assert result.success is False
    assert result.policy_rejected is True
    assert calls == []


def test_http_dns_is_revalidated_and_pinned_at_socket_connect_time():
    resolver = SequencedResolver(
        "service.battle.test",
        ("10.0.0.20",),  # trusted registration
        ("10.0.0.20",),  # request policy check
        ("169.254.169.254",),  # attempted rebind before connect
    )
    policy = _policy(
        resolver=resolver,
        battle_local_origins=("http://service.battle.test:8000",),
    )
    policy.validate_url("http://service.battle.test:8000/")

    class Recorder:
        calls: list[str] = []

        def connect_tcp(self, host, port, **kwargs):
            del port, kwargs
            self.calls.append(host)
            raise AssertionError("forbidden address reached the socket layer")

    backend = _PinnedNetworkBackend(policy)
    recorder = Recorder()
    backend._backend = recorder

    with pytest.raises(FighterNetworkPolicyError) as exc:
        backend.connect_tcp("service.battle.test", 8000)

    assert exc.value.code == "metadata_destination_blocked"
    assert recorder.calls == []


def test_http_response_body_is_bounded(tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(200, content=b"x" * (1024 * 1024 + 512))

    session = _session(
        tmp_path,
        policy=_policy(battle_local_origins=("http://127.0.0.1:8000",)),
        handler=handler,
    )
    try:
        result = _request(session, "http://127.0.0.1:8000/large")
    finally:
        session.close()

    assert result.success is True
    assert result.truncated is True
    assert len(result.output) < 4000


def test_http_pinned_transport_reaches_an_authorized_local_service(tmp_path):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            payload = b"authorized-local-service"
            self.send_response(200)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *args):
            del args

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    origin = f"http://127.0.0.1:{server.server_port}"
    policy = _policy(battle_local_origins=(origin,))
    session = ToolSession(tmp_path, network_policy=policy)
    try:
        result = _request(session, f"{origin}/health")
    finally:
        session.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert result.success is True
    assert "authorized-local-service" in result.output


class _FakeCursor:
    description = [SimpleNamespace(name="value")]

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, query: str) -> None:
        self.query = query

    def fetchall(self):
        return [(1,)]


class _FakeConnection:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def cursor(self):
        return _FakeCursor()


def test_sql_uses_only_battle_scoped_read_only_connection(tmp_path, monkeypatch):
    battle_url = "postgresql://battle_reader:pw@battle-db.test/battle"
    control_url = "postgresql://control_admin:pw@control-db.test/arena"
    calls: list[tuple[str, dict]] = []

    def connect(url: str, **kwargs):
        calls.append((url, kwargs))
        return _FakeConnection()

    monkeypatch.setenv("ARENA_HERMETIC", "0")
    monkeypatch.setenv("BATTLE_RO_DATABASE_URL", battle_url)
    monkeypatch.setenv("DATABASE_URL", control_url)
    monkeypatch.setitem(sys.modules, "psycopg", SimpleNamespace(connect=connect))

    session = ToolSession(tmp_path)
    try:
        result = session.exec_tool(
            {"tool": "sql_query", "query": "SELECT 1"}, count_step=False
        )
    finally:
        session.close()

    assert result.success is True
    assert calls and calls[0][0] == battle_url
    assert calls[0][0] != control_url
    assert "default_transaction_read_only=on" in calls[0][1]["options"]
    assert "search_path=app_public" in calls[0][1]["options"]


@pytest.mark.parametrize(
    "extra_env",
    [
        {},
        {"DATABASE_URL": "postgresql://control@control-db.test/arena"},
        {"DATABASE_URL_UNPOOLED": "postgresql://control@control-db.test/arena"},
        {"BATTLE_DATABASE_URL": "postgresql://battle-writer@battle-db.test/battle"},
    ],
)
def test_sql_missing_read_only_battle_credential_fails_closed(
    tmp_path, monkeypatch, extra_env
):
    monkeypatch.delenv("BATTLE_RO_DATABASE_URL", raising=False)
    for name in ("DATABASE_URL", "DATABASE_URL_UNPOOLED", "BATTLE_DATABASE_URL"):
        monkeypatch.delenv(name, raising=False)
    for name, value in extra_env.items():
        monkeypatch.setenv(name, value)

    session = ToolSession(tmp_path)
    try:
        result = session.exec_tool(
            {"tool": "sql_query", "query": "SELECT 1"}, count_step=False
        )
    finally:
        session.close()

    assert result.success is False
    assert result.error_type == "infrastructure_failure"
    assert result.policy_rejected is False
    assert "battle-scoped" in result.output.lower()
    assert "DATABASE_URL" not in result.output


def test_sql_missing_credential_is_infrastructure_failure_before_query_policy(
    tmp_path, monkeypatch
):
    monkeypatch.delenv("BATTLE_RO_DATABASE_URL", raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgresql://control@control-db.test/arena")

    session = ToolSession(tmp_path)
    try:
        result = session.exec_tool(
            {
                "tool": "sql_query",
                "query": "SELECT * FROM arena_trusted.evaluator_secrets",
            },
            count_step=False,
        )
    finally:
        session.close()

    assert result.success is False
    assert result.error_type == "infrastructure_failure"
    assert result.policy_rejected is False


@pytest.mark.parametrize(
    "alias",
    [
        "DATABASE_URL",
        "DATABASE_URL_UNPOOLED",
        "POSTGRES_URL",
        "SQLALCHEMY_DATABASE_URI",
    ],
)
def test_sql_rejects_battle_credential_that_aliases_other_database_authority(
    tmp_path, monkeypatch, alias
):
    shared_url = "postgresql://control-admin@control-db.test/arena"
    monkeypatch.setenv("BATTLE_RO_DATABASE_URL", shared_url)
    monkeypatch.setenv(alias, shared_url)

    session = ToolSession(tmp_path)
    try:
        result = session.exec_tool(
            {"tool": "sql_query", "query": "SELECT 1"}, count_step=False
        )
    finally:
        session.close()

    assert result.success is False
    assert result.error_type == "infrastructure_failure"
    assert result.metadata["reason"] == "battle_database_authority_collision"
    assert shared_url not in result.output


def test_sql_explicit_battle_mock_credential_remains_hermetic(tmp_path, monkeypatch):
    monkeypatch.setenv("ARENA_HERMETIC", "1")
    monkeypatch.setenv(
        "BATTLE_RO_DATABASE_URL",
        "postgresql://mock_reader:mock@battle.mock.invalid/battle",
    )

    session = ToolSession(tmp_path)
    try:
        result = session.exec_tool(
            {"tool": "sql_query", "query": "SELECT 1"}, count_step=False
        )
    finally:
        session.close()

    assert result.success is True
    assert "mock" in result.output.lower()


def test_fighter_child_environment_strips_all_database_authority_aliases():
    env = {
        "PATH": "/usr/bin",
        "DATABASE_URL": "control-pooled",
        "DATABASE_URL_UNPOOLED": "control-direct",
        "BATTLE_DATABASE_URL": "battle-writer",
        "BATTLE_RO_DATABASE_URL": "battle-reader",
        "BATTLE_TOKEN": "battle-token",
        "PGHOST": "control-db.internal",
        "PGPASSWORD": "control-password",
        "PGUSER": "control-admin",
        "NEON_DATABASE_URL": "neon-control",
        "POSTGRES_URL": "postgres-control",
        "SQLALCHEMY_DATABASE_URI": "sqlalchemy-control",
    }

    stripped = _strip_secret_env(env)

    assert stripped == {"PATH": "/usr/bin"}
