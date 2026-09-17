import json
import subprocess
import time
import pytest
from pathlib import Path

DEV_CLI = Path(__file__).parent.parent / "seekharness-dev"

def run_cli(args):
    start = time.time()
    res = subprocess.run([str(DEV_CLI)] + args, capture_output=True, text=True)
    duration = time.time() - start
    return res, duration

def test_cli_exists():
    assert DEV_CLI.exists(), "seekharness-dev CLI executable must exist"

def test_preflight_command():
    res, duration = run_cli(["preflight", "--json"])
    assert res.returncode == 0, f"Error: {res.stderr}"
    assert duration < 2.0, f"Preflight took too long: {duration}s"
    data = json.loads(res.stdout)
    assert "repo_root" in data
    assert "branch" in data
    assert "dirty_files" in data
    assert isinstance(data["dirty_files"], list)
    assert "staged_files" in data
    assert "applicable_agents_files" in data
    assert "env_status" in data
    assert "migration_head" in data

def test_lifecycle_command():
    res, duration = run_cli(["lifecycle", "--json"])
    assert res.returncode == 0, f"Error: {res.stderr}"
    assert duration < 2.0
    data = json.loads(res.stdout)
    expected_keys = [
        "semantic_verification",
        "battle_db",
        "service_lifecycle",
        "breaker_handoff",
        "trusted_completion"
    ]
    valid_states = {"VERIFIED", "PARTIAL", "MISSING", "UNKNOWN"}
    for k in expected_keys:
        assert k in data, f"Missing key {k}"
        assert data[k] in valid_states, f"Invalid state {data[k]} for {k}"

def test_tests_command():
    res, duration = run_cli(["tests", "--json"])
    assert res.returncode == 0, f"Error: {res.stderr}"
    assert duration < 2.0
    data = json.loads(res.stdout)
    assert "test_groups" in data
    assert len(data["test_groups"]) > 0
    for group in data["test_groups"]:
        assert "name" in group
        assert "path" in group

def test_migrations_command():
    res, duration = run_cli(["migrations", "--json"])
    assert res.returncode == 0, f"Error: {res.stderr}"
    assert duration < 2.0
    data = json.loads(res.stdout)
    assert "head" in data
    assert "revisions" in data
    assert isinstance(data["revisions"], list)

def test_target_command():
    res, duration = run_cli(["target", "fullstack-bank-vault", "--json"])
    assert res.returncode == 0, f"Error: {res.stderr}"
    assert duration < 2.0
    data = json.loads(res.stdout)
    assert data["target_name"] == "fullstack-bank-vault"
    assert "ranked" in data
    assert "evaluator_available" in data
    assert "manifest_path" in data

def test_target_unknown():
    res, duration = run_cli(["target", "non-existent-target", "--json"])
    assert res.returncode != 0
    data = json.loads(res.stdout)
    assert "error" in data

def test_codex_health_command():
    res, duration = run_cli(["codex-health", "--json"])
    assert res.returncode in (0, 1)
    data = json.loads(res.stdout)
    assert "status" in data
    assert data["status"] in {"HEALTHY", "DEGRADED", "UNHEALTHY"}
