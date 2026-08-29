from typing import Any, Literal

from pydantic import BaseModel, Field


class ProviderCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    base_url: str = Field(min_length=1)
    api_key: str = Field(min_length=1)
    auth_style: str = Field(default="bearer", pattern="^(bearer|modal_proxy|custom)$")
    model_name: str = Field(min_length=1, max_length=100)


class ProviderOut(BaseModel):
    id: str
    name: str
    base_url: str
    masked_key: str
    auth_style: str
    model_name: str


class ProviderHealth(BaseModel):
    base_url: str = Field(min_length=1)
    api_key: str = Field(min_length=1)
    auth_style: str = Field(default="bearer", pattern="^(bearer|modal_proxy|custom)$")
    model: str | None = None
    model_name: str | None = None


class BattleCreate(BaseModel):
    format_id: str = Field(min_length=1)
    model_ids: list[str] = Field(min_length=1, max_length=6)
    arena_size: int = Field(default=2, ge=1, le=6)
    timeout_seconds: int = Field(default=600, ge=30, le=3600)
    round_visibility: str = Field(default="isolated", pattern="^(isolated|open)$")
    save: bool = False
    judge_provider_id: str | None = None
    difficulty: Literal["novice", "general", "advanced", "expert"] | None = None
    target_id: str | None = None
    target_version: str | None = None


class TargetSummaryOut(BaseModel):
    id: str
    name: str
    description: str
    category: str
    difficulty: str
    format: str
    runtime: str
    tags: list[str]
    version: str
    visible_test_count: int
    hidden_test_count: int
    handoff_required: bool
    verification_type: str
    network: bool
    manifest_hash: str


class TargetDetailOut(TargetSummaryOut):
    # objectives is public; the remaining evaluator-internal fields are only
    # populated for authenticated callers (see target_router.get_target).
    objectives: list[str]
    starter_files: list[str] | None = None
    visible_tests: list[str] | None = None
    protected_paths: list[str] | None = None
    handoff_allowlist: list[str] | None = None
    limits: dict[str, int] | None = None
    safety: dict[str, Any] | None = None


class BattleDraftCreate(BaseModel):
    mode: Literal["quick", "verified"]
    architect_provider_id: str | None = None


class BattleDraftMessage(BaseModel):
    content: str = Field(min_length=1, max_length=8000)
    architect_provider_id: str | None = None


class BattleDraftSpecPatch(BaseModel):
    title: str | None = Field(default=None, max_length=120)
    brief: str | None = None
    deliverables: list[str] | None = None
    constraints: list[str] | None = None
    required_artifacts: list[str] | None = None
    judge_rubric: str | None = None
    starter_files: dict[str, str] | None = None
    test_code: str | None = None
    languages: list[str] | None = None


class BattleDraftLaunch(BaseModel):
    revision: int = Field(ge=0)
    model_ids: list[str] = Field(min_length=2, max_length=6)
    timeout_seconds: int = Field(default=600, ge=30, le=3600)
    save: bool = False
    judge_provider_id: str | None = None
