# Adding a New Company Parser to earnings2

## Overview

This guide captures the complete process for adding a new company's earnings data. The pipeline extracts financial metrics from quarterly earnings documents (PDFs or HTML from SEC EDGAR) and stores them in SQLite. Adding a company means: figuring out where the documents live, understanding how the extractor sees the tables, and writing extraction logic that handles format changes across years.

## Architecture Quick Reference

```
earnings2/
  parsers/
    base.py              # CompanyParser ABC
    registry.py          # @register_parser decorator
    {company}/
      __init__.py
      url_patterns.py    # DOC_TYPES dict
      parser.py          # CompanyParser subclass
  pipeline/
    discovery.py         # Maps company slug -> URL generators
    fetcher.py           # Downloads + caches PDFs
    extractor.py         # pdfplumber (PDF) + BeautifulSoup (HTML) table extraction
    runner.py            # Orchestrates parse pipeline
    validator.py         # Checks extracted metrics
  db/
    schema.py            # SQLite schema
    queries.py           # Upsert/query helpers
  config.py              # COMPANY_REGISTRY, paths
  cli.py                 # Click commands
  web.py                 # Flask web UI
```

## Step-by-Step Process

### 1. Find the PDF URLs

Before writing any code, manually locate the company's quarterly financial supplement PDFs.

- Check the company's Investor Relations page
- Download a few PDFs spanning different years (early, mid, recent)
- Look for a URL pattern: most companies use a predictable scheme

**Example** (Morgan Stanley):
```
https://www.morganstanley.com/about-us-ir/finsup{q}q{year}/finsup{q}q{year}.pdf
```

**Tip**: URL patterns sometimes change across years. Check at least 3 different years before committing to a pattern. If the pattern changes, your `url_patterns.py` can have conditional logic based on the quarter.

### 2. Analyze PDF Table Formats with pdfplumber

This is the most critical step. PDF table extraction is unpredictable and varies by:
- **Year era**: Companies redesign supplements every few years
- **pdfplumber version**: What it can/cannot detect as tables

**Diagnostic script** — run this for each PDF era:

```python
import pdfplumber
from pathlib import Path

pdf_path = "path/to/supplement.pdf"
with pdfplumber.open(pdf_path) as pdf:
    for i, page in enumerate(pdf.pages, 1):
        # Check what pdfplumber extracts as tables
        tables = page.extract_tables()
        text = page.extract_text() or ""

        if tables:
            for t_idx, table in enumerate(tables):
                max_cols = max(len(r) for r in table if r)
                print(f"Page {i}, Table {t_idx}: {len(table)} rows x {max_cols} cols")
                for row in table[:5]:
                    print(f"  {[str(c)[:50] for c in (row or [])]}")

        # Also check raw text for pages with financial data
        if any(kw in text.lower() for kw in ["net revenues", "income statement"]):
            print(f"\nPage {i} — RAW TEXT (financial data detected):")
            for line in text.split("\n"):
                print(f"  {line[:120]}")
```

**What you're looking for:**

| Observation | Implication |
|---|---|
| Tables with 10+ columns, date headers | **Structured format** — extract by column index |
| Tables with 1-2 columns, data embedded in text | **Text-mode** — parse line by line |
| No tables found but text has the data | **Raw text fallback** needed |
| Format changes between years | Multiple extraction paths needed |

### 3. Identify the 3 Extraction Levels

From the Morgan Stanley experience, expect to need up to 3 levels:

#### Level 1: Structured Tables
- pdfplumber extracts proper multi-column tables
- Find the target quarter's column by matching date headers
- Read values from the identified column
- **Detection**: Row with 10+ columns containing month/year headers

#### Level 2: Text-Mode Tables
- pdfplumber extracts tables, but data is embedded in cell text
- Each cell may contain multiple lines like: `"Investment banking 1,318 938 1,252 41% 5%"`
- First number after the label is usually the current quarter value
- **Detection**: Tables with few columns but long text content

#### Level 3: Raw Page Text Fallback
- pdfplumber cannot extract tables at all (common in older PDFs)
- Use `extract_page_texts()` to get raw text per page
- Parse line by line, same as Level 2 but from page text
- **Trigger**: When Levels 1-2 find fewer than the expected number of metrics

