"""Tester för generering av Word-filer."""
from __future__ import annotations

import docx

from app.anonymization import CodebookEntry
from app.docx_output import build_codebook_docx, build_document_docx, build_transcription_docx
from app.extraction import Block, Section


def _all_text(path) -> str:
    document = docx.Document(str(path))
    parts = [p.text for p in document.paragraphs]
    parts += [cell.text for table in document.tables for row in table.rows for cell in row.cells]
    return "\n".join(parts)


def test_transkription_med_tidsstamplar(tmp_path):
    segments = [
        {"start": 0.0, "end": 4.2, "text": "Hej och välkomna."},
        {"start": 4.2, "end": 3661.0, "text": "Vi börjar nu."},
    ]
    path = build_transcription_docx(tmp_path / "ut.docx", "möte.mp3", segments, timestamps=True)
    text = _all_text(path)
    assert "möte.mp3" in text
    assert "[00:00:00] Hej och välkomna." in text
    assert "[00:00:04] Vi börjar nu." in text


def test_transkription_utan_tidsstamplar(tmp_path):
    segments = [{"start": 0.0, "end": 2.0, "text": "Hej."}]
    path = build_transcription_docx(tmp_path / "ut.docx", "möte.mp3", segments, timestamps=False)
    text = _all_text(path)
    assert "Hej." in text
    assert "[00:00:00]" not in text


def test_dokument_med_sektioner_och_tabell(tmp_path):
    sections = [
        Section(title="Blad 1", blocks=[
            Block(type="paragraph", text="Ett stycke."),
            Block(type="table", rows=[["A", "B"], ["1", "2"]]),
        ]),
    ]
    path = build_document_docx(tmp_path / "ut.docx", "källa.xlsx", sections)
    text = _all_text(path)
    assert "Blad 1" in text and "Ett stycke." in text and "A" in text and "2" in text


def test_kodnyckel_tabell_och_varning(tmp_path):
    entries = [
        CodebookEntry("[Person 1]", "Anna Andersson", "Person", 3),
        CodebookEntry("[Telefon 1]", "070-123 45 67", "Telefon", 1),
    ]
    path = build_codebook_docx(tmp_path / "nyckel.docx", "källa.docx", entries)
    text = _all_text(path)
    assert "Innehåller ursprungliga personuppgifter" in text
    assert "[Person 1]" in text and "Anna Andersson" in text and "3" in text


def test_tom_kodnyckel(tmp_path):
    path = build_codebook_docx(tmp_path / "nyckel.docx", "källa.docx", [])
    assert "kodnyckeln är tom" in _all_text(path)


def test_tidslinje_docx(tmp_path):
    from app.docx_output import build_timeline_docx

    events = [
        {"time": 0.0, "kind": "tal", "text": "Hej och välkomna."},
        {"time": 5.0, "kind": "skärm", "text": "Startsidan med menyn Ärenden visas."},
    ]
    path = build_timeline_docx(tmp_path / "tidslinje.docx", "film.mp4", events, timestamps=True)
    text = _all_text(path)
    assert "film.mp4" in text
    assert "[00:00:00] Tal: Hej och välkomna." in text
    assert "[00:00:05] Skärm: Startsidan med menyn Ärenden visas." in text
