"""Jobbkö: sekventiell bearbetning i bakgrundstråd, status och automatisk rensning."""
from __future__ import annotations

import logging
import queue
import shutil
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from app.config import settings

logger = logging.getLogger(__name__)

AUDIO_EXTENSIONS = {"mp3", "wav", "m4a", "flac", "ogg", "aac", "wma"}
VIDEO_EXTENSIONS = {"mp4", "mov", "avi", "mkv", "webm", "wmv"}
DOCUMENT_EXTENSIONS = {"pdf", "docx", "doc", "xlsx", "xls"}
ALL_EXTENSIONS = AUDIO_EXTENSIONS | VIDEO_EXTENSIONS | DOCUMENT_EXTENSIONS


def file_kind(filename: str) -> Optional[str]:
    """'media', 'document' eller None om formatet inte stöds."""
    ext = Path(filename).suffix.lower().lstrip(".")
    if ext in AUDIO_EXTENSIONS or ext in VIDEO_EXTENSIONS:
        return "media"
    if ext in DOCUMENT_EXTENSIONS:
        return "document"
    return None


@dataclass
class JobOptions:
    """Val per uppladdning.

    original: transkription (media) resp. oanonymiserad konverterad version (dokument).
    anonymized: anonymiserad version. keyfile: kodnyckel (kräver anonymized).
    timestamps: tidsstämplar i transkriptionen (endast media).
    vision: skärmbildsbeskrivning via Claude API (endast film) — ger en tidslinje
    med tal + skärminnehåll i de valda varianterna (original/anonymiserad).
    """

    original: bool = True
    anonymized: bool = False
    keyfile: bool = False
    timestamps: bool = True
    vision: bool = False

    def validate(self) -> Optional[str]:
        if not self.original and not self.anonymized:
            return "Välj minst ett resultat: transkription/konverterad version eller anonymiserad version."
        if self.keyfile and not self.anonymized:
            return "Kodnyckel kräver att anonymiserad version är vald."
        return None


@dataclass
class Job:
    id: str
    filename: str
    kind: str  # media | document
    options: JobOptions
    status: str = "queued"  # queued | processing | done | error
    progress: int = 0
    step: str = "Väntar i kö"
    error: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    result_files: list = field(default_factory=list)

    @property
    def upload_dir(self) -> Path:
        return settings.uploads_dir / self.id

    @property
    def result_dir(self) -> Path:
        return settings.results_dir / self.id

    @property
    def upload_path(self) -> Path:
        return self.upload_dir / self.filename

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "filename": self.filename,
            "kind": self.kind,
            "status": self.status,
            "progress": self.progress,
            "step": self.step,
            "error": self.error,
            "created_at": self.created_at,
            "files": list(self.result_files),
            "options": {
                "original": self.options.original,
                "anonymized": self.options.anonymized,
                "keyfile": self.options.keyfile,
                "timestamps": self.options.timestamps,
                "vision": self.options.vision,
            },
        }


class JobQueue:
    """In-process-kö som kör ett jobb åt gången (sekventiell GPU-kö)."""

    def __init__(self, processor: Callable[[Job], None]):
        self._processor = processor
        self._jobs: dict[str, Job] = {}
        self._queue: queue.Queue[str] = queue.Queue()
        self._lock = threading.Lock()
        self._worker: Optional[threading.Thread] = None
        self._cleaner: Optional[threading.Thread] = None
        self._stop = threading.Event()

    def start(self) -> None:
        self._stop.clear()
        self._worker = threading.Thread(target=self._work_loop, daemon=True, name="job-worker")
        self._worker.start()
        self._cleaner = threading.Thread(target=self._cleanup_loop, daemon=True, name="job-cleaner")
        self._cleaner.start()

    def stop(self) -> None:
        self._stop.set()

    def create(self, filename: str, kind: str, options: JobOptions) -> Job:
        job = Job(id=uuid.uuid4().hex[:12], filename=filename, kind=kind, options=options)
        with self._lock:
            self._jobs[job.id] = job
        return job

    def enqueue(self, job: Job) -> None:
        self._queue.put(job.id)

    def get(self, job_id: str) -> Optional[Job]:
        with self._lock:
            return self._jobs.get(job_id)

    def all_jobs(self) -> list:
        with self._lock:
            return sorted(self._jobs.values(), key=lambda j: j.created_at, reverse=True)

    def _work_loop(self) -> None:
        while not self._stop.is_set():
            try:
                job_id = self._queue.get(timeout=0.5)
            except queue.Empty:
                continue
            job = self.get(job_id)
            if job is None:
                continue
            job.status = "processing"
            job.step = "Bearbetar"
            try:
                self._processor(job)
                job.progress = 100
                job.status = "done"
                job.step = "Klar"
            except UserVisibleError as exc:
                logger.warning("Jobb %s misslyckades: %s", job.id, exc)
                job.status = "error"
                job.error = str(exc)
                job.step = "Fel"
            except Exception:
                logger.exception("Oväntat fel i jobb %s", job.id)
                job.status = "error"
                job.error = "Ett oväntat fel inträffade vid bearbetningen. Se serverloggen för detaljer."
                job.step = "Fel"

    def _cleanup_loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.cleanup_old_jobs()
            except Exception:
                logger.exception("Fel vid rensning av gamla jobb")
            self._stop.wait(timeout=600)

    def cleanup_old_jobs(self, max_age_hours: Optional[float] = None) -> int:
        """Ta bort jobb (uppladdningar + resultat) äldre än max_age_hours. Returnerar antal."""
        max_age = (max_age_hours if max_age_hours is not None else settings.cleanup_hours) * 3600
        cutoff = time.time() - max_age
        removed = 0
        with self._lock:
            old_ids = [
                j.id for j in self._jobs.values() if j.created_at < cutoff and j.status != "processing"
            ]
            for job_id in old_ids:
                del self._jobs[job_id]
        for job_id in old_ids:
            for base in (settings.uploads_dir, settings.results_dir):
                shutil.rmtree(base / job_id, ignore_errors=True)
            removed += 1
        # Kataloger utan jobb i minnet (t.ex. efter omstart)
        for base in (settings.uploads_dir, settings.results_dir):
            if not base.exists():
                continue
            for path in base.iterdir():
                if path.is_dir() and path.name not in self._jobs and path.stat().st_mtime < cutoff:
                    shutil.rmtree(path, ignore_errors=True)
        return removed


class UserVisibleError(Exception):
    """Fel med begripligt svenskt meddelande som visas i gränssnittet."""