### 4. Create the Parser Module

```
parsers/{company_slug}/
  __init__.py           # Empty or import parser
  url_patterns.py       # URL generators
  parser.py             # Main parser class
```

#### url_patterns.py

```python
from earnings2.models import Quarter

def financial_supplement_url(quarter: Quarter) -> str:
    # Build URL from quarter
    tag = f"{quarter.q}q{quarter.year}"
    return f"https://example.com/ir/{tag}/supplement.pdf"

DOC_TYPES = {
    "financial_supplement": financial_supplement_url,
}
```

#### parser.py

```python
from earnings2.models import ExtractedTable, ParsedMetric, Quarter
from earnings2.parsers.base import CompanyParser
from earnings2.parsers.registry import register_parser

@register_parser
class AcmeCorpParser(CompanyParser):
    company_slug = "acme-corp"

    def parse_tables(self, tables, quarter, page_texts=None):
        metrics = []

        # Level 1: Try structured tables
        # Level 2: Try text-mode tables
        # Level 3: Fallback to raw page text if len(metrics) < expected
        if len(metrics) < 5 and page_texts:
            metrics.extend(self._extract_from_text(page_texts, quarter))

        return metrics
```

### 5. Register the Company

**config.py** — add to `COMPANY_REGISTRY`:
```python
"acme-corp": {
    "name": "Acme Corporation",
    "ticker": "ACME",
    "cik": "0001234567",
},
```

**pipeline/discovery.py** — add routing:
```python
if company_slug == "acme-corp":
    from earnings2.parsers.acme_corp.url_patterns import DOC_TYPES
    # ... same pattern as morgan-stanley
```

### 6. Test Incrementally

```bash
# Start with ONE quarter to debug extraction
earnings2 fetch acme-corp --start "Q4 2024" --end "Q4 2024"
earnings2 parse acme-corp --start "Q4 2024" --end "Q4 2024"
earnings2 query acme-corp

# Then expand to a recent year
earnings2 run acme-corp --start "Q1 2024" --end "Q4 2024"

# Then test older format eras
earnings2 run acme-corp --start "Q1 2015" --end "Q4 2019"
```

## Critical Parsing Lessons (from Morgan Stanley)

### Number Parsing Pitfalls

1. **Footnote markers look like numbers**: `(1)`, `(2)` in text like `"Net revenues (1) $ 16,223"` get parsed as -1, -2. Strip all `\(\d\)` patterns before extracting values.

2. **Spaced dollar amounts**: Some PDFs render `$13,640` as `$ 1 3,640` due to character spacing. Handle with regex: `\$\s*([\d\s,]+)`.

3. **Parenthetical negatives**: `(1,234)` means -1,234 in financial PDFs.

4. **Percentage columns**: Lines often end with `41% 5%`. Skip tokens containing `%`.

5. **Multi-value lines**: `"Investment banking 1,318 938 1,252 41% 5%"` — the FIRST number after the label is the current quarter. Prior quarters and % changes follow.

### Section Context Matters

Financial PDFs reuse labels in different contexts:
- "Equity" under Investment Banking = equity underwriting revenue
- "Equity" under Sales & Trading = equities trading revenue

**Solution**: Track section state with flags (`found_ib`, `in_sales_trading`, `past_ib_total`). Only extract metrics when in the correct section.

### Table Finding Heuristics

- Search first 3-5 rows of each table for header keywords
- Use multiple keywords to disambiguate (e.g., "Institutional Securities" AND "Income Statement")
- Exclude false matches (e.g., skip "supplemental" or "calculation" tables)
- Some data lives on a different page than the main table (e.g., trading breakdown on the "Statistical Data" page)

### Value Thresholds

Use realistic thresholds to filter noise:
- Firmwide revenue: > $5,000M (rules out segment totals)
- Trading segment: > $50M (rules out footnotes and small items)
- Investment banking: > $500M (for total IB, not sub-lines)

### Multi-Era Handling

When the PDF format changes across years:
1. Detect the era by examining the table structure (column count, header format)
2. Route to the appropriate extraction function
3. Have the raw text fallback as a catch-all for older/unusual formats
4. Trigger fallback when extracted metric count < expected count

## Validation

