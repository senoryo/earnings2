from __future__ import annotations

from abc import ABC, abstractmethod

from earnings2.models import ExtractedTable, ParsedMetric, Quarter


class CompanyParser(ABC):
    """Base class for company-specific PDF parsers."""

    company_slug: str

    @abstractmethod
    def parse_tables(
        self,
        tables: list[ExtractedTable],
        quarter: Quarter,
        page_texts: list[tuple[int, str]] | None = None,
    ) -> list[ParsedMetric]:
        """Parse extracted tables and return metrics for the given quarter."""
        ...
