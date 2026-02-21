from earnings2.models import Quarter

_QUARTER_ORDINALS = {
    1: "1st-quarter",
    2: "2nd-quarter",
    3: "3rd-quarter",
    4: "4th-quarter",
}

_BASE_URL = (
    "https://www.jpmorganchase.com/content/dam/jpmc/jpmorgan-chase-and-co/"
    "investor-relations/documents/quarterly-earnings"
)

# UUID-based filenames for Q3 2020+ (supplement PDFs have non-predictable names)
_URL_MAP: dict[tuple[int, int], str] = {
    # 2020 (Q3+)
    (2020, 3): "6f1254af-ca3c-4b89-ac2e-da7fde4f5d21",
    (2020, 4): "64d9321a-23db-401f-89de-a259ac985044",
    # 2021
    (2021, 1): "f265e5f8-2363-421e-98b6-ba82c3403beb",
    (2021, 2): "5a908201-875f-46ea-8a1a-ce85be1db90e",
    (2021, 3): "875f74e6-e628-4587-af8b-443ab9362fdc",
    (2021, 4): "9f63e8ea-7af5-4808-8584-b012426b546c",
    # 2022
    (2022, 1): "f9d46f02-79ac-491e-920e-26d0d2008667",
    (2022, 2): "63c21d9c-de63-4257-a0ff-3363bc76a1c1",
    (2022, 3): "03e7493b-bc90-4ff5-8c1d-9e6611117091",
    (2022, 4): "c26bc548-2a18-4e7c-b579-3323c59e73f1",
    # 2023
    (2023, 1): "88617d8a-a183-45a7-acd9-eea77b439879",
    (2023, 2): "c9585f9b-75cc-4a49-b1ea-cec4423c87a7",
    (2023, 3): "393bfa53-d214-4230-8539-860a409b2107",
    (2023, 4): "16d9371e-30e9-4898-abf6-d1f7c86fd311",
    # 2024
    (2024, 1): "9387d4e9-a7dc-4613-822d-6848965485ee",
    (2024, 2): "0c34d80d-4a60-46ad-9bb9-cfdb3a51c12d",
    (2024, 3): "6bca0e4a-703c-4fff-8e70-f026f015fee5",
    (2024, 4): "42092156-03a0-428c-9692-d7e844b063a1",
    # 2025
    (2025, 1): "e243f5ee-ff5b-4608-8ff3-a71eb55dc042",
    (2025, 2): "ac6f00d5-6753-403a-94ca-87a0296fc28b",
    (2025, 3): "4d1864a5-0376-4269-8271-24f7f49662ba",
    (2025, 4): "ff69a4a4-ab52-4a38-b82a-f153ba695e41",
}


def financial_supplement_url(quarter: Quarter) -> str:
    """Generate URL for JP Morgan earnings release financial supplement PDF.

    Two eras:
    - Q1 2015 – Q2 2020: predictable filename {q}q{yy}-earnings-supplement.pdf
    - Q3 2020+: UUID-based filenames from _URL_MAP
    """
    ordinal = _QUARTER_ORDINALS[quarter.q]
    key = (quarter.year, quarter.q)

    if key in _URL_MAP:
        filename = f"{_URL_MAP[key]}.pdf"
    else:
        # Predictable pattern for Q1 2015 – Q2 2020
        yy = quarter.year % 100
        filename = f"{quarter.q}q{yy:02d}-earnings-supplement.pdf"

    return f"{_BASE_URL}/{quarter.year}/{ordinal}/{filename}"


DOC_TYPES = {
    "financial_supplement": financial_supplement_url,
}
