"""Target Catalog API Router: exposes public metadata for installed targets.

Endpoints:
- GET /targets: list all available target bundles with public metadata.
- GET /targets/{target_id}: detailed brief, public file tree, and objectives.

Enforces zero leakage of hidden tests, reference solutions, or host paths.
"""

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from .formats import get_optional_user
from .schemas import TargetDetailOut, TargetSummaryOut
from .target_library import TargetBundle, get_target_library

router = APIRouter(prefix="/targets", tags=["targets"])


def _to_summary(bundle: TargetBundle) -> TargetSummaryOut:
    return TargetSummaryOut(
        id=bundle.id,
        name=bundle.name,
        description=bundle.description,
        category=bundle.category,
        difficulty=bundle.difficulty,
        format=bundle.format,
        runtime=bundle.runtime,
        tags=bundle.tags,
        version=bundle.version,
        visible_test_count=len(bundle.visible_test_files),
        hidden_test_count=len(bundle.hidden_test_files),
        handoff_required=bool(bundle.workspace.handoff_allowlist),
        verification_type=(
            "visible+hidden"
            if (bundle.verification.visible_command and bundle.verification.hidden_command)
            else ("hidden_only" if bundle.verification.hidden_command else "visible_only")
        ),
        network=bundle.network,
        manifest_hash=bundle.manifest_hash,
    )


def _to_detail(bundle: TargetBundle, *, authenticated: bool) -> TargetDetailOut:
    summary = _to_summary(bundle)
    if not authenticated:
        # Public brief only: evaluator-internal metadata (file trees, protected
        # paths, limits, safety) stays behind the auth gate.
        return TargetDetailOut(
            **summary.model_dump(),
            objectives=bundle.objectives,
            role_objectives=bundle.role_objectives or None,
        )
    return TargetDetailOut(
        **summary.model_dump(),
        objectives=bundle.objectives,
        role_objectives=bundle.role_objectives or None,
        starter_files=sorted(bundle.starter_files.keys()),
        visible_tests=sorted(bundle.visible_test_files.keys()),
        protected_paths=bundle.workspace.protected_paths,
        handoff_allowlist=bundle.workspace.handoff_allowlist,
        limits={
            "max_tool_steps": bundle.limits.max_tool_steps,
            "exec_timeout_seconds": bundle.limits.exec_timeout_seconds,
        },
        safety={
            "scope": bundle.safety.scope,
            "real_targets": bundle.safety.real_targets,
            "network_required": bundle.safety.network_required,
        },
    )


@router.get("", response_model=List[TargetSummaryOut])
def list_targets(
    category: Optional[str] = Query(default=None, description="Filter by category"),
    difficulty: Optional[str] = Query(default=None, description="Filter by difficulty"),
    format: Optional[str] = Query(default=None, description="Filter by battle format"),
    tag: Optional[str] = Query(default=None, description="Filter by tag"),
    _user_id: Optional[str] = Depends(get_optional_user),
) -> List[TargetSummaryOut]:
    registry = get_target_library()
    bundles = registry.list_targets()

    if category:
        bundles = [b for b in bundles if b.category.lower() == category.lower()]
    if difficulty:
        bundles = [b for b in bundles if b.difficulty.lower() == difficulty.lower()]
    if format:
        bundles = [b for b in bundles if b.format.lower() == format.lower()]
    if tag:
        tag_lower = tag.lower()
        bundles = [b for b in bundles if any(t.lower() == tag_lower for t in b.tags)]

    return [_to_summary(b) for b in bundles]


@router.get("/{target_id}", response_model=TargetDetailOut)
def get_target(
    target_id: str,
    user_id: Optional[str] = Depends(get_optional_user),
) -> TargetDetailOut:
    registry = get_target_library()
    bundle = registry.get_target(target_id)
    if bundle is None:
        raise HTTPException(status_code=404, detail=f"Target '{target_id}' not found")
    return _to_detail(bundle, authenticated=user_id is not None)
