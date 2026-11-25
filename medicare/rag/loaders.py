"""Document loaders for PDF, DOCX, Markdown, Text, HTML, and CSV formats."""

import csv
import io
import os
import re
from collections import Counter
from collections.abc import Callable
from typing import Any

import docx
from bs4 import BeautifulSoup
from pypdf import PdfReader

from medicare.config import settings
from medicare.domain.errors import (
    DocumentLoaderError,
    MediCareError,
    UnsupportedFileTypeError,
)
from medicare.rag.models import PageText

UnsupportedFormatError = UnsupportedFileTypeError


class EncryptedPDFError(MediCareError):
    """Raised when a PDF file is password protected or encrypted."""

    def __init__(self, message: str = "Encrypted PDFs are not supported") -> None:
        super().__init__(message, status_code=400)


class DocumentTooLargeError(MediCareError):
    """Raised when document page count or size exceeds allowed threshold."""

    def __init__(self, message: str) -> None:
        super().__init__(message, status_code=400)


class NoExtractableTextError(MediCareError):
    """Raised when no text could be extracted from a document."""

    def __init__(self, message: str = "No extractable text found in document") -> None:
        super().__init__(message, status_code=400)


def load_pdf(source: str | bytes) -> list[PageText]:
    """Extract pages and text from a PDF document using pypdf.

    Performs header/footer stripping, hyphenated line un-breaking,
    and whitespace normalization.
    """
    stream = io.BytesIO(source) if isinstance(source, bytes) else open(source, "rb")  # noqa: SIM115
    try:
        try:
            reader = PdfReader(stream)
            if reader.is_encrypted:
                raise EncryptedPDFError()
            total_pages = len(reader.pages)
        except (EncryptedPDFError, DocumentTooLargeError):
            raise
        except Exception as e:
            raise DocumentLoaderError(f"Failed to parse PDF document: {e}") from e

        if total_pages > settings.UPLOAD_MAX_PAGES:
            raise DocumentTooLargeError(
                f"PDF has {total_pages} pages; maximum allowed is {settings.UPLOAD_MAX_PAGES}"
            )

        raw_pages_lines: list[list[str]] = []
        for page in reader.pages:
            text = page.extract_text() or ""
            lines = [line.strip() for line in text.splitlines() if line.strip()]
            raw_pages_lines.append(lines)

        # Detect headers/footers: lines that appear on >60% of pages (for docs with >=2 pages)
        repeated_lines = set()
        if total_pages >= 2:
            line_counts = Counter()
            for lines in raw_pages_lines:
                unique_page_lines = set(lines)
                for line in unique_page_lines:
                    # Ignore purely numeric or single character lines
                    if len(line) > 3:
                        line_counts[line] += 1
            threshold = total_pages * 0.6
            repeated_lines = {line for line, cnt in line_counts.items() if cnt > threshold}

        results: list[PageText] = []
        for idx, lines in enumerate(raw_pages_lines, start=1):
            cleaned_lines = [line for line in lines if line not in repeated_lines]
            combined = "\n".join(cleaned_lines)

            # Join hyphenated line breaks: e.g. "pre-\nexisting" -> "pre-existing" or "medi-\ncation" -> "medication"
            combined = re.sub(r"(\w+)-\n(\w+)", r"\1\2", combined)
            # Collapse multiple spaces and linebreaks
            combined = re.sub(r"[ \t]+", " ", combined)
            combined = re.sub(r"\n\s*\n+", "\n\n", combined).strip()

            if combined:
                results.append(PageText(page=idx, text=combined, heading_path=[]))

        if not results:
            raise NoExtractableTextError("PDF contains no extractable text.")

        return results
    finally:
        if isinstance(source, str):
            stream.close()


def load_docx(source: str | bytes) -> list[PageText]:
    """Extract paragraphs, headings, and tables from a DOCX document."""
    stream = io.BytesIO(source) if isinstance(source, bytes) else source
    doc = docx.Document(stream)

    results: list[PageText] = []
    current_headings: list[str] = []
    current_text_parts: list[str] = []

    for p in doc.paragraphs:
        text = p.text.strip()
        if not text:
            continue

        style_name = (p.style.name or "").lower() if p.style else ""
        if "heading 1" in style_name:
            if current_text_parts:
                results.append(
                    PageText(
                        page=1,
                        text="\n\n".join(current_text_parts),
                        heading_path=list(current_headings),
                    )
                )
                current_text_parts = []
            current_headings = [text]
        elif "heading 2" in style_name:
            if current_text_parts:
                results.append(
                    PageText(
                        page=1,
                        text="\n\n".join(current_text_parts),
                        heading_path=list(current_headings),
                    )
                )
                current_text_parts = []
            current_headings = current_headings[:1] + [text]
        elif "heading 3" in style_name:
            if current_text_parts:
                results.append(
                    PageText(
                        page=1,
                        text="\n\n".join(current_text_parts),
                        heading_path=list(current_headings),
                    )
                )
                current_text_parts = []
            current_headings = current_headings[:2] + [text]
        else:
            current_text_parts.append(text)

    # Tables
    for table in doc.tables:
        rows_data: list[list[str]] = []
        for row in table.rows:
            row_cells = [cell.text.strip().replace("\n", " ") for cell in row.cells]
            if any(row_cells):
                rows_data.append(row_cells)
        if rows_data:
            headers = rows_data[0]
            for row in rows_data[1:]:
                row_str = "; ".join(f"{h}: {v}" for h, v in zip(headers, row, strict=False) if v)
                if row_str:
                    current_text_parts.append(row_str)

    if current_text_parts:
        results.append(
            PageText(
                page=1, text="\n\n".join(current_text_parts), heading_path=list(current_headings)
            )
        )

    if not results:
        raise NoExtractableTextError("DOCX document contains no text.")

    return results


