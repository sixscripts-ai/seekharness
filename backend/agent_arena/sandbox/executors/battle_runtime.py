"""Small, reusable coordination primitives for advanced battles."""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping


ResultIdentity = tuple[str, str, str]


@dataclass(frozen=True)
class AdvancedRunConfig:
    """Typed, immutable view of the format settings used by a battle run.

    Format definitions are persisted as untyped JSON and historically each
    executor branch decoded the same values independently.  This boundary
    keeps the compatibility aliases and safety clamps in one place while
    leaving the original mapping available to callers that own unrelated
    format-specific settings.
    """

    max_turns: int = 6
    max_steps: int = 14
    tool_timeout: int | None = None
    race_max_tokens: int = 4096
    context_mode: str = "strict"
    allow_network: bool = False
    allowed_origins: tuple[str, ...] = ()
    target_code: str = ""
    default_test_code: str = ""
    role_test_code: Mapping[str, str] = field(default_factory=dict)
    role_missions: Mapping[str, str] = field(default_factory=dict)
    seed_solution_roles: frozenset[str] = frozenset()
    target_id: str = ""
    environment: Mapping[str, Any] = field(default_factory=dict)
    verification: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_format(
        cls,
        format_config: Mapping[str, Any] | None,
        *,
        default_test_code: str = "",
    ) -> "AdvancedRunConfig":
        config = dict(format_config or {})
        raw_limits = config.get("limits")
        limits = raw_limits if isinstance(raw_limits, Mapping) else {}

        def read(key: str, default: Any, aliases: tuple[str, ...] = ()) -> Any:
            for candidate in (key, *aliases):
                if candidate in config and config[candidate] is not None:
                    return config[candidate]
                if candidate in limits and limits[candidate] is not None:
                    return limits[candidate]
            return default

        def bounded_int(value: Any, default: int, upper: int) -> int:
            try:
                parsed = int(value)
            except (TypeError, ValueError):
                parsed = default
            return min(upper, max(1, parsed))

        def list_value(value: Any) -> list[str]:
            if value is None:
                return []
            if isinstance(value, str):
                return [value]
            try:
                return [str(item) for item in value]
            except TypeError:
                return [str(value)]

        raw_environment = config.get("environment")
        environment = (
            dict(raw_environment) if isinstance(raw_environment, Mapping) else {}
        )
        raw_verification = config.get("verification")
        verification = (
            dict(raw_verification) if isinstance(raw_verification, Mapping) else {}
        )
        origins = tuple(
            dict.fromkeys(
                list_value(environment.get("allowed_origins"))
                + list_value(config.get("allowed_origins"))
            )
        )
        judge_only = bool(
            config.get("judge_only") or config.get("evaluation_mode") == "quick"
        ) and config.get("evaluation_mode") != "verified"
        configured_test = str(config.get("test_code") or "")
        if judge_only:
            resolved_test = configured_test
        else:
            resolved_test = configured_test or default_test_code
        raw_role_test_code = config.get("role_test_code")
        role_test_code = (
            {str(key): str(value) for key, value in raw_role_test_code.items()}
            if isinstance(raw_role_test_code, Mapping)
            else {}
        )
        raw_role_missions = config.get("role_missions")
        role_missions = (
            {str(key): str(value) for key, value in raw_role_missions.items()}
            if isinstance(raw_role_missions, Mapping)
            else {}
        )
        seed_solution_roles = set(list_value(config.get("seed_solution_roles")))

        raw_timeout = read("tool_timeout", None, ("timeout", "timeout_seconds"))
        try:
            tool_timeout = int(raw_timeout) if raw_timeout else None
        except (TypeError, ValueError):
            tool_timeout = None

        try:
            race_max_tokens = int(
                read("race_max_tokens", 4096, ("max_tokens",)) or 4096
            )
        except (TypeError, ValueError):
            race_max_tokens = 4096

        return cls(
            max_turns=bounded_int(
                read("max_tool_turns", 6, ("max_turns",)), 6, 20
            ),
            max_steps=bounded_int(
                read("max_tool_steps", 14, ("max_steps",)), 14, 50
            ),
            tool_timeout=tool_timeout,
            race_max_tokens=race_max_tokens,
            context_mode=str(config.get("context_mode") or "strict")
            .lower()
            .strip(),
            allow_network=bool(environment.get("network")),
            allowed_origins=origins,
            target_code=str(config.get("target_code") or ""),
            default_test_code=resolved_test,
            role_test_code=role_test_code,
            role_missions=role_missions,
            seed_solution_roles=frozenset(seed_solution_roles),
            target_id=str(config.get("target_id") or ""),
            environment=environment,
            verification=verification,
        )


