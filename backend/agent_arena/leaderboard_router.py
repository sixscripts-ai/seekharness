from typing import Optional
from fastapi import APIRouter, Depends, Header

from . import db, leaderboard
from .auth import get_current_user

router = APIRouter(prefix="/leaderboard", tags=["leaderboard"])


def get_optional_user(authorization: Optional[str] = Header(default=None)) -> Optional[str]:
    if not authorization or not authorization.startswith("Bearer "):
        return None
    try:
        return get_current_user(authorization)
    except Exception:
        return None


@router.get("")
def get_leaderboard(format: str = "overall", _user_id: Optional[str] = Depends(get_optional_user)):
    from .persistence import service

    return service.leaderboard_rankings(format)
