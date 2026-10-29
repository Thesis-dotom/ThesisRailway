"""Refresh public SEC company identities without changing the research universe."""
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import requests
from refresh_recommendations import atomic_write

SOURCE_URL = "https://www.sec.gov/files/company_tickers.json"
DIRECTORY_PATH = Path(__file__).parent / "data" / "company_directory.json"


def make_directory(payload):
    if not isinstance(payload, dict):
        raise ValueError("Invalid SEC company directory")
    companies = {}
    for item in payload.values():
        symbol = str(item.get("ticker", "")).upper()
        name = str(item.get("title", "")).strip()
        if name and re.fullmatch(r"[A-Z0-9]+(?:-[A-Z0-9]+)?", symbol):
            companies[symbol] = {"symbol": symbol, "name": name}
    if len(companies) < 1000:
        raise ValueError("Incomplete company directory; keeping the prior file")
    return {"source": SOURCE_URL, "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "companies": sorted(companies.values(), key=lambda item: item["symbol"])}


def refresh_directory(path=DIRECTORY_PATH, fetch=requests.get):
    response = fetch(SOURCE_URL, timeout=20, headers={
        "User-Agent": "Thesis Company Research (https://github.com/Thesis-dotom/ThesisRailway)"})
    response.raise_for_status()
    directory = make_directory(response.json())
    if path.exists():
        previous_count = len(json.loads(path.read_text()).get("companies", []))
        if len(directory["companies"]) < previous_count * 0.8:
            raise ValueError("Company directory shrank unexpectedly; keeping the prior file")
    atomic_write(path, directory)
    return len(directory["companies"])


if __name__ == "__main__":
    print(f"Saved {refresh_directory()} company identities.")
