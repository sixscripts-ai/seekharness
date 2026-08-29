"""Target Library v1: multi-file target bundle loader, registry, and security model.

Loads target packages from `targets/library/<target_id>/` and validates:
1. Valid YAML manifest (`target.yaml`) conforming to specification.
2. Path traversal & partition separation prevention (rejects `..`, absolute paths, symlink escapes).
3. Evaluator separation (hidden tests and reference overlays are never exposed to fighters).
4. Deterministic hashing for manifest, starter bundle, and hidden test bundle.
5. Authoritative TARGET.md, role_missions, and battle plan compilation.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None

_SAFE_PATH_REGEX = re.compile(r"^[A-Za-z0-9_.*-][A-Za-z0-9_./*-]*$")


def _get_default_library_root() -> Path:
    env_dir = os.environ.get("ARENA_TARGETS_DIR")
    if env_dir and Path(env_dir).is_dir():
        return Path(env_dir).resolve()
    opt_dir = Path("/opt/arena-targets")
    if opt_dir.is_dir():
        return opt_dir.resolve()
    return (Path(__file__).resolve().parents[2] / "targets" / "library").resolve()


# Public API — thin wrappers over the private helpers that are now
# legitimate shared functionality for the authoring toolkit.


def get_default_library_root() -> Path:
    """Public: resolve the default target library root (env → /opt → repo)."""
    return _get_default_library_root()


def validate_safe_relative_path(rel_path: str, context: str = "") -> str:
    """Public: validate a relative path against traversal/unsafe chars."""
    return _validate_safe_relative_path(rel_path, context=context)


def compute_bundle_hash(file_dict: dict[str, bytes]) -> str:
    """Public: deterministic SHA256 over sorted paths and contents."""
    return _compute_bundle_hash(file_dict)


class TargetSecurityError(ValueError):
    """Raised when a target manifest attempts path traversal, symlink escape, or unsafe paths."""

    pass


class TargetManifestError(ValueError):
    """Raised when a target manifest is malformed or missing required fields."""

    pass


@dataclass(frozen=True)
class TargetWorkspaceConfig:
    starter_dir: str = "starter"
    visible_tests_dir: str = "tests/visible"
    hidden_tests_dir: str = "tests/hidden"
    reference_dir: str = "reference"
    protected_paths: list[str] = field(default_factory=list)
    handoff_allowlist: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class TargetVerificationConfig:
    visible_command: str = ""
    hidden_command: str = ""
    ranked_requires_hidden_pass: bool = True


@dataclass(frozen=True)
class TargetLimitsConfig:
    max_tool_steps: int = 18
    exec_timeout_seconds: int = 360


@dataclass(frozen=True)
class TargetSafetyConfig:
    scope: str = "synthetic-local-only"
    real_targets: bool = False
    network_required: bool = False


@dataclass(frozen=True)
class TargetBundle:
    schema_version: int
    id: str
    name: str
    category: str
    difficulty: str
    format: str
    runtime: str
    description: str
    tags: list[str]
    objectives: list[str]
    role_objectives: dict[str, list[str]]
    workspace: TargetWorkspaceConfig
    network: bool
    verification: TargetVerificationConfig
    limits: TargetLimitsConfig
    safety: TargetSafetyConfig
    version: str
    manifest_hash: str
    starter_hash: str
    hidden_hash: str
    starter_files: dict[str, bytes] = field(repr=False)
    visible_test_files: dict[str, bytes] = field(repr=False)
    hidden_test_files: dict[str, bytes] = field(repr=False)
    reference_files: dict[str, bytes] = field(repr=False)
    raw_manifest: dict[str, Any] = field(repr=False)


def _validate_safe_relative_path(rel_path: str, context: str = "") -> str:
    """Validate relative path to prevent directory traversal and special chars."""
    clean = str(rel_path or "").replace("\\", "/").strip()
    while clean.startswith("./"):
        clean = clean[2:]
    if not clean or clean.startswith("/"):
        raise TargetSecurityError(
            f"Invalid path '{rel_path}' in {context}: must be relative"
        )
    parts = clean.split("/")
    if ".." in parts or "." in parts:
        raise TargetSecurityError(
            f"Path traversal detected in '{rel_path}' ({context})"
        )
    if not _SAFE_PATH_REGEX.match(clean):
        raise TargetSecurityError(
            f"Invalid characters in path '{rel_path}' ({context})"
        )
    return clean


def _compute_bundle_hash(file_dict: dict[str, bytes]) -> str:
    """Compute deterministic SHA256 over sorted paths and contents."""
    h = hashlib.sha256()
    for path in sorted(file_dict.keys()):
        h.update(path.encode("utf-8"))
        h.update(b"\x00")
        h.update(file_dict[path])
        h.update(b"\x00")
    return h.hexdigest()


def _read_directory_files(base_dir: Path, sub_rel: str) -> dict[str, bytes]:
    """Recursively read all files under base_dir/sub_rel enforcing strict partition isolation."""
    sub_clean = _validate_safe_relative_path(sub_rel, context="directory resolution")
    target_dir = (base_dir / sub_clean).resolve()

    # Must reside strictly within base_dir
    try:
        target_dir.relative_to(base_dir.resolve())
    except ValueError:
        raise TargetSecurityError(
            f"Subdirectory '{sub_rel}' escapes target root '{base_dir}'"
        )

    if not target_dir.exists():
        return {}
    if not target_dir.is_dir():
        raise TargetManifestError(
            f"Path '{sub_rel}' is not a directory in '{base_dir.name}'"
        )

    files: dict[str, bytes] = {}
    for p in sorted(target_dir.rglob("*")):
        # Ignore Python cache artifacts – non-deterministic, not part of immutable bundle
        if "__pycache__" in p.parts or p.suffix == ".pyc" or p.name.endswith(".pyo"):
            continue
        if p.is_symlink():
            # In strict partition mode: reject symlinks that escape this specific partition
            resolved = p.resolve()
            try:
                resolved.relative_to(target_dir)
            except ValueError:
                raise TargetSecurityError(
                    f"Symlink '{p.name}' in '{sub_rel}' points outside partition '{sub_rel}'"
                )
        if p.is_file():
            rel = p.relative_to(target_dir).as_posix()
            files[rel] = p.read_bytes()
    return files


def load_target_bundle(target_dir: Path) -> TargetBundle:
    """Load, validate, and hash a single target directory."""
    if yaml is None:
        raise RuntimeError("PyYAML is required to load target bundles")

    target_dir = target_dir.resolve()
    manifest_path = target_dir / "target.yaml"
    if not manifest_path.is_file():
        raise TargetManifestError(f"Missing target.yaml in {target_dir}")

    raw_manifest_text = manifest_path.read_text(encoding="utf-8")
    try:
        raw = yaml.safe_load(raw_manifest_text)
    except Exception as exc:
        raise TargetManifestError(f"Malformed YAML in {manifest_path}: {exc}") from exc

    if not isinstance(raw, dict):
        raise TargetManifestError(f"{manifest_path} must be a YAML mapping")

    required_fields = {
        "schema_version",
        "id",
        "name",
        "category",
        "difficulty",
        "format",
        "runtime",
        "description",
        "workspace",
        "network",
        "verification",
        "limits",
        "safety",
    }
    missing = required_fields - set(raw)
    if missing:
        raise TargetManifestError(
            f"{manifest_path.name} missing required fields: {sorted(missing)}"
        )

    target_id = str(raw["id"]).strip()
    if target_id != target_dir.name:
        raise TargetManifestError(
            f"Target id '{target_id}' does not match folder name '{target_dir.name}'"
        )

    ws_raw = raw.get("workspace") or {}
    if not isinstance(ws_raw, dict):
        raise TargetManifestError(f"{target_id}: workspace must be a mapping")

    # Validate workspace relative paths
    starter_dir_name = ws_raw.get("starter_dir", "starter")
    visible_tests_dir_name = ws_raw.get("visible_tests_dir", "tests/visible")
    hidden_tests_dir_name = ws_raw.get("hidden_tests_dir", "tests/hidden")
    reference_dir_name = ws_raw.get("reference_dir", "reference")

    protected_paths = [
        _validate_safe_relative_path(p, context="protected_paths")
        for p in (ws_raw.get("protected_paths") or [])
        if str(p).strip()
    ]
    handoff_allowlist = [
        _validate_safe_relative_path(p, context="handoff_allowlist")
        for p in (ws_raw.get("handoff_allowlist") or [])
        if str(p).strip()
    ]

    workspace_cfg = TargetWorkspaceConfig(
        starter_dir=starter_dir_name,
        visible_tests_dir=visible_tests_dir_name,
        hidden_tests_dir=hidden_tests_dir_name,
        reference_dir=reference_dir_name,
        protected_paths=protected_paths,
        handoff_allowlist=handoff_allowlist,
    )

    ver_raw = raw.get("verification") or {}
    verification_cfg = TargetVerificationConfig(
        visible_command=str(ver_raw.get("visible_command") or ""),
        hidden_command=str(ver_raw.get("hidden_command") or ""),
        ranked_requires_hidden_pass=bool(
            ver_raw.get("ranked_requires_hidden_pass", True)
        ),
    )

    # Seatbelt at load time: refuse to ship a target whose verification commands
    # escape the workspace jail or reach the network without permission. This
    # mirrors the runtime guard applied by target_verifier.verify_target_submission.
    from .sandbox.executors._command_guard import command_block_reason as _block_reason

    network_flag = bool(raw.get("network", False))
    for label, cmd in (
        ("visible_command", verification_cfg.visible_command),
        ("hidden_command", verification_cfg.hidden_command),
    ):
        if not cmd:
            continue
        reason = _block_reason(cmd, allow_network=network_flag)
        if reason:
            raise ValueError(f"target '{target_id}' {label} rejected: {reason}")

    limits_raw = raw.get("limits") or {}
    limits_cfg = TargetLimitsConfig(
        max_tool_steps=int(limits_raw.get("max_tool_steps") or 18),
        exec_timeout_seconds=int(limits_raw.get("exec_timeout_seconds") or 360),
    )

    safety_raw = raw.get("safety") or {}
    safety_cfg = TargetSafetyConfig(
        scope=str(safety_raw.get("scope") or "synthetic-local-only"),
        real_targets=bool(safety_raw.get("real_targets", False)),
        network_required=bool(safety_raw.get("network_required", False)),
    )

    # Parse objectives (supports both flat list and dict with role keys)
    raw_objectives = raw.get("objectives")
    role_objectives: dict[str, list[str]] = {}
    flat_objectives: list[str] = []

    if isinstance(raw_objectives, dict):
        for role_key, items in raw_objectives.items():
            parsed_items = [
                str(x) for x in (items if isinstance(items, list) else [items])
            ]
            role_objectives[str(role_key)] = parsed_items
            for item in parsed_items:
                flat_objectives.append(f"[{role_key.upper()}] {item}")
    elif isinstance(raw_objectives, list):
        flat_objectives = [str(o) for o in raw_objectives]
        role_objectives["fighter"] = flat_objectives
    elif raw_objectives:
        flat_objectives = [str(raw_objectives)]
        role_objectives["fighter"] = flat_objectives

    # Read distinct file partitions
    starter_files = _read_directory_files(target_dir, starter_dir_name)
    visible_test_files = _read_directory_files(target_dir, visible_tests_dir_name)
    hidden_test_files = _read_directory_files(target_dir, hidden_tests_dir_name)
    reference_files = _read_directory_files(target_dir, reference_dir_name)

    # Compute deterministic hashes
    manifest_hash = hashlib.sha256(raw_manifest_text.encode("utf-8")).hexdigest()
    starter_hash = _compute_bundle_hash(starter_files)
    hidden_hash = _compute_bundle_hash(hidden_test_files)
    version = str(raw.get("version") or "1.0.0")

    return TargetBundle(
        schema_version=int(raw["schema_version"]),
        id=target_id,
        name=str(raw["name"]),
        category=str(raw["category"]),
        difficulty=str(raw["difficulty"]),
        format=str(raw["format"]),
        runtime=str(raw["runtime"]),
        description=str(raw["description"]),
        tags=[str(t) for t in (raw.get("tags") or [])],
        objectives=flat_objectives,
        role_objectives=role_objectives,
        workspace=workspace_cfg,
        network=bool(raw.get("network", False)),
        verification=verification_cfg,
        limits=limits_cfg,
        safety=safety_cfg,
        version=version,
        manifest_hash=manifest_hash,
        starter_hash=starter_hash,
        hidden_hash=hidden_hash,
        starter_files=starter_files,
        visible_test_files=visible_test_files,
        hidden_test_files=hidden_test_files,
        reference_files=reference_files,
        raw_manifest=raw,
    )


class TargetLibraryRegistry:
    """Registry discovering and caching loaded TargetBundles."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = (root or _get_default_library_root()).resolve()
        self._bundles: dict[str, TargetBundle] = {}
        self.reload()

    def reload(self) -> None:
        """Scan directory and load all valid bundles."""
        bundles: dict[str, TargetBundle] = {}
        if not self.root.is_dir():
            self._bundles = {}
            return

        for p in sorted(self.root.iterdir()):
            if p.is_dir() and (p / "target.yaml").is_file():
                bundle = load_target_bundle(p)
                bundles[bundle.id] = bundle
        self._bundles = bundles

    def list_targets(self) -> list[TargetBundle]:
        return [self._bundles[k] for k in sorted(self._bundles)]

    def get_target(self, target_id: str) -> TargetBundle | None:
        return self._bundles.get(target_id)

    def count(self) -> int:
        return len(self._bundles)


