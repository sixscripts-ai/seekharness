import os
import yaml
from pathlib import Path


def inspect_target(repo_root: Path, target_name: str) -> dict:
    target_dir = repo_root / "targets" / "library" / target_name
    if not target_dir.exists():
        target_dir = repo_root / "targets" / target_name

    if not target_dir.exists():
        return {
            "error": f"Target '{target_name}' not found",
            "searched_paths": [
                str(repo_root / "targets" / "library" / target_name),
                str(repo_root / "targets" / target_name)
            ]
        }

    manifest_file = target_dir / "target.yaml"
    manifest_data = {}
    if manifest_file.exists():
        try:
            with open(manifest_file, "r") as f:
                manifest_data = yaml.safe_load(f) or {}
        except Exception as e:
            manifest_data = {"parse_error": str(e)}

    # Evaluator check
    hidden_tests = target_dir / "tests" / "hidden"
    evaluator_available = hidden_tests.exists() and len(list(hidden_tests.glob("*"))) > 0

    # Tests check
    test_files = [str(p.relative_to(target_dir)) for p in target_dir.glob("tests/**/*.py")]

    return {
        "target_name": target_name,
        "path": str(target_dir),
        "manifest_path": str(manifest_file) if manifest_file.exists() else None,
        "ranked": bool(manifest_data.get("ranked", False)),
        "network": bool(manifest_data.get("network", False)),
        "evaluator_available": evaluator_available,
        "services": manifest_data.get("services", []),
        "test_files": test_files
    }
