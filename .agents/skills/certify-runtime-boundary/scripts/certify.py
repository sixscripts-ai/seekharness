#!/usr/bin/env python3
"""
certify.py - Deterministic boundary certification tool.
Runs negative tests, schema checks, and invariant assertions to certify a runtime boundary.
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


BOUNDARY_TEST_MAP = {
    "semantic_verification": [
        "backend/tests/test_builder_breaker_semantic_verification.py"
    ],
    "battle_db": [
        "backend/tests/test_battle_database_lifecycle.py"
    ],
    "service_lifecycle": [
        "backend/tests/test_battle_plan.py",
        "backend/tests/test_process_manager.py"
    ],
    "breaker_handoff": [
        "backend/tests/test_fighter_runtime.py",
        "backend/tests/test_fighter_tool_boundaries.py"
    ],
    "trusted_completion": [
        "backend/tests/test_finalization_authority.py",
        "backend/tests/test_finalization_idempotency.py"
    ]
}


def find_pytest(repo_root: Path) -> str:
    venv_pytest = repo_root / "backend" / ".venv" / "bin" / "pytest"
    if venv_pytest.exists():
        return str(venv_pytest)
    return "pytest"


def run_boundary_tests(repo_root: Path, boundary: str) -> dict:
    tests = BOUNDARY_TEST_MAP.get(boundary, [])
    if not tests:
        return {
            "boundary": boundary,
            "certified": False,
            "error": f"Unknown boundary '{boundary}'"
        }

    pytest_bin = find_pytest(repo_root)
    existing_tests = [t for t in tests if (repo_root / t).exists()]
    missing_tests = [t for t in tests if not (repo_root / t).exists()]

    if not existing_tests:
        return {
            "boundary": boundary,
            "certified": False,
            "error": f"Missing all test files: {missing_tests}",
            "tests_run": 0,
            "passed": False
        }

    cmd = [pytest_bin, "-q"] + existing_tests
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root / "backend")

    proc = subprocess.run(
        cmd,
        cwd=repo_root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env
    )

    passed = (proc.returncode == 0)
    return {
        "boundary": boundary,
        "certified": passed and len(missing_tests) == 0,
        "exit_code": proc.returncode,
        "existing_tests": existing_tests,
        "missing_tests": missing_tests,
        "stdout": proc.stdout.strip(),
        "stderr": proc.stderr.strip()
    }


def main():
    parser = argparse.ArgumentParser(description="Certify SeekHarness runtime boundaries via automated invariant tests.")
    parser.add_argument("--boundary", default="battle_db", choices=list(BOUNDARY_TEST_MAP.keys()), help="Boundary to certify")
    parser.add_argument("--all", action="store_true", help="Certify all runtime boundaries")
    parser.add_argument("--json", action="store_true", help="Output JSON format")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parent.parent.parent.parent.parent
    if not (repo_root / "backend").exists():
        repo_root = Path.cwd()

    if args.all:
        results = [run_boundary_tests(repo_root, b) for b in BOUNDARY_TEST_MAP.keys()]
        if args.json:
            print(json.dumps(results, indent=2))
        else:
            print("==================================================")
            print("         RUNTIME BOUNDARIES CERTIFICATION         ")
            print("==================================================")
            for r in results:
                mark = "[CERTIFIED]" if r["certified"] else "[UNVERIFIED]"
                print(f"{mark:<14} {r['boundary']}")
            print("==================================================")
        return

    res = run_boundary_tests(repo_root, args.boundary)
    if args.json:
        print(json.dumps(res, indent=2))
        return

    print("==================================================")
    print(f" BOUNDARY CERTIFICATION: {args.boundary}")
    print("==================================================")
    status_str = "CERTIFIED" if res["certified"] else "FAILED"
    print(f"Status       : {status_str}")
    print(f"Exit Code    : {res.get('exit_code')}")
    if res.get("missing_tests"):
        print(f"Missing Tests: {res['missing_tests']}")
    if res.get("stdout"):
        print(f"Output       : {res['stdout'][:200]}")
    print("==================================================")


if __name__ == "__main__":
    main()
