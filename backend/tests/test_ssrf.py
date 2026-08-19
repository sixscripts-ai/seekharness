"""Tests for outbound SSRF protection."""

import pytest
from fastapi import HTTPException

from agent_arena.ssrf import validate_base_url


@pytest.mark.parametrize(
    "url",
    [
        "https://api.openai.com/v1",
        "https://openrouter.ai/api/v1",
        "https://example.invalid/v1",
        "https://api.example.com/v1",
        "https://opencode.ai/zen/go/v1",
    ],
)
def test_validate_accepts_public_https(url):
    assert validate_base_url(url).startswith("https://")


@pytest.mark.parametrize(
    "url",
    [
        "http://169.254.169.254/latest/meta-data",  # cloud metadata
        "http://127.0.0.1:8000",  # loopback
        "http://localhost:8000",  # loopback by name
        "http://10.0.0.5",  # RFC1918
        "http://192.168.1.1",  # RFC1918
        "http://172.16.0.1",  # RFC1918
        "http://[::1]:8000",  # IPv6 loopback
        "http://0.0.0.0",  # unspecified
        "ftp://example.com",  # non-http scheme
        "http://",  # no host
        "not-a-url",
        "http://user:pass@example.com",  # embedded creds
    ],
)
def test_validate_rejects_private_or_invalid(url):
    with pytest.raises(HTTPException) as exc:
        validate_base_url(url)
    assert exc.value.status_code == 400


def test_validate_strips_trailing_slash():
    assert validate_base_url("https://api.openai.com/v1/") == "https://api.openai.com/v1"
