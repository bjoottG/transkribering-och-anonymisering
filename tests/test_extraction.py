"""Tester för textextraktion ur pdf/docx/xlsx."""
from __future__ import annotations

import pytest

from app.extraction import extract
from app.jobs import UserVisibleError


def test_docx_stycken_och_tabell(fixtures_dir):
    sections = extract(fixtures_dir / "svensk_text.docx")
    assert len(sections) == 1
    blocks = sections[0].blocks
    paragraphs = [b for b in blocks if b.type == "paragraph"]
    tables = [b for b in blocks if b.type == "table"]
    assert "Anna Andersson" in paragraphs[0].text
    assert len(tables) == 1
    assert tables[0].rows[1] == ["Anna Andersson", "Härnösand"]


def test_xlsx_ett_avsnitt_per_blad(fixtures_dir):
    sections = extract(fixtures_dir / "svensk_text.xlsx")
    assert [s.title for s in sections] == ["Kontakter", "Anteckningar"]
    table = sections[0].blocks[0]
    assert table.type == "table"
    assert table.rows[0] == ["Namn", "Telefon"]
    assert table.rows[1] == ["Anna Andersson", "070-123 45 67"]


def test_pdf_text_extraheras(fixtures_dir):
    sections = extract(fixtures_dir / "svensk_text.pdf")
    all_text = " ".join(b.text for s in sections for b in s.blocks)
    assert "Anna Andersson" in all_text
    assert "19850312-1234" in all_text


def test_pdf_utan_textlager_ger_begripligt_fel(fixtures_dir):
    with pytest.raises(UserVisibleError, match="saknar textlager"):
        extract(fixtures_dir / "utan_textlager.pdf")


def test_korrupt_fil_ger_begripligt_fel(tmp_path):
    trasig = tmp_path / "trasig.docx"
    trasig.write_bytes(b"detta \x00 ar inte en docx")
    with pytest.raises(UserVisibleError, match="kunde inte öppnas"):
        extract(trasig)


def test_gammalt_doc_format_ger_begripligt_fel(tmp_path):
    gammal = tmp_path / "gammal.doc"
    gammal.write_bytes(b"\xd0\xcf\x11\xe0 gammalt worddokument")
    with pytest.raises(UserVisibleError, match="spara om som .docx"):
        extract(gammal)
