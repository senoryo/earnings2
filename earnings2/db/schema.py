import sqlite3

from earnings2.config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS companies (
    slug TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    ticker TEXT,
    cik TEXT
);

CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_slug TEXT NOT NULL REFERENCES companies(slug),
    quarter TEXT NOT NULL,
    doc_type TEXT NOT NULL,
    url TEXT,
    local_path TEXT,
    format TEXT DEFAULT 'pdf',
    fetched_at TEXT,
    http_status INTEGER,
    file_hash TEXT,
    UNIQUE(company_slug, quarter, doc_type)
);

CREATE TABLE IF NOT EXISTS metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_slug TEXT NOT NULL REFERENCES companies(slug),
    quarter TEXT NOT NULL,
    metric_name TEXT NOT NULL,
    value_millions REAL,
    source_doc_id INTEGER REFERENCES documents(id),
    source_page INTEGER,
    raw_cell_text TEXT,
    confidence REAL DEFAULT 1.0,
    parsed_at TEXT,
    verification TEXT DEFAULT 'Don''t Know',
    verification_value REAL,
    verification_source_url TEXT,
    verification_feedback TEXT,
    verification_blame TEXT,
    UNIQUE(company_slug, quarter, metric_name)
);

CREATE TABLE IF NOT EXISTS validation_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_slug TEXT NOT NULL,
    quarter TEXT NOT NULL,
    check_name TEXT NOT NULL,
    status TEXT NOT NULL,
    message TEXT,
    validated_at TEXT
);
"""


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db() -> None:
    conn = get_conn()
    conn.executescript(SCHEMA)
    # Migrations: add verification columns to existing DBs
    for col_sql in [
        "ALTER TABLE metrics ADD COLUMN verification TEXT DEFAULT 'Don''t Know'",
        "ALTER TABLE metrics ADD COLUMN verification_value REAL",
        "ALTER TABLE metrics ADD COLUMN verification_source_url TEXT",
        "ALTER TABLE metrics ADD COLUMN verification_feedback TEXT",
        "ALTER TABLE metrics ADD COLUMN verification_blame TEXT",
    ]:
        try:
            conn.execute(col_sql)
            conn.commit()
        except sqlite3.OperationalError:
            pass  # Column already exists
    # Seed companies from registry
    from earnings2.config import COMPANY_REGISTRY
    for slug, info in COMPANY_REGISTRY.items():
        conn.execute(
            "INSERT OR IGNORE INTO companies (slug, name, ticker, cik) VALUES (?, ?, ?, ?)",
            (slug, info["name"], info["ticker"], info["cik"]),
        )
    conn.commit()
    conn.close()
