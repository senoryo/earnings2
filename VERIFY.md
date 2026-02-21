# Cross-Reference Verification

## Overview

The verification system compares extracted metrics stored in the database against independent external sources to confirm data accuracy. Each metric receives a verification status: **Correct**, **Incorrect**, or **Don't Know**.

## External Source: CNBC Earnings Articles

### Why CNBC?

Several sources were evaluated:

| Source | Pros | Cons |
|--------|------|------|
| **CNBC** (chosen) | Free, independent (journalist-reported), covers all three banks, segment-level data | Narrative prose (regex extraction), numbers rounded to billions, coverage starts ~2019 |
| Bloomberg/Reuters | Highly accurate, structured data | Paywalled, API requires expensive subscription |
| SEC filings | Authoritative, exact numbers | Same primary source we already use (not independent) |
| Yahoo Finance | Free API | Only firmwide metrics, no segment-level breakdown |

CNBC was chosen as the best balance of independence, coverage, and accessibility.

### How It Works

1. **URL Construction**: For each quarter, the verifier builds candidate CNBC article URLs based on the company, quarter, and typical earnings release dates (mid-month after quarter end).

2. **Article Fetching**: Tries each candidate URL until a valid article is found. CNBC articles follow predictable URL patterns like:
   ```
   https://www.cnbc.com/2024/10/15/morgan-stanley-ms-q3-2024-earnings.html
   ```

3. **Metric Extraction**: Regex patterns extract dollar values from article prose. CNBC reports in billions (e.g., "$5.01 billion"), which are converted to millions for comparison.

4. **Comparison**: Each extracted CNBC value is compared against the stored database value using tolerance thresholds.

5. **DB Update**: The `verification` column on the `metrics` table is updated with the result.

### Tolerance Thresholds

A metric is marked **Correct** if the stored and CNBC values are within:

- **2% relative difference**, OR
- **$100M absolute difference**

Whichever threshold is more lenient applies. This accounts for:
- CNBC rounding (e.g., "$5.01 billion" vs our exact $5,006M)
- Minor definitional differences in what's included in a line item

### Metrics Verified

| CNBC Pattern | Matches DB Metric Names |
|---|---|
| Fixed income/FICC revenue | FICC Revenue, Fixed Income Revenue |
| Equities revenue | Equities Revenue, Equity Revenue |
| Investment banking fees/revenue | IB Revenue, Investment Banking Revenue, IB Fees, Advisory Revenue |
| Net revenue (firmwide) | Net Revenue, Total Net Revenue, Net Revenues, Firmwide Revenue |

## Usage

```bash
# Verify JP Morgan for recent quarters
earnings2 verify jp-morgan --start "Q1 2024" --end "Q4 2025"

# Verify all companies for a single year
earnings2 verify morgan-stanley --start "Q1 2024" --end "Q4 2024"
earnings2 verify goldman-sachs --start "Q1 2024" --end "Q4 2024"

# Check results in the web UI (Verification column)
earnings2 web
```

The CLI prints a table of results and a summary. The web UI shows a color-coded **Verification** column (green = Correct, red = Incorrect, gray = Don't Know).

## Known Limitations

1. **CNBC coverage**: Articles may not exist for older quarters (pre-2019) or may use different URL patterns.
2. **Rounding**: CNBC reports in billions with limited decimal places. Small metrics (< $500M) may not appear.
3. **Narrative parsing**: Regex extraction from prose is inherently fragile. Article structure varies by author.
4. **Metric mapping**: Not all DB metrics have CNBC equivalents. Many segment-level metrics are too granular for CNBC coverage.
5. **Rate limiting**: Making many requests to CNBC in quick succession may trigger rate limiting. The verifier makes sequential requests with no built-in delay.

## Adding New Verification Sources

To add a new external source:

1. **Create fetch function**: Similar to `fetch_cnbc_article()`, fetch data from the new source.
2. **Create extraction function**: Parse the source format (HTML, JSON, CSV) into a `dict[str, float]` of metric values in millions.
3. **Register metric mappings**: Add entries to `METRIC_NAME_MAP` if the new source uses different metric names.
4. **Update `verify_quarter()`**: Add the new source as a fallback or complement to CNBC.



## Verification Feedback — CNBC Source Issues (2026-02-15)

These mismatches were attributed to problems in the CNBC verification source:

### morgan-stanley

- **Q1 2020 — equities_trading**: Stored $2,422M vs CNBC $2,230M. _The CNBC value is incorrect.  The number was extracted from the section of the website titled "Here's what wall street expected:".  I.e. this number is not an earnings result, it's an expectation.  When parsing CNBC articles, it's important to understand the context with which the number is._
- **Q1 2020 — firm_total_net_revenues**: Stored $9,487M vs CNBC $9,730M. _The CNBC value is incorrect.  The number was extracted from the section of the website titled "Here's what wall street expected:".  I.e. this number is not an earnings result, it's an expectation.  When parsing CNBC articles, it's important to understand the context with which the number is._
- **Q1 2020 — fixed_income_trading**: Stored $2,203M vs CNBC $1,710M. _The CNBC value is incorrect.  The number was extracted from the section of the website titled "Here's what wall street expected:".  I.e. this number is not an earnings result, it's an expectation.  When parsing CNBC articles, it's important to understand the context with which the number is._
- **Q2 2020 — equities_trading**: Stored $2,619M vs CNBC $2,350M. _The CNBC value is incorrect.  The number was extracted from the section of the website titled "Here's what wall street expected:".  I.e. this number is not an earnings result, it's an expectation.  When parsing CNBC articles, it's important to understand the context with which the number is._
- **Q2 2020 — fixed_income_trading**: Stored $3,033M vs CNBC $1,810M. _The CNBC value is incorrect.  The number was extracted from the section of the website titled "Here's what wall street expected:".  I.e. this number is not an earnings result, it's an expectation.  When parsing CNBC articles, it's important to understand the context with which the number is._
- **Q4 2022 — firm_total_net_revenues**: Stored $12,749M vs CNBC $6,630M. _This is poor.  The CNBC article clearly talks about the wealth management division WITHIN the firm.  Therefore, this number is NOT firm-wide._

