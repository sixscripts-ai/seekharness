"""Host-owned Kimi-K3 judge with retry, guarded JSON parse, and redaction."""

from __future__ import annotations

import json
import re
import time
from typing import Any

from fastapi import HTTPException

from . import llm_client
from .config import settings
from .redact import sanitize_artifact

DEFAULT_JUDGE_MODEL = "moonshotai/Kimi-K3"
DEFAULT_JUDGE_BASE = "https://inference.us-west.modal.direct/v1"
SCORE_MIN, SCORE_MAX = 0.0, 100.0
MAX_ATTEMPTS = 3


def _system_prompt(rubric: str, weights: dict[str, float] | None) -> str:
    weights_txt = json.dumps(weights or {})
    return f"""You are a rigorous, impartial AI battle judge.

## Rubric
{rubric}

## Scoring weights (JSON)
{weights_txt}

## Rules
- Score EACH model_id independently on a 0-100 scale.
- Do NOT favour models by prompt position or name length.
- Think step-by-step, then output ONLY a JSON object (no markdown fences):
{{
  "scores": {{"<model_id>": <float 0-100>, ...}},
  "reasoning": "<3-5 sentences>"
}}
"""


def _compact_artifacts(artifacts: list[dict], max_art_len: int = 1500) -> list[dict]:
    compacted: list[dict] = []
    for a in artifacts:
        if not isinstance(a, dict):
            continue
        art_str = str(a.get("artifact", ""))
        # Filter out verbose full-workspace snapshot file dumps
        if '"files":' in art_str and len(art_str) > 1000:
            continue
        if len(art_str) > max_art_len:
            art_str = art_str[:max_art_len] + "... [truncated]"
        compacted.append({
            "phase": a.get("phase", ""),
            "model_id": a.get("model_id", ""),
            "artifact": art_str,
            "role": a.get("role", ""),
        })
    return compacted


def _parse_json_object(raw: str) -> dict[str, Any]:
    text = (raw or "").strip()
    if not text:
        raise ValueError("Empty response from judge model")
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if not match:
            raise
        return json.loads(match.group(0))


def _clamp(score: float) -> float:
    return float(max(SCORE_MIN, min(SCORE_MAX, score)))


def _host_judge_spec() -> tuple[str, str, str, str]:
    s = settings()
    key = s.get("JUDGE_MODAL_KEY") or ""
    secret = s.get("JUDGE_MODAL_SECRET") or ""
    if not key or not secret:
        raise HTTPException(status_code=500, detail="Judge credentials not configured")
    base = s.get("JUDGE_MODAL_BASE") or DEFAULT_JUDGE_BASE
    model = s.get("JUDGE_MODAL_MODEL") or DEFAULT_JUDGE_MODEL
    return base, "modal_proxy", f"{key}:{secret}", model


def judge_battle(
    *,
    model_ids: list[str],
    artifacts: list[dict],
    rubric: str,
    weights: dict[str, float] | None = None,
    judge_model: str | None = None,
    call_spec: tuple[str, str, str, str] | None = None,
) -> dict[str, Any]:
    """Return {scores: {model_id: float}, justifications: {model_id: str}, judge_model: str}."""
    base_url, auth_style, api_key, model = call_spec or _host_judge_spec()
    if judge_model:
        model = judge_model

    user_payload = {
        "model_ids": model_ids,
        "artifacts": _compact_artifacts(artifacts),
    }
    messages = [
        {"role": "system", "content": _system_prompt(rubric, weights)},
        {"role": "user", "content": json.dumps(user_payload)},
    ]

    last_err: Exception | None = None
    raw = ""
    for attempt in range(MAX_ATTEMPTS):
        try:
            raw = llm_client.chat_completion(
                base_url=base_url,
                auth_style=auth_style,
                api_key=api_key,
                model=model,
                messages=messages,
                max_tokens=1024,
                temperature=0.1,
                response_format={"type": "json_object"},
            )
            parsed = _parse_json_object(raw)
            raw_scores = parsed.get("scores") or {}
            reasoning = sanitize_artifact(str(parsed.get("reasoning", "")))
            scores: dict[str, float] = {}
            justifications: dict[str, str] = {}
            for mid in model_ids:
                if mid not in raw_scores:
                    raise ValueError(f"missing score for {mid}")
                scores[mid] = _clamp(float(raw_scores[mid]))
                justifications[mid] = reasoning
            return {
                "scores": scores,
                "justifications": justifications,
                "judge_model": model,
            }
        except Exception as exc:  # noqa: BLE001 — retry then fail battle
            last_err = exc
            time.sleep(0.5 * (2**attempt))
    raise HTTPException(
        status_code=502, detail=f"Judge failed after retries: {last_err}"
    )
