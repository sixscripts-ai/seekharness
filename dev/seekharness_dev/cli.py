import argparse
import json
import os
import sys
from pathlib import Path

from .preflight import get_preflight_data
from .lifecycle import get_lifecycle_status
from .tests_mapper import get_test_groups
from .migrations_reporter import get_migrations_data
from .target_inspector import inspect_target
from .codex_health_bridge import get_codex_health


def find_repo_root() -> Path:
    cur = Path.cwd()
    for parent in [cur] + list(cur.parents):
        if (parent / "backend").exists() and (parent / "targets").exists():
            return parent
        if (parent / "agent-arena").exists():
            return parent / "agent-arena"
    return cur


def main():
    # Common parent parser for flags like --json
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--json", action="store_true", help="Emit structured output in JSON")

    parser = argparse.ArgumentParser(
        prog="seekharness-dev",
        description="Deterministic local developer CLI for SeekHarness",
        parents=[common]
    )

    subparsers = parser.add_subparsers(dest="command", help="Sub-commands")

    # preflight
    subparsers.add_parser("preflight", parents=[common], help="Report git, environment, and boundary preflight state")

    # lifecycle
    subparsers.add_parser("lifecycle", parents=[common], help="Report status of the 5 core SeekHarness lifecycle boundaries")

    # tests
    subparsers.add_parser("tests", parents=[common], help="List smallest relevant test groups and their paths")

    # migrations
    subparsers.add_parser("migrations", parents=[common], help="Read-only inspection of Alembic migrations")

    # target
    p_target = subparsers.add_parser("target", parents=[common], help="Inspect deterministic target manifest and metadata")
    p_target.add_argument("name", help="Name of target to inspect")

    # codex-health
    subparsers.add_parser("codex-health", parents=[common], help="Check Codex environment health status")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    repo_root = find_repo_root()

    if args.command == "preflight":
        data = get_preflight_data(repo_root)
        if args.json:
            print(json.dumps(data, indent=2))
        else:
            print(f"=== SeekHarness Preflight ({data['repo_root']}) ===")
            print(f"Branch: {data['branch']}")
            print(f"Dirty files: {len(data['dirty_files'])} | Staged: {len(data['staged_files'])}")
            print(f"Backend venv: {data['env_status']['backend_venv']}")
            print(f"Frontend modules: {data['env_status']['frontend_node_modules']}")
            print(f"Migration Head: {data['migration_head']}")
            print(f"Applicable AGENTS: {len(data['applicable_agents_files'])} files")
        sys.exit(0)

    elif args.command == "lifecycle":
        data = get_lifecycle_status(repo_root)
        if args.json:
            print(json.dumps(data, indent=2))
        else:
            print("=== SeekHarness Lifecycle Boundaries ===")
            for k, v in data.items():
                print(f"  {k:25} -> {v}")
        sys.exit(0)

    elif args.command == "tests":
        data = get_test_groups(repo_root)
        if args.json:
            print(json.dumps(data, indent=2))
        else:
            print("=== SeekHarness Test Groups ===")
            for g in data["test_groups"]:
                print(f"  [{g['name']}] {g['description']}")
                print(f"     Path: {g['path']}")
        sys.exit(0)

    elif args.command == "migrations":
        data = get_migrations_data(repo_root)
        if args.json:
            print(json.dumps(data, indent=2))
        else:
            print(f"=== Alembic Migrations (Head: {data['head']}) ===")
            for r in data["revisions"]:
                print(f"  - {r['revision']}: {r['file']}")
        sys.exit(0)

    elif args.command == "target":
        data = inspect_target(repo_root, args.name)
        if args.json:
            print(json.dumps(data, indent=2))
        else:
            if "error" in data:
                print(f"ERROR: {data['error']}")
            else:
                print(f"=== Target: {data['target_name']} ===")
                print(f"Ranked: {data['ranked']} | Network: {data['network']}")
                print(f"Evaluator available: {data['evaluator_available']}")
                print(f"Manifest: {data['manifest_path']}")
        sys.exit(0 if "error" not in data else 1)

    elif args.command == "codex-health":
        data = get_codex_health()
        if args.json:
            print(json.dumps(data, indent=2))
        else:
            print(f"Codex Health: {data.get('status', 'UNKNOWN')}")
            for k, v in data.get("checks", {}).items():
                print(f"  - {k}: {v}")
        sys.exit(0 if data.get("status") in ("HEALTHY", "OK") else 1)


if __name__ == "__main__":
    main()
