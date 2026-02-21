from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class Quarter:
    year: int
    q: int  # 1-4

    def __str__(self) -> str:
        return f"Q{self.q} {self.year}"

    @property
    def label(self) -> str:
        """Short label like '4Q24'."""
        return f"{self.q}Q{self.year % 100:02d}"

    @property
    def sort_key(self) -> tuple[int, int]:
        return (self.year, self.q)

    @classmethod
    def range(cls, start: Quarter, end: Quarter) -> list[Quarter]:
        quarters: list[Quarter] = []
        y, q = start.year, start.q
        while (y, q) <= (end.year, end.q):
            quarters.append(cls(y, q))
            q += 1
            if q > 4:
                q = 1
                y += 1
        return quarters

    @classmethod
    def parse(cls, s: str) -> Quarter:
        """Parse 'Q1 2024' or '1Q24' or '2024Q1'."""
        s = s.strip().upper()
        if s[0] == "Q":
            # Q1 2024
            parts = s.split()
            return cls(int(parts[1]), int(parts[0][1]))
        if "Q" in s and s[0].isdigit():
            idx = s.index("Q")
            left, right = s[:idx], s[idx + 1:]
            if len(left) <= 2:
                # 1Q24
                yr = int(right)
                if yr < 100:
                    yr += 2000
                return cls(yr, int(left))
            else:
                # 2024Q1
                return cls(int(left), int(right))
        raise ValueError(f"Cannot parse quarter: {s!r}")


@dataclass
class DocumentURL:
    company_slug: str
    quarter: Quarter
    doc_type: str  # e.g. "financial_supplement"
    url: str
    format: str = "pdf"


@dataclass
class ParsedMetric:
    company_slug: str
    quarter: Quarter
    metric_name: str
    value_millions: float
    source_page: int | None = None
    raw_cell_text: str = ""
    confidence: float = 1.0
    parsed_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())


@dataclass
class ExtractedTable:
    page_number: int
    table_index: int  # index within the page
    rows: list[list[str]]

    @property
    def header_row(self) -> list[str] | None:
        return self.rows[0] if self.rows else None
