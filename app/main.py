"""Transkribering och anonymisering — FastAPI-app."""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings

STATIC_DIR = Path(__file__).resolve().parent / "static"

app = FastAPI(title="Transkribering och anonymisering")


@app.get("/api/health")
def health() -> dict:
    return {
        "status": "ok",
        "device": settings.resolve_device(),
        "whisper_model": settings.whisper_model,
        "ner_model": settings.ner_model,
    }


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=settings.port)
