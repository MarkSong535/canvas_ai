"""
Extract readable text from course files so the agent can work with their contents, not just link to them.

Supported: PDF (per page), Word .docx (paragraphs and tables), PowerPoint .pptx (per slide, with notes),
Excel .xlsx (per sheet), old .doc/.ppt/.xls (via catdoc), Jupyter notebooks, and text-like files
(txt, md, csv, code, HTML, ...). Anything else (images, video, archives, scanned PDFs without a text layer)
returns no text and a note saying why, so the agent can tell the student instead of guessing.
"""

import io
import json
import os
import re
import shutil
import subprocess
import tempfile
from html.parser import HTMLParser
from pathlib import Path

MAX_SHEET_ROWS = 2000

TEXT_EXTENSIONS = {
    ".txt", ".md", ".markdown", ".csv", ".tsv", ".json", ".xml", ".yaml", ".yml", ".tex", ".bib", ".rtf",
    ".py", ".java", ".c", ".h", ".cpp", ".hpp", ".cc", ".js", ".ts", ".r", ".m", ".sql", ".sh", ".go", ".rs",
    ".rb", ".php", ".swift", ".kt", ".scala", ".hs", ".lisp", ".asm", ".s", ".v", ".sv", ".vhd", ".ml", ".jl",
}
HTML_EXTENSIONS = {".html", ".htm", ".xhtml"}
# Old binary Office formats, read with the catdoc package's tools (installed in the Docker image)
LEGACY_OFFICE = {".doc": ["catdoc", "-w", "-d", "utf-8"], ".ppt": ["catppt", "-d", "utf-8"],
                 ".xls": ["xls2csv", "-d", "utf-8"]}


class _HTMLText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._skip += 1
        elif tag in ("p", "br", "div", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6"):
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self._skip:
            self._skip -= 1

    def handle_data(self, data):
        if not self._skip:
            self.parts.append(data)


def html_to_text(html: str) -> str:
    parser = _HTMLText()
    parser.feed(html)
    return re.sub(r"\n{3,}", "\n\n", "".join(parser.parts)).strip()


def extract_text(data: bytes, name: str, content_type: str | None = None) -> tuple[str, str]:
    """Return (text, note). `text` is empty when nothing readable was found; `note` explains why."""
    ext = Path(name or "").suffix.lower()
    content_type = (content_type or "").lower()
    try:
        # The file name and the file's own signature decide; the declared content type is only a fallback
        if ext == ".pdf" or data[:5] == b"%PDF-" or (not ext and content_type == "application/pdf"):
            return _pdf(data)
        if ext == ".docx":
            return _docx(data), ""
        if ext == ".pptx":
            return _pptx(data), ""
        if ext in (".xlsx", ".xlsm"):
            return _xlsx(data)
        if ext == ".ipynb":
            return _notebook(data), ""
        if ext in HTML_EXTENSIONS or content_type == "text/html":
            return html_to_text(data.decode("utf-8", errors="replace")), ""
        if ext in TEXT_EXTENSIONS or content_type.startswith("text/"):
            return data.decode("utf-8", errors="replace"), ""
    except Exception as exc:  # noqa: BLE001 - a broken file must not break the agent
        return "", f"The file couldn't be read ({type(exc).__name__}: {str(exc)[:200]})."
    if ext in LEGACY_OFFICE:
        return _legacy_office(data, ext)
    kind = content_type or (ext[1:] if ext else "unknown")
    return "", f"This is a {kind} file, which has no readable text (images, video, audio and archives aren't read)."


def _pdf(data: bytes) -> tuple[str, str]:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    pages = []
    for number, page in enumerate(reader.pages, start=1):
        pages.append(f"--- Page {number} ---\n{(page.extract_text() or '').strip()}")
    text = "\n\n".join(pages)
    if not re.search(r"\w", re.sub(r"--- Page \d+ ---", "", text)):
        return "", (f"This PDF has {len(reader.pages)} page(s) but no text layer (probably scanned images), "
                    "so its text can't be read.")
    return text, ""


def _docx(data: bytes) -> str:
    import docx

    document = docx.Document(io.BytesIO(data))
    parts = [p.text for p in document.paragraphs if p.text.strip()]
    for number, table in enumerate(document.tables, start=1):
        parts.append(f"--- Table {number} ---")
        for row in table.rows:
            parts.append(" | ".join(cell.text.strip() for cell in row.cells))
    return "\n".join(parts)


def _pptx(data: bytes) -> str:
    from pptx import Presentation

    presentation = Presentation(io.BytesIO(data))
    slides = []
    for number, slide in enumerate(presentation.slides, start=1):
        lines = [f"--- Slide {number} ---"]
        for shape in slide.shapes:
            if shape.has_text_frame and shape.text_frame.text.strip():
                lines.append(shape.text_frame.text.strip())
            if getattr(shape, "has_table", False) and shape.has_table:
                for row in shape.table.rows:
                    lines.append(" | ".join(cell.text.strip() for cell in row.cells))
        if slide.has_notes_slide and slide.notes_slide.notes_text_frame.text.strip():
            lines.append("Notes: " + slide.notes_slide.notes_text_frame.text.strip())
        slides.append("\n".join(lines))
    return "\n\n".join(slides)


def _xlsx(data: bytes) -> tuple[str, str]:
    from openpyxl import load_workbook

    workbook = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    sheets, truncated = [], False
    for sheet in workbook.worksheets:
        rows = [f"--- Sheet: {sheet.title} ---"]
        for index, row in enumerate(sheet.iter_rows(values_only=True)):
            if index >= MAX_SHEET_ROWS:
                truncated = True
                break
            if any(cell is not None for cell in row):
                rows.append("\t".join("" if cell is None else str(cell) for cell in row))
        sheets.append("\n".join(rows))
    note = f"Only the first {MAX_SHEET_ROWS} rows of each sheet are included." if truncated else ""
    return "\n\n".join(sheets), note


def _legacy_office(data: bytes, ext: str) -> tuple[str, str]:
    command = LEGACY_OFFICE[ext]
    if not shutil.which(command[0]):
        return "", f"This is an old {ext} Office file, and the tool that reads those ({command[0]}) isn't installed."
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "file" + ext)
        with open(path, "wb") as f:
            f.write(data)
        try:
            result = subprocess.run([*command, path], capture_output=True, timeout=60)
        except subprocess.TimeoutExpired:
            return "", f"Reading this {ext} file took too long."
    text = result.stdout.decode("utf-8", errors="replace").strip()
    if result.returncode != 0 or not text:
        return "", f"This {ext} file couldn't be read (it may be damaged or not a real {ext} file)."
    return text, ""


def _notebook(data: bytes) -> str:
    notebook = json.loads(data.decode("utf-8", errors="replace"))
    cells = []
    for number, cell in enumerate(notebook.get("cells", []), start=1):
        source = "".join(cell.get("source", []))
        cells.append(f"--- Cell {number} ({cell.get('cell_type', '?')}) ---\n{source}")
    return "\n\n".join(cells)
