"""Target Library Authoring Toolkit CLI.

Developer-facing toolkit for inspecting, validating, and authoring Agent Arena
targets.  Consumes the trusted production ``target_library`` loader and
``_command_guard`` wherever possible instead of reimplementing security rules.

Usage:
    python -m agent_arena.targets_cli list [--json]
    python -m agent_arena.targets_cli inspect <target-id> [--json]
    python -m agent_arena.targets_cli validate <target-id> [--json]
    python -m agent_arena.targets_cli validate --all [--json]
    python -m agent_arena.targets_cli doctor [--json]
    python -m agent_arena.targets_cli scaffold <target-id> [--dest DIR] [--dry-run] [--force]
    python -m agent_arena.targets_cli hash <target-id> [--json]
    python -m agent_arena.targets_cli test <target-id> [--json]
    python -m agent_arena.targets_cli stats [--json]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

# Reuse production security/validation primitives.
from .sandbox.executors._command_guard import command_block_reason
from .target_library import (
    TargetLibraryRegistry,
    TargetManifestError,
    TargetSecurityError,
    get_default_library_root,
    load_target_bundle,
    validate_safe_relative_path,
)

# ---------------------------------------------------------------------------
# Vocabulary – derived from the 10 production targets (single source of truth
# for doctor categorisation; not an enforcement gate for load_target_bundle).
# ---------------------------------------------------------------------------
KNOWN_CATEGORIES = {
    "software-engineering",
    "cybersecurity",
    "cybersecurity-data",
    "ctf",
    "agent-security",
    "agent-tool-use",
    "data-sql",
    "systems",
}
KNOWN_DIFFICULTIES = {"novice", "general", "advanced", "expert"}
KNOWN_FORMATS = {"solo", "builder_breaker", "ctf", "adversarial_agent"}
KNOWN_RUNTIMES = {
    "python311",
    "python311-fastapi",
    "python311-sqlite",
    "node22",
    "linux-gcc-make",
}

# ID / version patterns
_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
# semver  MAJOR.MINOR.PATCH optionally with prerelease/build metadata
_SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")


def _library_root_override(args: argparse.Namespace) -> Path | None:
    if getattr(args, "library_root", None):
        return Path(args.library_root).resolve()
    return None


def _get_registry(root_override: Path | None) -> TargetLibraryRegistry:
    return (
        TargetLibraryRegistry(root_override)
        if root_override
        else TargetLibraryRegistry()
    )


def _iter_target_dirs(root: Path) -> list[Path]:
    if not root.is_dir():
        return []
    return sorted(
        [p for p in root.iterdir() if p.is_dir() and (p / "target.yaml").is_file()]
    )


# ---------------------------------------------------------------------------
# Helpers: JSON vs human output
# ---------------------------------------------------------------------------


def _print_json(data: Any) -> None:
    json.dump(data, sys.stdout, indent=2, sort_keys=False, ensure_ascii=False)
    sys.stdout.write("\n")


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------


def cmd_list(args: argparse.Namespace) -> int:
    root = _library_root_override(args)
    registry = _get_registry(root)
    bundles = registry.list_targets()
    if args.json:
        payload = [
            {
                "id": b.id,
                "name": b.name,
                "title": b.name,
                "version": b.version,
                "category": b.category,
                "difficulty": b.difficulty,
                "format": b.format,
                "runtime": b.runtime,
                "manifest_hash": b.manifest_hash,
            }
            for b in bundles
        ]
        _print_json(payload)
        return 0
    # human table
    if not bundles:
        print("No targets found.")
        return 0
    # column widths
    headers = ["id", "title", "version", "category", "difficulty", "format"]
    rows = [
        [b.id, b.name, b.version, b.category, b.difficulty, b.format] for b in bundles
    ]
    widths = [
        max(len(str(h)), max((len(str(r[i])) for r in rows), default=0))
        for i, h in enumerate(headers)
    ]
    fmt = "  ".join(f"{{:<{w}}}" for w in widths)
    print(fmt.format(*headers))
    print(fmt.format(*["-" * w for w in widths]))
    for r in rows:
        print(fmt.format(*r))
    print(f"\n{len(bundles)} targets")
    return 0


# ---------------------------------------------------------------------------
# inspect
# ---------------------------------------------------------------------------


def cmd_inspect(args: argparse.Namespace) -> int:
    root = _library_root_override(args)
    registry = _get_registry(root)
    b = registry.get_target(args.target_id)
    if b is None:
        # try direct load for more precise error if registry reload hid it
        candidate = registry.root / args.target_id
        if candidate.is_dir() and (candidate / "target.yaml").is_file():
            try:
                b = load_target_bundle(candidate)
            except Exception as exc:
                print(
                    f"ERROR: failed to load '{args.target_id}': {exc}", file=sys.stderr
                )
                return 1
        if b is None:
            print(
                f"ERROR: target '{args.target_id}' not found in {registry.root}",
                file=sys.stderr,
            )
            return 1
    # safe metadata only – never emit hidden test contents or reference solutions
    payload = {
        "id": b.id,
        "version": b.version,
        "title": b.name,
        "name": b.name,
        "description": b.description,
        "runtime": b.runtime,
        "format": b.format,
        "category": b.category,
        "difficulty": b.difficulty,
        "tags": b.tags,
        "objectives": b.objectives,
        "starter_files": sorted(b.starter_files.keys()),
        "visible_tests": sorted(b.visible_test_files.keys()),
        "protected_paths": b.workspace.protected_paths,
        "handoff_allowlist": b.workspace.handoff_allowlist,
        "verification": {
            "visible_command": b.verification.visible_command,
            "hidden_command": b.verification.hidden_command,
            "ranked_requires_hidden_pass": b.verification.ranked_requires_hidden_pass,
        },
        "limits": {
            "max_tool_steps": b.limits.max_tool_steps,
            "exec_timeout_seconds": b.limits.exec_timeout_seconds,
        },
        "safety": {
            "scope": b.safety.scope,
            "real_targets": b.safety.real_targets,
            "network_required": b.safety.network_required,
        },
        "network": b.network,
        "manifest_hash": b.manifest_hash,
        "starter_hash": b.starter_hash,
        "hidden_hash": b.hidden_hash,
        "visible_test_count": len(b.visible_test_files),
        "hidden_test_count": len(b.hidden_test_files),
    }
    if args.json:
        _print_json(payload)
        return 0
    print(f"id:               {payload['id']}")
    print(f"version:          {payload['version']}")
    print(f"title:            {payload['title']}")
    print(f"description:      {payload['description']}")
    print(f"runtime:          {payload['runtime']}")
    print(f"format:           {payload['format']}")
    print(f"category:         {payload['category']}")
    print(f"difficulty:       {payload['difficulty']}")
    print(
        f"tags:             {', '.join(payload['tags']) if payload['tags'] else '(none)'}"
    )
    print(f"objectives:       {len(payload['objectives'])}")
    for o in payload["objectives"][:8]:
        print(f"  - {o}")
    if len(payload["objectives"]) > 8:
        print(f"  ... ({len(payload['objectives']) - 8} more)")
    print(
        f"starter files:    {len(payload['starter_files'])}  {payload['starter_files']}"
    )
    print(
        f"visible tests:    {len(payload['visible_tests'])}  {payload['visible_tests']}"
    )
    print(f"protected paths:  {payload['protected_paths']}")
    print(f"handoff:          {payload['handoff_allowlist']}")
    print(f"visible_command:  {payload['verification']['visible_command']}")
    print(f"hidden_command:   {payload['verification']['hidden_command']}")
    print(f"manifest hash:    {payload['manifest_hash']}")
    print(f"hidden tests:     {payload['hidden_test_count']}")
    return 0


# ---------------------------------------------------------------------------
# validate
# ---------------------------------------------------------------------------


def _validate_one(target_dir: Path) -> tuple[bool, str | None]:
    """Return (ok, error_message) reusing authoritative loader."""
    try:
        load_target_bundle(target_dir)
        return True, None
    except (TargetManifestError, TargetSecurityError, ValueError, RuntimeError) as exc:
        return False, str(exc)


def cmd_validate(args: argparse.Namespace) -> int:
    root = _library_root_override(args) or get_default_library_root()
    # --all mode
    if getattr(args, "all", False):
        dirs = _iter_target_dirs(root)
        results: list[dict[str, Any]] = []
        invalid = 0
        for d in dirs:
            ok, err = _validate_one(d)
            results.append({"id": d.name, "valid": ok, "error": err})
            if not ok:
                invalid += 1
        if args.json:
            _print_json(
                {
                    "total": len(dirs),
                    "valid": len(dirs) - invalid,
                    "invalid": invalid,
                    "results": results,
                }
            )
        else:
            for r in results:
                status = "PASS" if r["valid"] else "FAIL"
                suffix = "" if r["valid"] else f" — {r['error']}"
                print(f"{status}  {r['id']}{suffix}")
            print(f"\n{len(dirs)} targets")
            print(f"{len(dirs) - invalid} valid")
            print(f"{invalid} invalid")
        return 0 if invalid == 0 else 1

    # single-target mode
    target_id: str | None = getattr(args, "target_id", None)
    if not target_id:
        print("ERROR: specify a target id or use --all", file=sys.stderr)
        return 2
    target_dir = root / target_id
    if not target_dir.is_dir():
        print(f"ERROR: target directory not found: {target_dir}", file=sys.stderr)
        return 1
    ok, err = _validate_one(target_dir)
    if args.json:
        _print_json({"id": target_id, "valid": ok, "error": err})
    else:
        if ok:
            print(f"PASS  {target_id}")
        else:
            print(f"FAIL  {target_id} — {err}")
    return 0 if ok else 1


# ---------------------------------------------------------------------------
# doctor
# ---------------------------------------------------------------------------


def cmd_doctor(args: argparse.Namespace) -> int:
    root = _library_root_override(args) or get_default_library_root()
    dirs = _iter_target_dirs(root)

    errors: list[str] = []
    warnings: list[str] = []
    infos: list[str] = []

    # Track IDs to detect duplicates (filesystem case issues) and version conflicts
    seen_ids: dict[str, list[str]] = {}
    tag_counter: dict[str, int] = {}

    # Also check for duplicate IDs via case-insensitive / filesystem weirdness:
    # scan all child entries even those without target.yaml? No – only bundles count.

    for d in dirs:
        tid = d.name
        seen_ids.setdefault(tid, []).append(str(d))

    for tid, paths in seen_ids.items():
        if len(paths) > 1:
            errors.append(f"duplicate target ID '{tid}' at: {', '.join(paths)}")

    # Per-bundle deep checks
    for d in dirs:
        tid = d.name
        # 1. ID pattern
        if not _ID_RE.match(tid):
            errors.append(
                f"[{tid}] invalid ID pattern '{tid}' (must match ^[a-z0-9][a-z0-9-]*$)"
            )
        if len(tid) > 64:
            warnings.append(f"[{tid}] ID longer than 64 chars")

        # 2. Try authoritative load
        try:
            b = load_target_bundle(d)
        except Exception as exc:
            errors.append(f"[{tid}] manifest load failed: {exc}")
            continue

        # 3. Version semver
        ver = b.version
        if not _SEMVER_RE.match(ver):
            warnings.append(
                f"[{tid}] malformed semantic version '{ver}' (expected MAJOR.MINOR.PATCH)"
            )

        # 4. Required files – manifest already required; check workspace dirs existence
        # Starter dir should exist if bundle claims starter files? Not strictly required but warn if empty
        if not b.starter_files and not (d / b.workspace.starter_dir).is_dir():
            warnings.append(
                f"[{tid}] starter directory '{b.workspace.starter_dir}' missing or empty"
            )
        # Visible/hidden dirs reported by loader – if manifest references but dir absent, loader returns {}
        # We warn if dir absent but manifest lists non-empty expectations? Hidden tests missing is an error.
        if not b.visible_test_files:
            # some targets have visible tests empty? Check if dir exists but no files
            vis_dir = d / b.workspace.visible_tests_dir
            if not vis_dir.is_dir():
                warnings.append(
                    f"[{tid}] visible tests directory '{b.workspace.visible_tests_dir}' missing"
                )
        if not b.hidden_test_files:
            hid_dir = d / b.workspace.hidden_tests_dir
            if not hid_dir.is_dir():
                warnings.append(
                    f"[{tid}] hidden tests directory '{b.workspace.hidden_tests_dir}' missing"
                )
        if not (d / b.workspace.reference_dir).is_dir():
            # reference optional? Warn at info level
            infos.append(
                f"[{tid}] reference directory '{b.workspace.reference_dir}' missing (optional)"
            )

        # 5. Manifest hash – always computed; check against any stored catalog?
        # No stored hash to compare beyond recomputation; we verify determinism by recomputing.
        recomputed = hashlib.sha256(
            (d / "target.yaml").read_text(encoding="utf-8").encode("utf-8")
        ).hexdigest()
        if recomputed != b.manifest_hash:
            errors.append(
                f"[{tid}] manifest hash mismatch (computed {recomputed} vs bundle {b.manifest_hash})"
            )

        # 6. Path traversal / absolute path / unsafe path checks for protected/handoff
        for kind, paths in [
            ("protected_paths", b.workspace.protected_paths),
            ("handoff_allowlist", b.workspace.handoff_allowlist),
        ]:
            for p in paths:
                # Re-validate via trusted function
                try:
                    validate_safe_relative_path(p, context=kind)
                except TargetSecurityError as se:
                    errors.append(f"[{tid}] invalid {kind} '{p}': {se}")
                if p.startswith("/"):
                    errors.append(f"[{tid}] {kind} '{p}' is absolute")
                if ".." in p.split("/"):
                    errors.append(f"[{tid}] {kind} '{p}' contains '..' traversal")

        # 7. Starter file references: if handoff refers to file not in starter, warn
        starter_keys = set(b.starter_files.keys())
        for h in b.workspace.handoff_allowlist:
            # handoff may be a file like app.py or tokens.py – check if any starter file matches prefix
            if h not in starter_keys and not any(
                k.startswith(h.rstrip("*")) for k in starter_keys
            ):
                # For glob patterns like app.py exact, warn if missing
                if not h.endswith("**") and not h.endswith("/*"):
                    warnings.append(
                        f"[{tid}] handoff_allowlist '{h}' not found in starter files {sorted(starter_keys)[:5]}"
                    )

        # 8. Runtime (closed set)
        if b.runtime not in KNOWN_RUNTIMES:
            errors.append(
                f"[{tid}] unsupported runtime '{b.runtime}' (known: {sorted(KNOWN_RUNTIMES)})"
            )

        # 9. Format
        if b.format not in KNOWN_FORMATS:
            errors.append(
                f"[{tid}] invalid format '{b.format}' (expected one of {sorted(KNOWN_FORMATS)})"
            )

        # 10. Category (extensible) / difficulty / format / runtime
        # Category: malformed/empty → ERROR, unknown safe syntax → WARNING
        if not b.category or not b.category.strip():
            errors.append(f"[{tid}] empty category")
        elif not re.match(r"^[a-z0-9][a-z0-9-]*$", b.category):
            errors.append(
                f"[{tid}] malformed category '{b.category}' (must match ^[a-z0-9][a-z0-9-]*$)"
            )
        elif b.category not in KNOWN_CATEGORIES:
            warnings.append(
                f"[{tid}] unknown category '{b.category}' (known: {sorted(KNOWN_CATEGORIES)}) — allowed but flagged"
            )
        if b.difficulty not in KNOWN_DIFFICULTIES:
            # difficulty has closed vocabulary (novice/general/advanced/expert) — strict
            errors.append(
                f"[{tid}] invalid difficulty '{b.difficulty}' (expected {sorted(KNOWN_DIFFICULTIES)})"
            )

        # 11. Tags
        if not b.tags:
            warnings.append(f"[{tid}] no tags")
        if len(b.tags) != len(set(b.tags)):
            errors.append(f"[{tid}] duplicated tags: {b.tags}")
        for t in b.tags:
            if not t or not t.strip():
                errors.append(f"[{tid}] empty tag")
            if t != t.lower():
                warnings.append(f"[{tid}] tag '{t}' not lowercase")
        for t in b.tags:
            tag_counter[t] = tag_counter.get(t, 0) + 1

        # 12. Handoff contract sanity
        if b.format == "builder_breaker" and not b.workspace.handoff_allowlist:
            warnings.append(
                f"[{tid}] builder_breaker format has empty handoff_allowlist"
            )

        # 13. Verification commands – check blocked
        for label, cmd in [
            ("visible_command", b.verification.visible_command),
            ("hidden_command", b.verification.hidden_command),
        ]:
            if not cmd:
                warnings.append(f"[{tid}] {label} is empty")
                continue
            reason = command_block_reason(cmd, allow_network=b.network)
            if reason:
                errors.append(f"[{tid}] {label} blocked: {reason}")

        # 14. Unsafe absolute paths inside starter file keys (should already be caught by loader partition)
        for k in (
            list(b.starter_files.keys())
            + list(b.visible_test_files.keys())
            + list(b.hidden_test_files.keys())
        ):
            if k.startswith("/") or ".." in k.split("/"):
                errors.append(f"[{tid}] unsafe file key '{k}'")

    total = len(dirs)
    payload = {
        "targets_checked": total,
        "errors": len(errors),
        "warnings": len(warnings),
        "infos": len(infos),
        "messages": [
            *[{"level": "ERROR", "message": m} for m in errors],
            *[{"level": "WARNING", "message": m} for m in warnings],
            *[{"level": "INFO", "message": m} for m in infos],
        ],
    }

    if args.json:
        _print_json(payload)
    else:
        for m in errors:
            print(f"ERROR   {m}")
        for m in warnings:
            print(f"WARNING {m}")
        for m in infos:
            print(f"INFO    {m}")
        print(f"\n{total} targets checked")
        print(f"{len(errors)} errors")
        print(f"{len(warnings)} warnings")
        if infos:
            print(f"{len(infos)} infos")

    return 0 if not errors else 1


# ---------------------------------------------------------------------------
# scaffold
# ---------------------------------------------------------------------------

SCAFFOLD_MANIFEST_TEMPLATE = """schema_version: 1
id: {id}
name: "{name}"
category: {category}
difficulty: {difficulty}
format: {fmt}
runtime: {runtime}
description: "{description}"
tags:
- python
objectives:
- Do the task.
workspace:
  starter_dir: starter
  visible_tests_dir: tests/visible
  hidden_tests_dir: tests/hidden
  reference_dir: reference
  protected_paths:
  - tests/hidden/**
  - reference/**
  handoff_allowlist: []
network: false
verification:
  visible_command: PYTHONPATH=. pytest -q tests/visible
  hidden_command: PYTHONPATH=. pytest -q tests/hidden
  ranked_requires_hidden_pass: true
limits:
  max_tool_steps: 18
  exec_timeout_seconds: 360
safety:
  scope: synthetic-local-only
  real_targets: false
  network_required: false
"""

CATEGORY_CHOICES = sorted(KNOWN_CATEGORIES)
DIFFICULTY_CHOICES = sorted(KNOWN_DIFFICULTIES)
FORMAT_CHOICES = sorted(KNOWN_FORMATS)
RUNTIME_CHOICES = sorted(KNOWN_RUNTIMES)


def _resolve_scaffold_dest(
    target_id: str, dest_arg: str | None, library_root: Path | None
) -> Path:
    if dest_arg:
        return Path(dest_arg).resolve()
    # default: <repo>/targets/drafts/<target-id>  or  <library_root.parent>/drafts/<id>
    if library_root and library_root.name == "library":
        return (library_root.parent / "drafts" / target_id).resolve()
    # fallback relative to backend file location
    repo_targets = (
        Path(__file__).resolve().parents[2] / "targets" / "drafts" / target_id
    )
    # if that path's parent exists, use it; else cwd
    if repo_targets.parent.parent.is_dir():
        return repo_targets.resolve()
    return (Path.cwd() / "targets" / "drafts" / target_id).resolve()


def cmd_scaffold(args: argparse.Namespace) -> int:
    target_id = args.target_id
    # validate ID
    if not _ID_RE.match(target_id):
        print(
            f"ERROR: invalid target ID '{target_id}' (must match ^[a-z0-9][a-z0-9-]*$, lowercase kebab)",
            file=sys.stderr,
        )
        return 2
    if len(target_id) > 64:
        print(f"ERROR: target ID too long (>64)", file=sys.stderr)
        return 2
    # sanitize – reject path separators / traversal
    if "/" in target_id or "\\" in target_id or ".." in target_id:
        print(f"ERROR: target ID must not contain path separators", file=sys.stderr)
        return 2

    root_override = _library_root_override(args)
    dest = _resolve_scaffold_dest(
        target_id,
        getattr(args, "dest", None),
        root_override or get_default_library_root(),
    )

    # refuse overwrite unless --force
    if dest.exists() and not getattr(args, "force", False):
        print(
            f"ERROR: destination already exists: {dest}  (use --force to overwrite)",
            file=sys.stderr,
        )
        return 1

    # Build file tree to create
    category = (
        args.category
        if getattr(args, "category", None) is not None
        else "software-engineering"
    )
    difficulty = getattr(args, "difficulty", None) or "general"
    fmt = getattr(args, "format", None) or "solo"
    runtime = getattr(args, "runtime", None) or "python311"

    # Category is extensible: validate syntax only (empty/malformed → reject)
    _CAT_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
    if not category or not _CAT_RE.match(category):
        print(
            f"ERROR: invalid category '{category}' (must match ^[a-z0-9][a-z0-9-]*$, non-empty)",
            file=sys.stderr,
        )
        return 2

    manifest_text = SCAFFOLD_MANIFEST_TEMPLATE.format(
        id=target_id,
        name=target_id.replace("-", " ").title(),
        category=category,
        difficulty=difficulty,
        fmt=fmt,
        runtime=runtime,
        description=f"TODO: describe {target_id}",
    )

    # minimal starter/README/tests/reference placeholders
    planned: list[tuple[Path, str]] = [
        (dest / "target.yaml", manifest_text),
        (
            dest / "README.md",
            f"# {target_id}\n\nTODO: describe the target.\n\n## Objectives\n- Do the task.\n",
        ),
        (
            dest / "starter" / "README.md",
            "Starter workspace – place the broken/buggy project here.\n",
        ),
        (dest / "starter" / ".gitkeep", ""),
        (dest / "tests" / "visible" / ".gitkeep", ""),
        (dest / "tests" / "hidden" / ".gitkeep", ""),
        (dest / "reference" / ".gitkeep", ""),
    ]
    # Add a tiny visible test placeholder so verification has something
    if runtime.startswith("python"):
        planned.append(
            (
                dest / "tests" / "visible" / "test_visible.py",
                "def test_placeholder():\n    assert True\n",
            )
        )
        planned.append(
            (
                dest / "tests" / "hidden" / "test_hidden.py",
                "def test_hidden_placeholder():\n    assert True\n",
            )
        )
    elif runtime == "node22":
        planned.append(
            (
                dest / "tests" / "visible" / "basic.test.js",
                "import assert from 'node:assert/strict';\nimport test from 'node:test';\ntest('placeholder', () => assert.equal(1,1));\n",
            )
        )
        planned.append(
            (
                dest / "tests" / "hidden" / "edge.test.js",
                "import assert from 'node:assert/strict';\nimport test from 'node:test';\ntest('hidden placeholder', () => assert.equal(1,1));\n",
            )
        )

    if getattr(args, "dry_run", False):
        if getattr(args, "json", False):
            _print_json(
                {
                    "target_id": target_id,
                    "dest": str(dest),
                    "files": [str(p.relative_to(dest)) for p, _ in planned],
                    "dry_run": True,
                }
            )
        else:
            print(f"Would create {target_id} at {dest}:")
            for p, _ in planned:
                print(f"  {p.relative_to(dest) if p.is_relative_to(dest) else p}")
        return 0

    # actually write
    for p, content in planned:
        p.parent.mkdir(parents=True, exist_ok=True)
        # if force and file exists, overwrite; else create
        p.write_text(content, encoding="utf-8")

    if getattr(args, "json", False):
        _print_json(
            {
                "target_id": target_id,
                "dest": str(dest),
                "files": [str(p.relative_to(dest)) for p, _ in planned],
            }
        )
    else:
        print(f"Created {target_id} at {dest}")
        for p, _ in planned:
            print(f"  {p.relative_to(dest) if p.is_relative_to(dest) else p}")
        print(
            f"\nNext: edit target.yaml / starter, then run:  python -m agent_arena.targets_cli validate {target_id}"
        )
    return 0


# ---------------------------------------------------------------------------
# hash
# ---------------------------------------------------------------------------


def cmd_hash(args: argparse.Namespace) -> int:
    root = _library_root_override(args) or get_default_library_root()
    target_dir = root / args.target_id
    if not target_dir.is_dir():
        print(f"ERROR: target not found: {target_dir}", file=sys.stderr)
        return 1
    manifest_path = target_dir / "target.yaml"
    if not manifest_path.is_file():
        print(f"ERROR: target.yaml missing in {target_dir}", file=sys.stderr)
        return 1
    # Canonical production hash: sha256 of raw target.yaml bytes
    raw = manifest_path.read_bytes()
    # Use same method as target_library: hashlib.sha256(text.encode utf8) – raw bytes identical for utf8
    canonical = hashlib.sha256(raw).hexdigest()
    # Also load bundle to get bundle.manifest_hash for comparison (same computation path)
    try:
        b = load_target_bundle(target_dir)
        bundle_hash = b.manifest_hash
    except Exception as exc:
        if args.json:
            _print_json(
                {
                    "id": args.target_id,
                    "canonical_hash": canonical,
                    "bundle_hash": None,
                    "match": False,
                    "error": str(exc),
                }
            )
        else:
            print(f"canonical manifest hash: {canonical}")
            print(f"bundle load failed: {exc}")
        return 1

    match = canonical == bundle_hash
    if args.json:
        _print_json(
            {
                "id": args.target_id,
                "canonical_hash": canonical,
                "bundle_hash": bundle_hash,
                "match": match,
            }
        )
    else:
        print(f"canonical manifest hash: {canonical}")
        print(f"bundle manifest hash:    {bundle_hash}")
        print(f"match: {match}")
        if not match:
            print(
                "WARNING: stored manifest hash differs from calculated – bundle was modified without reload",
                file=sys.stderr,
            )
    return 0 if match else 1


# ---------------------------------------------------------------------------
# test  (safe structural/runtime smoke – no hidden solutions, no destructive run)
# ---------------------------------------------------------------------------


def cmd_test(args: argparse.Namespace) -> int:
    root = _library_root_override(args) or get_default_library_root()
    target_dir = root / args.target_id
    checks: list[dict[str, Any]] = []
    ok_overall = True

    def add(name: str, ok: bool, detail: str = "") -> None:
        nonlocal ok_overall
        checks.append({"check": name, "passed": ok, "detail": detail})
        if not ok:
            ok_overall = False

    # 1. bundle loads
    try:
        b = load_target_bundle(target_dir)
        add("bundle loads", True, f"version {b.version}")
    except Exception as exc:
        add("bundle loads", False, str(exc))
        # cannot continue further checks without bundle
        if args.json:
            _print_json({"id": args.target_id, "passed": False, "checks": checks})
        else:
            for c in checks:
                print(
                    f"{'PASS' if c['passed'] else 'FAIL'}  {c['check']}: {c['detail']}"
                )
        return 1

    # 2. manifest validates (already did) – also check required files exist
    for sub in [
        b.workspace.starter_dir,
        b.workspace.visible_tests_dir,
        b.workspace.hidden_tests_dir,
    ]:
        exists = (target_dir / sub).is_dir()
        # starter is important; visible/hidden are warnings if absent but not hard fail for test
        if sub == b.workspace.starter_dir:
            add(f"starter dir '{sub}' exists", exists, "" if exists else "missing")
        else:
            add(
                f"tests dir '{sub}' exists",
                exists,
                "" if exists else "missing (optional)",
            )

    # 3. verifier can initialize – check commands are not blocked
    for label, cmd in [
        ("visible_command", b.verification.visible_command),
        ("hidden_command", b.verification.hidden_command),
    ]:
        if not cmd:
            add(f"verifier {label} present", False, "empty")
            continue
        reason = command_block_reason(cmd, allow_network=b.network)
        add(
            f"verifier {label} not blocked",
            reason is None,
            "" if reason is None else reason,
        )

    # 4. runtime recognized
    add(
        "runtime recognized",
        b.runtime in KNOWN_RUNTIMES,
        "" if b.runtime in KNOWN_RUNTIMES else f"unknown '{b.runtime}'",
    )

    # 5. starter / visible counts
    add(
        "starter files present",
        len(b.starter_files) > 0,
        f"{len(b.starter_files)} files",
    )
    add(
        "visible tests present",
        len(b.visible_test_files) > 0,
        f"{len(b.visible_test_files)} files",
    )

    # Note what is NOT tested
    note = "Not tested: hidden expected outputs, reference solutions, destructive execution outside sandbox"

    if args.json:
        _print_json(
            {"id": args.target_id, "passed": ok_overall, "checks": checks, "note": note}
        )
    else:
        for c in checks:
            print(f"{'PASS' if c['passed'] else 'FAIL'}  {c['check']}: {c['detail']}")
        print(f"\n{'PASS' if ok_overall else 'FAIL'}  overall")
        print(f"Note: {note}")
    return 0 if ok_overall else 1


# ---------------------------------------------------------------------------
# stats
# ---------------------------------------------------------------------------


def cmd_stats(args: argparse.Namespace) -> int:
    root = _library_root_override(args)
    registry = _get_registry(root)
    bundles = registry.list_targets()
    from collections import Counter

    by_category = Counter(b.category for b in bundles)
    by_difficulty = Counter(b.difficulty for b in bundles)
    by_format = Counter(b.format for b in bundles)
    by_runtime = Counter(b.runtime for b in bundles)
    tag_counts = Counter(t for b in bundles for t in b.tags)
    versions = {b.id: b.version for b in bundles}
    payload = {
        "total": len(bundles),
        "by_category": dict(by_category),
        "by_difficulty": dict(by_difficulty),
        "by_format": dict(by_format),
        "by_runtime": dict(by_runtime),
        "tags": dict(tag_counts),
        "versions": versions,
    }
    if args.json:
        _print_json(payload)
        return 0
    print(f"total targets: {payload['total']}")
    print("by category:")
    for k, v in sorted(by_category.items()):
        print(f"  {k}: {v}")
    print("by difficulty:")
    for k, v in sorted(by_difficulty.items()):
        print(f"  {k}: {v}")
    print("by format:")
    for k, v in sorted(by_format.items()):
        print(f"  {k}: {v}")
    print("by runtime:")
    for k, v in sorted(by_runtime.items()):
        print(f"  {k}: {v}")
    print("tags:")
    for k, v in sorted(tag_counts.items()):
        print(f"  {k}: {v}")
    print("versions:")
    for k, v in sorted(versions.items()):
        print(f"  {k}: {v}")
    return 0


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="arena-targets", description="Agent Arena Target Library authoring toolkit"
    )
    p.add_argument(
        "--library-root",
        dest="library_root",
        default=None,
        help="Override target library root (default: $ARENA_TARGETS_DIR or /opt/arena-targets or targets/library)",
    )
    sub = p.add_subparsers(dest="command", required=True)

    # list
    sp = sub.add_parser("list", help="List targets")
    sp.add_argument("--json", action="store_true", help="Machine-readable JSON output")
    sp.set_defaults(func=cmd_list)

    # inspect
    sp = sub.add_parser("inspect", help="Show safe metadata for a target")
    sp.add_argument("target_id", help="Target ID")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_inspect)

    # validate
    sp = sub.add_parser("validate", help="Validate target(s)")
    g = sp.add_mutually_exclusive_group()
    g.add_argument("target_id", nargs="?", help="Target ID to validate")
    g.add_argument(
        "--all", action="store_true", dest="all", help="Validate every target"
    )
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_validate)

    # doctor
    sp = sub.add_parser("doctor", help="Library-wide consistency checks")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_doctor)

    # scaffold
    sp = sub.add_parser("scaffold", help="Generate a new target skeleton")
    sp.add_argument("target_id", help="New target ID (kebab-case, e.g. my-new-target)")
    sp.add_argument(
        "--dest",
        default=None,
        help="Destination directory (default: targets/drafts/<id>)",
    )
    sp.add_argument(
        "--dry-run",
        action="store_true",
        dest="dry_run",
        help="Show what would be created without writing",
    )
    sp.add_argument(
        "--force", action="store_true", help="Overwrite existing destination"
    )
    sp.add_argument(
        "--category",
        default=None,
        metavar="CATEGORY",
        help=f"Category slug matching ^[a-z0-9][a-z0-9-]*$ (suggestions: {', '.join(CATEGORY_CHOICES)})",
    )
    sp.add_argument(
        "--difficulty", choices=DIFFICULTY_CHOICES, default=None, help="Difficulty"
    )
    sp.add_argument(
        "--format", dest="fmt", choices=FORMAT_CHOICES, default=None, help="Format"
    )
    sp.add_argument("--runtime", choices=RUNTIME_CHOICES, default=None, help="Runtime")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_scaffold)

    # hash
    sp = sub.add_parser("hash", help="Compute canonical manifest hash")
    sp.add_argument("target_id", help="Target ID")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_hash)

    # test
    sp = sub.add_parser("test", help="Safe structural/runtime smoke checks")
    sp.add_argument("target_id", help="Target ID")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_test)

    # stats
    sp = sub.add_parser("stats", help="Library statistics")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_stats)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
