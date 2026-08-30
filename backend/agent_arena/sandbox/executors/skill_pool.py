"""Load battle skill bodies from .agents/skills (or ARENA_SKILLS_ROOT).

Richer frontmatter (C8): name, description, version, tier, category, tags,
prerequisites, capabilities, allowed_environments. Exposes load_skill,
list_skills, filter_skills, validate_skill (explicit errors), resolve_prerequisites.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from ...skills import apply_canonical_metadata

BATTLE_SKILL_NAMES = (
    "secure-code-execution",
    "sandbox-runtime-engineer",
    "artifact-workspace-versioning",
    "realtime-execution-streaming",
    "battle-runtime-observability",
    "terminal-sandbox-ui",
    "python-kata-fixer",
)

REQUIRED_FIELDS = ("name", "description")

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
_LIST_RE = re.compile(r"[,\n]")


def skills_root() -> Path:
    env = os.environ.get("ARENA_SKILLS_ROOT", "").strip()
    if env:
        return Path(env)
    mounted = Path("/opt/arena-skills")
    if mounted.is_dir():
        return mounted
    return Path(__file__).resolve().parents[4] / ".agents" / "skills"


def _parse_frontmatter(text: str) -> dict[str, object]:
    """Parse simple YAML-ish frontmatter used by arena skills.

    Supports flat `key: value`, nested `metadata:` blocks (flattened into the
    top level), folded `>` / `>-` / `|` scalars, quoted values, and lists.
    """
    meta: dict[str, object] = {}
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return meta

    lines = m.group(1).splitlines()
    current_key: str | None = None
    folded: list[str] = []  # continuation lines for current folded/block key
    in_metadata = False  # we are inside a nested metadata: block

    def flush() -> None:
        nonlocal current_key, folded
        if current_key:
            if folded:
                meta[current_key] = _coerce_value(" ".join(folded).strip().strip("\"'"))
            folded = []
        current_key = None

    for line in lines:
        if not line.strip():
            flush()
            in_metadata = False
            continue
        indent = len(line) - len(line.lstrip())
        stripped = line.strip()
        if indent > 0 and current_key:
            # continuation of folded/block scalar, or nested key under metadata
            if ":" in stripped and indent > 0 and current_key == "metadata":
                k, v = stripped.split(":", 1)
                meta[k.strip()] = _coerce_value(v.strip().strip("\"'"))
            else:
                folded.append(stripped)
            continue
        flush()
        if ":" not in stripped:
            continue
        k, v = stripped.split(":", 1)
        key = k.strip()
        val = v.strip()
        if key == "metadata":
            in_metadata = True
            current_key = "metadata"
            folded = []
            continue
        if val in (">", ">-", "|"):
            current_key = key
            folded = []
            continue
        meta[key] = _coerce_value(val.strip("\"'"))
    flush()
    return meta


def _coerce_value(val: str):
    lowered = val.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    if re.fullmatch(r"\d+", val):
        return int(val)
    if re.fullmatch(r"\d+\.\d+", val):
        return float(val)
    return val


def _parse_list(meta: dict[str, object], key: str) -> list[str]:
    raw = meta.get(key)
    if raw is None:
        return []
    if isinstance(raw, list):
        return [str(x).strip() for x in raw if str(x).strip()]
    return [x.strip() for x in _LIST_RE.split(str(raw)) if x.strip()]


def _skill_dict(name: str, path: Path, text: str) -> dict:
    meta = _parse_frontmatter(text)
    desc = (str(meta.get("description") or "")).strip() or f"Skill {name}"
    if len(desc) > 240:
        desc = desc[:237] + "..."
    skill_id = _slugify(str(meta.get("name") or name))
    legacy = {
        "id": skill_id,
        "name": str(meta.get("name") or name),
        "slug": skill_id,
        "desc": desc,
        "description": str(meta.get("description") or desc),
        "version": str(meta.get("version") or "0.1.0"),
        "tier": str(meta.get("tier") or "general"),
        "category": str(meta.get("category") or "general"),
        "tags": _parse_list(meta, "tags"),
        "prerequisites": _parse_list(meta, "prerequisites"),
        "capabilities": _parse_list(meta, "capabilities"),
        "allowed_environments": _parse_list(meta, "allowed_environments"),
        "elo": 1200,
        "path": str(path),
        "body": text,
    }
    return apply_canonical_metadata(legacy)


def _slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def load_skill(name: str, root: Path | None = None) -> dict:
    """Load a single skill by name or slug. Raises FileNotFoundError if absent."""
    base = root or skills_root()
    exact = base / name / "SKILL.md"
    if exact.is_file():
        return _skill_dict(
            name, exact, exact.read_text(encoding="utf-8", errors="ignore")
        )
    for child in base.iterdir() if base.is_dir() else []:
        if child.is_dir() and _slugify(child.name) == _slugify(name):
            p = child / "SKILL.md"
            if p.is_file():
                return _skill_dict(
                    child.name, p, p.read_text(encoding="utf-8", errors="ignore")
                )
    raise FileNotFoundError(f"skill not found: {name} (in {base})")


def list_skills(root: Path | None = None) -> list[dict]:
    """Return all skills (full metadata, no bodies)."""
    base = root or skills_root()
    out: list[dict] = []
    if not base.is_dir():
        return out
    for child in sorted(base.iterdir()):
        if child.is_dir():
            p = child / "SKILL.md"
            if p.is_file():
                s = _skill_dict(
                    child.name, p, p.read_text(encoding="utf-8", errors="ignore")
                )
                s["body"] = ""
                out.append(s)
    return out


def filter_skills(
    query: str | None = None,
    *,
    tags: list[str] | None = None,
    category: str | None = None,
    tier: str | None = None,
    root: Path | None = None,
) -> list[dict]:
    """Filter skills by free-text query, tags, category, or tier."""
    skills = list_skills(root)
    if tags:
        skills = [s for s in skills if set(tags).intersection(set(s["tags"]))]
    if category:
        skills = [s for s in skills if s["category"] == category]
    if tier:
        skills = [s for s in skills if s["tier"] == tier]
    if query:
        q = query.lower()
        skills = [
            s
            for s in skills
            if q in s["name"].lower()
            or q in s["desc"].lower()
            or q in [t.lower() for t in s["tags"]]
        ]
    return skills


def validate_skill(text: str, name: str = "skill") -> list[str]:
    """Return a list of explicit errors (empty list = valid). Never silent."""
    errors: list[str] = []
    meta = _parse_frontmatter(text)
    if not _FRONTMATTER_RE.match(text):
        errors.append(f"{name}: missing --- frontmatter block")
    for field in REQUIRED_FIELDS:
        if not str(meta.get(field) or "").strip():
            errors.append(f"{name}: missing required frontmatter field '{field}'")
    if not text.strip():
        errors.append(f"{name}: empty SKILL.md body")
    for cap in _parse_list(meta, "capabilities"):
        if " " in cap or not cap:
            errors.append(f"{name}: invalid capability token {cap!r}")
    tier = str(meta.get("tier") or "")
    if tier and tier not in ("novice", "general", "advanced", "expert"):
        errors.append(f"{name}: invalid tier {tier!r} (novice|general|advanced|expert)")
    return errors


def resolve_prerequisites(
    skills: list[dict], pool: list[dict] | None = None
) -> list[str]:
    """Return names needed to satisfy all prerequisites across chosen skills.

    Missing prereqs are skipped (reported) rather than raising — selection
    should prune them.
    """
    available = {s["name"] for s in (pool or list_skills())}
    need: list[str] = []
    for s in skills:
        for p in s.get("prerequisites", []):
            if p in available and p not in {s["name"] for s in skills}:
                need.append(p)
    return sorted(set(need))


def load_skill_pool(root: Path | None = None) -> list[dict]:
    base = root or skills_root()
    pool: list[dict] = []
    for name in BATTLE_SKILL_NAMES:
        path = base / name / "SKILL.md"
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        pool.append(_skill_dict(name, path, text))
    return pool


def mount_skills(dest: Path, pool: list[dict | object]) -> Path:
    """Copy skill bodies into a participant workspace (read-only copies)."""
    skills_dir = dest / ".agents" / "skills"
    skills_dir.mkdir(parents=True, exist_ok=True)
    for s in pool:
        name = s.name if hasattr(s, "name") else s["name"]
        body = s.body if hasattr(s, "body") else s.get("body")
        desc = s.desc if hasattr(s, "desc") else s.get("desc", "")
        d = skills_dir / name
        d.mkdir(parents=True, exist_ok=True)
        target = d / "SKILL.md"
        target.write_text(
            body or f"# {name}\n{desc}\n", encoding="utf-8"
        )
        try:
            target.chmod(0o444)
        except OSError:
            pass
    return skills_dir