class ArtifactStore:
    """Ordered upsert store for one canonical result per fighter phase."""

    def __init__(self) -> None:
        self._items: dict[ResultIdentity, dict[str, Any]] = {}
        self._lock = threading.Lock()

    @staticmethod
    def identity(result: Mapping[str, Any]) -> ResultIdentity:
        return (
            str(result.get("phase") or "main"),
            str(result.get("role") or "fighter"),
            str(result.get("model_id") or ""),
        )

    def upsert(self, result: Mapping[str, Any]) -> dict[str, Any]:
        item = dict(result)
        with self._lock:
            self._items[self.identity(item)] = item
        return item

    def values(self) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(item) for item in self._items.values()]

    def __len__(self) -> int:
        with self._lock:
            return len(self._items)


class EventSink:
    """Serialize round writes and allocate strictly monotonic sequences."""

    def __init__(self, client, battle_id: str, *, lock: threading.Lock | None = None):
        self.client = client
        self.battle_id = battle_id
        self._lock = lock or threading.Lock()
        # A dict-shaped state keeps compatibility with the existing finalizer,
        # which receives the sequence counter by reference.
        self.state = {"n": 0}

    @property
    def sequence(self) -> int:
        with self._lock:
            return self.state["n"]

    def emit(
        self,
        phase: str,
        model_id: str,
        artifact: str | Callable[[int], str],
        *,
        event_type: str = "artifact",
        **kwargs: Any,
    ) -> int:
        with self._lock:
            self.state["n"] += 1
            sequence = self.state["n"]
            rendered = artifact(sequence) if callable(artifact) else artifact
            self.client.round(
                self.battle_id,
                phase,
                model_id,
                rendered,
                event_type=event_type,
                sequence=sequence,
                **kwargs,
            )
            return sequence


@dataclass
class BattleRunContext:
    """Shared state and dependencies for one advanced battle invocation."""

    battle_id: str
    client: Any
    config: AdvancedRunConfig
    role_to_model: Mapping[str, str]
    history: list[dict[str, Any]]
    artifact_store: ArtifactStore
    event_sink: EventSink
    deadline: float | None
    stop: Any = None
    status_check: Callable[..., Any] | None = None


@dataclass(frozen=True)
class PhaseRequest:
    """Normalized participant request consumed by ``PhaseRunner``."""

    phase: Mapping[str, Any]
    role_to_model: Mapping[str, str]
    parallel: bool = True

    @property
    def participants(self) -> tuple[str, ...]:
        return tuple(
            str(role)
            for role in (self.phase.get("participants") or [])
            if role and role != "judge" and self.role_to_model.get(str(role))
        )


class PhaseRunner:
    """Run one phase's fighter callbacks with deterministic participant order."""

    def __init__(self, execute_fighter: Callable[..., Any]):
        self.execute_fighter = execute_fighter

    def run(
        self,
        request: PhaseRequest,
        *,
        callback_kwargs: Mapping[str, Any] | None = None,
    ) -> list[Any]:
        kwargs = dict(callback_kwargs or {})
        jobs = list(enumerate(request.participants))

        def run_one(job: tuple[int, str]) -> Any:
            role_idx, role = job
            return self.execute_fighter(role_idx, role, **kwargs)

        if not request.parallel or len(jobs) <= 1:
            return [run_one(job) for job in jobs]
        with ThreadPoolExecutor(max_workers=len(jobs)) as executor:
            futures = [executor.submit(run_one, job) for job in jobs]
            outcomes: list[Any] = []
            errors: list[Exception] = []
            for future in futures:
                try:
                    outcomes.append(future.result())
                except Exception as exc:
                    errors.append(exc)
            if errors and not outcomes:
                raise errors[0]
            return outcomes


__all__ = [
    "AdvancedRunConfig",
    "ArtifactStore",
    "BattleRunContext",
    "EventSink",
    "PhaseRequest",
    "PhaseRunner",
]
