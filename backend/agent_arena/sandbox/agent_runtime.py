"""Bind declarative agent configurations to the existing battle runtime.

This module owns no provider client, model loop, or tool dispatcher.  It only
resolves a role's AgentConfig and chooses among models already admitted to the
battle.  The sandbox executor still calls ``/internal/model`` and the backend
provider layer remains the sole source of provider credentials and routing.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from ..agents import AgentConfig, get_agent, get_agent_for_role


class AgentRuntimeConfigurationError(ValueError):
    """A declared agent binding cannot be represented by this battle."""


@dataclass(frozen=True)
class RoleRuntimeBinding:
    role: str
    agent: AgentConfig | None
    model_id: str
    agent_source: str
    model_source: str


def _configured_agent(
    role: str, format_config: dict
) -> tuple[AgentConfig | None, str]:
    configured = format_config.get("role_to_agent_id") or {}
    requested_id = configured.get(role) or format_config.get("agent_id")
    if requested_id:
        agent = get_agent(str(requested_id))
        if agent is None:
            raise AgentRuntimeConfigurationError(
                f"role {role!r} names unknown agent {requested_id!r}"
            )
        return agent, "explicit"

    # Generic tournament slots (for example player_a/player_b) retain the
    # format's existing unrestricted tool profile unless an AgentConfig is
    # explicitly selected for them.  Only canonical agent roles opt into a
    # role default.
    if str(role).strip().lower() not in {
        "builder",
        "breaker",
        "fighter",
        "judge",
        "reviewer",
    }:
        return None, "unconfigured"
    agent = get_agent_for_role(role)
    if agent is None:
        raise AgentRuntimeConfigurationError(f"role {role!r} has no registered AgentConfig")
    return agent, "role_default"


def resolve_role_runtime_bindings(
    role_to_model: dict[str, str], format_config: dict | None,
) -> dict[str, RoleRuntimeBinding]:
    """Resolve role configs without adding a second provider or model system.

    A configuration preference is activated only when the battle's admitted
    assignment for that role is its preferred or fallback model.  Selection of
    a different participant model would duplicate or steal another role's
    allocation, so this bridge deliberately does not do that.  This preserves
    the persisted battle's provider/credential authorization boundary and
    leaves NewBattle model selection untouched.
    """
    cfg = format_config or {}
    bindings: dict[str, RoleRuntimeBinding] = {}

    for role, assigned_model in role_to_model.items():
        model_id = str(assigned_model)
        model_source = "battle_assignment"
        agent, agent_source = _configured_agent(role, cfg)

        if agent is None:
            bindings[role] = RoleRuntimeBinding(
                role=role,
                agent=None,
                model_id=model_id,
                agent_source=agent_source,
                model_source=model_source,
            )
            continue

        trusted_sandbox_bootstrap = (
            os.environ.get("ARENA_IN_SANDBOX") == "1"
            and bool(os.environ.get("BATTLE_BOOTSTRAP_JSON"))
            and bool(os.environ.get("BATTLE_TOKEN"))
        )
        if not trusted_sandbox_bootstrap:
            # Host-side activation validates IDs through the existing provider
            # catalogue.  Import lazily: the Fighter image intentionally omits
            # Appwrite/cryptography control-plane dependencies, and the backend
            # already validated and persisted this immutable binding before
            # constructing BATTLE_BOOTSTRAP_JSON.  /internal/model re-checks the
            # persisted model assignment before resolving any credential.
            from ..providers import get_model_spec

            try:
                preferred_spec = get_model_spec(agent.model.preferred)
                fallback_spec = (
                    get_model_spec(agent.model.fallback)
                    if agent.model.fallback
                    else None
                )
            except Exception as exc:
                raise AgentRuntimeConfigurationError(
                    f"agent {agent.agent_id!r} has an unknown configured model"
                ) from exc

            # A configuration preference must be usable by the configured role
            # before a battle is persisted and sandboxed.
            for candidate, spec in (
                (agent.model.preferred, preferred_spec),
                (agent.model.fallback, fallback_spec),
            ):
                if candidate and spec is not None and agent.role not in spec.roles:
                    raise AgentRuntimeConfigurationError(
                        f"agent {agent.agent_id!r} configures model {candidate!r} "
                        f"which is not admitted for role {agent.role!r}"
                    )

        if agent_source == "explicit":
            for candidate, source in (
                (agent.model.preferred, "agent_preferred"),
                (agent.model.fallback, "agent_fallback"),
            ):
                if candidate and candidate == model_id:
                    model_id = candidate
                    model_source = source
                    break

        bindings[role] = RoleRuntimeBinding(
            role=role,
            agent=agent,
            model_id=model_id,
            agent_source=agent_source,
            model_source=model_source,
        )

    return bindings
