"""Neon PostgreSQL + pgvector semantic memory engine (Mem0 compatible).

Provides deterministic vector embeddings and cosine-distance similarity search
backed directly by Neon PostgreSQL's native pgvector extension.
Enforces strict MemoryProvenance boundaries (user, model, role, visibility)
and safety content filtering before returning memory context to fighters.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import time
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .memory import (
    MemoryProvenance,
    is_memory_content_safe,
    is_provenance_eligible,
    sanitize_memory_content,
)
from .persistence.models import Memory
from .persistence.repositories import memories as mem_repo

log = logging.getLogger("agent_arena.mem0_pgvector")

EMBEDDING_DIM = 1536


def _deterministic_hash_vector(text: str, dim: int = EMBEDDING_DIM) -> list[float]:
    """Fallback deterministic unit vector generated via sha256 hashing.

    Guarantees that hermetic test runs, local offline development, and environments
    without active embedding API keys produce consistent, valid 1536-dim unit vectors.
    """
    clean = (text or "").strip().lower()
    if not clean:
        return [0.0] * dim

    words = clean.split()
    vec = [0.0] * dim
    for i, word in enumerate(words):
        h = hashlib.sha256(f"{word}_{i}".encode("utf-8")).digest()
        for b_idx, b in enumerate(h):
            idx = (i * 32 + b_idx) % dim
            vec[idx] += (b - 128) / 128.0

    # L2 normalize
    norm = math.sqrt(sum(x * x for x in vec))
    if norm > 0:
        vec = [round(x / norm, 6) for x in vec]
    return vec


def get_embedding(text: str) -> list[float]:
    """Generate a 1536-dimension embedding for text.

    Attempts OpenAI/OpenRouter embedding if configured; falls back cleanly
    to deterministic normalized hash vector if unconfigured or hermetic.
    """
    from .hermetic import hermetic_mode

    if hermetic_mode():
        return _deterministic_hash_vector(text)

    api_key = (
        os.environ.get("HOST_OPENAI_KEY")
        or os.environ.get("OPENAI_API_KEY")
        or os.environ.get("HOST_OPENROUTER_KEY")
    )
    if not api_key:
        return _deterministic_hash_vector(text)

    try:
        import httpx

        headers = {"Authorization": f"Bearer {api_key}"}
        base_url = (
            "https://openrouter.ai/api/v1"
            if api_key.startswith("sk-or-") or os.environ.get("HOST_OPENROUTER_KEY") == api_key
            else "https://api.openai.com/v1"
        )
        model = "text-embedding-3-small"
        payload = {"input": text[:8000], "model": model}

        resp = httpx.post(
            f"{base_url}/embeddings",
            json=payload,
            headers=headers,
            timeout=5.0,
        )
        if resp.status_code == 200:
            data = resp.json()
            vec = data["data"][0]["embedding"]
            if len(vec) == EMBEDDING_DIM:
                return vec
    except Exception as exc:
        log.debug("Remote embedding failed, using deterministic fallback: %s", exc)

    return _deterministic_hash_vector(text)


class NeonPgVectorMem0Store:
    """Mem0-compatible interface backed directly by Neon PostgreSQL + pgvector."""

    def __init__(self, session: Session):
        self.session = session

    def add(
        self,
        *,
        insight: str,
        user_id: str = "villain",
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
        context_mode: str = "adaptive",
        source_result_id: str = "",
    ) -> dict[str, Any]:
        """Store a provenance-gated, safety-sanitized memory with pgvector embedding."""
        combined = f"{insight} {theory}".strip()
        if not is_memory_content_safe(combined):
            insight = sanitize_memory_content(insight)
            theory = sanitize_memory_content(theory)

        embedding = get_embedding(combined)

        row = mem_repo.memory_create(
            self.session,
            user_id=user_id or "villain",
            insight=insight[:2000],
            tokens=insight.lower().split(),
            battle_id=battle_id,
            model_id=model_id,
            format=format_name,
            chosen_skills=chosen_skills or [],
            theory=(theory or "")[:500],
            outcome=outcome,
            target_id=target_id or format_name,
            role=role or "general",
            visibility_class=visibility_class,
            authoritative_status=authoritative_status,
            context_mode=context_mode,
            source_result_id=source_result_id,
        )
        row.embedding = embedding
        self.session.flush()
        return mem_repo.memory_to_dict(row)

    def search(
        self,
        query: str,
        *,
        user_id: str = "",
        model_id: str = "",
        role: str = "",
        target_id: str = "",
        limit: int = 5,
        context_mode: str = "strict",
        skills: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Perform semantic cosine distance retrieval using Neon pgvector."""
        mode = str(context_mode or "strict").lower().strip()
        if mode not in ("adaptive", "assisted"):
            # Strict Benchmark Mode: Zero historical memories are returned
            return []

        if not query.strip():
            return []

        query_vec = get_embedding(query)
        skills = skills or []

        # Cosine distance ordering: Memory.embedding.cosine_distance(query_vec)
        dist = Memory.embedding.cosine_distance(query_vec)
        stmt = (
            select(Memory, dist.label("distance"))
            .where(Memory.embedding.is_not(None))
            .order_by(dist.asc())
            .limit(limit * 5)
        )

        results = self.session.execute(stmt).all()
        scored: list[dict[str, Any]] = []

        for row, distance in results:
            data = mem_repo.memory_to_dict(row)
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

            # Cosine similarity is 1.0 - cosine_distance
            sim = max(0.0, 1.0 - float(distance or 1.0))
            skill_bonus = 0.15 * len(set(skills) & set(data.get("chosen_skills") or []))
            recency_days = max(0.0, (time.time() - float(data.get("created_at") or 0)) / 86400)
            recency_penalty = 1.0 + 0.02 * min(30, recency_days)

            final_score = round((sim + skill_bonus) / recency_penalty, 4)
            data["score"] = final_score
            data["distance"] = round(float(distance or 0.0), 4)
            scored.append(data)

        scored.sort(key=lambda m: m["score"], reverse=True)
        return scored[:limit]
