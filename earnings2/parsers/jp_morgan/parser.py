"""JP Morgan Chase earnings release financial supplement PDF parser.

Handles extraction from JPM quarterly supplements. Unlike Morgan Stanley's
structured multi-column tables, JPM's PDFs yield very few pdfplumber tables.
The primary extraction path uses raw page text (Level 3).

Key pages:
  - CIB Financial Highlights: "Commercial & Investment Bank" (Q3 2024+) or
    "Corporate & Investment Bank" (earlier), with IB fees, Fixed Income Markets,
    Equity Markets, and total net revenue.
  - Consolidated Financial Highlights: firmwide total net revenue (managed basis).
"""

from __future__ import annotations

import re

from earnings2.models import ExtractedTable, ParsedMetric, Quarter
from earnings2.parsers.base import CompanyParser
from earnings2.parsers.registry import register_parser

_COMPANY_SLUG = "jp-morgan"


# ---------------------------------------------------------------------------
# Number parsing utilities (same logic as Morgan Stanley parser)
# ---------------------------------------------------------------------------

def _parse_number(text: str) -> float | None:
    """Parse a number, handling ($1,234) negatives, $ prefixes, spaces in digits."""
    text = text.strip().lstrip("$").strip()
    if not text or text in ("-", "—", "–", "‐‐", "N/A", "NM", "*", "--"):
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


def _extract_first_number(line: str, after_label: str = "") -> float | None:
    """Extract the first number from a line of text, after the label.

    For lines like: "Fixed Income Markets 5,006 4,651 (d) 4,981 ..."
    Returns 5006.0 (the current quarter value, which is the first number).
    """
    if after_label:
        idx = line.lower().find(after_label.lower())
        if idx >= 0:
            line = line[idx + len(after_label):]

    # Strip footnote markers like "(1)", "(a)", "(d)" anywhere
    line = re.sub(r"\([a-z0-9]\)", " ", line)

    # Try to match dollar amounts with spaces: "$ 4 3,738" -> "43738"
    dollar_match = re.search(r"\$\s*([\d\s,]+)", line)
    if dollar_match:
        raw = dollar_match.group(1).replace(" ", "").replace(",", "")
        try:
            val = float(raw)
            if val > 0:
                return val
        except ValueError:
            pass

    # Fallback: find number-like tokens (>=3 digits to skip small footnotes)
    tokens = re.findall(r"\([\d,]+\)|[\d,]{3,}(?:\.\d+)?", line)
    for token in tokens:
        val = _parse_number(token)
        if val is not None:
            return val
    return None


# ---------------------------------------------------------------------------
# Page text extraction (primary path for JPM)
# ---------------------------------------------------------------------------

def _find_cib_pages(
    pages: list[tuple[int, str]],
) -> list[tuple[int, str]]:
    """Find pages belonging to the CIB (Corporate/Commercial & Investment Bank) section.

    The CIB section header appears in the first few lines of the page, like:
        JPMORGAN CHASE & CO.
        COMMERCIAL & INVESTMENT BANK
        FINANCIAL HIGHLIGHTS

    We must NOT match consolidated pages that merely mention CIB as a line item.
    """
    cib_pages = []
    for page_num, text in pages:
        # Check first 5 lines for CIB section header
        header_lines = text.split("\n")[:5]
        header_text = " ".join(header_lines).lower()
        if (
            ("corporate & investment bank" in header_text
             or "commercial & investment bank" in header_text)
            and "consolidated" not in header_text
        ):
            cib_pages.append((page_num, text))
    return cib_pages


def _find_consolidated_pages(
    pages: list[tuple[int, str]],
) -> list[tuple[int, str]]:
    """Find Consolidated Financial Highlights pages."""
    result = []
    for page_num, text in pages:
        text_lower = text.lower()
        if "consolidated financial highlights" in text_lower:
            result.append((page_num, text))
    return result


