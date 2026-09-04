"""Target Library v1: multi-file target bundle loader, registry, and security model.

Loads public target packages from `targets/library/<target_id>/` and validates:
1. Valid YAML manifest (`target.yaml`) conforming to specification.
2. Path traversal & partition separation prevention (rejects `..`, absolute paths, symlink escapes).
3. Evaluator separation: hidden tests and reference overlays load ONLY from
   `private_evaluator_dir()` (`$ARENA_EVALUATOR_DIR/<id>` or
   `targets/evaluators/<id>`). Public library copies are ignored.
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
    private_fixture_files: dict[str, bytes] = field(default_factory=dict, repr=False)
    services: dict[str, Any] = field(default_factory=dict, repr=False)


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

    # Public partitions only. Hidden/reference/fixtures never load from the library tree.
    starter_files = _read_directory_files(target_dir, starter_dir_name)
    visible_test_files = _read_directory_files(target_dir, visible_tests_dir_name)
    hidden_test_files: dict[str, bytes] = {}
    reference_files: dict[str, bytes] = {}
    private_fixture_files: dict[str, bytes] = {}
    overlay = private_evaluator_dir(target_id)
    if overlay is not None:
        hidden_test_files = _read_directory_files(overlay, "tests/hidden")
        reference_files = _read_directory_files(overlay, "reference")
        private_fixture_files = _read_overlay_fixtures(overlay)
    if target_requires_private_evaluator(verification_cfg):
        if overlay is None:
            raise TargetSecurityError(
                f"target '{target_id}' requires a private evaluator package "
                f"($ARENA_EVALUATOR_DIR/{target_id} or targets/evaluators/{target_id})"
            )
        if not hidden_test_files:
            raise TargetSecurityError(
                f"target '{target_id}' private evaluator package has no hidden tests"
            )

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
        private_fixture_files=private_fixture_files,
        raw_manifest=raw,
        services=raw.get("services") if isinstance(raw.get("services"), dict) else {},
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
        is_fullstack = bool(bundle.services) or "fullstack" in (bundle.runtime or "")
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
                "handoff_from": [] if is_fullstack else ["build"],
                "handoff_artifacts": [] if is_fullstack else bundle.workspace.handoff_allowlist,
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
        "ranked": target_ranked_eligible(bundle.id, bundle.version),
        "services": bundle.services,
        "battle_plan": {
            "plan_id": f"target-plan-{bundle.id}",
            "phases": phases,
        },
    }


# Explicit fighter-visible roots. Unknown directories default to deny.
FIGHTER_PUBLIC_ROOT_FILES = frozenset({"target.yaml", "README.md", "TARGET.md"})


def fighter_public_allowlist(
    workspace: TargetWorkspaceConfig | dict | None = None,
) -> tuple[tuple[str, ...], frozenset[str]]:
    """Return (directory roots, root files) that may appear on the fighter FS."""
    if isinstance(workspace, TargetWorkspaceConfig):
        starter = workspace.starter_dir or "starter"
        visible = workspace.visible_tests_dir or "tests/visible"
    elif isinstance(workspace, dict):
        starter = str(workspace.get("starter_dir") or "starter")
        visible = str(workspace.get("visible_tests_dir") or "tests/visible")
    else:
        starter = "starter"
        visible = "tests/visible"
    roots = tuple(
        p.replace("\\", "/").strip().strip("/")
        for p in (starter, visible)
        if p and ".." not in p.split("/") and not p.startswith("/")
    )
    return roots, FIGHTER_PUBLIC_ROOT_FILES


def _workspace_from_manifest_file(manifest_path: Path) -> TargetWorkspaceConfig | None:
    if yaml is None or not manifest_path.is_file():
        return None
    try:
        raw = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(raw, dict):
        return None
    ws = raw.get("workspace") or {}
    if not isinstance(ws, dict):
        return None
    return TargetWorkspaceConfig(
        starter_dir=str(ws.get("starter_dir") or "starter"),
        visible_tests_dir=str(ws.get("visible_tests_dir") or "tests/visible"),
        hidden_tests_dir=str(ws.get("hidden_tests_dir") or "tests/hidden"),
        reference_dir=str(ws.get("reference_dir") or "reference"),
    )


def rel_is_fighter_public(rel: str, roots: tuple[str, ...], root_files: frozenset[str]) -> bool:
    posix = str(rel).replace("\\", "/").strip().lstrip("./")
    if not posix or posix.startswith("/") or ".." in posix.split("/"):
        return False
    if posix in root_files:
        return True
    for root in roots:
        if posix == root or posix.startswith(root + "/"):
            return True
    return False


def target_requires_private_evaluator(
    verification: TargetVerificationConfig | dict | None,
) -> bool:
    """True when the target must have a private hidden-test package."""
    if isinstance(verification, TargetVerificationConfig):
        return bool(verification.hidden_command.strip())
    if isinstance(verification, dict):
        return bool(str(verification.get("hidden_command") or "").strip())
    return False


# Production trusted-backend mount. Isolation must see this even when an
# ambient ARENA_EVALUATOR_DIR points somewhere else.
PRODUCTION_EVALUATOR_MOUNT = Path("/opt/arena-evaluators")

# Historical public-library targets whose hidden/reference bodies already
# existed in git history. They remain executable and verifiable, but they
# cannot affect ranked competition until a rotated identity is allowlisted.
COMPROMISED_LIBRARY_TARGET_IDS = frozenset(
    {
        "authentication-gate",
        "broken-package-recovery",
        "makefile-from-hell",
        "migration-disaster",
        "poisoned-instructions",
        "readme-lied",
        "red-herring-repository",
        "session-replay-defense",
        "sql-login-service",
        "tinyshop",
    }
)

# Explicit (target_id, version) pairs that may update Elo / leaderboard /
# competitive skill learning. Empty on purpose: do not enable the current
# compromised revisions. Operators add a rotated pair after publishing a
# new private evaluator set that is not in public git history.
RANKED_TARGET_ALLOWLIST: frozenset[tuple[str, str]] = frozenset()


def target_ranked_eligible(
    target_id: str | None, target_version: str | None = None
) -> bool:
    """True only for an explicitly allowlisted rotated target identity."""
    tid = str(target_id or "").strip()
    version = str(target_version or "").strip()
    if not tid or not version:
        return False
    if tid in COMPROMISED_LIBRARY_TARGET_IDS and (
        tid,
        version,
    ) not in RANKED_TARGET_ALLOWLIST:
        return False
    return (tid, version) in RANKED_TARGET_ALLOWLIST


def fighter_visible_battle_config(cfg: dict | None) -> dict:
    """Copy a battle config with evaluator-private fields removed.

    Trusted verification keeps hidden_hash / hidden_command on the backend.
    Fighters receive only public mission, starter, and visible-test commands.
    """
    import copy

    public = copy.deepcopy(cfg) if isinstance(cfg, dict) else {}
    public.pop("hidden_hash", None)
    public.pop("hidden_test_files", None)
    public.pop("reference_files", None)
    public.pop("private_fixture_files", None)
    verification = public.get("verification")
    if isinstance(verification, dict):
        verification.pop("hidden_command", None)
        public["verification"] = verification
    return public


def default_evaluator_root() -> Path:
    """Preferred evaluator root for *loading* a target overlay.

    Lookup stays env-first with no repo fallback when the env var is set.
    Isolation uses `evaluator_storage_roots()` so a mismatched env cannot
    hide the production mount.
    """
    env_root = os.environ.get("ARENA_EVALUATOR_DIR")
    if env_root:
        return Path(env_root)
    return Path(__file__).resolve().parents[2] / "targets" / "evaluators"


def evaluator_storage_roots() -> list[Path]:
    """Filesystem roots that may hold private evaluator packages on this host."""
    roots: list[Path] = []
    seen: set[str] = set()

    def _add(path: Path) -> None:
        key = str(path)
        if key in seen:
            return
        seen.add(key)
        roots.append(path)

    env_root = os.environ.get("ARENA_EVALUATOR_DIR")
    if env_root:
        _add(Path(env_root))
    _add(PRODUCTION_EVALUATOR_MOUNT)
    if not env_root:
        _add(Path(__file__).resolve().parents[2] / "targets" / "evaluators")
    return roots


def relpath_is_private_evaluator(rel: str) -> bool:
    """True when a path is hidden-verifier or reference material.

    Fighter-visible packages must never contain these files. Path guards are
    not the isolation mechanism; this classifier is used when materializing
    the public tree so the files are absent from the fighter filesystem.
    """
    parts = [p for p in str(rel).replace("\\", "/").split("/") if p and p != "."]
    if not parts:
        return False
    lower = [p.lower() for p in parts]
    if lower[0] == "reference" or lower[0].startswith("reference"):
        return True
    if len(lower) >= 2 and lower[0] == "tests" and lower[1].startswith("hidden"):
        return True
    return False


def _read_overlay_fixtures(overlay: Path) -> dict[str, bytes]:
    """Trusted extra files (breaker harness, fixtures) excluding hidden/reference."""
    files: dict[str, bytes] = {}
    overlay = overlay.resolve()
    if not overlay.is_dir():
        return files
    for p in sorted(overlay.rglob("*")):
        if "__pycache__" in p.parts or p.suffix in {".pyc", ".pyo"}:
            continue
        if p.is_symlink() or not p.is_file():
            continue
        if p.name == ".gitkeep":
            continue
        rel = p.relative_to(overlay).as_posix()
        if relpath_is_private_evaluator(rel):
            continue
        files[rel] = p.read_bytes()
    return files


def private_evaluator_dir(target_id: str) -> Path | None:
    """Optional overlay root for private evaluator packages (not fighter-mounted).

    Lookup order:
    1. $ARENA_EVALUATOR_DIR/<target_id> when the env var is set (no repo fallback)
    2. repo targets/evaluators/<target_id> when the env var is unset
    """
    tid = str(target_id or "").strip()
    if not tid:
        return None
    env_root = os.environ.get("ARENA_EVALUATOR_DIR")
    if env_root:
        candidate = Path(env_root) / tid
        if candidate.is_dir():
            return candidate.resolve()
        return None
    repo = Path(__file__).resolve().parents[2] / "targets" / "evaluators" / tid
    if repo.is_dir():
        return repo.resolve()
    return None


def _root_has_evaluator_packages(root: Path) -> bool | None:
    """True/False when inspectable; None when the root cannot be trusted-denied."""
    try:
        if not root.exists():
            return False
        if not root.is_dir():
            return False
    except OSError:
        return None
    try:
        resolved = root.resolve()
    except OSError:
        resolved = root
    try:
        production = PRODUCTION_EVALUATOR_MOUNT.resolve()
    except OSError:
        production = PRODUCTION_EVALUATOR_MOUNT
    # A production mount directory is itself the isolation signal, even if
    # the volume is empty or an env override points elsewhere.
    if root == PRODUCTION_EVALUATOR_MOUNT or resolved == production:
        return True
    try:
        for entry in root.iterdir():
            if entry.name.startswith("."):
                continue
            if entry.is_dir():
                return True
    except OSError:
        return None
    return False


def private_evaluator_storage_present() -> bool:
    """True when this host can read private evaluator material.

    Presence is a filesystem question, not an environment question. An ambient
    `ARENA_EVALUATOR_DIR` override must not hide `/opt/arena-evaluators`.
    Unreadable configured/production roots fail closed.
    """
    env_root = os.environ.get("ARENA_EVALUATOR_DIR")
    for root in evaluator_storage_roots():
        try:
            present = _root_has_evaluator_packages(root)
        except OSError:
            present = None
        if present is True:
            return True
        if present is None:
            is_production = root == PRODUCTION_EVALUATOR_MOUNT
            is_configured = bool(env_root) and Path(env_root) == root
            if is_production or is_configured:
                return True
    return False


def get_trusted_library_root() -> Path:
    """Host/verifier library root. Never a fighter-visible public mount."""
    trusted = os.environ.get("ARENA_TRUSTED_TARGETS_DIR")
    if trusted and Path(trusted).is_dir():
        return Path(trusted).resolve()
    if os.environ.get("ARENA_IN_SANDBOX") == "1":
        repo = Path(__file__).resolve().parents[2] / "targets" / "library"
        if repo.is_dir():
            return repo.resolve()
    return _get_default_library_root()


def _assert_safe_public_file(path: Path, rel: str) -> None:
    """Fail closed on symlink or multi-link files in the public package."""
    if path.is_symlink():
        raise TargetSecurityError(
            f"symlink '{rel}' is not allowed in a fighter-visible package"
        )
    try:
        st = path.lstat()
    except OSError as exc:
        raise TargetSecurityError(
            f"cannot inspect '{rel}' for fighter materialization: {exc}"
        ) from exc
    if getattr(st, "st_nlink", 1) > 1:
        raise TargetSecurityError(
            f"hardlinked file '{rel}' is unsafe for fighter materialization"
        )


def _public_symlink_escape(path: Path, target_dir: Path) -> str | None:
    """Return a relative path if `path` or an ancestor under the target is a symlink."""
    current = path
    while True:
        if current.is_symlink():
            try:
                return current.relative_to(target_dir).as_posix()
            except ValueError:
                return str(current)
        if current == target_dir:
            return None
        parent = current.parent
        if parent == current:
            return None
        current = parent


def materialize_fighter_visible_library(src_root: Path, dest_root: Path) -> Path:
    """Copy only explicitly public target files into dest_root.

    Public roots come from the target manifest (starter + visible tests) plus
    a small set of root docs. Unknown directories are denied. A symlink target
    root, a symlink file/directory, or a hardlinked public file fails closed
    so the fighter never receives aliased private content.
    """
    import os
    import shutil

    src_root = Path(src_root)
    dest_root = Path(dest_root)
    dest_root.mkdir(parents=True, exist_ok=True)
    if not src_root.is_dir():
        return dest_root
    for target_dir in sorted(src_root.iterdir()):
        if target_dir.name.startswith("."):
            continue
        if not target_dir.is_dir():
            continue
        if target_dir.is_symlink():
            raise TargetSecurityError(
                f"target root '{target_dir.name}' is a symlink"
            )
        if not (target_dir / "target.yaml").is_file():
            continue
        workspace = _workspace_from_manifest_file(target_dir / "target.yaml")
        roots, root_files = fighter_public_allowlist(workspace)
        dest_target = dest_root / target_dir.name
        planned: list[tuple[Path, str]] = []
        for dirpath, dirnames, filenames in os.walk(target_dir, followlinks=False):
            current = Path(dirpath)
            escaped = _public_symlink_escape(current, target_dir)
            if escaped:
                rel = current.relative_to(target_dir).as_posix() if current != target_dir else escaped
                if rel_is_fighter_public(rel, roots, root_files) or any(
                    rel_is_fighter_public(f"{rel}/{name}", roots, root_files)
                    for name in (*dirnames, *filenames)
                ):
                    raise TargetSecurityError(
                        f"symlink '{escaped}' is not allowed in a fighter-visible package"
                    )
                dirnames.clear()
                continue
            for name in list(dirnames):
                child = current / name
                rel = child.relative_to(target_dir).as_posix()
                if child.is_symlink() and (
                    rel_is_fighter_public(rel, roots, root_files)
                    or rel_is_fighter_public(f"{rel}/x", roots, root_files)
                ):
                    raise TargetSecurityError(
                        f"symlink '{rel}' is not allowed in a fighter-visible package"
                    )
            for name in filenames:
                path = current / name
                if "__pycache__" in path.parts or path.suffix in {".pyc", ".pyo"}:
                    continue
                rel = path.relative_to(target_dir).as_posix()
                if relpath_is_private_evaluator(rel):
                    continue
                if not rel_is_fighter_public(rel, roots, root_files):
                    continue
                escaped = _public_symlink_escape(path, target_dir)
                if escaped:
                    raise TargetSecurityError(
                        f"symlink '{escaped}' is not allowed in a fighter-visible package"
                    )
                _assert_safe_public_file(path, rel)
                planned.append((path, rel))
        try:
            for path, rel in planned:
                dest = dest_target / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, dest, follow_symlinks=False)
                if dest.is_symlink() or dest.lstat().st_nlink > 1:
                    raise TargetSecurityError(
                        f"copied '{rel}' is not a regular unlinked file"
                    )
        except Exception:
            shutil.rmtree(dest_target, ignore_errors=True)
            raise
    return dest_root
