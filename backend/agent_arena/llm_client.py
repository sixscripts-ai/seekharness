"""OpenAI-compatible chat completions for user providers and host free model."""

from __future__ import annotations

import httpx
from fastapi import HTTPException

from .hermetic import assert_not_hermetic
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
    tools: list[dict] | None = None,
    tool_choice: str | None = None,
    return_response_obj: bool = False,
) -> str | ModelResponse:
    import time
    from .tool_protocol import ModelResponse

    assert_not_hermetic("model API")
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
    if tools is not None:
        payload["tools"] = tools
        if tool_choice:
            payload["tool_choice"] = tool_choice

    t0 = time.time()
    try:
        resp = httpx.post(url, headers=headers, json=payload, timeout=timeout)
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=502, detail=f"LLM request failed: {exc}"
        ) from exc
    latency_ms = int((time.time() - t0) * 1000)
    if resp.status_code != 200:
        raise HTTPException(
            status_code=502,
            detail=f"LLM returned {resp.status_code}: {resp.text[:300]}",
        )
    data = resp.json()
    try:
        choice = data["choices"][0]
        message = choice["message"]
        content = message.get("content") or ""
        native_tool_calls = message.get("tool_calls") or []
        finish_reason = choice.get("finish_reason")
    except (KeyError, IndexError, TypeError) as exc:
        raise HTTPException(status_code=502, detail="Malformed LLM response") from exc

    if return_response_obj:
        return ModelResponse(
            text=content,
            native_tool_calls=native_tool_calls,
            provider=base_url,
            model=model,
            raw_finish_reason=finish_reason,
            latency_ms=latency_ms,
        )

    if not content and native_tool_calls:
        # If content is empty but native tool calls exist, serialize for string callers
        import json
        return json.dumps([{"tool": tc.get("function", {}).get("name"), "arguments": json.loads(tc.get("function", {}).get("arguments", "{}"))} for tc in native_tool_calls])
    return content
