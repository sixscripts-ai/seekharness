"""Tests for sandbox egress guard (defense-in-depth against SSRF/metadata)."""

import pytest

from agent_arena.sandbox.client import _assert_egress_allowed


@pytest.mark.parametrize(
    "url",
    [
        "https://sixscripts--agent-arena-backend-fastapi-app.modal.run/internal/model",
        "https://api.openai.com/v1/chat/completions",
        "https://openrouter.ai/api/v1",
    ],
)
def test_egress_allows_public(url):
    _assert_egress_allowed(url)  # must not raise


@pytest.mark.parametrize(
    "url",
    [
        "http://169.254.169.254/latest/meta-data",  # cloud metadata
        "http://127.0.0.1:8000/internal/model",  # loopback
        "http://10.0.0.5",  # RFC1918
        "http://192.168.1.1:8000",  # RFC1918
        "http://[::1]:9000",  # IPv6 loopback
        "ftp://example.com",  # non-http scheme
    ],
)
def test_egress_blocks_private_or_non_http(url):
    with pytest.raises(RuntimeError):
        _assert_egress_allowed(url)
