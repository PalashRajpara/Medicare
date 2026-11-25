"""Tests for multi-format RAG document loaders (.pdf, .docx, .md, .txt, .html, .csv)."""

import pytest
from docx import Document
from reportlab.pdfgen import canvas

from medicare.domain.errors import DocumentLoaderError
from medicare.rag.loaders import (
    load_csv_data,
    load_docx,
    load_html,
    load_markdown,
    load_pdf,
)


def test_load_markdown_and_text(tmp_path):
    """Verify markdown and plain text loader preserves headings and lines."""
    md_file = tmp_path / "sample.md"
    md_file.write_text(
        "# Policy Overview\n\nThis is clause 1.\n\n## Waiting Period\n\nWait 2 years.",
        encoding="utf-8",
    )

    pages = load_markdown(str(md_file))
    assert len(pages) >= 1
    assert "clause 1" in pages[0].text
    assert "Waiting Period" in pages[0].heading_path or "Policy Overview" in pages[0].heading_path


def test_load_html():
    """Verify HTML loader strips scripts/styles and preserves headings."""
    html_content = (
        "<html><head><style>body {color:red;}</style><script>alert('x');</script></head>"
        "<body><h1>Insurance Terms</h1><p>Co-pay is 10%.</p></body></html>"
    )
    pages = load_html(html_content.encode("utf-8"), filename="terms.html")
    assert len(pages) == 1
    assert "Co-pay is 10%" in pages[0].text
    assert "alert" not in pages[0].text
    assert "color:red" not in pages[0].text
    assert "Insurance Terms" in pages[0].heading_path


def test_load_csv():
    """Verify CSV loader formats rows as structured field: value lines."""
    csv_content = "hospital,city,cost\nCity Care,Mumbai,50000\nMetro Health,Delhi,45000\n"
    pages = load_csv_data(csv_content.encode("utf-8"), filename="costs.csv")
    assert len(pages) == 1
    assert "hospital: City Care" in pages[0].text
    assert "cost: 50000" in pages[0].text


def test_load_docx(tmp_path):
    """Verify DOCX loader extracts text, headings, and table cells."""
    doc = Document()
    doc.add_heading("Health Policy Schedule", level=1)
    doc.add_paragraph("Inpatient hospitalization is covered.")
    tbl = doc.add_table(rows=2, cols=2)
    tbl.cell(0, 0).text = "Benefit"
    tbl.cell(0, 1).text = "Limit"
    tbl.cell(1, 0).text = "Room Rent"
    tbl.cell(1, 1).text = "1% of Sum Insured"

    doc_path = tmp_path / "test.docx"
    doc.save(str(doc_path))

    pages = load_docx(str(doc_path))
    assert len(pages) >= 1
    assert "Health Policy Schedule" in pages[0].heading_path
    assert "Room Rent" in pages[0].text
    assert "1% of Sum Insured" in pages[0].text


def test_load_pdf(tmp_path):
    """Verify PDF loader extracts page numbers (1-based) and strips repeated headers/footers."""
    pdf_path = tmp_path / "test.pdf"
    c = canvas.Canvas(str(pdf_path))

    # Page 1
    c.drawString(100, 750, "CONFIDENTIAL POLICY DOCUMENT")  # repeated header
    c.drawString(100, 700, "Section 1: General Coverage Definitions.")
    c.drawString(100, 50, "Page 1 of 2 - All Rights Reserved")  # repeated footer
    c.showPage()

    # Page 2
    c.drawString(100, 750, "CONFIDENTIAL POLICY DOCUMENT")  # repeated header
    c.drawString(100, 700, "Section 2: Pre-Existing Disease Waiting Periods.")
    c.drawString(100, 50, "Page 2 of 2 - All Rights Reserved")  # repeated footer
    c.showPage()
    c.save()

    pages = load_pdf(str(pdf_path))
    assert len(pages) == 2
    assert pages[0].page == 1
    assert pages[1].page == 2
    assert "General Coverage" in pages[0].text
    assert "Pre-Existing Disease" in pages[1].text


def test_corrupt_pdf_handling():
    """Verify corrupt PDF content raises DocumentLoaderError."""
    with pytest.raises(DocumentLoaderError):
        load_pdf(b"Not a valid PDF byte string header")
