from typing import Literal

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
    model_ids: list[str] = Field(min_length=2, max_length=6)
    arena_size: int = Field(default=2, ge=2, le=6)
    timeout_seconds: int = Field(default=600, ge=30, le=3600)
    round_visibility: str = Field(default="isolated", pattern="^(isolated|open)$")
    save: bool = False
    judge_provider_id: str | None = None
    difficulty: Literal["novice", "general", "advanced", "expert"] | None = None
