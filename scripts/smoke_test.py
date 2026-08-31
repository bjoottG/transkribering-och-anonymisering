"""Manuellt smoke-test som kör hela kedjan på fixtures med riktiga modeller.

Kräver att modellerna finns lokalt (kör scripts/download_models.py först)
och att ffmpeg är installerat. Kör:  python scripts/smoke_test.py
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.anonymization import Anonymizer  # noqa: E402
from app.docx_output import build_codebook_docx, build_document_docx, build_transcription_docx  # noqa: E402
from app.extraction import Block, Section, extract  # noqa: E402
from app.transcription import extract_audio, transcribe  # noqa: E402

FIXTURES = Path(__file__).resolve().parent.parent / "tests" / "fixtures"


def _require_fixtures() -> None:
    if not (FIXTURES / "svensk_text.docx").exists():
        print("Fixtures saknas — kör 'pytest' en gång först (de genereras då).")
        sys.exit(1)


def main() -> None:
    _require_fixtures()
    out_dir = Path(tempfile.mkdtemp(prefix="smoke_test_"))
    print(f"Utdata: {out_dir}\n")

    failures = 0

    # 1. Dokumentflödet: extraktion -> anonymisering -> Word + kodnyckel
    for fixture in ("svensk_text.docx", "svensk_text.xlsx", "svensk_text.pdf"):
        print(f"— Dokument: {fixture}")
        try:
            sections = extract(FIXTURES / fixture)
            anonymizer = Anonymizer()  # riktig KB-BERT-NER
            anonymized = [
                Section(
                    title=section.title,
                    blocks=[
                        Block(type="paragraph", text=anonymizer.anonymize(block.text))
                        if block.type == "paragraph"
                        else Block(
                            type="table",
                            rows=[[anonymizer.anonymize(c) for c in row] for row in block.rows],
                        )
                        for block in section.blocks
                    ],
                )
                for section in sections
            ]
            stem = Path(fixture).stem
            build_document_docx(out_dir / f"{stem}_anonymiserad.docx", fixture, anonymized, anonymized=True)
            entries = anonymizer.codebook()
            build_codebook_docx(out_dir / f"{stem}_kodnyckel.docx", fixture, entries)
            assert entries, "kodnyckeln blev tom — NER hittade inget"
            print(f"  OK — {len(entries)} poster i kodnyckeln")
        except Exception as exc:
            failures += 1
            print(f"  MISSLYCKADES: {exc}")

    # 2. Transkriberingsflödet: ffmpeg -> KB-Whisper -> Word
    print("— Ljud: ton.wav (förvänta tomt/kort resultat — fixturen är en ton)")
    try:
        wav = extract_audio(FIXTURES / "ton.wav", out_dir / "ljud_16k.wav")
        segments = transcribe(wav)
        build_transcription_docx(out_dir / "ton_transkription.docx", "ton.wav", segments)
        print(f"  OK — {len(segments)} segment")
    except Exception as exc:
        failures += 1
        print(f"  MISSLYCKADES: {exc}")

    print(f"\n{'ALLT OK' if failures == 0 else f'{failures} steg misslyckades'} — filer i {out_dir}")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
