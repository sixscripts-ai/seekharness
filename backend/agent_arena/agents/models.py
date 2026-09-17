"""Typed specifications and configuration models for SeekHarness Agents.

Defines the structure for all canonical agents (Builder, Breaker, Fighter,
Judge, Reviewer) and specialists operating on top of SeekHarness runtime.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any, Literal
from pydantic import BaseModel, Field

AgentRole = Literal["builder", "breaker", "fighter", "judge", "reviewer", "specialist"]


class ModelPreference(BaseModel):
    """Model selection and inference parameters for an agent."""

    preferred: str = Field(
        ...,
        description="Primary arena_model_id (e.g. host:or-qwen3-coder, host:deepseek-chat)",
    )
    fallback: str | None = Field(
        default=None,
        description="Secondary fallback arena_model_id if primary encounters rate limits",
    )
    temperature: float = Field(
        default=0.1, ge=0.0, le=2.0, description="Sampling temperature"
    )
    max_tokens: int = Field(
        default=4096, ge=256, le=16384, description="Maximum token generation limit"
    )
    reasoning_effort: str | None = Field(
        default=None, description="Reasoning effort if supported (off, high, max)"
    )


class ToolPermissions(BaseModel):
    """Tool permissions and access control for an agent."""

    allowed_tools: list[str] | None = Field(
        default=None,
        description=(
            "Explicit whitelist of tool names this agent may call. ``None`` leaves "
            "the runtime policy unchanged; an empty list denies every runtime tool."
        ),
    )
    denied_tools: list[str] = Field(
        default_factory=list,
        description="Explicit blacklist of tool names rejected at dispatch",
    )

    def is_allowed(self, tool_name: str) -> bool:
        norm = str(tool_name or "").strip().lower()
        denied = {str(item).strip().lower() for item in self.denied_tools}
        if norm in denied:
            return False
        if self.allowed_tools is None:
            return True
        return norm in {
            str(item).strip().lower() for item in self.allowed_tools
        }

    def resolved_allowed_tools(self, available_tools: Iterable[str]) -> set[str]:
        """Resolve this declarative policy against one runtime's tool registry.

        The configuration layer never executes tools itself.  The executor calls
        this method once, then uses the result both to expose schemas and to
        enforce dispatch.  Unknown configured names are deliberately ignored:
        they cannot manufacture a tool capability.
        """
        available = {
            str(item).strip().lower()
            for item in available_tools
            if str(item).strip()
        }
        denied = {
            str(item).strip().lower()
            for item in self.denied_tools
            if str(item).strip()
        }
        if self.allowed_tools is None:
            return available - denied
        allowed = {
            str(item).strip().lower()
            for item in self.allowed_tools
            if str(item).strip()
        }
        return (available & allowed) - denied


class AgentBudgets(BaseModel):
    """Resource, step, and turn budgets allocated to the agent."""

    max_turns: int = Field(default=10, ge=1, le=100, description="Maximum model turns")
    max_steps: int = Field(
        default=24, ge=1, le=200, description="Maximum tool execution steps"
    )
    tool_timeout_seconds: int = Field(
        default=120, ge=5, le=1200, description="Per-tool execution timeout in seconds"
    )
    total_timeout_seconds: int = Field(
        default=600, ge=30, le=3600, description="Total phase timeout in seconds"
    )


class EvidenceContract(BaseModel):
    """Expectations for evidence production before an agent may finalize or emit DONE."""

    required_artifacts: list[str] = Field(
        default_factory=list,
        description="Artifact filenames that must exist in the workspace root",
    )
    require_test_pass: bool = Field(
        default=True,
        description="Whether a successful TOOL test execution is required before DONE",
    )
    stopping_condition: str = Field(
        default="All tests pass and required artifacts are written",
        description="Human-readable description of valid completion state",
    )


class AgentConfig(BaseModel):
    """Declarative specification for a SeekHarness agent."""

    agent_id: str = Field(
        ...,
        pattern=r"^[a-z0-9][a-z0-9-]*$",
        description="Unique identifier (e.g. builder-v1, breaker-v1)",
    )
    name: str = Field(
        ..., min_length=1, max_length=120, description="Human-readable display name"
    )
    role: AgentRole = Field(
        ..., description="Canonical arena role: builder, breaker, fighter, judge, reviewer"
    )
    version: str = Field(default="1.0.0", description="Semver version string")
    description: str = Field(
        ..., min_length=1, description="Purpose, operational domain, and role summary"
    )

    # Core Intelligence & Behavioral Persona
    system_prompt: str = Field(
        ..., min_length=10, description="Base identity, role context, and instructions"
    )
    behavioral_instructions: list[str] = Field(
        default_factory=list,
        description="Specific behavioral rules (e.g. root-cause-first, minimal changes)",
    )
    anti_patterns: list[str] = Field(
        default_factory=list,
        description="Behaviors to explicitly avoid (e.g. infinite planning, fake assertions)",
    )

    # Capabilities & Constraints
    model: ModelPreference
    skill_bundle: list[str] = Field(
        default_factory=list,
        description="Curated skill names from arena-fighter-skills mounted for this agent",
    )
    tool_permissions: ToolPermissions = Field(default_factory=ToolPermissions)
    budgets: AgentBudgets = Field(default_factory=AgentBudgets)
    evidence_contract: EvidenceContract = Field(default_factory=EvidenceContract)

    # Network & Storage
    network_required: bool = Field(
        default=False,
        description="Whether this agent requires network egress (subject to Target policy)",
    )
    context_strategy: Literal["strict", "adaptive", "assisted"] = Field(
        default="strict",
        description="Memory context retrieval strategy (strict=no memory, adaptive=retrieve prior lessons)",
    )
