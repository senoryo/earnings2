"""Cross-reference verification of extracted metrics against CNBC earnings articles."""

from __future__ import annotations

import re
from dataclasses import dataclass

import click
import requests

from earnings2.config import COMPANY_REGISTRY
from earnings2.db.queries import query_metrics, update_verification
from earnings2.models import Quarter

# Mapping from company slug to CNBC article URL slug patterns
# Actual CNBC URLs: https://www.cnbc.com/2025/01/15/jpmorgan-chase-jpm-earnings-q4-2024.html
CNBC_SLUGS = {
    "jp-morgan": [
        "jpmorgan-chase-jpm-earnings-{q_label}-{year}",
        "jpmorgan-jpm-earnings-{q_label}-{year}",
    ],
    "morgan-stanley": [
        "morgan-stanley-ms-earnings-{q_label}-{year}",
        "morgan-stanley-earnings-{q_label}-{year}",
    ],
    "goldman-sachs": [
        "goldman-sachs-gs-earnings-{q_label}-{year}",
        "goldman-sachs-gs-{q_label}-{year}-earnings",
    ],
}

# Approximate earnings release months (month after quarter end)
# Q1 ends Mar -> reported in Apr, Q2 ends Jun -> Jul, Q3 ends Sep -> Oct, Q4 ends Dec -> Jan next year
RELEASE_MONTHS = {1: (4, 0), 2: (7, 0), 3: (10, 0), 4: (1, 1)}

# Day range to try for article URLs (earnings usually released 12-17th of the month)
RELEASE_DAYS = list(range(10, 22))

CNBC_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml",
}

# Regex patterns for extracting metrics from CNBC article prose.
# CNBC reports numbers in billions, e.g. "$5.01 billion".
# Regex patterns for extracting metrics from CNBC article prose.
# CNBC reports numbers in billions, e.g. "$5.01 billion".
# Use [^$.\n]{0,N} to avoid crossing sentence boundaries.
METRIC_PATTERNS: dict[str, list[re.Pattern]] = {
    "FICC Revenue": [
        re.compile(r"(?:fixed.income|ficc)\s+(?:trading\s+)?(?:revenue\s+)?(?:jumped|rose|fell|was|had|of|generated|came\s+in\s+at|surged|declined|climbed|edged|increased|decreased|dropped|slid|dipped|totaled)[^$\n]{0,40}\$([\d.]+)\s+billion", re.I),
        re.compile(r"(?:fixed.income|ficc)\s+(?:trading\s+)?(?:revenue\s+)?(?:of\s+)?\$([\d.]+)\s+billion", re.I),
    ],
    "Equities Revenue": [
        re.compile(r"equit(?:y|ies)\s+(?:trading\s+)?(?:revenue\s+)?(?:jumped|rose|fell|was|had|of|generated|came\s+in\s+at|surged|declined|climbed|edged|increased|decreased|dropped|slid|dipped|totaled)[^$\n]{0,40}\$([\d.]+)\s+billion", re.I),
        re.compile(r"equit(?:y|ies)\s+(?:trading\s+)?(?:revenue\s+)?(?:of\s+)?\$([\d.]+)\s+billion", re.I),
    ],
    "IB Revenue": [
        re.compile(r"investment.banking\s+(?:fees|revenue)\s+(?:jumped|rose|fell|was|had|of|generated|came\s+in\s+at|surged|declined|climbed|edged|increased|decreased|dropped|slid|dipped|totaled)[^$\n]{0,40}\$([\d.]+)\s+billion", re.I),
        re.compile(r"investment.banking\s+(?:fees|revenue)\s+(?:of\s+)?\$([\d.]+)\s+billion", re.I),
    ],
    "Net Revenue": [
        re.compile(r"revenue[:\s]+\$([\d.]+)\s+billion", re.I),
        re.compile(r"revenue\s+(?:of|was|came\s+in\s+at)\s+\$([\d.]+)\s+billion", re.I),
    ],
}

