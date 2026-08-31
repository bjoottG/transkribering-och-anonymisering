"""Inställningar lästa från .env / miljövariabler."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def _env(name: str, default: str) -> str:
    value = os.environ.get(name, "").strip()
    return value or default


def _env_int(name: str, default: int) -> int:
    try:
        return int(_env(name, str(default)))
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(_env(name, str(default)))
    except ValueError:
        return default


@dataclass
class Settings:
    whisper_model: str = _env("WHISPER_MODEL", "KBLab/kb-whisper-large")
    ner_model: str = _env("NER_MODEL", "KB/bert-base-swedish-cased-ner")
    ner_entity_types: tuple = tuple(
        t.strip().upper()
        for t in _env("NER_ENTITY_TYPES", "PER,LOC,ORG").split(",")
        if t.strip()
    )
    ner_score_threshold: float = _env_float("NER_SCORE_THRESHOLD", 0.70)
    device: str = _env("DEVICE", "auto").lower()  # auto | cuda | cpu
    hf_home: Path = field(default_factory=lambda: (BASE_DIR / _env("HF_HOME", "./hf_cache")).resolve())
    max_file_size_mb: int = _env_int("MAX_FILE_SIZE_MB", 2048)
    cleanup_hours: int = _env_int("CLEANUP_HOURS", 24)
    port: int = _env_int("PORT", 8000)
    data_dir: Path = field(default_factory=lambda: BASE_DIR / "data")

    @property
    def max_file_size_bytes(self) -> int:
        return self.max_file_size_mb * 1024 * 1024

    @property
    def uploads_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def results_dir(self) -> Path:
        return self.data_dir / "results"

    def resolve_device(self) -> str:
        """Faktisk enhet: cuda om vald/auto och tillgänglig, annars cpu."""
        if self.device == "cpu":
            return "cpu"
        try:
            import torch  # importeras sent — tung modul

            if torch.cuda.is_available():
                return "cuda"
        except Exception:
            pass
        return "cpu"


settings = Settings()
os.environ.setdefault("HF_HOME", str(settings.hf_home))
