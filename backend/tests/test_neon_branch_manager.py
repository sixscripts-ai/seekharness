from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

from agent_arena.neon_branch_manager import NeonBranchManager, BranchResult, _extract_project_id_from_url


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
