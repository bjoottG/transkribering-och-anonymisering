"""Transkribering med KB-Whisper: ffmpeg-extraktion + faster-whisper (fallback: transformers)."""
from __future__ import annotations

import logging
import shutil
import subprocess
import threading
from pathlib import Path
from typing import Callable, Optional

from app.config import settings
from app.jobs import UserVisibleError

logger = logging.getLogger(__name__)

_model_lock = threading.Lock()
_faster_whisper_model = None
_transformers_pipeline = None


def extract_audio(source: Path, target_wav: Path) -> Path:
    """Extrahera/konvertera ljudspåret till 16 kHz mono WAV med ffmpeg."""
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise UserVisibleError(
            "ffmpeg hittades inte på servern. Installera ffmpeg och starta om applikationen."
        )
    command = [
        ffmpeg, "-y", "-i", str(source),
        "-vn", "-ac", "1", "-ar", "16000", "-acodec", "pcm_s16le",
        str(target_wav),
    ]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0 or not target_wav.is_file() or target_wav.stat().st_size == 0:
        logger.error("ffmpeg misslyckades: %s", result.stderr[-2000:])
        raise UserVisibleError(
            "Ljudspåret kunde inte extraheras. Filen kan vara skadad eller sakna ljudspår."
        )
    return target_wav


def _load_faster_whisper():
    global _faster_whisper_model
    if _faster_whisper_model is None:
        from faster_whisper import WhisperModel

        device = settings.resolve_device()
        compute_type = "float16" if device == "cuda" else "int8"
        logger.info("Laddar %s via faster-whisper (%s, %s)", settings.whisper_model, device, compute_type)
        _faster_whisper_model = WhisperModel(
            settings.whisper_model, device=device, compute_type=compute_type
        )
    return _faster_whisper_model


def _transcribe_faster_whisper(wav: Path, progress: Optional[Callable] = None) -> list:
    model = _load_faster_whisper()
    segments, info = model.transcribe(str(wav), language="sv", beam_size=5, vad_filter=True)
    duration = max(info.duration or 0.0, 0.001)
    result: list = []
    for segment in segments:  # generator — transkriberingen sker här
        result.append({"start": segment.start, "end": segment.end, "text": segment.text.strip()})
        if progress is not None:
            progress(min(segment.end / duration, 1.0))
    return result


def _transcribe_transformers(wav: Path, progress: Optional[Callable] = None) -> list:
    global _transformers_pipeline
    if _transformers_pipeline is None:
        from transformers import pipeline

        device = 0 if settings.resolve_device() == "cuda" else -1
        logger.info("Laddar %s via transformers-pipeline (fallback)", settings.whisper_model)
        _transformers_pipeline = pipeline(
            "automatic-speech-recognition",
            model=settings.whisper_model,
            chunk_length_s=30,
            device=device,
        )
    output = _transformers_pipeline(
        str(wav),
        return_timestamps=True,
        generate_kwargs={"language": "sv", "task": "transcribe"},
    )
    result: list = []
    for chunk in output.get("chunks", []):
        start, end = chunk.get("timestamp") or (0.0, 0.0)
        result.append({"start": start or 0.0, "end": end or start or 0.0, "text": chunk.get("text", "").strip()})
    if not result and output.get("text"):
        result.append({"start": 0.0, "end": 0.0, "text": output["text"].strip()})
    if progress is not None:
        progress(1.0)
    return result


def transcribe(wav: Path, progress: Optional[Callable] = None) -> list:
    """Transkribera en WAV-fil till segment: list[dict] med start, end, text.

    Ett anrop i taget (modell-lås) — GPU-kön är sekventiell.
    """
    with _model_lock:
        try:
            return _transcribe_faster_whisper(wav, progress)
        except UserVisibleError:
            raise
        except ImportError:
            logger.warning("faster-whisper saknas — använder transformers-fallback")
        except Exception:
            logger.exception("faster-whisper misslyckades — provar transformers-fallback")
        try:
            return _transcribe_transformers(wav, progress)
        except Exception:
            logger.exception("Även transformers-fallback misslyckades")
            raise UserVisibleError(
                "Transkriberingen misslyckades. Kontrollera att modellen är nedladdad "
                "(scripts/download_models.py) och se serverloggen för detaljer."
            )
