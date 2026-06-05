"""FastAPI app entry point. Serves API routes + built React frontend."""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse

from llm_eval.api.routes import runs, results, history, compare, export
from llm_eval.storage.db import init_db


app = FastAPI(title="llm-eval-harness", version="1.0.0")

# /api/run spends real API credits, so we deny cross-origin browser calls by
# default. The Vite dev server origin is allowed out of the box; override with
# LLM_EVAL_CORS_ORIGINS (comma-separated) if hosting the playground elsewhere.
_default_origins = "http://localhost:5173,http://127.0.0.1:5173"
_allowed_origins = [
    o.strip()
    for o in os.getenv("LLM_EVAL_CORS_ORIGINS", _default_origins).split(",")
    if o.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Content-Type", "Authorization"],
)


@app.on_event("startup")
def _startup() -> None:
    init_db()


app.include_router(runs.router, prefix="/api")
app.include_router(results.router, prefix="/api")
app.include_router(history.router, prefix="/api")
app.include_router(compare.router, prefix="/api")
app.include_router(export.router, prefix="/api")


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


# Mount React static build if it exists.
PLAYGROUND_DIST = Path(__file__).resolve().parent.parent.parent / "playground" / "dist"
if PLAYGROUND_DIST.exists():
    app.mount(
        "/assets",
        StaticFiles(directory=str(PLAYGROUND_DIST / "assets")),
        name="assets",
    )

    @app.get("/{full_path:path}")
    def spa_fallback(full_path: str):
        # API requests already matched above; this serves index.html for the SPA.
        index = PLAYGROUND_DIST / "index.html"
        if index.exists():
            return FileResponse(str(index))
        return JSONResponse({"error": "frontend not built"}, status_code=404)
else:
    @app.get("/")
    def root() -> dict:
        return {
            "message": "llm-eval-harness API",
            "frontend": "not built - run `npm run build` inside playground/",
            "api_docs": "/docs",
        }
