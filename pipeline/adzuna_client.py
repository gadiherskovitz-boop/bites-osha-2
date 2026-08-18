"""Adzuna job-search API - the one candidate found for a true industry-wide
scan (query by keyword, not by a company you already know), unlike
Greenhouse/Lever/Workday which all require a known board first. See
docs/hiring_signal_scope.md.

**Unverified - not tested live.** Adzuna requires a free developer account
(app_id + app_key from developer.adzuna.com); creating third-party accounts
isn't something this pipeline does on its own, so this client is written
against Adzuna's documented API shape but has not been exercised against a
real response. Skips cleanly (returns []) when ADZUNA_APP_ID/ADZUNA_APP_KEY
aren't set, same gate pattern as ANTHROPIC_API_KEY in
pipeline/site_count.py's Rung 5 - treat every field name/shape below as
"per the docs," not "confirmed live," until it's actually run once real
credentials exist.
"""
from __future__ import annotations

import os
from datetime import date, datetime

import requests

BASE_URL = "https://api.adzuna.com/v1/api/jobs"

APP_ID = os.environ.get("ADZUNA_APP_ID")
APP_KEY = os.environ.get("ADZUNA_APP_KEY")


def _parse_date(text: str | None) -> date | None:
    if not text:
        return None
    return datetime.fromisoformat(text.replace("Z", "+00:00")).date()


def search_jobs(what: str, country: str = "us", results_per_page: int = 50, max_pages: int = 2) -> list[dict]:
    """Keyword job search, not scoped to any known company - Adzuna
    aggregates postings across many source boards. `what` should be an
    Adzuna-syntax query (e.g. `'"learning and development" OR "training
    manager" OR enablement'`); industry/company relevance is NOT filtered
    here - see pipeline/hiring_scanner.py's caller for the (also unverified)
    restaurant-industry heuristic layered on top, since Adzuna has no
    verified restaurant/QSR category slug to scope by server-side.

    Returns [] immediately if ADZUNA_APP_ID/ADZUNA_APP_KEY aren't set.
    """
    if not (APP_ID and APP_KEY):
        return []

    jobs = []
    for page in range(1, max_pages + 1):
        resp = requests.get(
            f"{BASE_URL}/{country}/search/{page}",
            params={
                "app_id": APP_ID,
                "app_key": APP_KEY,
                "results_per_page": results_per_page,
                "what": what,
                "content-type": "application/json",
            },
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        results = data.get("results", [])
        if not results:
            break

        for job in results:
            jobs.append(
                {
                    "title": job.get("title"),
                    "url": job.get("redirect_url"),
                    "location": (job.get("location") or {}).get("display_name"),
                    "company_name": (job.get("company") or {}).get("display_name"),
                    "description": job.get("description"),
                    "posted_date": _parse_date(job.get("created")),
                    "posting_id": str(job.get("id")),
                    "source": "adzuna",
                }
            )
    return jobs