The validator (`pipeline/validator.py`) runs these checks:
1. **Presence**: Are all expected metrics present?
2. **Segment consistency**: Do sub-segments sum to less than the total? (10% tolerance)
3. **Range**: Are values within realistic bounds?

When adding a company, review `validator.py` to ensure:
- Expected metric names match what your parser produces
- Range bounds are appropriate for the company's scale
- Any company-specific consistency checks are added

## Web UI

The web UI (`web.py`) automatically picks up new company data — the `/api/metrics` endpoint returns all metrics from all companies. The grid and chart work with any metric names and quarter ranges. No changes needed unless you want company-specific filtering.

## Updating This Guide

**This is a living document.** After successfully adding a new company, update this file with anything you learned:

- New parsing pitfalls encountered (add to "Critical Parsing Lessons")
- New PDF format patterns not covered by the 3 extraction levels
- Changes to the pipeline architecture (new files, modified interfaces)
- Company-specific quirks worth warning about (add a subsection under "Lessons")
- Diagnostic techniques or scripts that proved useful
- Corrections to any steps that turned out to be wrong or incomplete

The goal is that each company added makes the next one easier.

## Lessons from Goldman Sachs

### Bot Protection Blocking Direct PDF Downloads

Goldman Sachs uses Akamai bot detection that blocks programmatic access to PDFs on goldmansachs.com. Even with browser-like User-Agent headers, the site returns an HTML challenge page instead of the PDF.

**Solution**: Use SEC EDGAR instead. Goldman Sachs files earnings press releases as 8-K Exhibit 99.1 (HTML format) on EDGAR. The HTML tables are actually cleaner than PDF tables — BeautifulSoup extracts well-structured rows and columns with no pdfplumber ambiguity.

### HTML Document Support

The pipeline's `extractor.py` was extended to handle HTML files alongside PDFs:
- Auto-detects file format by checking first bytes (`%PDF` vs `<html`/`<DOCUMENT>`)
- Uses BeautifulSoup for HTML table extraction, producing the same `ExtractedTable` objects
- Set `format="html"` on `DocumentURL` in `discovery.py` so the cache path uses `.html` extension

EDGAR documents sometimes use an SGML wrapper (`<DOCUMENT>` tag before `<HTML>`). The detector must check for this pattern too.

### SEC EDGAR URL Discovery

EDGAR URLs contain unpredictable accession numbers, so URLs can't be generated from just the quarter. Two discovery methods are needed:

1. **EDGAR full-text search** (`efts.sec.gov/LATEST/search-index`): Fast batch lookup, but recently filed documents may not be indexed yet.
2. **EDGAR submissions API** (`data.sec.gov/submissions/CIK{cik}.json`): Covers all filings including very recent ones. Filter for 8-K with items `2.02,7.01,9.01` (earnings releases).

Both APIs require a `User-Agent` header with contact info — SEC blocks requests without it.

### EDGAR Exhibit Naming Changes

Exhibit filenames changed across filing eras:
- **Older filings**: `d903229dex991.htm` (contains "ex991")
- **Newer filings (2026+)**: `a4q25gsearningsresults.htm` (descriptive names, no "ex991")
- **Trap**: `a4q25gsearningsresultspr.htm` (with "pr") is the earnings *presentation*, NOT the press release. The presentation uses divs instead of tables and has no parseable financial data. Always prefer the larger file without "pr" in the name.

### Label Normalization Pitfalls

HTML cells may contain embedded newlines within labels:
- `"Investment banking\nfees"` instead of `"Investment banking fees"`

**Fix**: Always normalize labels with `re.sub(r"\s+", " ", text)` before matching.

Also strip footnote references from labels:
- `"Total net revenues (1)"` → `"Total net revenues"`

**Fix**: `re.sub(r"\s*\(\d+\)\s*$", "", text)`

### Segment Reorganizations

Goldman Sachs reorganized segments multiple times:
- **Pre-2020**: Investment Banking, Institutional Client Services (FICC + Equities), Investing & Lending, Investment Management
- **2020–2022**: Investment Banking, Global Markets, Asset Management, Consumer & Wealth Management
- **2023+**: Global Banking & Markets (IB + FICC + Equities), Asset & Wealth Management, Platform Solutions

