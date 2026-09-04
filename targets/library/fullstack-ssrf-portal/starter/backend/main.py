from __future__ import annotations

import ipaddress
import socket
import urllib.parse
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import httpx

app = FastAPI(title="Webhook SSRF Portal")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

webhook_logs: list[dict] = []
CANARY_TOKEN = "FLAG{ssrf_internal_pivot_confirmed}"


class WebhookTestRequest(BaseModel):
    url: str


def is_ip_private(ip_str: str) -> bool:
    try:
        ip = ipaddress.ip_address(ip_str)
        return ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_unspecified
    except ValueError:
        return True


def validate_url_safe(url: str) -> bool:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return False
    hostname = parsed.hostname
    if not hostname:
        return False
    if hostname.lower() in ("localhost", "127.0.0.1", "::1", "0.0.0.0"):
        return False
    try:
        # Resolve IP
        addr_info = socket.getaddrinfo(hostname, None)
        for entry in addr_info:
            ip_str = entry[4][0]
            if is_ip_private(ip_str):
                return False
    except socket.gaierror:
        return False
    return True


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/internal/secrets/canary")
def get_canary():
    # Diagnostic endpoint - only accessible locally, never via SSRF proxy
    return {"canary": CANARY_TOKEN, "service": "internal-metadata"}


@app.get("/api/webhooks/logs")
def get_logs():
    return {"logs": webhook_logs}


@app.post("/api/webhooks/test")
def test_webhook(req: WebhookTestRequest):
    if not validate_url_safe(req.url):
        raise HTTPException(status_code=400, detail="Disallowed target URL: internal or private destination")
    try:
        # Strict timeout, no redirect following to avoid redirect-based SSRF
        with httpx.Client(timeout=3.0, follow_redirects=False) as client:
            resp = client.get(req.url)
            log_entry = {"url": req.url, "status_code": resp.status_code, "body": resp.text[:200]}
            webhook_logs.append(log_entry)
            return {"status": "success", "status_code": resp.status_code, "preview": resp.text[:200]}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Webhook delivery failed: {exc}")
