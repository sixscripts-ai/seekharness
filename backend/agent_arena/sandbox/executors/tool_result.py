"""Structured tool-result contract for Agent Arena microVM execution."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class ToolResult:
    """Structured contract for tool execution results."""

    tool: str
    success: bool
    output: str
    error: str | None = None
    exit_code: int | None = None
    error_type: str | None = None
    duration_ms: int = 0
    timed_out: bool = False
    policy_rejected: bool = False
    truncated: bool = False
    mutated: bool = False
    step_charged: bool = True
    metadata: dict[str, Any] | None = None

    def __str__(self) -> str:
        return self.output

    def __contains__(self, item: Any) -> bool:
        return str(item) in self.output

    def __getitem__(self, item: Any) -> Any:
        return self.output[item]

    def __len__(self) -> int:
        return len(self.output)

    def startswith(self, prefix: Any, *args: Any, **kwargs: Any) -> bool:
        return self.output.startswith(prefix, *args, **kwargs)

    def endswith(self, suffix: Any, *args: Any, **kwargs: Any) -> bool:
        return self.output.endswith(suffix, *args, **kwargs)

    def strip(self, *args: Any, **kwargs: Any) -> str:
        return self.output.strip(*args, **kwargs)

    def split(self, *args: Any, **kwargs: Any) -> list[str]:
        return self.output.split(*args, **kwargs)

    def splitlines(self, *args: Any, **kwargs: Any) -> list[str]:
        return self.output.splitlines(*args, **kwargs)

    def replace(self, *args: Any, **kwargs: Any) -> str:
        return self.output.replace(*args, **kwargs)

    def lower(self) -> str:
        return self.output.lower()

    def upper(self) -> str:
        return self.output.upper()

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, str):
            return self.output == other
        if isinstance(other, ToolResult):
            return (
                self.tool == other.tool
                and self.success == other.success
                and self.output == other.output
                and self.error == other.error
                and self.exit_code == other.exit_code
                and self.error_type == other.error_type
                and self.timed_out == other.timed_out
                and self.policy_rejected == other.policy_rejected
                and self.truncated == other.truncated
                and self.mutated == other.mutated
                and self.step_charged == other.step_charged
            )
        return False

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool": self.tool,
            "success": self.success,
            "output": self.output,
            "error": self.error,
            "exit_code": self.exit_code,
            "error_type": self.error_type,
            "duration_ms": self.duration_ms,
            "timed_out": self.timed_out,
            "policy_rejected": self.policy_rejected,
            "truncated": self.truncated,
            "mutated": self.mutated,
            "step_charged": self.step_charged,
            "metadata": self.metadata or {},
        }
