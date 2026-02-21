"""Morgan Stanley financial supplement PDF parser.

Handles two PDF table extraction formats:
1. **Structured** (2024+): pdfplumber extracts proper multi-column tables with
   separate cells for labels and values.
2. **Text-mode** (2020-2023): pdfplumber extracts 1-2 column tables where each
   cell contains multiline text with labels and values embedded in the same string.

Both formats share the same logical table structure:
  - Institutional Securities Income Statement with IB and Trading breakdowns
  - Consolidated Financial Summary with firmwide net revenues
"""

from __future__ import annotations

import re

from earnings2.models import ExtractedTable, ParsedMetric, Quarter
from earnings2.parsers.base import CompanyParser
from earnings2.parsers.registry import register_parser

# Map quarter end month to quarter number
_QUARTER_END_MONTHS = {
    "mar": 1, "march": 1,
    "jun": 2, "june": 2,
    "sep": 3, "september": 3,
    "dec": 4, "december": 4,
}


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

    For lines like: "Investment banking 1,318 938 1,252 41% 5%"
    Returns 1318.0 (the current quarter value, which is the first number).

    Handles:
    - "$ 1 3,640" (spaces within dollar amounts)
    - "(14)" negative values
    - Skips footnote markers like "(1)" at start
    """
    # Remove the label portion
    if after_label:
        idx = line.lower().find(after_label.lower())
        if idx >= 0:
            line = line[idx + len(after_label):]

    # Strip footnote markers like "(1)" or "(2)" anywhere in the line
    line = re.sub(r"\(\d\)", " ", line)

    # Try to match dollar amounts with spaces: "$ 1 3,640" -> "13640"
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


def _find_is_table(tables: list[ExtractedTable]) -> ExtractedTable | None:
    """Find the Institutional Securities income statement table."""
    for table in tables:
        if not table.rows or len(table.rows) < 5:
            continue
        # Check first few rows for "Institutional Securities" + "Income Statement"
        header_text = ""
        for row in table.rows[:5]:
            header_text += " " + " ".join(row)
        header_lower = header_text.lower()
        if "institutional securities" in header_lower and "income statement" in header_lower:
            # Skip supplemental/calculation tables
            if "supplemental" in header_lower or "calculation" in header_lower:
                continue
            return table
    return None


def _find_consolidated_table(tables: list[ExtractedTable]) -> ExtractedTable | None:
    """Find the Consolidated Financial Summary data table (not TOC)."""
    for table in tables:
        if not table.rows or len(table.rows) < 5:
            continue
        # Gather text from first 3 rows
        header_text = ""
        for row in table.rows[:3]:
            for cell in row:
                header_text += " " + cell
        header_lower = header_text.lower()
        if "consolidated financial summary" not in header_lower:
            continue
        # Data tables have financial keywords, TOC tables don't
        if any(kw in header_lower for kw in ["unaudited", "dollars in millions", "quarter ended"]):
            return table
    return None


def _is_structured_table(table: ExtractedTable) -> bool:
    """Determine if the table is structured (multi-column) vs text-mode.

    Structured tables (2024+) have 10+ columns with separate date headers.
    Text-mode tables (2020-2023) have 1-5 columns with data in text strings.
    """
    if not table.rows:
        return False
    # Check if any row has 10+ columns (structured tables have many columns)
    max_cols = max(len(row) for row in table.rows)
    if max_cols >= 10:
        # Also verify there are separate date header cells
        for row in table.rows[:8]:
            date_cells = sum(1 for c in row if len(c.strip()) < 20 and any(
                m in c.lower() for m in ("mar", "jun", "sep", "dec")
            ))
            if date_cells >= 2:
                return True
    return False


def _find_quarter_column(rows: list[list[str]], quarter: Quarter) -> int | None:
    """Find column index matching the quarter's end date (for structured tables)."""
    target_year = str(quarter.year)
    target_months = [m for m, q in _QUARTER_END_MONTHS.items() if q == quarter.q]

    for row in rows[:8]:
        for col_idx, cell in enumerate(row):
            cell_lower = cell.lower().strip()
            if len(cell_lower) > 40:
                continue
            if target_year in cell_lower:
                for month in target_months:
                    if month in cell_lower:
                        return col_idx
    return None


