"""HTTP client for sandbox → backend /internal/* callbacks."""

from __future__ import annotations

import ipaddress
import threading
import time
from typing import Any, Protocol
from urllib.parse import urlsplit

import httpx


def _assert_egress_allowed(url: str) -> None:
    """Reject sandbox outbound requests to non-public / metadata endpoints.

    The sandbox's only sanctioned network target is the backend public URL.
    This is a defense-in-depth guard against compromised model code trying to
    reach the cloud metadata service (169.254.169.254) or other internal
    hosts. Modal's own network policy is the authoritative control; this
    guards the in-process and direct HTTP paths too.
    """
    try:
        parsed = urlsplit(url)
    except ValueError as exc:
        raise RuntimeError(f"Sandbox egress blocked: malformed URL") from exc

    scheme = parsed.scheme.lower()
    if scheme not in ("http", "https"):
        raise RuntimeError(f"Sandbox egress blocked: {scheme} scheme")

    host = parsed.hostname
    if not host:
        raise RuntimeError("Sandbox egress blocked: missing host")

    host = host.strip("[]").rstrip(".")
    try:
        addr = ipaddress.ip_address(host)
        if (
            not addr.is_global
            or addr.is_private
            or addr.is_loopback
            or addr.is_link_local
            or addr.is_multicast
            or addr.is_unspecified
        ):
            raise RuntimeError(f"Sandbox egress blocked: {host}")
        return
    except ValueError:
        # Hostname — resolve and validate all addresses (DNS-rebinding guard).
        import socket

        try:
            infos = socket.getaddrinfo(host, None)
        except socket.gaierror:
            # Non-resolvable host: let httpx surface the real error.
            return
        for info in infos:
            ip = info[4][0]
            try:
                a = ipaddress.ip_address(ip)
            except ValueError:
                continue
            if (
                not a.is_global
                or a.is_private
                or a.is_loopback
                or a.is_link_local
                or a.is_multicast
                or a.is_unspecified
            ):
                raise RuntimeError(f"Sandbox egress blocked: {host} -> {ip}")


class Transport(Protocol):
    def post(self, path: str, json: dict) -> dict: ...


