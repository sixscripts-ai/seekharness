"""Executor selection without eager package-wide imports.

The Fighter process runtime imports ``executors.procs`` in a fresh interpreter.
Keeping this package initializer lazy prevents that narrow dependency from
loading ``advanced_executor`` and recursively importing the partially-created
Fighter runtime module.
"""

from __future__ import annotations

from importlib import import_module


_EXPORTS = {
    "AgentVsAgentExecutor": (".agent_vs_agent", "AgentVsAgentExecutor"),
    "BuildAndBreakExecutor": (".build_and_break", "BuildAndBreakExecutor"),
    "DirectDuelExecutor": (".direct_duel", "DirectDuelExecutor"),
    "SameTargetRaceExecutor": (".same_target_race", "SameTargetRaceExecutor"),
    "ScriptedExecutor": (".scripted", "ScriptedExecutor"),
    "AdvancedExecutor": (".advanced_executor", "AdvancedExecutor"),
}

_ENGINE_EXPORTS = {
    "build_and_break": "BuildAndBreakExecutor",
    "same_target_race": "SameTargetRaceExecutor",
    "direct_duel": "DirectDuelExecutor",
    "agent_vs_agent": "AgentVsAgentExecutor",
    "script_vs_defense": "ScriptedExecutor",
    "high_complexity": "ScriptedExecutor",
    "agent_tool_race": "AdvancedExecutor",
    "universal": "AdvancedExecutor",
}


def _executor_class(name: str):
    module_name, class_name = _EXPORTS[name]
    return getattr(import_module(module_name, __name__), class_name)


def __getattr__(name: str):
    if name not in _EXPORTS:
        raise AttributeError(name)
    value = _executor_class(name)
    globals()[name] = value
    return value


def get_executor(engine_or_config):
    """Resolve by format name/slug, then engine. Accepts a config dict or engine string."""
    scripted = _executor_class("ScriptedExecutor")
    if isinstance(engine_or_config, str):
        cls_name = _ENGINE_EXPORTS.get(engine_or_config)
        return (_executor_class(cls_name) if cls_name else scripted)()
    cfg = engine_or_config or {}
    from .formats import FORMAT_EXECUTORS

    name = cfg.get("name") or ""
    cls = FORMAT_EXECUTORS.get(name)
    if cls is None:
        slug = cfg.get("id") or cfg.get("slug") or ""
        cls = FORMAT_EXECUTORS.get(slug)
    if cls is None and (cfg.get("battle_plan") or cfg.get("universal") or cfg.get("custom")):
        cls = _executor_class("AdvancedExecutor")
    if cls is None:
        engine = cfg.get("engine", "scripted")
        cls_name = _ENGINE_EXPORTS.get(engine)
        cls = _executor_class(cls_name) if cls_name else scripted
    return cls()


__all__ = [*_EXPORTS, "get_executor"]
