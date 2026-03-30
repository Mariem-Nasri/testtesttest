"""
main.py
──────────────────────────────────────────────────────────────────────────────
DocAI FastAPI backend.

Start:
    cd backend
    uvicorn main:app --reload --port 8000

Endpoints are prefixed with /api to match the frontend service:
    http://localhost:8000/api/auth/token
    http://localhost:8000/api/documents/upload
    ...
"""

import os
from pathlib import Path

# Load .env from backend directory before anything else
_env_file = Path(__file__).parent / ".env"
if _env_file.exists():
    for _line in _env_file.read_text().splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip())

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from database          import init_db
from routers           import auth as auth_router
from routers           import documents as docs_router

# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(
    title       = "DocAI API",
    description = "OCR + Multi-Agent Extraction Pipeline — VERMEG PFE 2025-2026",
    version     = "1.0.0",
    docs_url    = "/api/docs",
    redoc_url   = "/api/redoc",
    openapi_url = "/api/openapi.json",
)

# ── CORS — allow Vite dev server ──────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",   # Vite default
        "http://localhost:3000",   # CRA fallback
        "http://127.0.0.1:5173",
        "http://127.0.0.1:3000",
    ],
    allow_credentials = True,
    allow_methods     = ["*"],
    allow_headers     = ["*"],
)

# ── DB init on startup ────────────────────────────────────────────────────────
@app.on_event("startup")
async def startup():
    init_db()
    import pipeline_runner
    pipeline_runner.prewarm()   # pre-load sentence-transformers in background thread


# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(auth_router.router, prefix="/api/auth",  tags=["auth"])
app.include_router(docs_router.router, prefix="/api",       tags=["documents"])


# ── Health check ──────────────────────────────────────────────────────────────
@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "DocAI API"}
