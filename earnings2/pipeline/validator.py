"""Validation checks for parsed earnings metrics."""

from __future__ import annotations

from dataclasses import dataclass

from earnings2.models import ParsedMetric, Quarter


@dataclass
class ValidationResult:
    check_name: str
    status: str  # "pass", "warn", "fail"
    message: str


def validate_metrics(
    metrics: list[ParsedMetric], quarter: Quarter, company_slug: str = "morgan-stanley"
) -> list[ValidationResult]:
    """Run validation checks on parsed metrics for a quarter."""
    results: list[ValidationResult] = []
    by_name = {m.metric_name: m.value_millions for m in metrics}

    # Check 1: All expected metrics present
    expected = ["total_net_revenues", "equities_trading", "fixed_income_trading", "investment_banking"]
    for name in expected:
        if name not in by_name:
            results.append(ValidationResult(
                check_name=f"metric_present_{name}",
                status="warn",
                message=f"Missing metric: {name} for {quarter}",
            ))
        else:
            results.append(ValidationResult(
                check_name=f"metric_present_{name}",
                status="pass",
                message=f"{name} = {by_name[name]:,.0f}M",
            ))

    # Check 2: Trading segments shouldn't exceed IS net revenues
    total = by_name.get("total_net_revenues")
    equities = by_name.get("equities_trading", 0)
    fixed_income = by_name.get("fixed_income_trading", 0)
    ib = by_name.get("investment_banking", 0)

    if total is not None:
        segment_sum = equities + fixed_income + ib
        if segment_sum > total * 1.1:  # 10% tolerance
            results.append(ValidationResult(
                check_name="segments_within_total",
                status="warn",
                message=f"Segment sum ({segment_sum:,.0f}) exceeds IS net revenues ({total:,.0f}) by >10%",
            ))
        else:
            results.append(ValidationResult(
                check_name="segments_within_total",
                status="pass",
                message=f"Segment sum ({segment_sum:,.0f}) within IS total ({total:,.0f})",
            ))

    # Check 3: Values in reasonable range (company-specific)
    if company_slug == "jp-morgan":
        # JPM is ~3x larger than MS
        firm_range = (20000, 55000)
        segment_max = 30000
    else:
        # Morgan Stanley defaults
        firm_range = (3000, 25000)
        segment_max = 15000

    for name, val in by_name.items():
        if name == "firm_total_net_revenues":
            if not (firm_range[0] <= val <= firm_range[1]):
                results.append(ValidationResult(
                    check_name=f"range_{name}",
                    status="warn",
                    message=f"{name} = {val:,.0f}M seems out of typical range",
                ))
        elif val < -2000 or val > segment_max:
            results.append(ValidationResult(
                check_name=f"range_{name}",
                status="warn",
                message=f"{name} = {val:,.0f}M seems out of typical range",
            ))

    return results
