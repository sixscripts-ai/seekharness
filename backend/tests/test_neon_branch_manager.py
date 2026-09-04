from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

from agent_arena.neon_branch_manager import (
    NeonBranchManager,
    BranchResult,
    NeonProvisioningError,
    _extract_project_id_from_url,
)


def test_extract_project_id_from_url():
    url = "postgresql://user:pass@ep-silent-fog-a60c8fb5-pooler.us-west-2.aws.neon.tech/neondb"
    assert _extract_project_id_from_url(url) == "ep-silent-fog-a60c8fb5"
    assert _extract_project_id_from_url("") is None


def test_neon_branch_manager_hermetic_mock(monkeypatch):
    monkeypatch.setenv("ARENA_HERMETIC", "1")
    mgr = NeonBranchManager(api_key="", project_id="ep-test-123")
    assert mgr.use_mock is True

    res = mgr.create_ephemeral_branch("battle-xyz-123456")
    assert isinstance(res, BranchResult)
    assert res.is_mock is True
    assert res.name == "battle-xyz-123456"
    assert "default_transaction_read_only" in res.read_only_database_url

    # Builder baseline snapshot test
    baseline = mgr.create_builder_baseline_snapshot("battle-xyz-123456", res.branch_id)
    assert baseline["is_mock"] is True
    assert baseline["name"] == "builder-baseline-xyz-123456"
    assert baseline["status"] == "frozen"

    snap = mgr.create_exploit_snapshot("battle-xyz-123456", res.branch_id)
    assert snap["is_mock"] is True
    assert snap["name"] == "exploit-snapshot-xyz-123456"

    rb = mgr.rollback_branch("battle-xyz-123456", res.branch_id)
    assert rb is True

    del_res = mgr.delete_branch(res.branch_id)
    assert del_res is True


def test_neon_branch_manager_api_call(monkeypatch):
    mgr = NeonBranchManager(api_key="neon_sec_test", project_id="ep-project-999")
    mgr.use_mock = False

    fake_resp = MagicMock()
    fake_resp.status_code = 201
    fake_resp.json.return_value = {
        "branch": {"id": "br-real-123", "name": "battle-test-123"},
        "endpoints": [{"host": "ep-real-123.aws.neon.tech"}],
    }

    with patch("httpx.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_client.post.return_value = fake_resp
        mock_client_cls.return_value = mock_client

        res = mgr.create_ephemeral_branch("test-123")
        assert res.branch_id == "br-real-123"
        assert res.is_mock is False
        assert "ep-real-123.aws.neon.tech" in res.database_url
        assert "default_transaction_read_only" in res.read_only_database_url


def test_neon_branch_manager_fails_closed_without_falling_back_to_database_url(monkeypatch):
    """Verify that if Neon API fails, the manager fails closed with NeonProvisioningError

    and NEVER exposes or falls back to the control-plane DATABASE_URL.
    """
    control_db = "postgresql://control_admin:secret_password@control-plane.neon.tech/control_db"
    monkeypatch.setenv("DATABASE_URL", control_db)
    mgr = NeonBranchManager(api_key="neon_sec_test", project_id="ep-project-999")
    mgr.use_mock = False

    fake_resp = MagicMock()
    fake_resp.status_code = 500
    fake_resp.text = "Internal Server Error"

    with patch("httpx.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_client.post.return_value = fake_resp
        mock_client_cls.return_value = mock_client

        with pytest.raises(NeonProvisioningError) as exc_info:
            mgr.create_ephemeral_branch("test-fail-closed")

        assert "ARENA_INFRA_FAILURE" in str(exc_info.value)
        assert control_db not in str(exc_info.value)

