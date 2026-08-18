"""Greenhouse and Lever public job-board API clients.

Both are unauthenticated, unlike the OSHA path's data source - the harder
problem here isn't rate limits, it's discovery: neither API offers a
"search all companies" endpoint. Each only serves postings for a company you
already know the board token/slug for (see pipeline/hiring_seed.py). This is
the single biggest architectural difference from the OSHA scanner, which
gets a real global scan via NAICS codes - see docs/hiring_signal_scope.md.

Verified live 2026-08-18 against real boards: Greenhouse (sweetgreen,
caribou) and Lever (bluebottlecoffee, insomniacookies) all returned real,
current job data with the field shapes below.
"""
from __future__ import annotations

from datetime import date, datetime

import requests

GREENHOUSE_BASE_URL = "https://boards-api.greenhouse.io/v1/boards"
LEVER_BASE_URL = "https://api.lever.co/v0/postings"


def _parse_greenhouse_date(text: str | None) -> date | None:
    if not text:
        return None
    return datetime.fromisoformat(text).date()


def greenhouse_jobs(board_token: str) -> list[dict]:
    """Live postings for one Greenhouse board. 404s for a token with no
    board (confirmed live against ~90 guessed slugs, only 2 hit) - treated
    as "no postings," not an error, since a wrong/defunct token shouldn't
    crash a scan across many boards.

    `first_published` (when the posting first went live) is used as the
    posted date, not `updated_at` (bumped by routine edits like a typo fix,
    verified against real postings where the two differ by days) - the same
    care osha_client.py takes over which date field is meaningful.
    """
    resp = requests.get(
        f"{GREENHOUSE_BASE_URL}/{board_token}/jobs",
        params={"content": "false"},
        timeout=30,
    )
    if resp.status_code == 404:
        return []
    resp.raise_for_status()

    jobs = []
    for job in resp.json()["jobs"]:
        jobs.append(
            {
                "title": job["title"],
                "url": job["absolute_url"],
                "location": (job.get("location") or {}).get("name"),
                "team": None,  # Greenhouse jobs don't carry a department/team field
                "posted_date": _parse_greenhouse_date(job.get("first_published") or job.get("updated_at")),
                "posting_id": str(job["id"]),
                "source": "greenhouse",
            }
        )
    return jobs


def lever_postings(board_slug: str) -> list[dict]:
    """Live postings for one Lever board. 404s for a slug with no board -
    same fail-open treatment as greenhouse_jobs.

    `categories.team` (e.g. "People Team") is real signal Greenhouse doesn't
    have an equivalent for - confirmed live on Insomnia Cookies' "Senior
    Field HRBP | People Team" posting, used as a secondary relevance cue in
    pipeline/hiring_scanner.py.
    """
    resp = requests.get(
        f"{LEVER_BASE_URL}/{board_slug}",
        params={"mode": "json"},
        timeout=30,
    )
    if resp.status_code == 404:
        return []
    resp.raise_for_status()

    jobs = []
    for job in resp.json():
        categories = job.get("categories", {})
        jobs.append(
            {
                "title": job["text"],
                "url": job["hostedUrl"],
                "location": categories.get("location"),
                "team": categories.get("team"),
                "posted_date": date.fromtimestamp(job["createdAt"] / 1000),
                "posting_id": str(job["id"]),
                "source": "lever",
            }
        )
    return jobs