class HttpTransport:
    def __init__(
        self,
        base_url: str,
        internal_key: str,
        timeout: float = 600.0,
        sandbox_token: str | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.internal_key = internal_key
        self.sandbox_token = sandbox_token
        self.timeout = timeout
        self.client = httpx.Client(timeout=timeout, follow_redirects=True)

    def post(self, path: str, json: dict) -> dict:
        url = self.base_url + path
        _assert_egress_allowed(url)
        headers: dict[str, str] = {}
        # Battle-scoped endpoints require the per-battle token. The legacy
        # global key is retained only as a fallback for environments that have
        # not yet been migrated (it is rejected for battle-scoped routes).
        if self.sandbox_token:
            headers["X-Sandbox-Token"] = self.sandbox_token
        elif self.internal_key:
            headers["X-Internal-Key"] = self.internal_key
        last_err: Exception | None = None
        for attempt in range(3):
            try:
                resp = self.client.post(url, headers=headers, json=json)
                if resp.status_code >= 500:
                    raise httpx.HTTPError(f"server {resp.status_code}")
                if resp.status_code >= 400:
                    raise RuntimeError(
                        f"internal {path} failed: {resp.status_code} {resp.text[:200]}"
                    )
                try:
                    return resp.json()
                except ValueError as exc:
                    raise RuntimeError(
                        f"internal {path} returned non-JSON body "
                        f"(status {resp.status_code}, {len(resp.content)} bytes): "
                        f"{resp.text[:120]!r}"
                    ) from exc
            except (httpx.HTTPError, RuntimeError) as exc:
                last_err = exc
                if isinstance(exc, RuntimeError) and "failed: 4" in str(exc):
                    raise
                time.sleep(0.5 * (2**attempt))
        raise RuntimeError(f"internal {path} exhausted retries: {last_err}")


class FakeTransport:
    """In-memory transport for hermetic unit tests."""

    def __init__(self):
        self.calls: list[tuple[str, dict]] = []
        self.model_replies: dict[str, Any] = {}
        self.judge_result: dict[str, Any] = {
            "scores": {},
            "justifications": {},
            "judge_model": "mock",
        }
        self.rounds: list[dict] = []
        self.battle_status: str = "running"
        self._lock = threading.Lock()

    def post(self, path: str, json: dict) -> dict:
        with self._lock:
            return self._post_locked(path, json)

    def _post_locked(self, path: str, json: dict) -> dict:
        self.calls.append((path, json))
        if path == "/internal/model":
            mid = json.get("model_id", "")
            reply = self.model_replies.get(mid, f"[reply:{mid}]")
            if isinstance(reply, list):
                content = reply.pop(0) if reply else f"[reply:{mid}]"
            else:
                content = reply
            if isinstance(content, dict):
                return content
            return {"content": content, "tool_calls": []}
        if path == "/internal/judge":
            return self.judge_result
        if path == "/internal/round":
            self.rounds.append(json)
            return {"ok": True, "event_id": "fake", "sequence": json.get("sequence")}
        if path == "/internal/status":
            return {"status": self.battle_status}
        if path == "/internal/finalize":
            return {"ok": True, "status": json.get("status") or "completed"}
        if path == "/internal/verify":
            return {
                "ok": True,
                "passed": False,
                "error": "fake transport does not run the trusted verifier",
            }
        raise RuntimeError(f"unknown path {path}")


class InternalClient:
    def __init__(self, transport: Transport):
        self.t = transport

    def model(
        self,
        battle_id: str,
        model_id: str,
        messages: list[dict],
        phase: str = "",
        max_tokens: int | None = None,
        tools: list[dict] | None = None,
        tool_choice: str | None = None,
        return_raw: bool = False,
    ) -> str | dict:
        payload: dict[str, Any] = {
            "battle_id": battle_id,
            "model_id": model_id,
            "phase": phase,
            "messages": messages,
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        if tools is not None:
            payload["tools"] = tools
        if tool_choice is not None:
            payload["tool_choice"] = tool_choice
        data = self.t.post("/internal/model", payload)
        if return_raw:
            return data
        return data.get("content", "")

    def judge(
        self,
        battle_id: str,
        rubric: str,
        artifacts: list[dict],
        weights: dict | None = None,
    ) -> dict:
        return self.t.post(
            "/internal/judge",
            {
                "battle_id": battle_id,
                "rubric": rubric,
                "weights": weights,
                "artifacts": artifacts,
            },
        )

    def round(
        self,
        battle_id: str,
        phase: str,
        model_id: str,
        artifact: str,
        event_type: str = "artifact",
        sequence: int | None = None,
        tool_trace: dict | None = None,
        verification_log: str | None = None,
        meta: dict | None = None,
    ) -> None:
        payload: dict[str, Any] = {
            "battle_id": battle_id,
            "phase": phase,
            "model_id": model_id,
            "artifact": artifact,
            "event_type": event_type,
        }
        if sequence is not None:
            payload["sequence"] = sequence
        if tool_trace is not None:
            payload["tool_trace"] = tool_trace
        if verification_log is not None:
            payload["verification_log"] = verification_log
        if meta is not None:
            payload["meta"] = meta
        self.t.post("/internal/round", payload)

    def status(self, battle_id: str) -> str:
        data = self.t.post("/internal/status", {"battle_id": battle_id})
        return str(data.get("status") or "unknown")

    def finalize(self, battle_id: str, status: str, scores: dict | None = None) -> dict:
        return self.t.post(
            "/internal/finalize",
            {
                "battle_id": battle_id,
                "status": status,
                "scores": scores or {},
            },
        )

    def verify_target(
        self,
        battle_id: str,
        target_id: str,
        submitted_files: dict[str, str] | None = None,
        *,
        kind: str = "solo",
        builder_files: dict[str, str] | None = None,
        breaker_files: dict[str, str] | None = None,
        phase: str = "",
        role: str = "",
        model_id: str = "",
    ) -> dict:
        payload: dict[str, Any] = {
            "battle_id": battle_id,
            "target_id": target_id,
            "kind": kind,
            "submitted_files": submitted_files or {},
        }
        if builder_files is not None:
            payload["builder_files"] = builder_files
        if breaker_files is not None:
            payload["breaker_files"] = breaker_files
        if phase:
            payload["phase"] = phase
        if role:
            payload["role"] = role
        if model_id:
            payload["model_id"] = model_id
        return self.t.post("/internal/verify", payload)
