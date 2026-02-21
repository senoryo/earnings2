"""Pipeline orchestration: discover, fetch, extract, parse, validate, store."""

from __future__ import annotations

from pathlib import Path

import click

from earnings2.db.queries import get_document, upsert_metric, upsert_validation
from earnings2.models import Quarter
from earnings2.parsers.registry import get_parser
from earnings2.pipeline.discovery import discover_urls
from earnings2.pipeline.extractor import extract_page_texts, extract_tables
from earnings2.pipeline.fetcher import fetch_documents
from earnings2.pipeline.validator import validate_metrics


def run_parse(company_slug: str, start: Quarter, end: Quarter) -> None:
    """Parse already-fetched PDFs and store metrics."""
    parser = get_parser(company_slug)
    quarters = Quarter.range(start, end)

    for q in quarters:
        doc = get_document(company_slug, q, "financial_supplement")
        if not doc or not doc.get("local_path"):
            click.echo(f"  [skip] {q} — not fetched")
            continue

        local_path = Path(doc["local_path"])
        if not local_path.exists():
            click.echo(f"  [skip] {q} — file missing: {local_path}")
            continue

        click.echo(f"  [parse] {q}")
        tables = extract_tables(local_path)
        page_texts = extract_page_texts(local_path)
        click.echo(f"    extracted {len(tables)} tables")

        metrics = parser.parse_tables(tables, q, page_texts=page_texts)
        click.echo(f"    found {len(metrics)} metrics")

        for m in metrics:
            click.echo(f"      {m.metric_name}: {m.value_millions:,.0f}M")
            upsert_metric(m, source_doc_id=doc["id"])

        # Validate
        results = validate_metrics(metrics, q, company_slug=company_slug)
        for r in results:
            if r.status != "pass":
                click.echo(f"    [{r.status.upper()}] {r.check_name}: {r.message}")
            upsert_validation(company_slug, q, r.check_name, r.status, r.message)


def run_full(company_slug: str, start: Quarter, end: Quarter) -> None:
    """Run the full pipeline: discover, fetch, parse, validate, store."""
    click.echo(f"=== Pipeline: {company_slug} {start} -> {end} ===")

    # Step 1: Discover URLs
    click.echo("\n[1/3] Discovering documents...")
    urls = discover_urls(company_slug, start, end)
    click.echo(f"  Found {len(urls)} documents")

    # Step 2: Fetch
    click.echo("\n[2/3] Fetching documents...")
    fetch_documents(urls)

    # Step 3: Parse + Validate + Store
    click.echo("\n[3/3] Parsing and validating...")
    run_parse(company_slug, start, end)

    click.echo("\n=== Pipeline complete ===")
