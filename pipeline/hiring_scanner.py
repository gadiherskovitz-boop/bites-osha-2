from __future__ import annotations

import re
from datetime import date, timedelta

from pipeline.adzuna_client import search_jobs as adzuna_search_jobs
from pipeline.ats_client import greenhouse_jobs, lever_postings, workday_jobs
from pipeline.company_names import brand_name
from pipeline.hiring_seed import ATS_BOARDS

# Corrected 2026-08-18, per explicit user direction: the TRIGGER is any
# L&D/Enablement/Training posting, at ANY seniority - a Coordinator-level
# Training hire is just as real a signal as a Director-level one (arguably
# a stronger volume signal, since leadership openings are rare). Seniority
# belongs entirely downstream, at contact resolution
# (pipeline/persona_tracks.py:HIRING_TRACKS already encodes Director/VP/
# Head/Chief as who to CONTACT, not what counts as a signal) - conflating
# the two was a real design mistake in the first version of this filter,
# caught in planning before it shipped.
#
# Scope is deliberately narrower than "People/HR" broadly: only L&D/
# Training/Enablement, per the same direction. Real postings that don't
# qualify under this narrower scope: "Manager, Talent Acquisition"
# (Sweetgreen), "Sr. People Business Partner (HRBP)" (Insomnia Cookies),
# "Field HR Business Partner" (Chipotle), "Regional Field Human Resources
# Manager" (Whataburger) - all genuine People-function activity, but
# recruiting/generalist HR, not L&D/Training/Enablement specifically.
#
# The one thing seniority WAS incidentally doing right - excluding "Store
# Manager in Training (MIT)"/"Leader in Training", a ubiquitous entry-level
# frontline title pattern across QSR chains that isn't an L&D-team hire at
# all - is now handled directly via TRAINEE_PATTERN instead, since that's
# actually a different problem (a title-pattern false positive) than a
# seniority bar, and needs solving either way.
FUNCTION_KEYWORDS = [
    (r"\blearning\b", "Learning"),
    (r"\btraining\b", "Training"),
    (r"\bl&d\b", "L&D"),
    (r"\benablement\b", "Enablement"),
    (r"\borganizational development\b", "Organizational Development"),
]

# "Manager in Training (MIT)", "Leader in Training", "Management Trainee" -
# describes the employee's own onboarding status, not an L&D-department
# role. Excluded before the function-keyword check runs, so it can't be
# accidentally let back in by a broadened keyword list later.
TRAINEE_PATTERN = re.compile(r"\bin training\b|\btrainee\b", re.I)


def is_relevant_hiring_posting(title: str, team: str | None = None) -> tuple[bool, str | None]:
    """L&D/Training/Enablement trigger filter, any seniority - see
    docs/hiring_signal_scope.md for the real false positives this was
    tuned against, and the seniority-vs-trigger correction."""
    if TRAINEE_PATTERN.search(title):
        return False, None

    function_haystack = f"{title} {team or ''}".lower()
    function_hit = next((label for pattern, label in FUNCTION_KEYWORDS if re.search(pattern, function_haystack)), None)
    if not function_hit:
        return False, None

    return True, function_hit


def _fetch_board_jobs(board: dict) -> list[dict]:
    if board["ats"] == "greenhouse":
        return greenhouse_jobs(board["board_token"])
    if board["ats"] == "lever":
        return lever_postings(board["board_token"])
    return workday_jobs(board["tenant"], board["shard"], board["site"], board.get("job_family_group_id"))


