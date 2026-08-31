"""Gemensamma fixtures. Testfilerna i fixtures/ genereras om de saknas."""
from __future__ import annotations

import math
import struct
import wave
from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"

SWEDISH_TEXT = (
    "Anna Andersson bor i Härnösand och arbetar på Tillväxtverket. "
    "Hennes personnummer är 19850312-1234 och telefonnumret är 070-123 45 67. "
    "Annas e-post är anna.andersson@example.se."
)


def _ensure_docx(path: Path) -> None:
    import docx

    document = docx.Document()
    document.add_paragraph(SWEDISH_TEXT)
    document.add_paragraph("Ett andra stycke utan personuppgifter.")
    table = document.add_table(rows=2, cols=2)
    table.rows[0].cells[0].text = "Namn"
    table.rows[0].cells[1].text = "Ort"
    table.rows[1].cells[0].text = "Anna Andersson"
    table.rows[1].cells[1].text = "Härnösand"
    document.save(str(path))


def _ensure_xlsx(path: Path) -> None:
    import openpyxl

    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "Kontakter"
    sheet.append(["Namn", "Telefon"])
    sheet.append(["Anna Andersson", "070-123 45 67"])
    second = workbook.create_sheet("Anteckningar")
    second.append(["Möte med Anna i Härnösand."])
    workbook.save(str(path))


def _ensure_pdf(path: Path) -> None:
    import fitz

    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), SWEDISH_TEXT, fontsize=11)
    document.save(str(path))
    document.close()


def _ensure_empty_pdf(path: Path) -> None:
    import fitz

    document = fitz.open()
    document.new_page()
    document.save(str(path))
    document.close()


def _ensure_wav(path: Path) -> None:
    """En sekund 440 Hz-ton, 16 kHz mono — räcker som ljudfixture."""
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        for i in range(16000):
            value = int(12000 * math.sin(2 * math.pi * 440 * i / 16000))
            wav.writeframes(struct.pack("<h", value))


_GENERATORS = {
    "svensk_text.docx": _ensure_docx,
    "svensk_text.xlsx": _ensure_xlsx,
    "svensk_text.pdf": _ensure_pdf,
    "utan_textlager.pdf": _ensure_empty_pdf,
    "ton.wav": _ensure_wav,
}


@pytest.fixture(scope="session")
def fixtures_dir() -> Path:
    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
    for name, generator in _GENERATORS.items():
        target = FIXTURES_DIR / name
        if not target.exists():
            generator(target)
    return FIXTURES_DIR


@pytest.fixture
def fake_ner():
    """Deterministisk NER-ersättning för tester (modellen är för tung för CI)."""
    import re

    known = {
        "Anna Andersson": "PER",
        "Anna": "PER",
        "Björn Otterberg": "PER",
        "Härnösand": "LOC",
        "Stockholm": "LOC",
        "Tillväxtverket": "ORG",
    }

    def ner(text: str) -> list:
        hits = []
        for phrase, type_code in sorted(known.items(), key=lambda kv: len(kv[0]), reverse=True):
            for match in re.finditer(r"\b" + re.escape(phrase) + r"\b", text):
                if any(h["start"] < match.end() and match.start() < h["end"] for h in hits):
                    continue
                hits.append({
                    "entity_group": type_code,
                    "word": match.group(),
                    "start": match.start(),
                    "end": match.end(),
                    "score": 0.99,
                })
        return hits

    return ner