_GLOBAL_REGISTRY: TargetLibraryRegistry | None = None


def get_target_library(root: Path | None = None) -> TargetLibraryRegistry:
    global _GLOBAL_REGISTRY
    if _GLOBAL_REGISTRY is None or (root and _GLOBAL_REGISTRY.root != root.resolve()):
        _GLOBAL_REGISTRY = TargetLibraryRegistry(root)
    return _GLOBAL_REGISTRY


def compile_target_to_battle_config(
    bundle: TargetBundle, arena_size: int = 2
) -> dict[str, Any]:
    """Compile a TargetBundle into an authoritative battle_config with TARGET.md and role_missions."""
    starter_dict: dict[str, str] = {}
    for rel, data in bundle.starter_files.items():
        try:
            starter_dict[rel] = data.decode("utf-8")
        except UnicodeDecodeError:
            starter_dict[rel] = data.decode("latin-1")

    visible_tests_dict: dict[str, str] = {}
    for rel, data in bundle.visible_test_files.items():
        full_rel = f"tests/visible/{rel}"
        try:
            visible_tests_dict[full_rel] = data.decode("utf-8")
        except UnicodeDecodeError:
            visible_tests_dict[full_rel] = data.decode("latin-1")

    merged_starters = {**starter_dict, **visible_tests_dict}

    # Generate authoritative TARGET.md content
    obj_lines = "\n".join(f"- {o}" for o in bundle.objectives)
    target_code = (
        f"# TARGET: {bundle.name} ({bundle.category.upper()} / {bundle.difficulty.upper()})\n\n"
        f"**Runtime:** `{bundle.runtime}`  \n"
        f"**Format:** `{bundle.format}`  \n\n"
        f"## Mission Overview\n{bundle.description}\n\n"
        f"## Objectives\n{obj_lines}\n\n"
        f"## Verification Instructions\n"
        f"- Run visible tests using `TOOL test` (runs: `{bundle.verification.visible_command}`)\n"
        f"- Do not modify test harnesses or attempt to read evaluator tests.\n"
    )

    # Only protected paths present in starter workspace need restore tracking
    protected_in_starter = [
        s
        for s in merged_starters
        if any(
            (
                p == s
                or (p.endswith("/**") and s.startswith(p[:-3]))
                or (p.endswith("/*") and s.startswith(p[:-2]))
            )
            for p in bundle.workspace.protected_paths
        )
    ]

    if bundle.format == "builder_breaker":
        roles = ["builder", "breaker"]
        builder_objs = bundle.role_objectives.get("builder") or bundle.objectives
        breaker_objs = bundle.role_objectives.get("breaker") or bundle.objectives

        b_lines = "\n".join(f"- {o}" for o in builder_objs)
        brk_lines = "\n".join(f"- {o}" for o in breaker_objs)

        role_missions = {
            "builder": (
                f"# BUILDER ROLE: {bundle.name}\n\n"
                f"Your goal is to harden and repair the codebase.\n\n"
                f"### Objectives\n{b_lines}\n\n"
                f"Deliverable outputs: {', '.join(bundle.workspace.handoff_allowlist)}\n"
            ),
            "breaker": (
                f"# BREAKER ROLE: {bundle.name}\n\n"
                f"Your goal is to identify and demonstrate an exploit against the hardened builder output.\n\n"
                f"### Objectives\n{brk_lines}\n"
            ),
        }
        phases = [
            {
                "phase_id": "build",
                "phase_type": "build",
                "actor": "builder",
                "starter_files": merged_starters,
                "protected_artifacts": protected_in_starter,
                "required_outputs": bundle.workspace.handoff_allowlist,
                "workspace_policy": "fresh",
            },
            {
                "phase_id": "break",
                "phase_type": "break",
                "actor": "breaker",
                "handoff_from": ["build"],
                "handoff_artifacts": bundle.workspace.handoff_allowlist,
                "protected_artifacts": protected_in_starter,
                "workspace_policy": "fresh",
            },
        ]
    else:
        # Solo / CTF / Race benchmark format
        if arena_size <= 1:
            roles = ["fighter"]
            role_missions = {
                "fighter": (
                    f"# FIGHTER MISSION: {bundle.name}\n\n"
                    f"{bundle.description}\n\n"
                    f"### Objectives\n{obj_lines}\n"
                )
            }
            phases = [
                {
                    "phase_id": "solve",
                    "phase_type": "solve",
                    "actor": "fighter",
                    "starter_files": merged_starters,
                    "protected_artifacts": protected_in_starter,
                    "workspace_policy": "fresh",
                }
            ]
        else:
            roles = [f"fighter_{i}" for i in range(1, arena_size + 1)]
            role_missions = {
                r: (
                    f"# FIGHTER MISSION ({r.upper()}): {bundle.name}\n\n"
                    f"{bundle.description}\n\n"
                    f"### Objectives\n{obj_lines}\n"
                )
                for r in roles
            }
            phases = [
                {
                    "phase_id": f"solve_{r}",
                    "phase_type": "solve",
                    "actor": r,
                    "starter_files": merged_starters,
                    "protected_artifacts": protected_in_starter,
                    "workspace_policy": "fresh",
                }
                for r in roles
            ]
        if bundle.workspace.handoff_allowlist:
            for p in phases:
                p["required_outputs"] = bundle.workspace.handoff_allowlist

    return {
        "id": bundle.id,
        "name": bundle.name,
        "target_id": bundle.id,
        "target_version": bundle.version,
        "manifest_hash": bundle.manifest_hash,
        "starter_hash": bundle.starter_hash,
        "hidden_hash": bundle.hidden_hash,
        "category": bundle.category,
        "difficulty": bundle.difficulty,
        "format": bundle.format,
        "runtime": bundle.runtime,
        "description": bundle.description,
        "target_code": target_code,
        "objectives": bundle.objectives,
        "roles": roles,
        "role_missions": role_missions,
        "starter_files": merged_starters,
        "protected_paths": bundle.workspace.protected_paths,
        "handoff_allowlist": bundle.workspace.handoff_allowlist,
        "verification": {
            "visible_command": bundle.verification.visible_command,
            "hidden_command": bundle.verification.hidden_command,
            "ranked_requires_hidden_pass": bundle.verification.ranked_requires_hidden_pass,
        },
        "limits": {
            "max_tool_steps": bundle.limits.max_tool_steps,
            "exec_timeout_seconds": bundle.limits.exec_timeout_seconds,
        },
        "safety": {
            "scope": bundle.safety.scope,
            "real_targets": bundle.safety.real_targets,
            "network_required": bundle.safety.network_required,
        },
        "environment": {
            "network": bundle.network,
        },
        "battle_plan": {
            "plan_id": f"target-plan-{bundle.id}",
            "phases": phases,
        },
    }
