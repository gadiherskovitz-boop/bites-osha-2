from __future__ import annotations

import json
import os
from datetime import date

from pipeline.osha_client import establishment_search, inspection_detail
from pipeline.signal_scanner import RESTAURANT_NAICS

HISTORY_YEARS_BACK = 2  # covers "2025" and "2024" alongside the current year's YTD

# A brand's multi-year history doesn't change hour to hour, but it costs
# several seconds and N+1 detail fetches to build. Cached per brand per
# day, keyed on the date, so a run handling 20 McDonald's signals pays for
# one lookup rather than 20. This is what makes the brand-level collapse
# (pipeline/company_names.py) pay off - signals converge on far fewer
# distinct brands than establishment names.
CACHE_DIR = os.path.join(os.path.dirname(__file__), "..", "output", "history_cache")


def _cache_path(brand: str, today: date) -> str:
    safe = "".join(c if c.isalnum() else "_" for c in brand.lower())[:80]
    return os.path.join(CACHE_DIR, f"{today.isoformat()}_{safe}.json")


def _read_cache(path: str) -> dict | None:
    if not os.path.exists(path):
        return None
    with open(path) as f:
        # JSON keys are strings; restore the int years the callers expect.
        return {int(year): data for year, data in json.load(f).items()}


def _write_cache(path: str, summary: dict) -> None:
    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(path, "w") as f:
        json.dump(summary, f)


def year_summary(brand_name: str, today: date | None = None) -> dict[int, dict]:
    """Brand-wide (all locations nationally) inspection/fine history by year,
    via osha.gov/ords/imis's establishment-name search - "is this a pattern
    at this chain, not a one-off" is a stronger sales signal than one site's
    history alone.

    establishment_search's `NAICS` param is silently ignored when a name is
    also given (confirmed live - a NAICS=722511 filter still returned
    unrelated 339113/423830 results), so restaurant-NAICS filtering happens
    client-side here instead, dropping name-collision noise (e.g. "Team
    Wendy, Llc." - a helmet maker, not the restaurant chain).

    Bucketed by each inspection's date_opened year, not each citation's
    issuance_date - a citation issued after year-end for a late-December
    inspection counts against the inspection's year. A documented
    simplification, not an oversight.
    """
    today = today or date.today()
    cache_path = _cache_path(brand_name, today)
    cached = _read_cache(cache_path)
    if cached is not None:
        return cached

    start = date(today.year - HISTORY_YEARS_BACK, 1, 1)

    summary = {
        year: {"count": 0, "total_penalty": 0.0}
        for year in range(today.year - HISTORY_YEARS_BACK, today.year + 1)
    }

    rows = [
        row
        for row in establishment_search(brand_name, start, today)
        if row["naics"] in RESTAURANT_NAICS
    ]
    for row in rows:
        year = row["date_opened"].year
        if year not in summary:
            continue
        summary[year]["count"] += 1
        if row["violations_count"] > 0:
            detail = inspection_detail(row["activity_nr"])
            summary[year]["total_penalty"] += sum(
                v["current_penalty"] for v in detail["violations"]
            )

    _write_cache(cache_path, summary)
    return summary