Key label changes across eras:
- **Section headers**: `"Global Banking & Markets"` (2023+) vs `"Global Markets"` (2020–2022) vs `"Institutional Client Services"` (pre-2020). All three must be recognized as section transitions. Also add era-specific exit headers: `"Asset Management"`, `"Consumer & Wealth Management"` (2020–2022).
- **IB total**: `"Investment banking fees"` (2023+) vs `"Net revenues"` under IB section (2020–2022) vs `"Total Investment Banking"` (pre-2020)
- `"FICC"` (2020+) vs `"FICC Client Execution"` vs `"Fixed Income, Currency and Commodities Client Execution"` (2018)
- `"Equities"` (2020+) vs `"Total Equities"` (pre-2023)

**Solution**: Track section state (`in_gbm`, `in_ib`, `in_ics`) and match multiple label variants per metric. Treat `"Global Markets"` (2020–2022) the same as `"Global Banking & Markets"` (2023+) since both contain FICC + Equities sub-segments.

### Segment Consistency Validator Warnings

In the pre-2023 era, `total_net_revenues` maps to ICS only (trading), while `investment_banking` is a separate top-level segment. The validator's segment sum check (IB + FICC + Equities < total) will always warn for pre-2023 quarters. This is expected and acceptable.

### Unicode Whitespace in HTML Cells

EDGAR HTML uses Unicode spaces (`\u2002`–`\u200b`, `\u2009`, `\xa0`) within cell text, especially in dollar amounts like `$\u2003\u2002\u2007\u20091,234`. These must be normalized to regular spaces before number parsing:
```python
text = re.sub(r"[\u2002-\u200b\u2009\xa0]", " ", text)
```

## Lessons from JP Morgan Chase

### UUID-Based PDF URLs

JP Morgan changed from predictable to UUID-based filenames starting Q3 2020. When a company uses non-predictable URLs:

1. Use web search to discover individual PDF UUIDs by searching for `"earnings release financial supplement" "{quarter}" site:companysite.com`
2. Store discovered UUIDs in a `_URL_MAP` dict in `url_patterns.py`
3. Differentiate between supplement PDFs, press releases, and presentations — search results often return all three types per quarter
4. Scribd, SEC EDGAR, and financial sites can help confirm UUID-to-document mappings when the company site title is ambiguous

### Page Text as Primary Extraction Path

Unlike Morgan Stanley (where pdfplumber extracts useful tables), JP Morgan's PDFs yield very few pdfplumber tables. **Raw page text extraction was the primary (and only needed) parsing path**, not a fallback. When pdfplumber tables are poor quality:

- Skip Levels 1-2 and go straight to raw page text
- The `_extract_page_texts()` output is clean and reliable for JPM supplements
- Line-by-line parsing with `_extract_first_number()` works well

### CIB Page Detection

JP Morgan's consolidated pages mention CIB segment names as line items (e.g., "Commercial & Investment Bank 17,598 ..."). This can cause false matches when searching for the CIB-dedicated page. **Fix**: Check the first 5 lines of each page for the section header — the CIB page has it as a title, not as a line item within consolidated data.

### Segment Reorganizations

JP Morgan reorganized segments in Q2 2024 (merged Commercial Banking into CIB). The segment name changed from "Corporate & Investment Bank" to "Commercial & Investment Bank". The IB/trading metric lines remain the same labels across both eras. Always check for both segment names.

### Company-Specific Validation Ranges

JP Morgan is ~3x larger than Morgan Stanley. The validator needed company-aware ranges:
- Firmwide revenue: $20,000–$55,000M (vs MS $3,000–$25,000M)
- Segment max: $30,000M (vs MS $15,000M)

Pass `company_slug` to `validate_metrics()` so it can use appropriate thresholds.



## Verification Feedback — Parser Issues (2026-02-15)

These mismatches were attributed to problems in our parser/extraction logic:

### morgan-stanley

- **Q2 2020 — firm_total_net_revenues**: Stored $13,414M vs CNBC $10,300M. _The CNBC value is incorrect.  The number was extracted from the section of the website titled "Here's what wall street expected:".  I.e. this number is not an earnings result, it's an expectation.  When parsing CNBC articles, it's important to understand the context with which the number is._

