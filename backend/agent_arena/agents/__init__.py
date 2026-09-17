"""SeekHarness Agent Ecosystem.

Provides structured definitions, registry lookups, and lifecycle contracts
for Builder, Breaker, Fighter, Judge, and Reviewer agents.
"""

from .models import (
    AgentConfig,
    AgentRole,
    ModelPreference,
    ToolPermissions,
    AgentBudgets,
    EvidenceContract,
)
from .registry import (
    BUILDER_V1,
    BREAKER_V1,
    FIGHTER_V1,
    JUDGE_V1,
    REVIEWER_V1,
    BUILDER_FASTAPI,
    BUILDER_SECURITY_HARDENING,
    BUILDER_PYTHON_KATA,
    BREAKER_AUTH,
    BREAKER_API,
    BREAKER_WEB,
    REVIEWER_SECURITY,
    get_agent,
    get_agent_for_role,
    list_agents,
    register_agent,
)

__all__ = [
    "AgentConfig",
    "AgentRole",
    "ModelPreference",
    "ToolPermissions",
    "AgentBudgets",
    "EvidenceContract",
    "BUILDER_V1",
    "BREAKER_V1",
    "FIGHTER_V1",
    "JUDGE_V1",
    "REVIEWER_V1",
    "BUILDER_FASTAPI",
    "BUILDER_SECURITY_HARDENING",
    "BUILDER_PYTHON_KATA",
    "BREAKER_AUTH",
    "BREAKER_API",
    "BREAKER_WEB",
    "REVIEWER_SECURITY",
    "get_agent",
    "get_agent_for_role",
    "list_agents",
    "register_agent",
]
