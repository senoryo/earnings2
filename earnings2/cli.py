import click

from earnings2.config import DB_PATH
from earnings2.db.schema import init_db
from earnings2.models import Quarter


@click.group()
def cli() -> None:
    """earnings2 — Quarterly Earnings Parser System."""
    init_db()


@cli.command()
@click.argument("company")
@click.option("--start", default="Q1 2015", help="Start quarter, e.g. 'Q1 2020'")
@click.option("--end", default="Q4 2025", help="End quarter, e.g. 'Q4 2025'")
def fetch(company: str, start: str, end: str) -> None:
    """Download financial supplement PDFs for COMPANY."""
    from earnings2.pipeline.discovery import discover_urls
    from earnings2.pipeline.fetcher import fetch_documents

    q_start = Quarter.parse(start)
    q_end = Quarter.parse(end)
    urls = discover_urls(company, q_start, q_end)
    click.echo(f"Discovered {len(urls)} documents for {company}")
    fetch_documents(urls)
    click.echo("Fetch complete.")


@cli.command()
@click.argument("company")
@click.option("--start", default="Q1 2015")
@click.option("--end", default="Q4 2025")
def parse(company: str, start: str, end: str) -> None:
    """Parse downloaded PDFs and extract metrics for COMPANY."""
    from earnings2.pipeline.runner import run_parse

    q_start = Quarter.parse(start)
    q_end = Quarter.parse(end)
    run_parse(company, q_start, q_end)
    click.echo("Parse complete.")


@cli.command()
@click.argument("company")
@click.option("--start", default="Q1 2015")
@click.option("--end", default="Q4 2025")
def run(company: str, start: str, end: str) -> None:
    """Run full pipeline: fetch, parse, validate, store."""
    from earnings2.pipeline.runner import run_full

    q_start = Quarter.parse(start)
    q_end = Quarter.parse(end)
    run_full(company, q_start, q_end)
    click.echo("Full pipeline complete.")


@cli.command()
@click.argument("company")
@click.option("--quarter", default=None, help="Specific quarter, e.g. 'Q4 2024'")
@click.option("--metric", default=None, help="Filter by metric name")
def query(company: str, quarter: str | None, metric: str | None) -> None:
    """Query stored metrics for COMPANY."""
    from earnings2.db.queries import query_metrics

    q = Quarter.parse(quarter) if quarter else None
    rows = query_metrics(company, quarter=q, metric_name=metric)
    if not rows:
        click.echo("No results found.")
        return
    click.echo(f"{'Quarter':<12} {'Metric':<35} {'Value ($M)':>12} {'Confidence':>10}")
    click.echo("-" * 72)
    for r in rows:
        click.echo(f"{r['quarter']:<12} {r['metric_name']:<35} {r['value_millions']:>12,.0f} {r['confidence']:>10.2f}")


@cli.command()
@click.argument("company")
@click.option("--start", default="Q1 2019", help="Start quarter, e.g. 'Q1 2019'")
@click.option("--end", default="Q4 2025", help="End quarter, e.g. 'Q4 2025'")
def verify(company: str, start: str, end: str) -> None:
    """Cross-reference stored metrics for COMPANY against CNBC articles."""
    from earnings2.pipeline.verifier import verify_company

    q_start = Quarter.parse(start)
    q_end = Quarter.parse(end)
    click.echo(f"Verifying {company} from {q_start} to {q_end} against CNBC...")
    results = verify_company(company, q_start, q_end)

    if not results:
        click.echo("No metrics to verify.")
        return

    # Summary
    correct = sum(1 for r in results if r.status == "Correct")
    incorrect = sum(1 for r in results if r.status == "Incorrect")
    unknown = sum(1 for r in results if r.status == "Don't Know")
    click.echo(f"\n{'Quarter':<12} {'Metric':<35} {'Stored ($M)':>12} {'CNBC ($M)':>12} {'Status':<12}")
    click.echo("-" * 86)
    for r in results:
        ext = f"{r.external_value:>12,.0f}" if r.external_value is not None else "         N/A"
        click.echo(f"{str(r.quarter):<12} {r.metric_name:<35} {r.stored_value:>12,.0f} {ext} {r.status:<12}")

    click.echo(f"\nSummary: {correct} correct, {incorrect} incorrect, {unknown} unknown out of {len(results)} metrics")


@cli.command()
@click.option("--host", default="127.0.0.1", help="Host to bind to")
@click.option("--port", default=5000, type=int, help="Port to listen on")
def web(host: str, port: int) -> None:
    """Launch web UI for browsing metrics."""
    from earnings2.web import run_server

    click.echo(f"Starting web UI at http://{host}:{port}")
    run_server(host=host, port=port)
