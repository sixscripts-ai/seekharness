"""Focused containment tests for the secretless Fighter process runtime."""

from __future__ import annotations

import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

import agent_arena.sandbox.executors.advanced_executor as advanced_executor
from agent_arena.sandbox.executors.advanced_executor import ToolSession
from agent_arena.sandbox.fighter_runtime import FighterRuntimeUnavailable


class _RecordingHandler(BaseHTTPRequestHandler):
    hits: list[str] = []

    def do_GET(self) -> None:
        type(self).hits.append(self.path)
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"unexpected-network-success")

    def log_message(self, *_args) -> None:
        pass


def _listener():
    _RecordingHandler.hits = []
    server = ThreadingHTTPServer(("127.0.0.1", 0), _RecordingHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def _close_listener(server, thread) -> None:
    server.shutdown()
    server.server_close()
    thread.join(timeout=2)


def _probe_code(port: int) -> str:
    return (
        "import socket; "
        f"s=socket.create_connection(('127.0.0.1', {port}), timeout=2); "
        "s.sendall(b'GET /raw HTTP/1.0\\r\\n\\r\\n'); "
        "print(s.recv(32))"
    )


@pytest.mark.parametrize("allow_network", [False, True])
def test_raw_run_network_cannot_reach_trusted_local_listener(tmp_path, allow_network):
    server, thread = _listener()
    session = ToolSession(tmp_path / "fighter", allow_network=allow_network)
    try:
        result = session.run(inline=_probe_code(server.server_port))
    finally:
        session.close()
        _close_listener(server, thread)

    assert result.success is False
    assert _RecordingHandler.hits == []


def test_shell_and_descendant_share_raw_network_containment(tmp_path):
    server, thread = _listener()
    work = tmp_path / "fighter"
    session = ToolSession(work, allow_network=False)
    try:
        session.write("probe.py", _probe_code(server.server_port))
        shell = session.shell("python3 probe.py")
        descendant = session.run(
            inline=(
                "import subprocess, sys; "
                "raise SystemExit(subprocess.run([sys.executable, 'probe.py']).returncode)"
            )
        )
    finally:
        session.close()
        _close_listener(server, thread)

    assert shell.success is False
    assert descendant.success is False
    assert _RecordingHandler.hits == []


def test_background_processes_are_contained_and_terminated_with_phase(tmp_path):
    server, thread = _listener()
    work = tmp_path / "fighter"
    session = ToolSession(work, allow_network=False)
    try:
        session.write("probe.py", _probe_code(server.server_port))
        started = session.bg("raw-probe", "python3 probe.py")
        assert started.success is True
        deadline = time.time() + 2
        logs = ""
        while time.time() < deadline:
            logs = session.logs("raw-probe").output
            if "Permission" in logs or "Operation not permitted" in logs:
                break
            time.sleep(0.05)
        assert _RecordingHandler.hits == []

        session.bg("late-writer", "sleep 0.5; printf escaped > late.txt")
    finally:
        session.close()
        _close_listener(server, thread)

    time.sleep(0.8)
    assert not (work / "late.txt").exists()

    breaker = ToolSession(work, allow_network=False)
    try:
        assert breaker.run(inline="print('breaker-runtime')").success is True
    finally:
        breaker.close()


def test_fighter_runtime_has_no_trusted_credentials_or_proxy_environment(
    tmp_path, monkeypatch
):
    secrets = {
        "DATABASE_URL": "postgresql://control-plane/arena",
        "BATTLE_RO_DATABASE_URL": "postgresql://battle-reader/battle",
        "OPENAI_API_KEY": "provider-secret",
        "MODAL_TOKEN_ID": "modal-id",
        "MODAL_TOKEN_SECRET": "modal-secret",
        "INTERNAL_API_KEY": "internal-secret",
        "BATTLE_TOKEN": "battle-token",
        "HTTP_PROXY": "http://trusted-proxy.invalid:8080",
        "HTTPS_PROXY": "http://trusted-proxy.invalid:8080",
        "ALL_PROXY": "http://trusted-proxy.invalid:8080",
    }
    for name, value in secrets.items():
        monkeypatch.setenv(name, value)

    session = ToolSession(tmp_path / "fighter")
    try:
        result = session.run(
            inline=(
                "import os; "
                "print('|'.join(os.environ.get(k, 'absent') for k in "
                "['DATABASE_URL','BATTLE_RO_DATABASE_URL','OPENAI_API_KEY',"
                "'MODAL_TOKEN_ID','MODAL_TOKEN_SECRET','INTERNAL_API_KEY',"
                "'BATTLE_TOKEN','HTTP_PROXY','HTTPS_PROXY','ALL_PROXY']))"
            )
        )
    finally:
        session.close()

    assert result.success is True
    assert "absent|absent|absent|absent|absent|absent|absent|absent|absent|absent" in result.output
    assert not any(value in result.output for value in secrets.values())


def test_unavailable_runtime_fails_closed_without_host_process_fallback(
    tmp_path, monkeypatch
):
    def unavailable(_self) -> None:
        raise FighterRuntimeUnavailable("test containment runtime unavailable")

    monkeypatch.setattr(advanced_executor.FighterRuntimeClient, "start", unavailable)
    session = ToolSession(tmp_path / "fighter")
    try:
        result = session.run(inline="print('must-not-run')")
    finally:
        session.close()

    assert result.success is False
    assert result.error_type == "infrastructure_failure"
    assert "must-not-run" not in result.output


def test_runtime_preserves_run_shell_and_background_tool_semantics(tmp_path):
    session = ToolSession(tmp_path / "fighter", tool_timeout=2)
    try:
        run = session.run(inline="import sys; print('out'); print('err', file=sys.stderr)")
        shell = session.shell("printf shell-ok")
        started = session.bg("echoer", "echo bg-ok; sleep 30")
        deadline = time.time() + 2
        logs = ""
        while time.time() < deadline:
            logs = session.logs("echoer").output
            if "bg-ok" in logs:
                break
            time.sleep(0.05)
        killed = session.kill("echoer")
    finally:
        session.close()

    assert run.success is True
    assert "STDOUT:\nout" in run.output
    assert "STDERR:\nerr" in run.output
    assert "rc=0" in run.output
    assert shell.success is True
    assert "shell-ok" in shell.output
    assert started.success is True
    assert "bg-ok" in logs
    assert killed.success is True
