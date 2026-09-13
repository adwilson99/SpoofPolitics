"""Loony to Westminster — FastAPI application.

Serves the JSON API under /api and the static frontend from /frontend.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.api.game_routes import router as game_router
from backend.api.game_routes import saves_router
from backend.api.routes import router

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"

app = FastAPI(
    title="Loony to Westminster",
    version="0.4.0",
    description=(
        "A satirical campaign game: go from joke by-election candidate to "
        "Prime Minister. Purely for humour — not affiliated with any real "
        "party, politician, or person."
    ),
)

app.include_router(router)
app.include_router(game_router)
app.include_router(saves_router)
app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "index.html")


@app.get("/sw.js", include_in_schema=False)
def service_worker() -> FileResponse:
    # served at the root so the service worker can control the whole app
    return FileResponse(FRONTEND_DIR / "sw.js", media_type="application/javascript")


@app.get("/manifest.json", include_in_schema=False)
def pwa_manifest() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "manifest.json", media_type="application/manifest+json")
