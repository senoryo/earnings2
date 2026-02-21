"""Goldman Sachs earnings press release HTML parser.

Parses financial tables from SEC EDGAR 8-K Exhibit 99.1 (HTML format).
Goldman Sachs blocks direct PDF downloads, so we use EDGAR filings instead.

The key data table is the quarterly segment breakdown ("THREE MONTHS ENDED"),
which contains:
  - Segment sub-lines: Advisory, FICC, Equities, etc.
  - Segment totals: Investment banking fees, FICC, Equities, Net revenues
  - Firmwide total: Total net revenues

Two segment eras exist:
  - **2023+**: Global Banking & Markets (IB fees, FICC, Equities)
  - **Pre-2023**: Investment Banking + Institutional Client Services
    (Total Investment Banking, FICC Client Execution, Total Equities)

In both eras, the same five metrics are extracted.
"""

from __future__ import annotations

import re

from earnings2.models import ExtractedTable, ParsedMetric, Quarter
from earnings2.parsers.base import CompanyParser
from earnings2.parsers.registry import register_parser


def _parse_number(text: str) -> float | None:
    """Parse a number, handling ($1,234) negatives, $ prefixes, Unicode spaces."""
    text = re.sub(r"[\u2002-\u200b\u2009\xa0]", " ", text)
    text = text.strip().lstrip("$").strip()
    if not text or text in ("-", "—", "\u2013", "\u2014", "N/A", "NM", "N.M.", "*", "--", "–"):
        return None

    negative = False
    if text.startswith("(") and text.endswith(")"):
        negative = True
        text = text[1:-1]

    text = text.replace(",", "").replace(" ", "").strip()
    if text.endswith("%"):
        return None

    try:
        val = float(text)
        return -val if negative else val
    except ValueError:
        return None


def _find_quarterly_segment_table(tables: list[ExtractedTable]) -> ExtractedTable | None:
    """Find the quarterly segment breakdown table.

    This is the table with "THREE MONTHS ENDED" header that contains both
    segment sub-lines (IB, FICC, Equities) and "Total net revenues".
    """
    for table in tables:
        if not table.rows or len(table.rows) < 20:
            continue

        full_text = " ".join(
            " ".join(row) for row in table.rows[:10]
        ).lower()

        # Must have quarterly header
        if "three months ended" not in full_text:
            continue

        # Must have segment keywords (IB + trading)
        body_text = " ".join(
            " ".join(row) for row in table.rows
        ).lower()

        has_ib = "investment banking" in body_text
        has_trading = "ficc" in body_text or "equities" in body_text
        has_total = "total net revenues" in body_text

        if has_ib and has_trading and has_total:
            return table

    return None


def _get_first_value_cell(row: list[str]) -> float | None:
    """Get the first parseable number from a row (skipping the label cell)."""
    for cell in row[1:]:
        val = _parse_number(cell)
        if val is not None:
            return val
    return None


def _get_label(row: list[str]) -> str:
    """Get the label (first non-empty cell) from a row, normalized."""
    for cell in row:
        text = cell.strip()
        if text:
            # Collapse internal newlines/whitespace to single space
            text = re.sub(r"\s+", " ", text)
            # Strip footnote markers like "(1)", "(2)" at end of label
            text = re.sub(r"\s*\(\d+\)\s*$", "", text)
            return text
    return ""