def _extract_cib_metrics(
    pages: list[tuple[int, str]], quarter: Quarter,
) -> list[ParsedMetric]:
    """Extract CIB metrics from page text.

    Targets:
    - total_net_revenues: "TOTAL NET REVENUE" line
    - investment_banking: "Investment banking fees" line (INCOME STATEMENT section)
    - fixed_income_trading: "Fixed Income Markets" line (REVENUE BY BUSINESS section)
    - equities_trading: "Equity Markets" line (REVENUE BY BUSINESS section)
    """
    metrics: list[ParsedMetric] = []
    found: set[str] = set()

    cib_pages = _find_cib_pages(pages)
    for page_num, text in cib_pages:
        lines = text.split("\n")

        for line in lines:
            line_stripped = line.strip()
            line_lower = line_stripped.lower()

            # CIB Total Net Revenue
            if (line_lower.startswith("total net revenue")
                    and "total_net_revenues" not in found):
                val = _extract_first_number(line_stripped, "total net revenue")
                if val is not None and val > 5000:
                    metrics.append(ParsedMetric(
                        company_slug=_COMPANY_SLUG, quarter=quarter,
                        metric_name="total_net_revenues", value_millions=val,
                        source_page=page_num, raw_cell_text=line_stripped,
                    ))
                    found.add("total_net_revenues")

            # Investment banking fees (from INCOME STATEMENT section)
            elif (line_lower.startswith("investment banking fees")
                  and "investment_banking" not in found):
                val = _extract_first_number(line_stripped, "investment banking fees")
                if val is not None and val > 500:
                    metrics.append(ParsedMetric(
                        company_slug=_COMPANY_SLUG, quarter=quarter,
                        metric_name="investment_banking", value_millions=val,
                        source_page=page_num, raw_cell_text=line_stripped,
                    ))
                    found.add("investment_banking")

            # Fixed Income Markets (from REVENUE BY BUSINESS section)
            elif (line_lower.startswith("fixed income markets")
                  and "fixed_income_trading" not in found):
                val = _extract_first_number(line_stripped, "fixed income markets")
                if val is not None and abs(val) > 500:
                    metrics.append(ParsedMetric(
                        company_slug=_COMPANY_SLUG, quarter=quarter,
                        metric_name="fixed_income_trading", value_millions=val,
                        source_page=page_num, raw_cell_text=line_stripped,
                    ))
                    found.add("fixed_income_trading")

            # Equity Markets (from REVENUE BY BUSINESS section)
            elif (line_lower.startswith("equity markets")
                  and "equities_trading" not in found):
                val = _extract_first_number(line_stripped, "equity markets")
                if val is not None and val > 200:
                    metrics.append(ParsedMetric(
                        company_slug=_COMPANY_SLUG, quarter=quarter,
                        metric_name="equities_trading", value_millions=val,
                        source_page=page_num, raw_cell_text=line_stripped,
                    ))
                    found.add("equities_trading")

    return metrics


def _extract_firmwide_revenue(
    pages: list[tuple[int, str]], quarter: Quarter,
) -> ParsedMetric | None:
    """Extract firmwide total net revenue from Consolidated Financial Highlights.

    Prefers the Managed Basis total net revenue.
    Falls back to Reported Basis if managed is not found.
    """
    cons_pages = _find_consolidated_pages(pages)
    for page_num, text in cons_pages:
        lines = text.split("\n")
        in_managed = False

        for line in lines:
            line_stripped = line.strip()
            line_lower = line_stripped.lower()

            if "managed basis" in line_lower:
                in_managed = True

            # Match "Total net revenue" line (not segment lines)
            if line_lower.startswith("total net revenue") and in_managed:
                val = _extract_first_number(line_stripped, "total net revenue")
                if val is not None and val > 20000:
                    return ParsedMetric(
                        company_slug=_COMPANY_SLUG, quarter=quarter,
                        metric_name="firm_total_net_revenues", value_millions=val,
                        source_page=page_num, raw_cell_text=line_stripped,
                    )

    # Fallback: try reported basis from same pages
    for page_num, text in cons_pages:
        lines = text.split("\n")
        for line in lines:
            line_stripped = line.strip()
            line_lower = line_stripped.lower()
            if line_lower.startswith("total net revenue"):
                val = _extract_first_number(line_stripped, "total net revenue")
                if val is not None and val > 20000:
                    return ParsedMetric(
                        company_slug=_COMPANY_SLUG, quarter=quarter,
                        metric_name="firm_total_net_revenues", value_millions=val,
                        source_page=page_num, raw_cell_text=line_stripped,
                    )
    return None


