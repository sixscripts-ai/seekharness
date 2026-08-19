"""Tests for per-battle sandbox token issuance and verification."""

import pytest

from agent_arena.battle_token import issue_battle_token, verify_battle_token


@pytest.fixture
def signed_key(monkeypatch):
    monkeypatch.setenv("INTERNAL_API_KEY", "test-signing-secret")
    from agent_arena.config import settings

    settings.cache_clear()
    yield
    settings.cache_clear()


def test_token_roundtrip_for_matching_battle(signed_key):
    token = issue_battle_token("battle-123")
    assert verify_battle_token(token, "battle-123") is True


def test_token_rejected_for_other_battle(signed_key):
    token = issue_battle_token("battle-123")
    assert verify_battle_token(token, "battle-999") is False


def test_token_rejected_for_tampered_battle(signed_key):
    token = issue_battle_token("battle-123")
    # Same length, different battle id — signature must not match.
    tampered = issue_battle_token("battle-999")
    assert verify_battle_token(tampered, "battle-123") is False


def test_token_expiry(signed_key):
    token = issue_battle_token("battle-123", ttl=-1)
    assert verify_battle_token(token, "battle-123") is False


def test_empty_or_garbage_token_rejected(signed_key):
    assert verify_battle_token("", "battle-123") is False
    assert verify_battle_token("not-a-token", "battle-123") is False
    assert verify_battle_token(None, "battle-123") is False
