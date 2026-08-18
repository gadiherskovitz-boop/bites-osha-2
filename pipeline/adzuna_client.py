"""Adzuna job-search API - the one candidate found for a true industry-wide
scan (query by keyword, not by a company you already know), unlike
Greenhouse/Lever/Workday which all require a known board first. See
docs/hiring_signal_scope.md.

Verified live 2026-08-18 once real credentials existed (a free developer
account at developer.adzuna.com - created by the user, not this pipeline).
Two real corrections from that first live run, both now reflected here:

1. `what` does NOT support inline boolean/quoted-OR syntax
   (`'"learning and development" OR "training manager"'` silently returns
   0 results, no error) - only `what_phrase` (exact phrase) is real.
   OR-of-phrases means one API call per phrase, not one combined query.
2. Adzuna's real `category` taxonomy (`GET /v1/api/jobs/us/categories`)
   includes `hospitality-catering-jobs` and `hr-jobs` - both confirmed live
   to surface genuine hits ("Learning & Development Manager" at McDonald's,
   "Training Manager" at Dunkin', "Restaurant Training Coordinator" at
   Chick-fil-A - all three already in accounts_seed.py's QSR50 list). This
   is a much better-grounded industry scope than a guessed keyword filter,
   and replaces the untested INDUSTRY_KEYWORDS approach from the first
   version of this file.
"""
from __future__ import annotations

import os
from datetime import date, datetime

import requests
from dotenv import load_dotenv

# Called here rather than relying on pipeline.config's load_dotenv() -
# scripts/scan_hiring_signals.py never imports pipeline.config (no
# HubSpot/Slack/DOL/Clay calls in a dry run), so without this,
# ADZUNA_APP_ID/KEY silently read as unset even with real values in .env.
# Confirmed live: this was a real bug, not a hypothetical - the first run
# with real credentials in .env still reported "skipped, not set."
load_dotenv()

BASE_URL = "https://api.adzuna.com/v1/api/jobs"

APP_ID = os.environ.get("ADZUNA_APP_ID")
APP_KEY = os.environ.get("ADZUNA_APP_KEY")


def _parse_date(text: str | None) -> date | None:
    if not text:
        return None
    return datetime.fromisoformat(text.replace("Z", "+00:00")).date()


def search_jobs(
    what_phrase: str, category: str | None = None, country: str = "us", results_per_page: int = 50, max_pages: int = 2
) -> list[dict]:
    """Exact-phrase job search, optionally scoped to an Adzuna category
    (e.g. `hospitality-catering-jobs`, `hr-jobs`). Not scoped to any known
    company - Adzuna aggregates postings across many source boards.

    Returns [] immediately if ADZUNA_APP_ID/ADZUNA_APP_KEY aren't set.
    """
    if not (APP_ID and APP_KEY):
        return []

    jobs = []
    for page in range(1, max_pages + 1):
        params = {
            "app_id": APP_ID,
            "app_key": APP_KEY,
            "results_per_page": results_per_page,
            "what_phrase": what_phrase,
            "content-type": "application/json",
        }
        if category:
            params["category"] = category
        resp = requests.get(f"{BASE_URL}/{country}/search/{page}", params=params, timeout=30)
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