# ---------------------------------------------------------------------------
# Fallback: scan all pages for metrics when CIB page is not found
# ---------------------------------------------------------------------------

def _extract_from_all_pages(
    pages: list[tuple[int, str]], quarter: Quarter,
    already_found: set[str],
) -> list[ParsedMetric]:
    """Fallback extraction from any page containing relevant keywords."""
    metrics: list[ParsedMetric] = []

    for page_num, text in pages:
        lines = text.split("\n")
        text_lower = text.lower()

        # Skip pages that are clearly not relevant
        if "investment bank" not in text_lower and "consolidated" not in text_lower:
            continue

        for line in lines:
            line_stripped = line.strip()
            line_lower = line_stripped.lower()

            if (line_lower.startswith("fixed income markets")
                    and "fixed_income_trading" not in already_found):
                val = _extract_first_number(line_stripped, "fixed income markets")
                if val is not None and abs(val) > 500:
                    metrics.append(ParsedMetric(
                        company_slug=_COMPANY_SLUG, quarter=quarter,
                        metric_name="fixed_income_trading", value_millions=val,
                        source_page=page_num, raw_cell_text=line_stripped,
                    ))
                    already_found.add("fixed_income_trading")

            elif (line_lower.startswith("equity markets")
                  and "equities_trading" not in already_found):
                val = _extract_first_number(line_stripped, "equity markets")
                if val is not None and val > 200:
                    metrics.append(ParsedMetric(
                        company_slug=_COMPANY_SLUG, quarter=quarter,
                        metric_name="equities_trading", value_millions=val,
                        source_page=page_num, raw_cell_text=line_stripped,
                    ))
                    already_found.add("equities_trading")

            elif ("investment_banking" not in already_found
                  and (line_lower.startswith("investment banking fees")
                       or line_lower.startswith("investment banking revenue"))):
                label = "investment banking fees" if "fees" in line_lower else "investment banking revenue"
                val = _extract_first_number(line_stripped, label)
                if val is not None and val > 500:
                    metrics.append(ParsedMetric(
                        company_slug=_COMPANY_SLUG, quarter=quarter,
                        metric_name="investment_banking", value_millions=val,
                        source_page=page_num, raw_cell_text=line_stripped,
                    ))
                    already_found.add("investment_banking")

    return metrics


# ---------------------------------------------------------------------------
# Main parser
# ---------------------------------------------------------------------------

@register_parser
class JPMorganParser(CompanyParser):
    company_slug = "jp-morgan"

    def parse_tables(
        self,
        tables: list[ExtractedTable],
        quarter: Quarter,
        page_texts: list[tuple[int, str]] | None = None,
    ) -> list[ParsedMetric]:
        metrics: list[ParsedMetric] = []

        if not page_texts:
            return metrics

        # Phase 1: Extract CIB metrics from CIB Financial Highlights page
        cib_metrics = _extract_cib_metrics(page_texts, quarter)
        metrics.extend(cib_metrics)

        # Phase 2: Extract firmwide total net revenue
        firmwide = _extract_firmwide_revenue(page_texts, quarter)
        if firmwide:
            metrics.append(firmwide)

        # Phase 3: Fallback — scan all pages for any missing metrics
        if len(metrics) < 5:
            found_names = {m.metric_name for m in metrics}
            fallback = _extract_from_all_pages(page_texts, quarter, found_names)
            metrics.extend(fallback)

        return metrics