def _extract_from_segment_table(
    table: ExtractedTable, quarter: Quarter
) -> list[ParsedMetric]:
    """Extract metrics from the quarterly segment breakdown table.

    Handles both segment eras:
      2023+: GBM section with "Investment banking fees", "FICC", "Equities"
      Pre-2023: Separate IB and ICS sections with "Total Investment Banking",
                "FICC Client Execution", "Total Equities"
    """
    metrics: list[ParsedMetric] = []
    found: set[str] = set()

    # Track which segment section we're in
    in_gbm = False  # Global Banking & Markets (2023+)
    in_ib = False  # Investment Banking (pre-2023)
    in_ics = False  # Institutional Client Services (pre-2023)

    for row in table.rows:
        label = _get_label(row).lower()
        if not label:
            continue

        # Section headers (all caps)
        if label in ("global banking & markets", "global markets"):
            in_gbm = True
            in_ib = False
            in_ics = False
            continue
        elif label == "investment banking":
            in_ib = True
            in_ics = False
            in_gbm = False
            continue
        elif label in ("institutional client services", "institutional client services(1)"):
            in_ics = True
            in_ib = False
            in_gbm = False
            continue
        elif label in (
            "asset & wealth management",
            "asset management",
            "consumer & wealth management",
            "investing & lending",
            "investment management",
            "platform solutions",
        ):
            in_gbm = False
            in_ib = False
            in_ics = False
            continue

        raw_cell = row[1] if len(row) > 1 else ""

        # --- Investment Banking ---
        if in_gbm and label == "investment banking fees" and "investment_banking" not in found:
            val = _get_first_value_cell(row)
            if val is not None:
                metrics.append(ParsedMetric(
                    company_slug="goldman-sachs", quarter=quarter,
                    metric_name="investment_banking", value_millions=val,
                    source_page=table.page_number, raw_cell_text=raw_cell,
                ))
                found.add("investment_banking")

        elif in_ib and label in ("total investment banking", "net revenues") and "investment_banking" not in found:
            val = _get_first_value_cell(row)
            if val is not None:
                metrics.append(ParsedMetric(
                    company_slug="goldman-sachs", quarter=quarter,
                    metric_name="investment_banking", value_millions=val,
                    source_page=table.page_number, raw_cell_text=raw_cell,
                ))
                found.add("investment_banking")

        # --- FICC ---
        elif (in_gbm or in_ics) and label == "ficc" and "fixed_income_trading" not in found:
            val = _get_first_value_cell(row)
            if val is not None:
                metrics.append(ParsedMetric(
                    company_slug="goldman-sachs", quarter=quarter,
                    metric_name="fixed_income_trading", value_millions=val,
                    source_page=table.page_number, raw_cell_text=raw_cell,
                ))
                found.add("fixed_income_trading")

        elif in_ics and label in ("ficc client execution", "fixed income, currency and commodities client execution") and "fixed_income_trading" not in found:
            val = _get_first_value_cell(row)
            if val is not None:
                metrics.append(ParsedMetric(
                    company_slug="goldman-sachs", quarter=quarter,
                    metric_name="fixed_income_trading", value_millions=val,
                    source_page=table.page_number, raw_cell_text=raw_cell,
                ))
                found.add("fixed_income_trading")

        # --- Equities ---
        elif (in_gbm or in_ics) and label == "equities" and "equities_trading" not in found:
            val = _get_first_value_cell(row)
            if val is not None:
                metrics.append(ParsedMetric(
                    company_slug="goldman-sachs", quarter=quarter,
                    metric_name="equities_trading", value_millions=val,
                    source_page=table.page_number, raw_cell_text=raw_cell,
                ))
                found.add("equities_trading")

        elif in_ics and label == "total equities" and "equities_trading" not in found:
            val = _get_first_value_cell(row)
            if val is not None:
                metrics.append(ParsedMetric(
                    company_slug="goldman-sachs", quarter=quarter,
                    metric_name="equities_trading", value_millions=val,
                    source_page=table.page_number, raw_cell_text=raw_cell,
                ))
                found.add("equities_trading")

        # --- GBM segment Net revenues (total_net_revenues) ---
        elif in_gbm and label == "net revenues" and "total_net_revenues" not in found:
            val = _get_first_value_cell(row)
            if val is not None:
                metrics.append(ParsedMetric(
                    company_slug="goldman-sachs", quarter=quarter,
                    metric_name="total_net_revenues", value_millions=val,
                    source_page=table.page_number, raw_cell_text=raw_cell,
                ))
                found.add("total_net_revenues")

        # Pre-2023: ICS net revenues as total_net_revenues
        elif in_ics and label in ("total institutional client services", "net revenues") and "total_net_revenues" not in found:
            val = _get_first_value_cell(row)
            if val is not None and val > 1000:
                metrics.append(ParsedMetric(
                    company_slug="goldman-sachs", quarter=quarter,
                    metric_name="total_net_revenues", value_millions=val,
                    source_page=table.page_number, raw_cell_text=raw_cell,
                ))
                found.add("total_net_revenues")

        # --- Firmwide Total net revenues ---
        elif label == "total net revenues" and "firm_total_net_revenues" not in found:
            val = _get_first_value_cell(row)
            if val is not None and val > 5000:
                metrics.append(ParsedMetric(
                    company_slug="goldman-sachs", quarter=quarter,
                    metric_name="firm_total_net_revenues", value_millions=val,
                    source_page=table.page_number, raw_cell_text=raw_cell,
                ))
                found.add("firm_total_net_revenues")

    return metrics


@register_parser
class GoldmanSachsParser(CompanyParser):
    company_slug = "goldman-sachs"

    def parse_tables(
        self,
        tables: list[ExtractedTable],
        quarter: Quarter,
        page_texts: list[tuple[int, str]] | None = None,
    ) -> list[ParsedMetric]:
        seg_table = _find_quarterly_segment_table(tables)
        if seg_table:
            return _extract_from_segment_table(seg_table, quarter)
        return []
