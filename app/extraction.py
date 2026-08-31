"""Textextraktion ur PDF (PyMuPDF), Word (python-docx) och Excel (openpyxl).

Resultatet är en lista av sektioner med block som bevarar dokumentets struktur:
stycken och tabeller för Word, ett blad per sektion för Excel, styckevis text för PDF.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from app.jobs import UserVisibleError


@dataclass
class Block:
    """Ett stycke ('paragraph', text) eller en tabell ('table', rows)."""

    type: str
    text: str = ""
    rows: list = field(default_factory=list)  # list[list[str]]


@dataclass
class Section:
    title: str = ""
    blocks: list = field(default_factory=list)  # list[Block]


def extract(path: Path) -> list:
    """Extrahera text ur pdf/docx/xlsx. Returnerar list[Section]."""
    ext = path.suffix.lower().lstrip(".")
    if ext == "pdf":
        return _extract_pdf(path)
    if ext in ("docx", "doc"):
        return _extract_docx(path)
    if ext in ("xlsx", "xls"):
        return _extract_xlsx(path)
    raise UserVisibleError(f"Filformatet .{ext} stöds inte för dokumentanonymisering.")


def _extract_pdf(path: Path) -> list:
    import fitz  # PyMuPDF

    try:
        doc = fitz.open(path)
    except Exception:
        raise UserVisibleError(
            "PDF-filen kunde inte öppnas — den kan vara skadad eller lösenordsskyddad."
        ) from None

    sections: list = []
    has_text = False
    with doc:
        if doc.needs_pass:
            raise UserVisibleError("PDF-filen är lösenordsskyddad och kan inte läsas.")
        for page_number, page in enumerate(doc, start=1):
            text = page.get_text("text").strip()
            if not text:
                continue
            has_text = True
            blocks = [
                Block(type="paragraph", text=" ".join(part.split()))
                for part in text.split("\n\n")
                if part.strip()
            ]
            sections.append(Section(title=f"Sida {page_number}", blocks=blocks))
    if not has_text:
        raise UserVisibleError(
            "Dokumentet saknar textlager. Skannade PDF:er utan text stöds inte "
            "(OCR ingår inte i denna version)."
        )
    return sections


def _extract_docx(path: Path) -> list:
    if path.suffix.lower() == ".doc":
        raise UserVisibleError(
            "Det gamla Word-formatet (.doc) kan inte läsas. Öppna filen i Word, "
            "spara om som .docx och försök igen."
        )
    import docx
    from docx.table import Table as DocxTable
    from docx.text.paragraph import Paragraph as DocxParagraph

    try:
        document = docx.Document(str(path))
    except Exception:
        raise UserVisibleError(
            "Word-filen kunde inte öppnas — den kan vara skadad eller i fel format."
        ) from None

    blocks: list = []
    try:
        contents = list(document.iter_inner_content())
    except AttributeError:  # äldre python-docx utan iter_inner_content
        contents = list(document.paragraphs) + list(document.tables)

    for item in contents:
        if isinstance(item, DocxParagraph):
            if item.text.strip():
                blocks.append(Block(type="paragraph", text=item.text))
        elif isinstance(item, DocxTable):
            rows = [[cell.text for cell in row.cells] for row in item.rows]
            if any(cell.strip() for row in rows for cell in row):
                blocks.append(Block(type="table", rows=rows))
    return [Section(blocks=blocks)]


def _extract_xlsx(path: Path) -> list:
    if path.suffix.lower() == ".xls":
        raise UserVisibleError(
            "Det gamla Excel-formatet (.xls) kan inte läsas. Öppna filen i Excel, "
            "spara om som .xlsx och försök igen."
        )
    import openpyxl

    try:
        workbook = openpyxl.load_workbook(path, data_only=True, read_only=True)
    except Exception:
        raise UserVisibleError(
            "Excel-filen kunde inte öppnas — den kan vara skadad eller i fel format."
        ) from None

    sections: list = []
    for sheet in workbook.worksheets:
        rows: list = []
        for row in sheet.iter_rows(values_only=True):
            cells = ["" if value is None else str(value) for value in row]
            if any(cell.strip() for cell in cells):
                rows.append(cells)
        if rows:
            sections.append(Section(title=sheet.title, blocks=[Block(type="table", rows=rows)]))
    workbook.close()
    return sections
