"""Förhämtar modellerna till den lokala cachen så att första jobbet inte behöver vänta.

Kör:  python scripts/download_models.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings  # noqa: E402  (sätter HF_HOME)


def main() -> None:
    print(f"Modellcache: {settings.hf_home}")

    print(f"\n1/2 Hämtar NER-modellen {settings.ner_model} ...")
    from transformers import AutoModelForTokenClassification, AutoTokenizer

    AutoTokenizer.from_pretrained(settings.ner_model)
    AutoModelForTokenClassification.from_pretrained(settings.ner_model)
    print("    Klar.")

    print(f"\n2/2 Hämtar Whisper-modellen {settings.whisper_model} ...")
    try:
        from faster_whisper import WhisperModel

        WhisperModel(settings.whisper_model, device="cpu", compute_type="int8")
        print("    Klar (faster-whisper/CTranslate2-format).")
    except Exception as exc:  # t.ex. faster-whisper saknas
        print(f"    faster-whisper misslyckades ({exc}) — hämtar transformers-varianten i stället.")
        from transformers import AutoModelForSpeechSeq2Seq, AutoProcessor

        AutoProcessor.from_pretrained(settings.whisper_model)
        AutoModelForSpeechSeq2Seq.from_pretrained(settings.whisper_model)
        print("    Klar (transformers-format).")

    print("\nAlla modeller är nedladdade och cachade.")


if __name__ == "__main__":
    main()
