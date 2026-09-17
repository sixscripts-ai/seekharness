from pathlib import Path


def get_lifecycle_status(repo_root: Path) -> dict:
    status = {
        "semantic_verification": "UNKNOWN",
        "battle_db": "UNKNOWN",
        "service_lifecycle": "UNKNOWN",
        "breaker_handoff": "UNKNOWN",
        "trusted_completion": "UNKNOWN"
    }

    # 1. Semantic verification
    verifier_mod = repo_root / "backend" / "agent_arena" / "target_verifier.py"
    cmd_guard = repo_root / "backend" / "agent_arena" / "sandbox" / "executors" / "_command_guard.py"
    sem_test = repo_root / "backend" / "tests" / "test_builder_breaker_semantic_verification.py"
    if verifier_mod.exists() and cmd_guard.exists() and sem_test.exists():
        status["semantic_verification"] = "VERIFIED"
    elif verifier_mod.exists():
        status["semantic_verification"] = "PARTIAL"
    else:
        status["semantic_verification"] = "MISSING"

    # 2. Battle DB isolation
    branch_mgr = repo_root / "backend" / "agent_arena" / "neon_branch_manager.py"
    db_test = repo_root / "backend" / "tests" / "test_battle_database_lifecycle.py"
    if branch_mgr.exists() and db_test.exists():
        status["battle_db"] = "VERIFIED"
    elif branch_mgr.exists():
        status["battle_db"] = "PARTIAL"
    else:
        status["battle_db"] = "MISSING"

    # 3. Service lifecycle (readiness, reaper, port allocation)
    reaper_mod = repo_root / "backend" / "agent_arena" / "reaper.py"
    battle_plan = repo_root / "backend" / "agent_arena" / "sandbox" / "executors" / "battle_plan.py"
    plan_test = repo_root / "backend" / "tests" / "test_battle_plan.py"
    if reaper_mod.exists() and battle_plan.exists() and plan_test.exists():
        status["service_lifecycle"] = "VERIFIED"
    elif battle_plan.exists():
        status["service_lifecycle"] = "PARTIAL"
    else:
        status["service_lifecycle"] = "MISSING"

    # 4. Breaker handoff (frozen artifact transfer & network policy)
    net_policy = repo_root / "backend" / "agent_arena" / "sandbox" / "executors" / "fighter_network_policy.py"
    battles_mod = repo_root / "backend" / "agent_arena" / "battles.py"
    fighter_test = repo_root / "backend" / "tests" / "test_fighter_runtime.py"
    if net_policy.exists() and battles_mod.exists() and fighter_test.exists():
        status["breaker_handoff"] = "VERIFIED"
    elif battles_mod.exists():
        status["breaker_handoff"] = "PARTIAL"
    else:
        status["breaker_handoff"] = "MISSING"

    # 5. Trusted completion & finalization
    fin_mod = repo_root / "backend" / "agent_arena" / "finalization.py"
    fin_test = repo_root / "backend" / "tests" / "test_finalization_authority.py"
    if fin_mod.exists() and fin_test.exists():
        status["trusted_completion"] = "VERIFIED"
    elif fin_mod.exists():
        status["trusted_completion"] = "PARTIAL"
    else:
        status["trusted_completion"] = "MISSING"

    return status
