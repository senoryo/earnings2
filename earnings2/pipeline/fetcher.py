from __future__ import annotations

import hashlib
from pathlib import Path

import click
import httpx

from earnings2.config import CACHE_DIR
from earnings2.db.queries import get_document, upsert_document
from earnings2.models import DocumentURL


def _cache_path(doc: DocumentURL) -> Path:
    """Deterministic local path for a document."""
    filename = f"{doc.company_slug}_{doc.quarter.label}_{doc.doc_type}.{doc.format}"
    return CACHE_DIR / filename


def fetch_documents(urls: list[DocumentURL]) -> list[Path]:
    """Download documents, skip if already cached. Returns local paths."""
    paths: list[Path] = []
    headers = {"User-Agent": "earnings2 research bot admin@example.com"}
    with httpx.Client(timeout=60, follow_redirects=True, headers=headers) as client:
        for doc in urls:
            local = _cache_path(doc)

            # Check if already fetched
            existing = get_document(doc.company_slug, doc.quarter, doc.doc_type)
            if existing and existing.get("local_path") and Path(existing["local_path"]).exists():
                click.echo(f"  [cached] {doc.quarter}")
                paths.append(Path(existing["local_path"]))
                continue

            click.echo(f"  [fetch]  {doc.quarter} <- {doc.url}")
            try:
                resp = client.get(doc.url)
                status = resp.status_code
                if status == 200:
                    local.write_bytes(resp.content)
                    file_hash = hashlib.sha256(resp.content).hexdigest()
                    upsert_document(
                        doc.company_slug,
                        doc.quarter,
                        doc.doc_type,
                        doc.url,
                        local_path=str(local),
                        http_status=status,
                        file_hash=file_hash,
                    )
                    paths.append(local)
                else:
                    click.echo(f"  [WARN]   HTTP {status} for {doc.quarter}")
                    upsert_document(
                        doc.company_slug,
                        doc.quarter,
                        doc.doc_type,
                        doc.url,
                        http_status=status,
                    )
            except httpx.HTTPError as e:
                click.echo(f"  [ERROR]  {doc.quarter}: {e}")
                upsert_document(
                    doc.company_slug,
                    doc.quarter,
                    doc.doc_type,
                    doc.url,
                )

    return paths
