from __future__ import annotations

import sqlite3
from datetime import datetime

from earnings2.db.schema import get_conn
from earnings2.models import ParsedMetric, Quarter


def upsert_document(
    company_slug: str,
    quarter: Quarter,
    doc_type: str,
    url: str,
    local_path: str | None = None,
    http_status: int | None = None,
    file_hash: str | None = None,
    format: str = "pdf",
) -> int:
    conn = get_conn()
    cur = conn.execute(
        """INSERT INTO documents (company_slug, quarter, doc_type, url, local_path, format, fetched_at, http_status, file_hash)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(company_slug, quarter, doc_type) DO UPDATE SET
               url=excluded.url,
               local_path=COALESCE(excluded.local_path, local_path),
               fetched_at=COALESCE(excluded.fetched_at, fetched_at),
               http_status=COALESCE(excluded.http_status, http_status),
               file_hash=COALESCE(excluded.file_hash, file_hash)""",
        (
            company_slug,
            str(quarter),
            doc_type,
            url,
            local_path,
            format,
            datetime.utcnow().isoformat() if local_path else None,
            http_status,
            file_hash,
        ),
    )
    conn.commit()
    doc_id = cur.lastrowid
    conn.close()
    return doc_id


def get_document(company_slug: str, quarter: Quarter, doc_type: str) -> dict | None:
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM documents WHERE company_slug=? AND quarter=? AND doc_type=?",
        (company_slug, str(quarter), doc_type),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def upsert_metric(metric: ParsedMetric, source_doc_id: int | None = None) -> None:
    conn = get_conn()
    conn.execute(
        """INSERT INTO metrics (company_slug, quarter, metric_name, value_millions, source_doc_id, source_page, raw_cell_text, confidence, parsed_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(company_slug, quarter, metric_name) DO UPDATE SET
               value_millions=excluded.value_millions,
               source_doc_id=COALESCE(excluded.source_doc_id, source_doc_id),
               source_page=COALESCE(excluded.source_page, source_page),
               raw_cell_text=excluded.raw_cell_text,
               confidence=excluded.confidence,
               parsed_at=excluded.parsed_at""",
        (
            metric.company_slug,
            str(metric.quarter),
            metric.metric_name,
            metric.value_millions,
            source_doc_id,
            metric.source_page,
            metric.raw_cell_text,
            metric.confidence,
            metric.parsed_at,
        ),
    )
    conn.commit()
    conn.close()


def upsert_validation(
    company_slug: str,
    quarter: Quarter,
    check_name: str,
    status: str,
    message: str = "",
) -> None:
    conn = get_conn()
    conn.execute(
        """INSERT INTO validation_results (company_slug, quarter, check_name, status, message, validated_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (company_slug, str(quarter), check_name, status, message, datetime.utcnow().isoformat()),
    )
    conn.commit()
    conn.close()


def update_verification(
    company_slug: str,
    quarter: Quarter,
    metric_name: str,
    status: str,
    verification_value: float | None = None,
    verification_source_url: str | None = None,
) -> None:
    """Update the verification status for a specific metric.

    status: 'Correct', 'Incorrect', or "Don't Know"
    """
    conn = get_conn()
    conn.execute(
        "UPDATE metrics SET verification=?, verification_value=?, verification_source_url=? "
        "WHERE company_slug=? AND quarter=? AND metric_name=?",
        (status, verification_value, verification_source_url, company_slug, str(quarter), metric_name),
    )
    conn.commit()
    conn.close()


def update_feedback(
    company_slug: str,
    quarter: str,
    metric_name: str,
    blame: str,
    feedback: str,
) -> None:
    """Save user feedback for a verification mismatch.

    blame: 'original_source' or 'verification_source'
    """
    conn = get_conn()
    conn.execute(
        "UPDATE metrics SET verification_feedback=?, verification_blame=? "
        "WHERE company_slug=? AND quarter=? AND metric_name=?",
        (feedback, blame, company_slug, quarter, metric_name),
    )
    conn.commit()
    conn.close()


def get_all_feedback() -> list[dict]:
    """Return all metrics that have user feedback."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT company_slug, quarter, metric_name, value_millions, "
        "verification, verification_value, verification_source_url, "
        "verification_feedback, verification_blame "
        "FROM metrics WHERE verification_feedback IS NOT NULL "
        "ORDER BY company_slug, quarter, metric_name"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def clear_feedback() -> int:
    """Clear all feedback after consolidation. Returns count cleared."""
    conn = get_conn()
    cur = conn.execute(
        "UPDATE metrics SET verification_feedback=NULL, verification_blame=NULL "
        "WHERE verification_feedback IS NOT NULL"
    )
    count = cur.rowcount
    conn.commit()
    conn.close()
    return count


def query_metrics(
    company_slug: str,
    quarter: Quarter | None = None,
    metric_name: str | None = None,
) -> list[dict]:
    conn = get_conn()
    sql = "SELECT * FROM metrics WHERE company_slug=?"
    params: list = [company_slug]
    if quarter:
        sql += " AND quarter=?"
        params.append(str(quarter))
    if metric_name:
        sql += " AND metric_name LIKE ?"
        params.append(f"%{metric_name}%")
    sql += " ORDER BY quarter, metric_name"
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]
