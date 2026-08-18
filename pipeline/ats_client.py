"""Greenhouse, Lever, and Workday public job-board API clients.

All three are unauthenticated, unlike the OSHA path's data source - the
harder problem here isn't rate limits, it's discovery: none of the three
offer a "search all companies" endpoint. Each only serves postings for a
company you already know the board token (or tenant/shard/site, for
Workday) for - see pipeline/hiring_seed.py. This is the single biggest
architectural difference from the OSHA scanner, which gets a real global
scan via NAICS codes - see docs/hiring_signal_scope.md.

Verified live 2026-08-18 against real boards: Greenhouse (sweetgreen,
caribou), Lever (bluebottlecoffee, insomniacookies), and Workday (chipotle,
whataburger, shakeshack) all returned real, current job data with the field
shapes below.
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta

import requests

GREENHOUSE_BASE_URL = "https://boards-api.greenhouse.io/v1/boards"
LEVER_BASE_URL = "https://api.lever.co/v0/postings"
WORKDAY_PAGE_SIZE = 20  # Workday 400s on limit > 20 - confirmed live 2026-08-18, not documented anywhere
WORKDAY_MAX_JOBS = 1000  # safety cap - see workday_jobs docstring


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


def _parse_workday_relative_date(text: str, today: date) -> date | None:
    """Workday's CXS API only exposes a relative string ('Posted Today',
    'Posted Yesterday', 'Posted N Days Ago', 'Posted 30+ Days Ago') - no ISO
    date field, confirmed live. '30+ Days Ago' is genuinely unknown beyond
    "more than 30" - returned as None (unknown) rather than guessed, same
    fail-open pattern as a missing Greenhouse first_published."""
    if "Today" in text:
        return today
    if "Yesterday" in text:
        return today - timedelta(days=1)
    match = re.search(r"(\d+)\s+Days? Ago", text)
    if match:
        return today - timedelta(days=int(match.group(1)))
    return None


def workday_jobs(
    tenant: str, shard: str, site: str, job_family_group_id: str | None = None, today: date | None = None
) -> list[dict]:
    """Live postings for one Workday tenant's career site, via the same
    unauthenticated JSON endpoint (`/wday/cxs/{tenant}/{site}/jobs`, POST)
    the site's own search box calls - confirmed live 2026-08-18 against
    Chipotle (216 total), Shake Shack (561), and Whataburger (4,290,
    overwhelmingly frontline "Restaurant Operations" reqs).

    `job_family_group_id` scopes the query server-side to one
    `jobFamilyGroup` facet value via `appliedFacets` - confirmed live to work
    exactly as expected (Whataburger's total dropped from 4,290 to 3 when
    scoped to its "Human Resources" facet id). Facet ids are opaque and
    tenant-specific (Chipotle uses 3-letter codes like "HRA", Whataburger
    spells out "Human Resources", Shake Shack has no HR-shaped facet at
    all) - there's no universal id to guess, so this is only set in
    pipeline/hiring_seed.py for tenants large enough to need it (currently
    just Whataburger). Small boards are paginated in full instead
    (WORKDAY_MAX_JOBS caps this either way, so a misconfigured/missing
    facet on a future large tenant fails safe rather than pulling
    unboundedly).

    Undocumented quirk, confirmed live 2026-08-18: `total` in the response
    is only reliable on the first page (offset=0) - every subsequent page
    reports `total: 0` even though it still returns real jobPostings data.
    Looping on the per-page `total` (the obvious way to write this) breaks
    pagination after the second page, silently truncating the scan - caught
    by cross-checking a raw title count against the paginated result rather
    than trusting the loop not to lie. `total` is read once, from the first
    page only, and reused as the fixed loop bound below.
    """
    today = today or date.today()
    applied_facets = {"jobFamilyGroup": [job_family_group_id]} if job_family_group_id else {}

    jobs = []
    offset = 0
    total = None
    while offset < WORKDAY_MAX_JOBS and (total is None or offset < total):
        resp = requests.post(
            f"https://{tenant}.{shard}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs",
            json={"appliedFacets": applied_facets, "limit": WORKDAY_PAGE_SIZE, "offset": offset, "searchText": ""},
            timeout=30,
        )
        if resp.status_code == 404:
            return []
        resp.raise_for_status()
        data = resp.json()
        if total is None:
            total = data["total"]

        for job in data["jobPostings"]:
            jobs.append(
                {
                    "title": job["title"],
                    "url": f"https://{tenant}.{shard}.myworkdayjobs.com/{site}{job['externalPath']}",
                    "location": job.get("locationsText"),
                    "team": None,
                    "posted_date": _parse_workday_relative_date(job.get("postedOn", ""), today),
                    "posting_id": job["bulletFields"][0] if job.get("bulletFields") else job["externalPath"],
                    "source": "workday",
                }
            )

        offset += WORKDAY_PAGE_SIZE
    return jobs