# Map our DB metric names to the CNBC pattern keys above.
# Includes both human-readable and underscore DB-style names.
METRIC_NAME_MAP: dict[str, list[str]] = {
    "FICC Revenue": [
        "FICC Revenue", "Fixed Income Revenue", "fixed_income_trading",
    ],
    "Equities Revenue": [
        "Equities Revenue", "Equity Revenue", "equities_trading",
    ],
    "IB Revenue": [
        "IB Revenue", "Investment Banking Revenue", "IB Fees",
        "Investment Banking Fees", "Advisory Revenue",
        "investment_banking",
    ],
    "Net Revenue": [
        "Net Revenue", "Total Net Revenue", "Net Revenues",
        "Total Net Revenues", "Firmwide Revenue",
        "firm_total_net_revenues",
    ],
}


@dataclass
class VerificationResult:
    quarter: Quarter
    metric_name: str
    stored_value: float
    external_value: float | None
    status: str  # 'Correct', 'Incorrect', "Don't Know"
    source: str
    source_url: str | None = None


def _build_cnbc_urls(company_slug: str, quarter: Quarter) -> list[str]:
    """Build candidate CNBC article URLs to try."""
    slugs = CNBC_SLUGS.get(company_slug, [])
    if not slugs:
        return []

    month_offset = RELEASE_MONTHS[quarter.q]
    release_month = month_offset[0]
    release_year = quarter.year + month_offset[1]

    # CNBC uses both "q4" and "4q" formats across different articles
    q_labels = [f"q{quarter.q}", f"{quarter.q}q"]

    urls = []
    for slug_template in slugs:
        for q_label in q_labels:
            slug = slug_template.format(q_label=q_label, year=quarter.year)
            for day in RELEASE_DAYS:
                url = f"https://www.cnbc.com/{release_year}/{release_month:02d}/{day:02d}/{slug}.html"
                urls.append(url)
    return urls


def fetch_cnbc_article(company_slug: str, quarter: Quarter) -> tuple[str | None, str | None]:
    """Try to fetch CNBC earnings article text.

    Returns (article_html, article_url) or (None, None).
    Uses HEAD requests (~70ms each) to find the correct URL, then GET to fetch content.
    """
    urls = _build_cnbc_urls(company_slug, quarter)
    # Phase 1: HEAD requests to find a valid URL
    found_url = None
    for url in urls:
        try:
            resp = requests.head(url, headers=CNBC_HEADERS, timeout=5, allow_redirects=True)
            if resp.status_code == 200:
                found_url = url
                break
        except requests.RequestException:
            continue

    if not found_url:
        return None, None

    # Phase 2: GET the article content
    try:
        resp = requests.get(found_url, headers=CNBC_HEADERS, timeout=10)
        if resp.status_code == 200 and len(resp.text) > 1000:
            return resp.text, found_url
    except requests.RequestException:
        pass
    return None, None


def _extract_article_body(html: str) -> str:
    """Extract article body text from CNBC HTML, skipping JSON metadata/scripts.

    Removes <script>/<style> blocks (which contain structured data with analyst
    expectations), then strips remaining HTML tags. Finally filters out sentences
    about analyst expectations/estimates so we only match actual reported results.
    """
    # Remove <script> and <style> blocks — these contain JSON metadata with
    # expectations data that otherwise pollutes regex matching
    text = re.sub(r"<script[^>]*>.*?</script>", " ", html, flags=re.DOTALL | re.I)
    text = re.sub(r"<style[^>]*>.*?</style>", " ", text, flags=re.DOTALL | re.I)
    # Strip remaining HTML tags
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)

    # Remove sentences about expectations/estimates (analyst forecasts, not actuals)
    sentences = re.split(r"(?<=[.!?])\s+", text)
    filtered = []
    skip_patterns = re.compile(
        r"(?:here.s what|wall street expected|analysts? (?:expected|estimated|surveyed|polled)"
        r"|what (?:wall street|analysts?) (?:expected|estimated))",
        re.I,
    )
    for s in sentences:
        if not skip_patterns.search(s):
            filtered.append(s)

    return " ".join(filtered)


