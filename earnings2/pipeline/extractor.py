from __future__ import annotations

import re
from pathlib import Path

import pdfplumber
from bs4 import BeautifulSoup

from earnings2.models import ExtractedTable


def _is_html_file(file_path: Path) -> bool:
    """Detect if a file is HTML by checking its first bytes."""
    with open(file_path, "rb") as f:
        head = f.read(512).lstrip()
    head_lower = head.lower()
    if head[:4] == b"%PDF":
        return False
    return (
        b"<html" in head_lower
        or b"<!doctype" in head_lower
        or b"<document>" in head_lower  # EDGAR SGML wrapper
    )


def _extract_tables_html(html_path: Path) -> list[ExtractedTable]:
    """Extract tables from an HTML file using BeautifulSoup."""
    html = html_path.read_text(encoding="utf-8", errors="replace")
    soup = BeautifulSoup(html, "html.parser")

    tables: list[ExtractedTable] = []
    for table_idx, table_el in enumerate(soup.find_all("table")):
        rows_data: list[list[str]] = []
        for tr in table_el.find_all("tr"):
            cells = tr.find_all(["td", "th"])
            row = [_clean_html_cell(c.get_text()) for c in cells]
            rows_data.append(row)
        if rows_data:
            tables.append(
                ExtractedTable(
                    page_number=table_idx + 1,
                    table_index=table_idx,
                    rows=rows_data,
                )
            )
    return tables


def _clean_html_cell(text: str) -> str:
    """Normalize whitespace in HTML cell text."""
    # Replace Unicode spaces (thin space, em space, etc.) with regular spaces
    text = re.sub(r"[\u2002-\u200b\u2009\xa0]", " ", text)
    # Collapse multiple spaces
    text = re.sub(r" {2,}", " ", text)
    return text.strip()


def _extract_page_texts_html(html_path: Path) -> list[tuple[int, str]]:
    """Extract text from an HTML file. Returns all text as a single 'page'."""
    html = html_path.read_text(encoding="utf-8", errors="replace")
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text("\n", strip=True)
    text = re.sub(r"[\u2002-\u200b\u2009\xa0]", " ", text)
    if text.strip():
        return [(1, text)]
    return []


def extract_tables(pdf_path: Path) -> list[ExtractedTable]:
    """Extract all tables from a PDF or HTML file."""
    if _is_html_file(pdf_path):
        return _extract_tables_html(pdf_path)

    tables: list[ExtractedTable] = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            page_tables = page.extract_tables()
            if not page_tables:
                continue
            for table_idx, raw_table in enumerate(page_tables):
                # Clean cells: replace None with empty string, strip whitespace
                cleaned_rows: list[list[str]] = []
                for row in raw_table:
                    if row is None:
                        continue
                    cleaned_rows.append(
                        [(cell or "").strip() for cell in row]
                    )
                if cleaned_rows:
                    tables.append(
                        ExtractedTable(
                            page_number=page_num,
                            table_index=table_idx,
                            rows=cleaned_rows,
                        )
                    )
    return tables


def extract_page_texts(pdf_path: Path) -> list[tuple[int, str]]:
    """Extract raw text from each page. Returns list of (page_number, text)."""
    if _is_html_file(pdf_path):
        return _extract_page_texts_html(pdf_path)

    pages: list[tuple[int, str]] = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            if text.strip():
                pages.append((page_num, text))
    return pages