# ---------------------------------------------------------------------------
# Structured table extraction (2024+)
# ---------------------------------------------------------------------------

def _extract_is_structured(table: ExtractedTable, quarter: Quarter) -> list[ParsedMetric]:
    """Extract IS metrics from a structured multi-column table."""
    qcol = _find_quarter_column(table.rows, quarter)
    if qcol is None:
        return []

    metrics: list[ParsedMetric] = []
    found_ib = False

    for row in table.rows:
        if not row or len(row) <= qcol:
            continue

        label_cell = row[0].strip()
        value_cell = row[qcol].strip()
        if not label_cell:
            continue

        label_lower = label_cell.lower()

        # Net revenues
        if label_lower in ("net revenues", "net revenues:"):
            val = _parse_number(value_cell)
            if val is not None:
                metrics.append(ParsedMetric(
                    company_slug="morgan-stanley", quarter=quarter,
                    metric_name="total_net_revenues", value_millions=val,
                    source_page=table.page_number, raw_cell_text=value_cell,
                ))

        # Investment banking total
        elif label_lower.startswith("investment banking"):
            val = _parse_number(value_cell)
            if val is not None:
                metrics.append(ParsedMetric(
                    company_slug="morgan-stanley", quarter=quarter,
                    metric_name="investment_banking", value_millions=val,
                    source_page=table.page_number, raw_cell_text=value_cell,
                ))
                found_ib = True

        # Multiline Equity/Fixed Income cells
        elif "\n" in label_cell and "equity" in label_lower:
            labels = label_cell.split("\n")
            values = value_cell.split("\n")
            while len(values) < len(labels):
                values.append("")
            for sub_label, sub_value in zip(labels, values):
                sub_lower = sub_label.strip().lower()
                val = _parse_number(sub_value)
                if val is None:
                    continue
                if found_ib:
                    if sub_lower in ("equity", "equities"):
                        metrics.append(ParsedMetric(
                            company_slug="morgan-stanley", quarter=quarter,
                            metric_name="equities_trading", value_millions=val,
                            source_page=table.page_number, raw_cell_text=sub_value,
                        ))
                    elif sub_lower == "fixed income":
                        metrics.append(ParsedMetric(
                            company_slug="morgan-stanley", quarter=quarter,
                            metric_name="fixed_income_trading", value_millions=val,
                            source_page=table.page_number, raw_cell_text=sub_value,
                        ))

    return metrics


# ---------------------------------------------------------------------------
# Text-mode extraction (2020-2023)
# ---------------------------------------------------------------------------

def _collect_text_lines(table: ExtractedTable) -> list[str]:
    """Flatten all cells in a table into individual text lines."""
    lines: list[str] = []
    for row in table.rows:
        for cell in row:
            if cell.strip():
                for line in cell.split("\n"):
                    line = line.strip()
                    if line:
                        lines.append(line)
    return lines