def scan_hiring_signals(window_days: int = 100, today: date | None = None) -> list[dict]:
    """Hiring trigger: a live L&D/Training/Enablement posting (any
    seniority - see is_relevant_hiring_posting) on a known QSR/fast-casual
    company's Greenhouse, Lever, or Workday board.

    Unlike scan_inspections/scan_violations, this can only ever see the
    companies in ATS_BOARDS - none of the three APIs offer company
    discovery, so there is no equivalent of OSHA's global NAICS scan here
    (see docs/hiring_signal_scope.md). window_days also means something
    different: OSHA rows are historical events, but a posting with no
    posted_date (rare, fails open rather than being dropped - notably
    common for Workday's "30+ Days Ago" bucket, which is genuinely unknown
    beyond "more than 30") or one open longer than the window is still a
    live, real signal - a long-open req isn't "stale" the way an old OSHA
    inspection record is.
    """
    today = today or date.today()
    start = today - timedelta(days=window_days)

    signals = []
    for board in ATS_BOARDS:
        jobs = _fetch_board_jobs(board)
        for job in jobs:
            if job["posted_date"] and job["posted_date"] < start:
                continue
            relevant, reason = is_relevant_hiring_posting(job["title"], job["team"])
            if not relevant:
                continue
            signals.append(
                {
                    "signal_type": "Hiring",
                    "establishment_name": board["name"],
                    "domain": board["domain"],
                    "job_title": job["title"],
                    "team": job["team"],
                    "location": job["location"],
                    "posted_date": job["posted_date"],
                    "relevance_reason": reason,
                    "source_url": job["url"],
                    "ats_source": job["source"],
                    "posting_id": job["posting_id"],
                }
            )
    return signals


# Adzuna's own `what` query does the L&D/Training/Enablement pre-filter
# server-side (fewer results to pull), then is_relevant_hiring_posting()
# still re-checks the title locally - same belt-and-suspenders reasoning as
# not trusting Workday's fuzzy searchText alone (see ats_client.py).
ADZUNA_QUERY = '"learning and development" OR "training manager" OR "training coordinator" OR "l&d" OR enablement'

# Adzuna aggregates across every industry - unlike the ATS-native boards,
# which only ever contain companies we already picked, nothing here scopes
# results to restaurants/QSR server-side. This keyword heuristic is the
# stand-in, checked against title+description+company - **unverified**,
# same status as the rest of pipeline/adzuna_client.py, since there's no
# live Adzuna response yet to tune it against. Expect to revisit once real
# results exist.
INDUSTRY_KEYWORDS = re.compile(
    r"\brestaurant\b|\bQSR\b|\bquick.service\b|\bfast.casual\b|\bfranchise\b|\bhospitality\b|\bfood service\b|\bmulti.unit\b",
    re.I,
)


def scan_adzuna_hiring_signals(window_days: int = 100, today: date | None = None) -> list[dict]:
    """Discovery scan via Adzuna - complements scan_hiring_signals() rather
    than replacing it (see docs/hiring_signal_scope.md): this is the only
    candidate found for a genuine industry-wide scan, since Adzuna doesn't
    require knowing the company first. Returns [] with no error if
    ADZUNA_APP_ID/ADZUNA_APP_KEY aren't set (pipeline/adzuna_client.py).

    **Unverified end to end** - the query string, the industry heuristic,
    and the field mapping are all written against Adzuna's documented API,
    not confirmed against a real response. Treat the first real run as a
    tuning pass, the same way Rung 5's LLM classifier or the original
    Greenhouse/Lever relevance filter needed a real pass before being
    trusted.
    """
    today = today or date.today()
    start = today - timedelta(days=window_days)

    signals = []
    for job in adzuna_search_jobs(ADZUNA_QUERY):
        if job["posted_date"] and job["posted_date"] < start:
            continue
        haystack = f"{job['title']} {job.get('description') or ''} {job.get('company_name') or ''}"
        if not INDUSTRY_KEYWORDS.search(haystack):
            continue
        relevant, reason = is_relevant_hiring_posting(job["title"])
        if not relevant:
            continue
        signals.append(
            {
                "signal_type": "Hiring",
                "establishment_name": brand_name(job["company_name"]) if job["company_name"] else "Unknown",
                "domain": None,  # Adzuna doesn't carry a domain - company enrichment resolves this later
                "job_title": job["title"],
                "team": None,
                "location": job["location"],
                "posted_date": job["posted_date"],
                "relevance_reason": reason,
                "source_url": job["url"],
                "ats_source": job["source"],
                "posting_id": job["posting_id"],
            }
        )
    return signals
