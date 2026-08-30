"""Appwrite / Postgres-backed battle memory (Change Set B Hardened).

Provides provenance-first, model-scoped, user-scoped, mode-gated, and safety-sanitized battle memory.
- Strict Benchmark Mode: Zero memories are retrieved (returns []).
- Adaptive Mode: Retrieves compact, safe model-scoped and user-scoped lessons.
- Provenance Gate: Evaluator-private, opponent-private, cross-user, or unverified memories
  are structurally rejected before content is even examined.
- Secondary Safety Filtering: Rejects hidden tests, reference solutions, secrets, and credentials.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from typing import Any

from appwrite.query import Query

_STOPWORDS = {
    "a", "an", "the", "and", "or", "of", "to", "in", "on", "for", "with",
    "by", "as", "at", "from", "into", "that", "this", "which", "was", "were",
    "is", "are", "be", "been", "have", "has", "had", "it", "its", "their",
    "they", "we", "you", "your", "our", "not", "no", "but", "do", "does",
    "did", "then", "than", "also", "each", "every", "after", "before",
    "between", "during", "will", "would", "should", "could", "can", "may",
}
_TOKEN_RE = re.compile(r"[a-z0-9]{3,}")

# Safety patterns for forbidden content (secondary defense-in-depth)
_FORBIDDEN_PATTERNS = [
    re.compile(r"FLAG\{[^\}]+\}", re.IGNORECASE),
    re.compile(r"\b(?:sk-[a-zA-Z0-9_-]{20,}|bearer\s+[a-zA-Z0-9_\-\.]{20,})\b", re.IGNORECASE),
    re.compile(r"\b(?:appwrite_api_key|fernet_key|internal_api_key|host_credentials)\b", re.IGNORECASE),
    re.compile(r"\b(?:test_target\.py|test_verifier|verifier_environment)\b", re.IGNORECASE),
    re.compile(r"\b(?:reference_solution|hidden_tests?|challenge_secret)\b", re.IGNORECASE),
    re.compile(r"\b(?:opponent_private|breaker_private|builder_private_pre_handoff)\b", re.IGNORECASE),
]

from .results import is_infra_outcome, is_learnable_model_outcome


@dataclass
class MemoryProvenance:
    user_id: str = "villain"
    model_id: str = ""
    battle_id: str = ""
    target_id: str = ""
    role: str = "general"
    visibility_class: str = "model_private"  # public, model_private, evaluator_private, opponent_private
    authoritative_status: str = "verified_pass"  # verified_pass, verified_fail, unverified, infra_failure
    context_mode: str = "adaptive"
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "user_id": self.user_id,
            "model_id": self.model_id,
            "battle_id": self.battle_id,
            "target_id": self.target_id,
            "role": self.role,
            "visibility_class": self.visibility_class,
            "authoritative_status": self.authoritative_status,
            "context_mode": self.context_mode,
            "created_at": self.created_at,
        }


def is_provenance_eligible(
    memory_data: dict[str, Any],
    *,
    user_id: str,
    model_id: str,
    role: str = "",
    target_id: str = "",
) -> bool:
    """Primary Security Boundary: Check provenance and visibility rules.

    Evaluates structural eligibility BEFORE looking at textual content.
    """
    visibility = str(memory_data.get("visibility_class") or "model_private").lower()
    auth_status = str(memory_data.get("authoritative_status") or "verified_pass").lower()
    mem_user = str(memory_data.get("user_id") or "")
    mem_model = str(memory_data.get("model_id") or "")
    mem_role = str(memory_data.get("role") or "").lower()

    # Rule 1: Evaluator-private, opponent-private, and infra failures are structurally blocked
    if visibility in ("evaluator_private", "opponent_private", "forbidden"):
        return False
    if auth_status in ("infra_failure", "unverified", "invalid"):
        return False

    # Rule 2: User isolation (different user is always blocked)
    if user_id and mem_user and mem_user != user_id:
        return False

    # Rule 3: Model isolation (different model is blocked unless explicitly public)
    if visibility != "public":
        if model_id and mem_model and mem_model != model_id:
            return False

    # Rule 4: Cross-role boundary in asymmetric battles (Builder vs Breaker)
    if role:
        req_role = role.lower()
        if req_role == "breaker" and mem_role == "builder":
            return False
        if req_role == "builder" and mem_role == "breaker":
            return False

    return True


def is_memory_content_safe(text: str) -> bool:
    """Secondary defense: Verify text does not contain secrets, hidden tests, or private artifacts."""
    if not text:
        return True
    for pattern in _FORBIDDEN_PATTERNS:
        if pattern.search(text):
            return False
    return True


def sanitize_memory_content(text: str) -> str:
    """Redact any potential credentials, tokens, or private tags from memory text."""
    if not text:
        return ""
    sanitized = text
    for pattern in _FORBIDDEN_PATTERNS:
        sanitized = pattern.sub("[REDACTED_SAFEGUARD]", sanitized)
    return sanitized


def _tokens(text: str) -> list[str]:
    words = _TOKEN_RE.findall((text or "").lower())
    return [w for w in words if w not in _STOPWORDS]


def remember(
    databases,
    database_id: str,
    *,
    insight: str,
    battle_id: str = "",
    model_id: str = "",
    target_id: str = "",
    role: str = "general",
    visibility_class: str = "model_private",
    authoritative_status: str = "verified_pass",
    format_name: str = "",
    chosen_skills: list[str] | None = None,
    theory: str = "",
    outcome: str = "",
    user_id: str = "",
    context_mode: str = "adaptive",
    policy_status: str = "clean",
    **extra: Any,
) -> dict | None:
    """Persist one provenance-tagged and safety-sanitized battle memory."""
    combined = f"{insight} {theory}"
    if not is_memory_content_safe(combined):
        insight = sanitize_memory_content(insight)
        theory = sanitize_memory_content(theory)

    prov = MemoryProvenance(
        user_id=user_id or "villain",
        model_id=model_id,
        battle_id=battle_id,
        target_id=target_id or format_name,
        role=role or "general",
        visibility_class=visibility_class,
        authoritative_status=authoritative_status,
        context_mode=context_mode,
        created_at=time.time(),
    )

    payload = {
        **prov.to_dict(),
        "insight": insight[:2000],
        "tokens": _tokens(insight + " " + theory),
        "format": format_name,
        "chosen_skills": chosen_skills or [],
        "theory": (theory or "")[:500],
        "outcome": outcome,
    }
    try:
        doc = databases.create_document(database_id, "memories", "unique()", payload)
        return doc.data
    except Exception:
        return payload



def retrieve(
    databases,
    database_id: str,
    query: str,
    *,
    context_mode: str = "strict",
    limit: int = 5,
    user_id: str = "",
    model_id: str = "",
    role: str = "",
    target_id: str = "",
    skills: list[str] | None = None,
) -> list[dict]:
    """Retrieve relevant memories with provenance as primary security boundary.

    Strict Mode: Mode-gated to ALWAYS return [] (zero memories).
    Adaptive Mode: Enforces provenance boundaries (user, model, role, visibility)
    prior to secondary content safety filtering.
    """
    mode = str(context_mode or "strict").lower().strip()
    if mode not in ("adaptive", "assisted"):
        # Strict benchmark mode: strictly zero historical memory supplied
        return []

    skills = skills or []
    try:
        res = databases.list_documents(
            database_id,
            "memories",
            queries=[Query.limit(limit * 10 if limit else 50)],
        )
        raw_docs = res.documents
    except Exception:
        raw_docs = []

    docs = [dict(d.data if hasattr(d, "data") else d) for d in raw_docs]
    return _score_memory_docs(
        docs,
        query,
        limit=limit,
        user_id=user_id,
        model_id=model_id,
        role=role,
        target_id=target_id,
        skills=skills,
    )


def retrieve_pg(
    session,
    query: str,
    *,
    context_mode: str = "strict",
    limit: int = 5,
    user_id: str = "",
    model_id: str = "",
    role: str = "",
    target_id: str = "",
    skills: list[str] | None = None,
) -> list[dict]:
    """Postgres retrieve using the same Change Set B provenance gates."""
    mode = str(context_mode or "strict").lower().strip()
    if mode not in ("adaptive", "assisted"):
        return []
    from agent_arena.persistence.repositories import memories as mem_repo

    docs = [mem_repo.memory_to_dict(r) for r in mem_repo.memory_list_all(session, limit=200)]
    return _score_memory_docs(
        docs,
        query,
        limit=limit,
        user_id=user_id,
        model_id=model_id,
        role=role,
        target_id=target_id,
        skills=skills or [],
    )


def _score_memory_docs(
    docs: list[dict],
    query: str,
    *,
    limit: int,
    user_id: str,
    model_id: str,
    role: str,
    target_id: str,
    skills: list[str],
) -> list[dict]:
    q_tokens = set(_tokens(query))
    scored: list[dict] = []
    for data in docs:
        if not is_provenance_eligible(
            data,
            user_id=user_id,
            model_id=model_id,
            role=role,
            target_id=target_id,
        ):
            continue
        insight = str(data.get("insight") or "")
        theory = str(data.get("theory") or "")
        if not is_memory_content_safe(insight) or not is_memory_content_safe(theory):
            continue
        doc_tokens = set(data.get("tokens") or [])
        overlap = len(q_tokens & doc_tokens) if q_tokens else 0
        skill_bonus = 3 * len(set(skills) & set(data.get("chosen_skills") or []))
        recency = 1.0 + 0.05 * max(
            0, min(20, (time.time() - float(data.get("created_at") or 0)) / 86400)
        )
        score = overlap + skill_bonus
        if score <= 0:
            continue
        scored.append({"score": round(score / recency, 3), **data})
    scored.sort(key=lambda m: m["score"], reverse=True)
    return scored[:limit]
def forget(databases, database_id: str, older_than_days: int = 180) -> int:
    """Best-effort cleanup of stale memories. Returns number deleted."""
    cutoff = time.time() - older_than_days * 86400
    try:
        res = databases.list_documents(
            database_id,
            "memories",
            queries=[Query.limit(100)],
        )
        docs = res.documents
    except Exception:
        docs = []

    removed = 0
    for d in docs:
        if float(d.data.get("created_at") or 0) < cutoff:
            try:
                databases.delete_document(database_id, "memories", d.id)
                removed += 1
            except Exception:
                pass
    return removed


def dump(databases, database_id: str, limit: int = 20) -> list[dict]:
    """Recent memories as plain JSON (for stats/debug endpoints)."""
    try:
        res = databases.list_documents(
            database_id,
            "memories",
            queries=[Query.limit(limit)],
        )
        docs = res.documents
    except Exception:
        docs = []

    out = []
    for d in docs:
        data = dict(d.data)
        data.pop("tokens", None)
        data.pop("theory", None)
        out.append(data)
    return out


def encode_metadata(meta: dict) -> dict:
    """Coerce a JSON-safe metadata dict into Appwrite-friendly flat fields."""
    out: dict = {}
    for k, v in (meta or {}).items():
        if isinstance(v, (list, dict)):
            out[k] = json.dumps(v)
        else:
            out[k] = v
    return out


def novelty_score(
    databases,
    database_id: str,
    *,
    insight: str,
    skills: list[str] | None = None,
    theory: str = "",
) -> float:
    """Novelty fingerprint: 0.0 (duplicate) .. 1.0 (novel)."""
    q_tokens = set(_tokens(insight + " " + theory))
    if not q_tokens:
        return 1.0
    try:
        res = databases.list_documents(
            database_id,
            "memories",
            queries=[Query.limit(100)],
        )
        docs = res.documents
    except Exception:
        docs = []

    best_sim = 0.0
    seen_skills: set[str] = set()
    for d in docs:
        data = d.data
        doc_tokens = set(data.get("tokens") or [])
        if not doc_tokens:
            continue
        inter = len(q_tokens & doc_tokens)
        union = len(q_tokens | doc_tokens)
        best_sim = max(best_sim, inter / union)
        seen_skills.update(data.get("chosen_skills") or [])
    if not docs:
        return 1.0
    skills = skills or []
    diversity = (
        1.0
        if not seen_skills
        else min(
            1.0, 0.5 + 0.5 * len(set(skills) - seen_skills) / max(1, len(set(skills)))
        )
    )
    return round(max(0.0, 1.0 - best_sim) * diversity, 3)


def maybe_remember(
    databases, database_id: str, *, novelty_threshold: float = 0.25, **kwargs
) -> dict | None:
    """Persist a memory only if it represents a learnable authoritative outcome and clears novelty & safety gates."""
    outcome = str(kwargs.get("outcome") or "").strip().upper()
    policy_status = str(kwargs.get("policy_status") or "clean").lower()

    # Reject unlearnable infrastructure failures, crashes, and invalid policy violations
    if is_infra_outcome(outcome) or not is_learnable_model_outcome(outcome) or policy_status == "invalid":
        return None

    # Classify authoritative status
    if outcome in ("TEST_PASS", "PASS", "WIN", "JUDGE_ONLY"):
        kwargs.setdefault("authoritative_status", "verified_pass")
    elif outcome in ("TEST_FAIL", "STEP_BUDGET_EXCEEDED", "FAIL", "LOSS"):
        kwargs.setdefault("authoritative_status", "verified_fail")

    score = novelty_score(
        databases,
        database_id,
        insight=kwargs.get("insight", ""),
        skills=kwargs.get("chosen_skills"),
        theory=kwargs.get("theory", ""),
    )
    if score < novelty_threshold:
        return None
    return remember(databases, database_id, **kwargs)


def _novelty_from_records(
    records: list[dict],
    *,
    insight: str,
    skills: list[str] | None = None,
    theory: str = "",
) -> float:
    q_tokens = set(_tokens(insight + " " + theory))
    if not q_tokens:
        return 1.0
    best_sim = 0.0
    seen_skills: set[str] = set()
    for data in records:
        doc_tokens = set(data.get("tokens") or [])
        if not doc_tokens:
            continue
        inter = len(q_tokens & doc_tokens)
        union = len(q_tokens | doc_tokens)
        best_sim = max(best_sim, inter / union if union else 0.0)
        seen_skills.update(data.get("chosen_skills") or [])
    if not records:
        return 1.0
    skills = skills or []
    diversity = (
        1.0
        if not seen_skills
        else min(
            1.0, 0.5 + 0.5 * len(set(skills) - seen_skills) / max(1, len(set(skills)))
        )
    )
    return round(max(0.0, 1.0 - best_sim) * diversity, 3)


def maybe_remember_pg(
    session,
    *,
    novelty_threshold: float = 0.25,
    **kwargs,
) -> dict | None:
    """Persist a Postgres memory only if Change Set B policy would allow it."""
    outcome = str(kwargs.get("outcome") or "").strip().upper()
    policy_status = str(kwargs.get("policy_status") or "clean").lower()
    if is_infra_outcome(outcome) or not is_learnable_model_outcome(outcome) or policy_status == "invalid":
        return None
    user_id = str(kwargs.get("user_id") or "").strip()
    if not user_id:
        return None
    if outcome in ("TEST_PASS", "PASS", "WIN", "JUDGE_ONLY"):
        kwargs.setdefault("authoritative_status", "verified_pass")
    elif outcome in ("TEST_FAIL", "STEP_BUDGET_EXCEEDED", "FAIL", "LOSS"):
        kwargs.setdefault("authoritative_status", "verified_fail")

    from agent_arena.persistence.repositories import memories as mem_repo

    existing = [mem_repo.memory_to_dict(r) for r in mem_repo.memory_list_all(session, limit=200)]
    score = _novelty_from_records(
        existing,
        insight=str(kwargs.get("insight") or ""),
        skills=kwargs.get("chosen_skills"),
        theory=str(kwargs.get("theory") or ""),
    )
    if score < novelty_threshold:
        return None

    insight = str(kwargs.get("insight") or "")[:2000]
    theory = str(kwargs.get("theory") or "")[:500]
    combined = f"{insight} {theory}"
    if not is_memory_content_safe(combined):
        insight = sanitize_memory_content(insight)
        theory = sanitize_memory_content(theory)

    row = mem_repo.memory_create(
        session,
        user_id=user_id,
        insight=insight,
        tokens=_tokens(insight + " " + theory),
        battle_id=str(kwargs.get("battle_id") or "") or None,
        model_id=str(kwargs.get("model_id") or "") or None,
        format=str(kwargs.get("format_name") or kwargs.get("format") or "") or None,
        chosen_skills=list(kwargs.get("chosen_skills") or []),
        theory=theory,
        outcome=str(kwargs.get("outcome") or "") or None,
        target_id=str(kwargs.get("target_id") or "") or None,
        role=str(kwargs.get("role") or "general") or None,
        visibility_class=str(kwargs.get("visibility_class") or "model_private"),
        authoritative_status=str(kwargs.get("authoritative_status") or "verified_pass"),
        context_mode=str(kwargs.get("context_mode") or "adaptive"),
        source_result_id=str(kwargs.get("source_result_id") or "") or None,
    )
    return mem_repo.memory_to_dict(row)