def _extract_is_textmode(table: ExtractedTable, quarter: Quarter) -> list[ParsedMetric]:
    """Extract IS metrics from a text-mode table (2020-2023).

    Lines look like:
      Investment banking 1,318 938 1,252 41% 5% 4,578 5,235 (13%)
      Equity 2,202 2,507 2,176 (12%) 1% 9,986 10,769 (7%)
      Fixed income 1,434 1,947 1,418 (26%) 1% 7,673 9,022 (15%)
      Net revenues 4,940 5,669 4,800 (13%) 3% 23,060 24,393 (5%)

    The first number after the label is the current quarter value.
    """
    lines = _collect_text_lines(table)
    metrics: list[ParsedMetric] = []
    found_ib = False
    found_sales_trading = False

    for line in lines:
        line_lower = line.lower().strip()

        # Investment banking (total)
        if line_lower.startswith("investment banking"):
            val = _extract_first_number(line, "investment banking")
            if val is not None:
                metrics.append(ParsedMetric(
                    company_slug="morgan-stanley", quarter=quarter,
                    metric_name="investment_banking", value_millions=val,
                    source_page=table.page_number, raw_cell_text=line,
                ))
                found_ib = True

        # "Sales and Trading" or "Trading" sub-total (marks trading section)
        elif "sales and trading" in line_lower or (line_lower.startswith("trading") and not line_lower.startswith("trading var")):
            found_sales_trading = True

        # Equity trading revenue (after IB section, in trading section)
        elif found_ib and not found_sales_trading and line_lower.startswith("equity") and not line_lower.startswith("equity underwriting"):
            # Check it's not a percentage-only line
            val = _extract_first_number(line, "equity")
            if val is not None and val > 50:  # Trading equity should be >$50M
                metrics.append(ParsedMetric(
                    company_slug="morgan-stanley", quarter=quarter,
                    metric_name="equities_trading", value_millions=val,
                    source_page=table.page_number, raw_cell_text=line,
                ))

        # Fixed income trading revenue (after IB, in trading section)
        elif found_ib and not found_sales_trading and line_lower.startswith("fixed income"):
            val = _extract_first_number(line, "fixed income")
            if val is not None and abs(val) > 50:
                metrics.append(ParsedMetric(
                    company_slug="morgan-stanley", quarter=quarter,
                    metric_name="fixed_income_trading", value_millions=val,
                    source_page=table.page_number, raw_cell_text=line,
                ))

        # Net revenues
        elif line_lower.startswith("net revenues"):
            val = _extract_first_number(line, "net revenues")
            if val is not None:
                metrics.append(ParsedMetric(
                    company_slug="morgan-stanley", quarter=quarter,
                    metric_name="total_net_revenues", value_millions=val,
                    source_page=table.page_number, raw_cell_text=line,
                ))

    return metrics


# ---------------------------------------------------------------------------
# Firmwide revenue extraction
# ---------------------------------------------------------------------------

def _extract_firmwide_structured(table: ExtractedTable, quarter: Quarter) -> ParsedMetric | None:
    """Extract firmwide net revenues from structured consolidated table."""
    for row in table.rows:
        if len(row) < 3:
            continue
        for col_idx in range(min(3, len(row))):
            cell = row[col_idx].strip().lower()
            if re.match(r"net revenues\s*(\(\d+\))?$", cell):
                for val_col in range(col_idx + 1, len(row)):
                    val = _parse_number(row[val_col])
                    if val is not None and val > 5000:
                        return ParsedMetric(
                            company_slug="morgan-stanley", quarter=quarter,
                            metric_name="firm_total_net_revenues", value_millions=val,
                            source_page=table.page_number, raw_cell_text=row[val_col],
                        )
    return None


def _extract_firmwide_textmode(table: ExtractedTable, quarter: Quarter) -> ParsedMetric | None:
    """Extract firmwide net revenues from text-mode consolidated table.

    Lines like: "Net revenues $ 1 3,640 $ 1 1,657 ..."
    or: "Net revenues (1) $ 16,223 $ 15,383 ..."
    """
    lines = _collect_text_lines(table)
    for line in lines:
        line_lower = line.lower().strip()
        # Match "net revenues" (possibly with footnote) NOT preceded by segment names
        if re.match(r"net revenues\s*(\(\d+\))?\s", line_lower):
            # Skip lines that are segment-level (contain "institutional" etc.)
            if any(x in line_lower for x in ["institutional", "wealth", "investment management"]):
                continue
            val = _extract_first_number(line, "net revenues")
            # Handle the "$ 1 3,640" format with spaces
            if val is not None and val > 5000:
                return ParsedMetric(
                    company_slug="morgan-stanley", quarter=quarter,
                    metric_name="firm_total_net_revenues", value_millions=val,
                    source_page=table.page_number, raw_cell_text=line,
                )
    return None


