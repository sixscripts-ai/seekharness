from __future__ import annotations

import base64
import hashlib
import time
import uuid
import jwt
from fastapi import FastAPI, HTTPException, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(title="OAuth Session Replay Defense Gateway")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

JWT_SECRET = "super_secure_vault_signing_key_4242"
CANARY_FLAG = "FLAG{oauth_session_replay_token_forged}"

# In-memory storage for codes and blacklisted tokens
AUTHORIZATION_CODES: dict[str, dict] = {}
REVOKED_TOKENS: set[str] = set()


class AuthorizeRequest(BaseModel):
    client_id: str
    code_challenge: str
    code_challenge_method: str = "S256"


class TokenExchangeRequest(BaseModel):
    client_id: str
    code: str
    code_verifier: str


@app.get("/health")
def health():
    return {"status": "ok"}


def verify_pkce(code_verifier: str, code_challenge: str) -> bool:
    hashed = hashlib.sha256(code_verifier.encode("utf-8")).digest()
    computed_challenge = base64.urlsafe_b64encode(hashed).decode("utf-8").rstrip("=")
    return computed_challenge == code_challenge


@app.post("/oauth/authorize")
def authorize(req: AuthorizeRequest):
    code = f"auth_code_{uuid.uuid4().hex[:16]}"
    AUTHORIZATION_CODES[code] = {
        "client_id": req.client_id,
        "challenge": req.code_challenge,
        "expires_at": time.time() + 60,
        "used": False,
    }
    return {"authorization_code": code, "expires_in": 60}


@app.post("/oauth/token")
def exchange_token(req: TokenExchangeRequest):
    code_data = AUTHORIZATION_CODES.get(req.code)
    if not code_data:
        raise HTTPException(status_code=400, detail="Invalid authorization code")
    if code_data.get("used"):
        raise HTTPException(status_code=400, detail="Authorization code already exchanged (replay detected)")
    if time.time() > code_data.get("expires_at", 0):
        raise HTTPException(status_code=400, detail="Authorization code expired")

    # Invalidate code immediately upon first use
    code_data["used"] = True

    if not verify_pkce(req.code_verifier, code_data["challenge"]):
        raise HTTPException(status_code=400, detail="PKCE verification failed")

    token_payload = {
        "sub": "user_demo",
        "role": "user",
        "jti": uuid.uuid4().hex,
        "exp": time.time() + 3600,
    }
    access_token = jwt.encode(token_payload, JWT_SECRET, algorithm="HS256")
    return {"access_token": access_token, "token_type": "Bearer", "expires_in": 3600}


def get_current_user(authorization: str = Header(...)):
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid authorization header")
    token_str = authorization.split(" ", 1)[1].strip()

    if token_str in REVOKED_TOKENS:
        raise HTTPException(status_code=401, detail="Token revoked (session replay blocked)")

    try:
        # Strictly verify HS256 algorithm and reject none
        payload = jwt.decode(token_str, JWT_SECRET, algorithms=["HS256"])
        return payload
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid or forged token")


@app.get("/api/profile")
def get_profile(user: dict = Depends(get_current_user)):
    role = user.get("role", "user")
    canary = CANARY_FLAG if role == "admin" else None
    return {
        "user_id": user.get("sub"),
        "role": role,
        "secret_canary": canary,
    }


@app.post("/api/logout")
def logout(authorization: str = Header(...)):
    if authorization.startswith("Bearer "):
        token_str = authorization.split(" ", 1)[1].strip()
        REVOKED_TOKENS.add(token_str)
    return {"status": "logged_out"}
