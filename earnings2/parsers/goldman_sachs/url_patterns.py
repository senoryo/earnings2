"""Goldman Sachs earnings press release URL discovery via SEC EDGAR.

Goldman Sachs blocks direct PDF downloads from goldmansachs.com (Akamai bot
protection). Instead, we fetch the earnings press release (Exhibit 99.1) from
SEC EDGAR 8-K filings, which are publicly accessible HTML documents.

Two discovery methods are used:
1. EDGAR full-text search index (covers most filings, fast batch lookup)
2. EDGAR submissions API (fallback for recent filings not yet indexed)
"""

from __future__ import annotations

import httpx

from earnings2.models import Quarter

CIK = "0000886982"
CIK_NUM = "886982"
_EDGAR_HEADERS = {"User-Agent": "earnings2 research bot admin@example.com"}

# Cache: {(year, q): url} populated lazily
_url_cache: dict[tuple[int, int], str] = {}
_discovery_done = False


def _filing_date_to_quarter(filing_date: str) -> Quarter | None:
    """Map an 8-K filing date to the earnings quarter it reports.

    GS earnings releases follow this schedule:
        Filed in Jan -> Q4 of previous year
        Filed in Apr -> Q1 of current year
        Filed in Jul -> Q2 of current year
        Filed in Oct -> Q3 of current year
    """
    parts = filing_date.split("-")
    year, month = int(parts[0]), int(parts[1])
    mapping = {1: (year - 1, 4), 4: (year, 1), 7: (year, 2), 10: (year, 3)}
    result = mapping.get(month)
    if result:
        return Quarter(result[0], result[1])
    return None


def _find_press_release_exhibit(accession: str) -> str | None:
    """Find the press release exhibit filename in a filing's index.

    Exhibit naming varies across filing eras:
    - Older: d903229dex991.htm (pattern: *ex991*.htm)
    - Newer: a4q25gsearningsresults.htm (the full press release)
    - Also newer: a4q25gsearningsresultspr.htm (the presentation, NOT what we want)
    """
    acc_no_dashes = accession.replace("-", "")
    url = (
        f"https://www.sec.gov/Archives/edgar/data/{CIK_NUM}"
        f"/{acc_no_dashes}/index.json"
    )
    resp = httpx.get(url, headers=_EDGAR_HEADERS, timeout=30, follow_redirects=True)
    if resp.status_code != 200:
        return None

    data = resp.json()
    candidates: list[tuple[str, int]] = []
    for item in data.get("directory", {}).get("item", []):
        name = item.get("name", "")
        if not name.endswith(".htm"):
            continue
        name_lower = name.lower()
        size = int(item.get("size", 0))
        # Match ex991 pattern (older filings)
        if "ex991" in name_lower:
            return name
        # Match earnings results pattern (newer filings)
        # Exclude "pr" (presentation) variant — we want the full press release
        if "earningsresults" in name_lower and "pr" not in name_lower:
            candidates.append((name, size))
        elif "earningsresults" in name_lower:
            # Keep as low-priority fallback
            candidates.append((name, 0))

    if not candidates:
        return None
    # Prefer the largest file (the full press release is ~1MB vs ~64KB presentation)
    candidates.sort(key=lambda x: x[1], reverse=True)
    return candidates[0][0]


def _discover_via_fulltext_search() -> None:
    """Query EDGAR full-text search for Goldman Sachs earnings 8-K filings.

    Runs two queries: "earnings results" (matches 2018+) and "press release"
    (matches older filings back to 2014).
    """
    queries = [
        "%22earnings+results%22",
        "%22press+release%22",
        "%22net+revenues%22",
    ]
    for query in queries:
        url = (
            "https://efts.sec.gov/LATEST/search-index"
            f"?q={query}"
            "&forms=8-K"
            "&dateRange=custom&startdt=2014-01-01&enddt=2027-01-01"
            "&entityName=goldman+sachs"
            "&_source=file_date,ciks"
            "&from=0&size=100"
        )
        resp = httpx.get(
            url, headers=_EDGAR_HEADERS, timeout=30, follow_redirects=True
        )
        resp.raise_for_status()
        data = resp.json()

        for hit in data.get("hits", {}).get("hits", []):
            src = hit["_source"]
            file_id = hit["_id"]  # format: "accession:filename"

            if CIK not in str(src.get("ciks", "")):
                continue

            parts = file_id.split(":")
            if len(parts) != 2:
                continue
            accession, filename = parts

            if "ex991" not in filename:
                continue

            quarter = _filing_date_to_quarter(src["file_date"])
            if quarter is None:
                continue

            acc_no_dashes = accession.replace("-", "")
            edgar_url = (
                f"https://www.sec.gov/Archives/edgar/data/{CIK_NUM}"
                f"/{acc_no_dashes}/{filename}"
            )
            key = (quarter.year, quarter.q)
            if key not in _url_cache:
                _url_cache[key] = edgar_url


def _discover_via_submissions() -> None:
    """Fallback: use EDGAR submissions API to find recent earnings filings."""
    url = f"https://data.sec.gov/submissions/CIK{CIK}.json"
    resp = httpx.get(url, headers=_EDGAR_HEADERS, timeout=30, follow_redirects=True)
    resp.raise_for_status()
    data = resp.json()

    recent = data["filings"]["recent"]
    forms = recent["form"]
    dates = recent["filingDate"]
    accessions = recent["accessionNumber"]
    items = recent.get("items", [])

    for i in range(len(forms)):
        # Earnings 8-K filings have item 2.02 + 7.01 + 9.01
        if forms[i] != "8-K":
            continue
        item_str = items[i] if i < len(items) else ""
        if "2.02" not in item_str or "9.01" not in item_str:
            continue

        quarter = _filing_date_to_quarter(dates[i])
        if quarter is None:
            continue

        key = (quarter.year, quarter.q)
        if key in _url_cache:
            continue

        # Look up the exhibit filename
        exhibit = _find_press_release_exhibit(accessions[i])
        if exhibit:
            acc_no_dashes = accessions[i].replace("-", "")
            edgar_url = (
                f"https://www.sec.gov/Archives/edgar/data/{CIK_NUM}"
                f"/{acc_no_dashes}/{exhibit}"
            )
            _url_cache[key] = edgar_url


def _discover_filings() -> None:
    """Discover all available Goldman Sachs earnings filing URLs."""
    global _discovery_done
    if _discovery_done:
        return
    _discovery_done = True

    # Primary: full-text search (fast, covers most filings)
    _discover_via_fulltext_search()
    # Fallback: submissions API (covers recent filings not yet indexed)
    _discover_via_submissions()


def financial_supplement_url(quarter: Quarter) -> str:
    """Return the SEC EDGAR URL for Goldman Sachs earnings press release."""
    _discover_filings()
    key = (quarter.year, quarter.q)
    if key not in _url_cache:
        raise ValueError(
            f"No Goldman Sachs earnings filing found for {quarter}. "
            f"Available: {sorted(_url_cache.keys())}"
        )
    return _url_cache[key]


DOC_TYPES = {
    "financial_supplement": financial_supplement_url,
}
