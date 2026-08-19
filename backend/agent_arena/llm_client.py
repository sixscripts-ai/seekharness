"""OpenAI-compatible chat completions for user providers and host free model."""

from __future__ import annotations

import httpx
from fastapi import HTTPException

from .ssrf import validate_base_url


def build_headers(auth_style: str, api_key: str) -> dict[str, str]:
    if auth_style == "modal_proxy":
        parts = [p.strip() for p in api_key.split(":")]
        if len(parts) != 2:
            raise HTTPException(
                status_code=400, detail="modal_proxy key must be 'wk-...:ws-...'"
            )
        return {"Modal-Key": parts[0], "Modal-Secret": parts[1]}
    return {"Authorization": f"Bearer {api_key}"}


def chat_completion(
    *,
    base_url: str,
    auth_style: str,
    api_key: str,
    model: str,
    messages: list[dict],
    max_tokens: int = 1024,
    temperature: float = 0.7,
    timeout: float = 300.0,
    response_format: dict | None = None,
) -> str:
    headers = build_headers(auth_style, api_key)
    base_url = validate_base_url(base_url)
    url = base_url.rstrip("/") + "/chat/completions"
    payload: dict = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    if response_format is not None:
        payload["response_format"] = response_format
    try:
        resp = httpx.post(url, headers=headers, json=payload, timeout=timeout)
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=502, detail=f"LLM request failed: {exc}"
        ) from exc
    if resp.status_code != 200:
        raise HTTPException(
            status_code=502,
            detail=f"LLM returned {resp.status_code}: {resp.text[:300]}",
        )
    data = resp.json()
    try:
        return data["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError, TypeError) as exc:
        raise HTTPException(status_code=502, detail="Malformed LLM response") from exc
