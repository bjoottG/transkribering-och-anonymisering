"""Transkribering och anonymisering — FastAPI-app."""
from __future__ import annotations

import io
import zipfile
from pathlib import Path

from fastapi import FastAPI, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.jobs import ALL_EXTENSIONS, Job, JobOptions, JobQueue, UserVisibleError, file_kind

STATIC_DIR = Path(__file__).resolve().parent / "static"

app = FastAPI(title="Transkribering och anonymisering")


def _process_job(job: Job) -> None:
    raise UserVisibleError("Bearbetningen är inte implementerad ännu.")


job_queue = JobQueue(processor=_process_job)


@app.on_event("startup")
def _startup() -> None:
    settings.uploads_dir.mkdir(parents=True, exist_ok=True)
    settings.results_dir.mkdir(parents=True, exist_ok=True)
    job_queue.start()


@app.on_event("shutdown")
def _shutdown() -> None:
    job_queue.stop()


@app.get("/api/health")
def health() -> dict:
    return {
        "status": "ok",
        "device": settings.resolve_device(),
        "whisper_model": settings.whisper_model,
        "ner_model": settings.ner_model,
        "max_file_size_mb": settings.max_file_size_mb,
    }


@app.post("/api/jobs")
async def create_job(
    file: UploadFile,
    original: bool = Form(True),
    anonymized: bool = Form(False),
    keyfile: bool = Form(False),
    timestamps: bool = Form(True),
) -> dict:
    filename = Path(file.filename or "").name
    if not filename:
        raise HTTPException(400, "Ingen fil skickades med.")
    kind = file_kind(filename)
    if kind is None:
        tillatna = ", ".join(sorted(ALL_EXTENSIONS))
        raise HTTPException(400, f"Filformatet stöds inte. Tillåtna format: {tillatna}.")

    options = JobOptions(original=original, anonymized=anonymized, keyfile=keyfile, timestamps=timestamps)
    error = options.validate()
    if error:
        raise HTTPException(400, error)

    job = job_queue.create(filename=filename, kind=kind, options=options)
    job.upload_dir.mkdir(parents=True, exist_ok=True)
    job.result_dir.mkdir(parents=True, exist_ok=True)

    size = 0
    max_bytes = settings.max_file_size_bytes
    try:
        with open(job.upload_path, "wb") as out:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > max_bytes:
                    raise HTTPException(
                        413, f"Filen är för stor. Maxstorlek är {settings.max_file_size_mb} MB."
                    )
                out.write(chunk)
    except HTTPException:
        job.upload_path.unlink(missing_ok=True)
        raise
    if size == 0:
        job.upload_path.unlink(missing_ok=True)
        raise HTTPException(400, "Filen är tom.")

    job_queue.enqueue(job)
    return job.to_dict()


@app.get("/api/jobs")
def list_jobs() -> list:
    return [job.to_dict() for job in job_queue.all_jobs()]


def _get_job_or_404(job_id: str) -> Job:
    job = job_queue.get(job_id)
    if job is None:
        raise HTTPException(404, "Jobbet finns inte (kan ha rensats bort).")
    return job


@app.get("/api/jobs/{job_id}")
def job_status(job_id: str) -> dict:
    return _get_job_or_404(job_id).to_dict()


@app.get("/api/jobs/{job_id}/files")
def job_files(job_id: str) -> dict:
    job = _get_job_or_404(job_id)
    return {"files": list(job.result_files)}


@app.get("/api/jobs/{job_id}/files/{name}")
def download_file(job_id: str, name: str) -> FileResponse:
    job = _get_job_or_404(job_id)
    if name not in job.result_files:
        raise HTTPException(404, "Filen finns inte i det här jobbet.")
    path = job.result_dir / name
    if not path.is_file():
        raise HTTPException(404, "Filen finns inte längre på disk.")
    return FileResponse(
        path,
        filename=name,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )


@app.get("/api/jobs/{job_id}/download-all")
def download_all(job_id: str) -> StreamingResponse:
    job = _get_job_or_404(job_id)
    if not job.result_files:
        raise HTTPException(404, "Jobbet har inga resultatfiler.")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for name in job.result_files:
            path = job.result_dir / name
            if path.is_file():
                zf.write(path, arcname=name)
    buffer.seek(0)
    zip_name = f"{Path(job.filename).stem}_resultat.zip"
    return StreamingResponse(
        buffer,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{zip_name}"'},
    )


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=settings.port)
