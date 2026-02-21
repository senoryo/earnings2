from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = PROJECT_ROOT / "cache"
DATA_DIR = PROJECT_ROOT / "data"
DB_PATH = DATA_DIR / "earnings2.db"

CACHE_DIR.mkdir(exist_ok=True)
DATA_DIR.mkdir(exist_ok=True)

COMPANY_REGISTRY = {
    "morgan-stanley": {
        "name": "Morgan Stanley",
        "ticker": "MS",
        "cik": "0000895421",
    },
    "jp-morgan": {
        "name": "JPMorgan Chase & Co.",
        "ticker": "JPM",
        "cik": "0000019617",
    },
    "goldman-sachs": {
        "name": "Goldman Sachs",
        "ticker": "GS",
        "cik": "0000886982",
    },
}
