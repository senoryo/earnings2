from earnings2.models import Quarter


def financial_supplement_url(quarter: Quarter) -> str:
    """Generate URL for Morgan Stanley financial supplement PDF.

    Pattern: https://www.morganstanley.com/about-us-ir/finsup{Q}q{YYYY}/finsup{Q}q{YYYY}.pdf
    """
    tag = f"{quarter.q}q{quarter.year}"
    return f"https://www.morganstanley.com/about-us-ir/finsup{tag}/finsup{tag}.pdf"


DOC_TYPES = {
    "financial_supplement": financial_supplement_url,
}