def _read_source_text(source: str | bytes) -> str:
    """Read text from bytes or file path using proper file context management."""
    if isinstance(source, bytes):
        return source.decode("utf-8")
    if os.path.exists(str(source)):
        with open(str(source), encoding="utf-8") as f:
            return f.read()
    return str(source)


def load_markdown(source: str | bytes) -> list[PageText]:
    """Extract sections from Markdown using heading structure."""
    text = _read_source_text(source)
    lines = text.splitlines()

    results: list[PageText] = []
    current_headings: list[str] = []
    current_paras: list[str] = []

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("#"):
            match = re.match(r"^(#{1,6})\s+(.*)$", stripped)
            if match:
                level = len(match.group(1))
                h_text = match.group(2).strip()
                if current_paras:
                    results.append(
                        PageText(
                            page=1,
                            text="\n\n".join(current_paras),
                            heading_path=list(current_headings),
                        )
                    )
                    current_paras = []
                current_headings = current_headings[: level - 1] + [h_text]
                continue
        if stripped:
            current_paras.append(stripped)

    if current_paras:
        results.append(
            PageText(page=1, text="\n\n".join(current_paras), heading_path=list(current_headings))
        )

    if not results:
        raise NoExtractableTextError("Markdown document contains no text.")

    return results


def load_text(source: str | bytes) -> list[PageText]:
    """Extract text from plain text file split by double newlines."""
    text = _read_source_text(source)
    paras = [p.strip() for p in text.split("\n\n") if p.strip()]
    if not paras:
        raise NoExtractableTextError("Plain text document is empty.")
    return [PageText(page=1, text="\n\n".join(paras), heading_path=[])]


def load_html(source: str | bytes, filename: str | None = None, **kwargs: Any) -> list[PageText]:
    """Extract clean text and headings from HTML content."""
    html = _read_source_text(source)
    soup = BeautifulSoup(html, "html.parser")

    # Strip scripts, styles, navigations, footers
    for tag in soup(["script", "style", "nav", "footer", "header", "noscript"]):
        tag.decompose()

    results: list[PageText] = []
    current_heading = ""
    current_paras: list[str] = []

    for element in soup.find_all(["h1", "h2", "h3", "p", "li"]):
        txt = element.get_text().strip()
        if not txt:
            continue
        if element.name in ("h1", "h2", "h3"):
            if current_paras:
                results.append(
                    PageText(
                        page=1,
                        text="\n\n".join(current_paras),
                        heading_path=[current_heading] if current_heading else [],
                    )
                )
                current_paras = []
            current_heading = txt
        else:
            current_paras.append(txt)

    if current_paras:
        results.append(
            PageText(
                page=1,
                text="\n\n".join(current_paras),
                heading_path=[current_heading] if current_heading else [],
            )
        )

    if not results:
        raise NoExtractableTextError("HTML contains no extractable text.")

    return results


def load_csv_data(
    source: str | bytes, filename: str | None = None, **kwargs: Any
) -> list[PageText]:
    """Extract CSV rows formatted as key-value lines, grouping 10 rows per unit."""
    content = _read_source_text(source)
    reader = csv.reader(io.StringIO(content))
    rows = list(reader)
    if not rows:
        raise NoExtractableTextError("CSV file is empty.")

    header = rows[0]
    results: list[PageText] = []
    chunk_rows: list[str] = []

    for idx, row in enumerate(rows[1:], start=1):
        row_str = "; ".join(f"{h}: {v}" for h, v in zip(header, row, strict=False) if v)
        if row_str:
            chunk_rows.append(row_str)
        if len(chunk_rows) >= 10:
            results.append(PageText(page=1, text="\n".join(chunk_rows), heading_path=["CSV Data"]))
            chunk_rows = []

    if chunk_rows:
        results.append(PageText(page=1, text="\n".join(chunk_rows), heading_path=["CSV Data"]))

    return results


class LoaderRegistry:
    """Registry managing format loaders and extensions."""

    def __init__(self) -> None:
        self._loaders: dict[str, Callable[[Any], list[PageText]]] = {
            ".pdf": load_pdf,
            ".docx": load_docx,
            ".md": load_markdown,
            ".txt": load_text,
            ".html": load_html,
            ".htm": load_html,
            ".csv": load_csv_data,
        }

    def register_loader(self, ext: str, loader_fn: Callable[[Any], list[PageText]]) -> None:
        normalized = ext.lower() if ext.startswith(".") else f".{ext.lower()}"
        self._loaders[normalized] = loader_fn

    def get_loader(self, ext: str) -> Callable[[Any], list[PageText]]:
        normalized = ext.lower() if ext.startswith(".") else f".{ext.lower()}"
        if normalized not in self._loaders:
            raise UnsupportedFormatError(normalized)
        return self._loaders[normalized]


loader_registry = LoaderRegistry()
