from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from . import battles, formats, internal_router, leaderboard_router, providers, stats

app = FastAPI(title="Agent Arena", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        # Exact production frontend origins (tighten from wildcard *.vercel.app
        # so any unrelated Vercel page cannot make credentialed requests).
        "https://seekharness.vercel.app",
        "https://agent-arena-blond.vercel.app",
        "https://frontend-seven-snowy-59.vercel.app",
        # Local development.
        "http://localhost:3000",
        "http://localhost:3010",
    ],
    # allow_origin_regex kept off: a wildcard regex reintroduces the same
    # permissive behaviour the explicit list above is meant to close.
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(formats.router)
app.include_router(providers.router)
app.include_router(battles.router)
app.include_router(leaderboard_router.router)
app.include_router(internal_router.router)
app.include_router(stats.router)


@app.get("/health")
def health():
    return {"status": "ok", "project": settings()["APPWRITE_PROJECT_ID"]}
