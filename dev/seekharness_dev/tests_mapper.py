from pathlib import Path


def get_test_groups(repo_root: Path) -> dict:
    backend_tests = repo_root / "backend" / "tests"
    groups = [
        {
            "name": "core_health",
            "description": "FastAPI health and basic endpoints",
            "path": str(backend_tests / "test_health.py")
        },
        {
            "name": "security_boundaries",
            "description": "Fighter sandbox isolation, network egress, command guards",
            "path": str(backend_tests / "test_fighter_tool_boundaries.py")
        },
        {
            "name": "semantic_verification",
            "description": "Builder vs Breaker deterministic verification assertions",
            "path": str(backend_tests / "test_builder_breaker_semantic_verification.py")
        },
        {
            "name": "battle_database_lifecycle",
            "description": "Ephemeral database provisioning and isolation",
            "path": str(backend_tests / "test_battle_database_lifecycle.py")
        },
        {
            "name": "finalization_audit",
            "description": "Idempotent transactional finalization & Elo ratings",
            "path": str(backend_tests / "test_finalization_transactional_audit.py")
        },
        {
            "name": "fullstack_e2e",
            "description": "Hermetic fullstack battle simulation",
            "path": str(backend_tests / "test_fullstack_arena_e2e.py")
        }
    ]

    # Filter only paths that exist on disk
    valid_groups = [g for g in groups if Path(g["path"]).exists()]

    return {"test_groups": valid_groups}
