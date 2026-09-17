#!/usr/bin/env python3
"""
orient.py - Deterministic orientation script for SeekHarness.
Runs preflight checks and lifecycle inspection to identify the next active boundary.
"""

import argparse
import json
import subprocess
import sys


def run_cmd(cmd: list[str]) -> dict:
    try:
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
        return json.loads(proc.stdout)
    except subprocess.CalledProcessError as e:
        return {"error": f"Command failed with exit code {e.returncode}", "details": e.stderr}
    except Exception as e:
        return {"error": str(e)}


BOUNDARY_ORDER = [
    ("semantic_verification", "Semantic Verification & Target Guard"),
    ("battle_db", "Battle DB & Ephemeral Branch Isolation"),
    ("service_lifecycle", "Service Lifecycle & Sandbox Reaper"),
    ("breaker_handoff", "Breaker Handoff & Network Policy"),
    ("trusted_completion", "Trusted Completion & Transactional Audit")
]


def determine_next_boundary(lifecycle_data: dict) -> dict:
    if "error" in lifecycle_data or not isinstance(lifecycle_data, dict):
        return {
            "stage": "UNKNOWN",
            "name": "UNKNOWN",
            "status": "UNKNOWN",
            "reason": "Unable to deterministically parse lifecycle status."
        }

    for key, name in BOUNDARY_ORDER:
        status = lifecycle_data.get(key, "MISSING")
        if status in ("PARTIAL", "MISSING", "FAILED"):
            return {
                "stage": key,
                "name": name,
                "status": status,
                "reason": f"Boundary '{key}' is currently {status} and requires certification."
            }

    return {
        "stage": "COMPLETE",
        "name": "All Boundaries Certified",
        "status": "VERIFIED",
        "reason": "All 5 core architectural boundaries have been certified."
    }


def main():
    parser = argparse.ArgumentParser(
        description="SeekHarness Orientation Tool: Determines current workspace status and next active boundary."
    )
    parser.add_argument("--json", action="store_true", help="Output results in JSON format")
    args = parser.parse_args()

    preflight = run_cmd(["seekharness-dev", "preflight", "--json"])
    lifecycle = run_cmd(["seekharness-dev", "lifecycle", "--json"])
    next_boundary = determine_next_boundary(lifecycle)

    result = {
        "preflight": preflight,
        "lifecycle": lifecycle,
        "next_boundary": next_boundary
    }

    if args.json:
        print(json.dumps(result, indent=2))
        return

    print("==================================================")
    print("           SEEKHARNESS ORIENTATION                ")
    print("==================================================")
    status_str = "OK" if preflight.get("status") == "healthy" else "DEGRADED"
    print(f"Preflight Status: {status_str}")
    if "checks" in preflight:
        for c in preflight["checks"]:
            mark = "[PASS]" if c.get("status") == "pass" else "[WARN]"
            print(f"  {mark} {c.get('name')}: {c.get('details')}")

    print("\nLifecycle Boundaries:")
    for key, name in BOUNDARY_ORDER:
        st = lifecycle.get(key, "UNKNOWN")
        print(f"  - {name:<42} : {st}")

    print("\nNext Active Boundary:")
    print(f"  Stage ID   : {next_boundary.get('stage')}")
    print(f"  Stage Name : {next_boundary.get('name')}")
    print(f"  Status     : {next_boundary.get('status')}")
    print(f"  Action     : {next_boundary.get('reason')}")
    print("==================================================")


if __name__ == "__main__":
    main()
