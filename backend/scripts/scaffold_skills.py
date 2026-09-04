"""Populate canonical SKILL.md and directory structure for all skills in catalog.v0.3.yaml."""

import yaml
from pathlib import Path

catalog_path = Path(__file__).resolve().parents[1] / "agent_arena" / "skills" / "catalog.v0.3.yaml"
repo_root = Path(__file__).resolve().parents[2]
skills_dir = repo_root / ".agents" / "skills"

with open(catalog_path, encoding="utf-8") as f:
    catalog = yaml.safe_load(f)

skills_list = catalog.get("skills", [])
print(f"Loaded {len(skills_list)} skills from catalog.")

for skill in skills_list:
    s_id = skill["id"]
    s_dir = skills_dir / s_id
    s_dir.mkdir(parents=True, exist_ok=True)
    
    # Subdirectories per Agent Skills specification
    (s_dir / "scripts").mkdir(exist_ok=True)
    (s_dir / "scripts" / ".gitkeep").touch(exist_ok=True)
    
    (s_dir / "references").mkdir(exist_ok=True)
    ref_file = s_dir / "references" / "REFERENCE.md"
    if not ref_file.exists():
        ref_file.write_text(
            f"# Reference Guide for {s_id}\n\n"
            f"Detailed diagnostic patterns and extended guidance for `{s_id}`.\n",
            encoding="utf-8"
        )
        
    (s_dir / "assets").mkdir(exist_ok=True)
    (s_dir / "assets" / ".gitkeep").touch(exist_ok=True)
    
    (s_dir / "examples").mkdir(exist_ok=True)
    (s_dir / "examples" / ".gitkeep").touch(exist_ok=True)
    
    skill_md = s_dir / "SKILL.md"
    
    # Don't overwrite the 9 pre-existing core skills
    pre_existing = {
        "artifact-workspace-versioning",
        "battle-runtime-observability",
        "deepeval",
        "live-battle-telemetry-synthesizer",
        "python-kata-fixer",
        "realtime-execution-streaming",
        "sandbox-runtime-engineer",
        "secure-code-execution",
        "terminal-sandbox-ui",
    }
    if s_id in pre_existing and skill_md.exists():
        continue

    name_title = " ".join(word.capitalize() for word in s_id.split("-"))
    summary = skill.get("summary", "").strip()
    indexes = skill.get("indexes", [])
    primary_idx = indexes[0] if indexes else "general"
    other_indexes = indexes[1:] if len(indexes) > 1 else []
    related = skill.get("related_skills", [])
    foundations = skill.get("suggested_foundations", [])
    discovery_strong = skill.get("discovery", {}).get("strong", [])
    discovery_normal = skill.get("discovery", {}).get("normal", [])
    cost = skill.get("context_cost_class", "medium")
    roles = ", ".join(skill.get("roles", ["general"]))
    runtimes = ", ".join(skill.get("runtimes", ["*"]))
    
    trigger_words = ", ".join(discovery_strong + discovery_normal)
    related_md = "\n".join([f"- `{r}`" for r in related]) if related else "- None"
    foundations_md = "\n".join([f"- `{f}`" for f in foundations]) if foundations else "- None"
    indexes_md = "\n".join([f"- `{idx}`" for idx in indexes])

    content = f"""---
name: {s_id}
description: >
  {summary} Use this skill when diagnosing {primary_idx} or when seeing signals: {trigger_words}.
license: MIT
compatibility: No special requirements
metadata:
  author: sixscripts-ai
  version: "1.0.0"
  context_cost: "{cost}"
  roles: "{roles}"
  runtimes: "{runtimes}"
---

# {name_title}

## Overview

{summary}

- **Primary Index**: `{primary_idx}`
- **Context Cost**: `{cost}`
- **Applicable Roles**: `{roles}`

### Graph Indexes
{indexes_md}

### Suggested Foundations
{foundations_md}

## Step-by-Step Instructions

1. **Observe and Collect Baseline**:
   - Inspect visible logs, test outputs, or error traces without modifying code.
   - Run `TOOL read`, `TOOL grep`, or `TOOL ls` to understand the current workspace state.

2. **Formulate Hypotheses**:
   - Match symptoms against domain patterns for `{primary_idx}`.
   - Separate verified facts from unverified assumptions.

3. **Verify with Targeted Probing**:
   - Execute targeted tests (`TOOL test`) or specific diagnostics.
   - Narrow down failure points before changing implementation logic.

4. **Apply Minimal Targeted Changes**:
   - Make small, localized edits using `TOOL write` preserving existing conventions.
   - Keep changes isolated to the required fix.

5. **Validate and Regression-Test**:
   - Re-run test suites with `TOOL test`.
   - Confirm the defect is resolved and no unrelated tests were broken.

## Gotchas & Failure Modes

- Avoid speculative refactoring before establishing reproducible evidence.
- Do not assume external network access is available unless explicitly permitted by the target.
- Path operations must stay within the assigned workspace.

## Related Skills

{related_md}

## References

- Read [`references/REFERENCE.md`](references/REFERENCE.md) for deeper implementation patterns.
"""
    skill_md.write_text(content, encoding="utf-8")

print("Skill scaffolding complete.")
