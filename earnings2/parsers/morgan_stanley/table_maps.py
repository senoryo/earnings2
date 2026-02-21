"""Morgan Stanley financial supplement table identification and field mappings.

The financial supplement PDF contains multiple tables. We need to find:
1. The "Institutional Securities" income statement table
2. Within that, the net revenue breakdown rows

Key challenge: "Equity" appears in multiple contexts:
- Under Trading: refers to Equities trading revenue
- Under Investment Banking: refers to Equity underwriting

We solve this by context-aware row matching: we scope searches under
parent section labels.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class FieldMapping:
    metric_name: str
    # Row labels to search for (tried in order, first match wins)
    row_labels: list[str]
    # If set, only match rows that appear AFTER this section header
    under_section: str | None = None


@dataclass
class TableEra:
    """Defines how to find and parse tables for a given time period."""
    name: str
    # Header text patterns to identify the target table (any must match)
    table_header_patterns: list[str]
    # Field mappings for this era
    fields: list[FieldMapping]
    # Quarter label format used in column headers
    quarter_label_format: str = "{q}Q{yy}"  # e.g. "4Q24"


# Default era covers 2020-present (format has been stable)
DEFAULT_ERA = TableEra(
    name="2020_present",
    table_header_patterns=[
        "Institutional Securities",
        "Income Statement",
        "Institutional Securities Income Statement",
    ],
    fields=[
        FieldMapping(
            metric_name="total_net_revenues",
            row_labels=["Net revenues", "Net Revenues", "Total net revenues"],
        ),
        FieldMapping(
            metric_name="equities_trading",
            row_labels=["Equity", "Equities"],
            under_section="Trading",
        ),
        FieldMapping(
            metric_name="fixed_income_trading",
            row_labels=["Fixed income", "Fixed Income"],
            under_section="Trading",
        ),
        FieldMapping(
            metric_name="investment_banking",
            row_labels=[
                "Total investment banking",
                "Investment banking",
                "Investment Banking",
            ],
        ),
        # Firmwide net revenues come from a different table (consolidated)
        FieldMapping(
            metric_name="firm_total_net_revenues",
            row_labels=["Net revenues", "Net Revenues", "Total net revenues"],
        ),
    ],
)

# For firmwide total, we need the consolidated financial summary table
FIRMWIDE_TABLE = TableEra(
    name="firmwide",
    table_header_patterns=[
        "Financial Summary",
        "Consolidated",
        "Financial Overview",
        "Firm",
    ],
    fields=[
        FieldMapping(
            metric_name="firm_total_net_revenues",
            row_labels=["Net revenues", "Net Revenues", "Total net revenues"],
        ),
    ],
)

ERAS = [DEFAULT_ERA]
FIRMWIDE_ERAS = [FIRMWIDE_TABLE]
