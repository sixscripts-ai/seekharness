from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, EmailStr

from .auth import get_current_user
from .native_auth import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from .persistence.models import User, _new_id
from .persistence.session import session_scope

router = APIRouter(prefix="/auth", tags=["auth"])


class SignupRequest(BaseModel):
    email: str
    password: str
    name: str | None = None


class LoginRequest(BaseModel):
    email: str
    password: str


def _user_dict(user: User) -> dict:
    return {
        "id": user.id,
        "$id": user.id,  # Appwrite compatibility for frontend components
        "email": user.email,
        "name": user.name or "",
    }


@router.post("/signup")
def signup(req: SignupRequest):
    email = req.email.strip().lower()
    if not email or "@" not in email:
        raise HTTPException(status_code=400, detail="Valid email is required")
    if not req.password or len(req.password) < 6:
        raise HTTPException(
            status_code=400, detail="Password must be at least 6 characters"
        )

    name = req.name.strip() if req.name else email.split("@")[0]

    with session_scope() as session:
        existing = session.query(User).filter(User.email == email).first()
        if existing:
            raise HTTPException(
                status_code=409,
                detail="An account with this email already exists",
            )

        hashed = hash_password(req.password)
        user = User(
            id=_new_id(),
            email=email,
            name=name,
            password_hash=hashed,
        )
        session.add(user)
        session.commit()
        session.refresh(user)

        token = create_access_token(user.id, user.email, user.name)
        return {
            "user": _user_dict(user),
            "token": token,
        }


@router.post("/login")
def login(req: LoginRequest):
    email = req.email.strip().lower()
    if not email or not req.password:
        raise HTTPException(status_code=400, detail="Email and password required")

    with session_scope() as session:
        user = session.query(User).filter(User.email == email).first()
        if not user or not verify_password(req.password, user.password_hash):
            raise HTTPException(
                status_code=401, detail="Invalid email or password"
            )

        token = create_access_token(user.id, user.email, user.name)
        return {
            "user": _user_dict(user),
            "token": token,
        }


@router.get("/me")
def me(user_id: str = Depends(get_current_user)):
    with session_scope() as session:
        user = session.query(User).filter(User.id == user_id).first()
        if user:
            return _user_dict(user)
        # Fallback if user ID is authenticated (e.g. legacy/admin)
        return {"id": user_id, "$id": user_id, "email": "", "name": "User"}


@router.post("/logout")
def logout():
    return {"ok": True}
