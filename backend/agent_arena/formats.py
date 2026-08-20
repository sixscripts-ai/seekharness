import json
from typing import Optional

from appwrite.query import Query
from fastapi import APIRouter, Depends, Header

from . import db
from .auth import get_current_user
from .seed_formats import is_playable_format

router = APIRouter(prefix="/formats", tags=["formats"])


def get_optional_user(authorization: Optional[str] = Header(default=None)) -> Optional[str]:
    if not authorization or not authorization.startswith("Bearer "):
        return None
    try:
        return get_current_user(authorization)
    except Exception:
        return None


@router.get("")
def list_formats(_user_id: Optional[str] = Depends(get_optional_user)):
    databases = db.get_databases()
    res = databases.list_documents(db.get_database_id(), "formats", queries=[Query.limit(100)])
    out = []
    for doc in res.documents:
        cfg = json.loads(doc.data["config"])
        if not is_playable_format(cfg):
            continue
        out.append({
            "id": doc.id,
            "name": cfg["name"],
            "engine": cfg["engine"],
            "description": cfg["description"],
            "slug": cfg["id"],
            "roles": cfg.get("roles", []),
            "config": cfg,
        })
    out.sort(key=lambda f: f["name"])
    return out
