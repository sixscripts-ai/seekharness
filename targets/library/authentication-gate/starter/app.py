from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

app = FastAPI()
USERS = {"admin": "swordfish", "guest": "guest"}
TOKENS = {}

class Login(BaseModel):
    username: str
    password: str

@app.post("/login")
def login(body: Login):
    # TODO: validate credentials and issue an opaque token.
    token = body.username
    TOKENS[token] = body.username
    return {"token": token}

@app.get("/admin")
def admin(authorization: str | None = Header(default=None)):
    # TODO: authorize only a token issued by a successful admin login.
    if not authorization:
        raise HTTPException(status_code=401)
    token = authorization.removeprefix("Bearer ")
    user = TOKENS.get(token, token)
    if user != "admin":
        raise HTTPException(status_code=403)
    return {"secret": "ARENA_ADMIN_OK"}