# ---------------------------------------------------------------------------
# Main parser
# ---------------------------------------------------------------------------

def _extract_from_page_text(
    pages: list[tuple[int, str]], quarter: Quarter
) -> list[ParsedMetric]:
    """Fallback: extract metrics from raw page text when table extraction fails.

    Older PDFs (2015-2018) have data that pdfplumber can't extract as tables.
    We look for the Financial Information page with Sales & Trading breakdown,
    the IS Income Statement page, and the Consolidated Financial Summary page.
    """
    metrics: list[ParsedMetric] = []
    metric_names_found: set[str] = set()

    for page_num, text in pages:
        lines = text.split("\n")
        text_lower = text.lower()

        # Page with Sales & Trading breakdown (Equity / Fixed Income lines)
        # Two formats:
        #   1. Older: "Sales & Trading" header, then Equity/Fixed Income children
        #   2. 2019+: "Investment Banking" total, then Equity/Fixed Income (trading),
        #             then "Sales & Trading" total
        if "sales & trading" in text_lower or "sales &amp; trading" in text_lower:
            past_ib_total = False
            in_sales_trading = False
            for line in lines:
                line_stripped = line.strip()
                line_lower = line_stripped.lower()

                # Track "Investment Banking" total line (marks end of IB section)
                if re.match(r"(total )?investment banking\b", line_lower) and "underwriting" not in line_lower:
                    val = _extract_first_number(line_stripped, re.match(r"(total )?investment banking", line_lower).group())
                    if val is not None and val > 500:
                        past_ib_total = True

                # "Sales & Trading" as section header (older format)
                if line_lower.startswith("sales & trading") or line_lower.startswith("sales &amp; trading"):
                    if not past_ib_total:
                        in_sales_trading = True
                    continue

                if past_ib_total or in_sales_trading:
                    if line_lower.startswith("equity") and "equities_trading" not in metric_names_found:
                        val = _extract_first_number(line_stripped, "equity")
                        if val is not None and val > 50:
                            metrics.append(ParsedMetric(
                                company_slug="morgan-stanley", quarter=quarter,
                                metric_name="equities_trading", value_millions=val,
                                source_page=page_num, raw_cell_text=line_stripped,
                            ))
                            metric_names_found.add("equities_trading")

                    elif line_lower.startswith("fixed income") and "fixed_income_trading" not in metric_names_found:
                        val = _extract_first_number(line_stripped, "fixed income")
                        if val is not None and abs(val) > 10:
                            metrics.append(ParsedMetric(
                                company_slug="morgan-stanley", quarter=quarter,
                                metric_name="fixed_income_trading", value_millions=val,
                                source_page=page_num, raw_cell_text=line_stripped,
                            ))
                            metric_names_found.add("fixed_income_trading")

                    elif line_lower.startswith("sales & trading") or line_lower.startswith("total sales"):
                        break

            # Also grab total investment banking from the same page
            for line in lines:
                line_stripped = line.strip()
                ll = line_stripped.lower()
                if (ll.startswith("total investment banking") or ll.startswith("investment banking")) and "investment_banking" not in metric_names_found:
                    label = "total investment banking" if "total" in ll else "investment banking"
                    val = _extract_first_number(line_stripped, label)
                    if val is not None and val > 500:
                        metrics.append(ParsedMetric(
                            company_slug="morgan-stanley", quarter=quarter,
                            metric_name="investment_banking", value_millions=val,
                            source_page=page_num, raw_cell_text=line_stripped,
                        ))
                        metric_names_found.add("investment_banking")

        # IS Income Statement page — get net revenues and investment banking
        if "institutional securities" in text_lower and "income statement" in text_lower and "net revenues" in text_lower:
            for line in lines:
                line_stripped = line.strip()
                line_lower = line_stripped.lower()

                if line_lower.startswith("investment banking") and "investment_banking" not in metric_names_found:
                    val = _extract_first_number(line_stripped, "investment banking")
                    if val is not None:
                        metrics.append(ParsedMetric(
                            company_slug="morgan-stanley", quarter=quarter,
                            metric_name="investment_banking", value_millions=val,
                            source_page=page_num, raw_cell_text=line_stripped,
                        ))
                        metric_names_found.add("investment_banking")

                if re.match(r"net revenues\b", line_lower) and "total_net_revenues" not in metric_names_found:
                    val = _extract_first_number(line_stripped, "net revenues")
                    if val is not None and val > 1000:
                        metrics.append(ParsedMetric(
                            company_slug="morgan-stanley", quarter=quarter,
                            metric_name="total_net_revenues", value_millions=val,
                            source_page=page_num, raw_cell_text=line_stripped,
                        ))
                        metric_names_found.add("total_net_revenues")

        # Also get IS net revenues from Financial Info page
        if "institutional securities net revenues" in text_lower and "total_net_revenues" not in metric_names_found:
            for line in lines:
                line_stripped = line.strip()
                if line_stripped.lower().startswith("institutional securities net revenues"):
                    val = _extract_first_number(line_stripped, "institutional securities net revenues")
                    if val is not None and val > 1000:
                        metrics.append(ParsedMetric(
                            company_slug="morgan-stanley", quarter=quarter,
                            metric_name="total_net_revenues", value_millions=val,
                            source_page=page_num, raw_cell_text=line_stripped,
                        ))
                        metric_names_found.add("total_net_revenues")

        # Consolidated Financial Summary — firmwide net revenues
        if "consolidated" in text_lower and "firm_total_net_revenues" not in metric_names_found:
            for line in lines:
                line_stripped = line.strip()
                line_lower = line_stripped.lower()
                # Match "Net revenues $X" or "Consolidated net revenues $X"
                if re.match(r"(consolidated\s+)?net revenues\s+(\(\d\)\s+)?\$?\s*[\d,]", line_lower):
                    # Skip segment lines
                    if any(x in line_lower for x in ["institutional", "wealth", "investment management"]):
                        continue
                    val = _extract_first_number(line_stripped, "net revenues")
                    if val is not None and val > 5000:
                        metrics.append(ParsedMetric(
                            company_slug="morgan-stanley", quarter=quarter,
                            metric_name="firm_total_net_revenues", value_millions=val,
                            source_page=page_num, raw_cell_text=line_stripped,
                        ))
                        metric_names_found.add("firm_total_net_revenues")
                        break

    return metrics


