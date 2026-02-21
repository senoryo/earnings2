from __future__ import annotations

from earnings2.models import DocumentURL, Quarter


def discover_urls(
    company_slug: str, start: Quarter, end: Quarter
) -> list[DocumentURL]:
    """Generate all document URLs for a company across a quarter range."""
    quarters = Quarter.range(start, end)

    if company_slug == "morgan-stanley":
        from earnings2.parsers.morgan_stanley.url_patterns import DOC_TYPES

        urls: list[DocumentURL] = []
        for q in quarters:
            for doc_type, url_fn in DOC_TYPES.items():
                urls.append(
                    DocumentURL(
                        company_slug=company_slug,
                        quarter=q,
                        doc_type=doc_type,
                        url=url_fn(q),
                    )
                )
        return urls

    elif company_slug == "jp-morgan":
        from earnings2.parsers.jp_morgan.url_patterns import DOC_TYPES

        urls: list[DocumentURL] = []
        for q in quarters:
            for doc_type, url_fn in DOC_TYPES.items():
                urls.append(
                    DocumentURL(
                        company_slug=company_slug,
                        quarter=q,
                        doc_type=doc_type,
                        url=url_fn(q),
                    )
                )
        return urls

    elif company_slug == "goldman-sachs":
        from earnings2.parsers.goldman_sachs.url_patterns import DOC_TYPES

        urls: list[DocumentURL] = []
        for q in quarters:
            for doc_type, url_fn in DOC_TYPES.items():
                urls.append(
                    DocumentURL(
                        company_slug=company_slug,
                        quarter=q,
                        doc_type=doc_type,
                        url=url_fn(q),
                        format="html",
                    )
                )
        return urls

    raise ValueError(f"Unknown company: {company_slug}")
