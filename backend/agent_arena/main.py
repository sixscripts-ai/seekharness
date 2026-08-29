import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from . import (
    battle_drafts,
    battles,
    formats,
    internal_router,
    leaderboard_router,
    providers,
    stats,
    target_router,
)
from .evidence import EVIDENCE_SCHEMA_VERSION, SCORING_VERSION

app = FastAPI(title="Agent Arena", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        # Exact production frontend origins (tighten from wildcard *.vercel.app
        # so any unrelated Vercel page cannot make credentialed requests).
        "https://seekharness.vercel.app",
        "https://agent-arena-blond.vercel.app",
        "https://frontend-seven-snowy-59.vercel.app",
        # Local development (Vite default 5173; 3000/3010 for other tools).
        "http://localhost:3000",
        "http://localhost:3010",
        "http://localhost:5173",
        "http://localhost:5174",
        "http://localhost:5175",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:5174",
        "http://127.0.0.1:5175",
    ],
    # Localhost any port only — not a Vercel wildcard.
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1):\d+",
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(formats.router)
app.include_router(providers.router)
app.include_router(battle_drafts.router)
app.include_router(battles.router)
app.include_router(target_router.router)
app.include_router(leaderboard_router.router)
app.include_router(internal_router.router)
app.include_router(stats.router)


@app.get("/health")
def health():
    return {
        "status": "ok",
        "project": settings()["APPWRITE_PROJECT_ID"],
        # Set at deploy time: modal deploy modal_entry.py --env ARENA_BUILD_SHA=$(git rev-parse HEAD)
        "build_sha": os.environ.get("ARENA_BUILD_SHA") or "unknown",
        "evidence_schema_version": EVIDENCE_SCHEMA_VERSION,
        "scoring_version": SCORING_VERSION,
    }
