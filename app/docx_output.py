"""Generering av Word-filer (.docx) med python-docx."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import docx
from docx.shared import Pt, RGBColor


def _new_document(title: str, subtitle: str) -> docx.document.Document:
    document = docx.Document()
    document.add_heading(title, level=1)
    meta = document.add_paragraph(subtitle)
    meta.runs[0].font.size = Pt(9)
    meta.runs[0].font.color.rgb = RGBColor(0x60, 0x60, 0x60)
    return document


def _timestamp(seconds: float) -> str:
    total = int(seconds)
    return f"{total // 3600:02d}:{(total % 3600) // 60:02d}:{total % 60:02d}"


def _now_string() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def build_transcription_docx(
    path: Path,
    source_name: str,
    segments: list,
    timestamps: bool = True,
    anonymized: bool = False,
) -> Path:
    """Transkription som Word-fil. segments: list[dict] med start, end, text."""
    label = "Anonymiserad transkription" if anonymized else "Transkription"
    document = _new_document(source_name, f"{label} — genererad {_now_string()}")
    for segment in segments:
        text = str(segment.get("text", "")).strip()
        if not text:
            continue
        paragraph = document.add_paragraph()
        if timestamps:
            run = paragraph.add_run(f"[{_timestamp(float(segment.get('start', 0)))}] ")
            run.font.color.rgb = RGBColor(0x60, 0x60, 0x60)
        paragraph.add_run(text)
    document.save(str(path))
    return path


def build_document_docx(path: Path, source_name: str, sections: list, anonymized: bool = False) -> Path:
    """Dokumentinnehåll (list[Section] från extraction) som Word-fil."""
    label = "Anonymiserad version" if anonymized else "Konverterad version"
    document = _new_document(source_name, f"{label} — genererad {_now_string()}")
    for section in sections:
        if section.title:
            document.add_heading(section.title, level=2)
        for block in section.blocks:
            if block.type == "paragraph":
                document.add_paragraph(block.text)
            elif block.type == "table" and block.rows:
                columns = max(len(row) for row in block.rows)
                table = document.add_table(rows=len(block.rows), cols=columns)
                table.style = "Table Grid"
                for row_index, row in enumerate(block.rows):
                    for column_index, cell in enumerate(row):
                        table.rows[row_index].cells[column_index].text = cell
                document.add_paragraph()
    document.save(str(path))
    return path


def build_codebook_docx(path: Path, source_name: str, entries: list) -> Path:
    """Kodnyckel som Word-fil. entries: list[CodebookEntry]."""
    document = _new_document(f"Kodnyckel — {source_name}", f"Genererad {_now_string()}")

    warning = document.add_paragraph()
    run = warning.add_run("⚠ Innehåller ursprungliga personuppgifter — hantera och lagra separat "
                          "från den anonymiserade filen.")
    run.bold = True
    run.font.color.rgb = RGBColor(0xB0, 0x00, 0x00)

    if not entries:
        document.add_paragraph("Inga uppgifter ersattes — kodnyckeln är tom.")
    else:
        table = document.add_table(rows=1, cols=4)
        table.style = "Table Grid"
        headers = ("Pseudonym", "Ursprunglig uppgift", "Typ", "Antal förekomster")
        for index, header in enumerate(headers):
            cell = table.rows[0].cells[index]
            cell.text = header
            cell.paragraphs[0].runs[0].bold = True
        for entry in entries:
            row = table.add_row()
            row.cells[0].text = entry.pseudonym
            row.cells[1].text = entry.original
            row.cells[2].text = entry.type_label
            row.cells[3].text = str(entry.count)
    document.save(str(path))
    return path
