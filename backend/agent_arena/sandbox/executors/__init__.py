from .agent_vs_agent import AgentVsAgentExecutor
from .build_and_break import BuildAndBreakExecutor
from .direct_duel import DirectDuelExecutor
from .same_target_race import SameTargetRaceExecutor
from .scripted import ScriptedExecutor
from .advanced_executor import AdvancedExecutor
from .formats import FORMAT_EXECUTORS

_ENGINE_REGISTRY = {
    "build_and_break": BuildAndBreakExecutor,
    "same_target_race": SameTargetRaceExecutor,
    "direct_duel": DirectDuelExecutor,
    "agent_vs_agent": AgentVsAgentExecutor,
    "script_vs_defense": ScriptedExecutor,
    "high_complexity": ScriptedExecutor,
    "agent_tool_race": AdvancedExecutor,
    "universal": AdvancedExecutor,
}


def get_executor(engine_or_config):
    """Resolve by format name/slug, then engine. Accepts a config dict or engine string."""
    if isinstance(engine_or_config, str):
        resolved = _ENGINE_REGISTRY.get(engine_or_config, ScriptedExecutor)()
        return resolved
    cfg = engine_or_config or {}
    name = cfg.get("name") or ""
    cls = FORMAT_EXECUTORS.get(name)
    if cls is None:
        slug = cfg.get("id") or cfg.get("slug") or ""
        cls = FORMAT_EXECUTORS.get(slug)
    if cls is None and (cfg.get("battle_plan") or cfg.get("universal")):
        cls = AdvancedExecutor
    if cls is None:
        engine = cfg.get("engine", "scripted")
        cls = _ENGINE_REGISTRY.get(engine, ScriptedExecutor)
    resolved = cls()
    return resolved
