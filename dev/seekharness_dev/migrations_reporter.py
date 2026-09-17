import re
from pathlib import Path


def get_migrations_data(repo_root: Path) -> dict:
    versions_dir = repo_root / "backend" / "alembic" / "versions"
    data = {
        "head": "NONE",
        "revisions": []
    }

    if not versions_dir.exists():
        return data

    py_files = sorted(versions_dir.glob("*.py"))
    for pf in py_files:
        try:
            content = pf.read_text(encoding="utf-8")
            rev_match = re.search(r"revision\s*(?::\s*str)?\s*=\s*['\"]([^'\"]+)['\"]", content)
            down_match = re.search(r"down_revision\s*(?::\s*Union\[[^\]]+\]|\s*:\s*str|\s*:\s*None)?\s*=\s*['\"]?([^'\"\n]+)['\"]?", content)
            rev_id = rev_match.group(1) if rev_match else pf.stem
            down_rev = down_match.group(1).strip() if down_match else None
            if down_rev == "None":
                down_rev = None

            data["revisions"].append({
                "revision": rev_id,
                "down_revision": down_rev,
                "file": pf.name
            })
        except Exception:
            data["revisions"].append({"revision": pf.stem, "file": pf.name})

    if data["revisions"]:
        data["head"] = data["revisions"][-1]["revision"]

    return data