@register_parser
class MorganStanleyParser(CompanyParser):
    company_slug = "morgan-stanley"

    def parse_tables(
        self,
        tables: list[ExtractedTable],
        quarter: Quarter,
        page_texts: list[tuple[int, str]] | None = None,
    ) -> list[ParsedMetric]:
        metrics: list[ParsedMetric] = []

        # Phase 1: Institutional Securities table
        is_table = _find_is_table(tables)
        if is_table:
            if _is_structured_table(is_table):
                metrics.extend(_extract_is_structured(is_table, quarter))
            else:
                metrics.extend(_extract_is_textmode(is_table, quarter))

        # Phase 2: Firmwide total from consolidated table
        # Try both extraction methods since the table format varies
        cons_table = _find_consolidated_table(tables)
        if cons_table:
            firm = _extract_firmwide_structured(cons_table, quarter)
            if not firm:
                firm = _extract_firmwide_textmode(cons_table, quarter)
            if firm:
                metrics.append(firm)

        # Phase 3: Fallback to raw page text for older PDFs
        if len(metrics) < 5 and page_texts:
            text_metrics = _extract_from_page_text(page_texts, quarter)
            # Only add metrics we didn't already find
            found_names = {m.metric_name for m in metrics}
            for m in text_metrics:
                if m.metric_name not in found_names:
                    metrics.append(m)

        return metrics
