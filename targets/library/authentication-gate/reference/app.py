import secrets
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

app = FastAPI()
USERS = {"admin": "swordfish", "guest": "guest"}
TOKENS: dict[str,str] = {}

class Login(BaseModel):
    username: str
    password: str

@app.post("/login")
def login(body: Login):
    if USERS.get(body.username) != body.password or not body.password:
        raise HTTPException(status_code=401, detail="invalid credentials")
    token = secrets.token_urlsafe(24)
    TOKENS[token] = body.username
    return {"token": token}

@app.get("/admin")
def admin(authorization: str | None = Header(default=None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401)
    token = authorization[7:]
    user = TOKENS.get(token)
    if user is None:
        raise HTTPException(status_code=401)
    if user != "admin":
        raise HTTPException(status_code=403)
    return {"secret": "ARENA_ADMIN_OK"}