def extract_cnbc_metrics(html: str) -> dict[str, float]:
    """Extract metric values (in millions) from CNBC article HTML/text.

    Returns dict mapping pattern key -> value in millions.
    """
    text = _extract_article_body(html)

    found: dict[str, float] = {}
    for metric_key, patterns in METRIC_PATTERNS.items():
        for pattern in patterns:
            match = pattern.search(text)
            if match:
                billions = float(match.group(1))
                found[metric_key] = round(billions * 1000, 1)  # Convert to millions
                break
    return found


def _find_cnbc_key(db_metric_name: str) -> str | None:
    """Map a DB metric name to a CNBC pattern key."""
    for cnbc_key, db_names in METRIC_NAME_MAP.items():
        for name in db_names:
            if name.lower() == db_metric_name.lower():
                return cnbc_key
    return None


def compare_value(stored: float, external: float, tolerance_pct: float = 0.02, tolerance_abs: float = 100.0) -> bool:
    """Check if stored and external values are close enough.

    Match if within tolerance_pct (2%) OR tolerance_abs ($100M), whichever is more lenient.
    """
    if stored == 0 and external == 0:
        return True
    abs_diff = abs(stored - external)
    pct_diff = abs_diff / max(abs(stored), abs(external), 1)
    return pct_diff <= tolerance_pct or abs_diff <= tolerance_abs


def verify_quarter(
    company_slug: str,
    quarter: Quarter,
    stored_metrics: list[dict],
    update_db: bool = True,
) -> list[VerificationResult]:
    """Verify metrics for a single quarter against CNBC data."""
    results: list[VerificationResult] = []

    article_html, article_url = fetch_cnbc_article(company_slug, quarter)
    if not article_html:
        click.echo(f"  [{quarter}] No CNBC article found")
        for m in stored_metrics:
            results.append(VerificationResult(
                quarter=quarter,
                metric_name=m["metric_name"],
                stored_value=m["value_millions"],
                external_value=None,
                status="Don't Know",
                source="CNBC (article not found)",
            ))
        return results

    cnbc_values = extract_cnbc_metrics(article_html)
    click.echo(f"  [{quarter}] CNBC values found: {len(cnbc_values)}")

    for m in stored_metrics:
        cnbc_key = _find_cnbc_key(m["metric_name"])
        if cnbc_key and cnbc_key in cnbc_values:
            ext_val = cnbc_values[cnbc_key]
            matches = compare_value(m["value_millions"], ext_val)
            status = "Correct" if matches else "Incorrect"
            results.append(VerificationResult(
                quarter=quarter,
                metric_name=m["metric_name"],
                stored_value=m["value_millions"],
                external_value=ext_val,
                status=status,
                source="CNBC",
                source_url=article_url,
            ))
            if update_db:
                update_verification(
                    company_slug, quarter, m["metric_name"], status,
                    verification_value=ext_val,
                    verification_source_url=article_url,
                )
        else:
            results.append(VerificationResult(
                quarter=quarter,
                metric_name=m["metric_name"],
                stored_value=m["value_millions"],
                external_value=None,
                status="Don't Know",
                source="CNBC (metric not in article)",
                source_url=article_url,
            ))

    return results


def verify_company(
    company_slug: str,
    start: Quarter,
    end: Quarter,
    update_db: bool = True,
) -> list[VerificationResult]:
    """Verify all metrics for a company across a range of quarters."""
    if company_slug not in COMPANY_REGISTRY:
        raise ValueError(f"Unknown company: {company_slug}")

    all_results: list[VerificationResult] = []
    quarters = Quarter.range(start, end)

    for q in quarters:
        stored = query_metrics(company_slug, quarter=q)
        if not stored:
            click.echo(f"  [{q}] No stored metrics — skipping")
            continue

        results = verify_quarter(company_slug, q, stored, update_db=update_db)
        all_results.extend(results)

    return all_results
