"""Neon Ephemeral Database Branch Manager for Full-Stack Arena Battles.

Provides point-in-time branch provisioning, exploit snapshotting, and rollbacks
via the Neon Management API v2.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from typing import Any, Dict, Optional

try:
    import httpx
except ImportError:  # pragma: no cover
    httpx = None

logger = logging.getLogger("agent_arena.neon_branch_manager")

NEON_API_BASE = "https://console.neon.tech/api/v2"


def _extract_project_id_from_url(database_url: str) -> Optional[str]:
    """Extract project/endpoint identifier from a Neon connection string."""
    if not database_url:
        return None
    match = re.search(r"ep-([a-z0-9-]+)\.([a-z0-9-]+)\.aws\.neon\.tech", database_url)
    if match:
        raw_id = match.group(1)
        if raw_id.endswith("-pooler"):
            raw_id = raw_id[:-7]
        return f"ep-{raw_id}"
    return None


class NeonProvisioningError(RuntimeError):
    """Raised when isolated Neon branch creation fails.

    Under the Arena security contract, battle provisioning MUST fail closed;
    it must never fall back to the control-plane database URL.
    """


@dataclass
class BranchResult:
    branch_id: str
    name: str
    database_url: str
    read_only_database_url: str
    parent_id: str
    is_mock: bool = False


class NeonBranchManager:
    """Manages ephemeral PostgreSQL branches for isolated battle executions."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        project_id: Optional[str] = None,
        base_url: Optional[str] = None,
    ) -> None:
        # Separate battle Neon credentials from SeekHarness control-plane
        self.api_key = (
            api_key
            or os.environ.get("BATTLE_NEON_API_KEY")
            or os.environ.get("NEON_API_KEY", "")
        )
        self.project_id = (
            project_id
            or os.environ.get("BATTLE_NEON_PROJECT_ID")
            or os.environ.get("NEON_PROJECT_ID")
            or _extract_project_id_from_url(os.environ.get("BATTLE_DATABASE_URL", ""))
            or "ep-silent-fog-a60c8fb5"
        )
        self.base_url = base_url or os.environ.get("NEON_API_BASE", NEON_API_BASE)
        self.use_mock = (
            not self.api_key
            or os.environ.get("ARENA_HERMETIC") == "1"
            or os.environ.get("ARENA_USE_MOCK", "0").lower() in ("1", "true")
        )

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def create_ephemeral_branch(
        self,
        battle_id: str,
        parent_branch_id: str = "main",
        ttl: str = "1d",
    ) -> BranchResult:
        clean_id = battle_id.removeprefix("battle-")
        branch_name = f"battle-{clean_id[:16]}"
        if self.use_mock or not httpx:
            mock_rw = f"postgresql://mock_user:mock_pass@ep-{branch_name}.mock.neon.tech/neondb?sslmode=require"
            mock_ro = f"postgresql://mock_ro:mock_pass@ep-{branch_name}.mock.neon.tech/neondb?sslmode=require&options=-cdefault_transaction_read_only%3Don"
            return BranchResult(
                branch_id=f"br-{branch_name}",
                name=branch_name,
                database_url=mock_rw,
                read_only_database_url=mock_ro,
                parent_id=parent_branch_id,
                is_mock=True,
            )

        url = f"{self.base_url}/projects/{self.project_id}/branches"
        payload = {
            "branch": {
                "name": branch_name,
                "parent_id": parent_branch_id,
            },
            "endpoints": [
                {
                    "type": "read_write",
                    "autoscaling_limit_min_cu": 0.25,
                    "autoscaling_limit_max_cu": 1.0,
                }
            ],
        }

        try:
            with httpx.Client(timeout=30.0) as client:
                res = client.post(url, headers=self._headers(), json=payload)
                if res.status_code not in (200, 201):
                    logger.error(
                        "Neon API branch creation failed (%s): %s",
                        res.status_code,
                        res.text,
                    )
                    # FAIL CLOSED: Never fall back to control-plane DATABASE_URL
                    raise NeonProvisioningError(
                        f"ARENA_INFRA_FAILURE: Neon branch creation failed ({res.status_code}): {res.text}"
                    )

                data = res.json()
                branch_info = data.get("branch", {})
                branch_id = branch_info.get("id", f"br-{branch_name}")
                endpoints = data.get("endpoints", [])
                host = (
                    endpoints[0].get("host")
                    if endpoints
                    else f"{branch_name}.aws.neon.tech"
                )

                rw_url = f"postgresql://neondb_owner@{host}/neondb?sslmode=require"
                ro_url = f"postgresql://neondb_owner@{host}/neondb?sslmode=require&options=-cdefault_transaction_read_only%3Don"

                return BranchResult(
                    branch_id=branch_id,
                    name=branch_name,
                    database_url=rw_url,
                    read_only_database_url=ro_url,
                    parent_id=parent_branch_id,
                    is_mock=False,
                )
        except NeonProvisioningError:
            raise
        except Exception as exc:
            logger.error("Exception creating Neon ephemeral branch: %s", exc)
            # FAIL CLOSED: Never fall back to control-plane DATABASE_URL
            raise NeonProvisioningError(
                f"ARENA_INFRA_FAILURE: Exception communicating with Neon API: {exc}"
            ) from exc

    def create_builder_baseline_snapshot(
        self,
        battle_id: str,
        source_branch_id: str,
    ) -> Dict[str, Any]:
        """Capture the exact state of the database immediately after Builder completes.

        Used as the authoritative baseline: unauthorized mutation = breaker_final_state vs builder_baseline_snapshot.
        """
        clean_id = battle_id.removeprefix("battle-")
        snapshot_name = f"builder-baseline-{clean_id[:16]}"
        if self.use_mock or not httpx:
            return {
                "snapshot_id": f"br-{snapshot_name}",
                "name": snapshot_name,
                "status": "frozen",
                "source_branch_id": source_branch_id,
                "is_mock": True,
            }

        url = f"{self.base_url}/projects/{self.project_id}/branches"
        payload = {
            "branch": {
                "name": snapshot_name,
                "parent_id": source_branch_id,
            }
        }
        try:
            with httpx.Client(timeout=30.0) as client:
                res = client.post(url, headers=self._headers(), json=payload)
                if res.status_code in (200, 201):
                    data = res.json().get("branch", {})
                    return {
                        "snapshot_id": data.get("id", f"br-{snapshot_name}"),
                        "name": snapshot_name,
                        "status": "frozen",
                        "source_branch_id": source_branch_id,
                        "is_mock": False,
                    }
                logger.warning("Failed to create builder baseline snapshot in Neon: %s", res.text)
        except Exception as exc:
            logger.error("Exception creating Neon builder baseline snapshot: %s", exc)

        return {
            "snapshot_id": f"br-{snapshot_name}",
            "name": snapshot_name,
            "status": "simulated",
            "source_branch_id": source_branch_id,
            "is_mock": False,
        }

    def create_exploit_snapshot(
        self,
        battle_id: str,
        source_branch_id: str,
    ) -> Dict[str, Any]:
        clean_id = battle_id.removeprefix("battle-")
        snapshot_name = f"exploit-snapshot-{clean_id[:16]}"
        if self.use_mock or not httpx:
            return {
                "snapshot_id": f"br-{snapshot_name}",
                "name": snapshot_name,
                "status": "frozen",
                "is_mock": True,
            }

        url = f"{self.base_url}/projects/{self.project_id}/branches"
        payload = {
            "branch": {
                "name": snapshot_name,
                "parent_id": source_branch_id,
            }
        }
        try:
            with httpx.Client(timeout=30.0) as client:
                res = client.post(url, headers=self._headers(), json=payload)
                if res.status_code in (200, 201):
                    return res.json().get("branch", {"name": snapshot_name, "id": f"br-{snapshot_name}"})
                logger.warning("Failed to create exploit snapshot in Neon: %s", res.text)
        except Exception as exc:
            logger.error("Exception creating Neon snapshot: %s", exc)

        return {"name": snapshot_name, "id": f"br-{snapshot_name}", "status": "simulated"}

    def rollback_branch(
        self,
        battle_id: str,
        branch_id: str,
        parent_branch_id: str = "main",
    ) -> bool:
        """Reset a branch back to clean state after destructive testing."""
        if self.use_mock or not httpx:
            return True

        self.delete_branch(branch_id)
        # Re-provision clean branch
        self.create_ephemeral_branch(battle_id, parent_branch_id)
        return True

    def delete_branch(self, branch_id: str) -> bool:
        """Teardown branch upon battle cleanup."""
        if self.use_mock or not httpx:
            return True

        url = f"{self.base_url}/projects/{self.project_id}/branches/{branch_id}"
        try:
            with httpx.Client(timeout=15.0) as client:
                res = client.delete(url, headers=self._headers())
                return res.status_code in (200, 204)
        except Exception as exc:
            logger.warning("Error deleting branch %s: %s", branch_id, exc)
            return False


