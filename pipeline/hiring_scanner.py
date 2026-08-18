from __future__ import annotations

import re
from datetime import date, timedelta

from pipeline.ats_client import greenhouse_jobs, lever_postings
from pipeline.hiring_seed import ATS_BOARDS

# Leadership bar, deliberately narrower than a plain "training"/"HR" keyword
# match - kept consistent with pipeline/persona_tracks.py's own definition
# of "leadership" (vp/director/head/c-suite, not "senior" individual
# contributors or bare "Manager" titles). This matters for real precision:
# a live scan against Insomnia Cookies turned up "Senior Field HRBP" and
# "Manager, Talent Acquisition" (Sweetgreen) - real People-function roles,
# but ICs/managers, not leadership hires - and "Store Manager in Training
# (MIT)"/"Leader in Training" - a ubiquitous entry-level frontline title
# across QSR chains that a naive substring match on "training" would
# wrongly treat as a leadership signal. All three are correctly excluded by
# requiring a seniority marker AND a function marker together.
SENIORITY_KEYWORDS = [
    (r"\bdirector\b", "Director"),
    (r"\bhead of\b", "Head of"),
    (r"\bvp\b", "VP"),
    (r"\bvice president\b", "Vice President"),
    (r"\bchief\b", "Chief"),
    (r"\bclo\b", "CLO"),
    (r"\bchro\b", "CHRO"),
]

# Checked against the job title AND (Lever only) the posting's team/
# department field - "Senior Field HRBP | People Team" carries its clearest
# functional signal in the team field, not the title, confirmed live.
# Greenhouse postings have no team-equivalent field.
FUNCTION_KEYWORDS = [
    (r"\blearning\b", "Learning"),
    (r"\btraining\b", "Training"),
    (r"\bl&d\b", "L&D"),
    (r"\bpeople\b", "People"),
    (r"\bhuman resources\b", "Human Resources"),
    (r"\bhr\b", "HR"),
    (r"\btalent\b", "Talent"),
    (r"\benablement\b", "Enablement"),
    (r"\borganizational development\b", "Organizational Development"),
]


def is_relevant_hiring_posting(title: str, team: str | None = None) -> tuple[bool, str | None]:
    """L&D/Training/People-Ops leadership filter - see
    docs/hiring_signal_scope.md for the real false positives this was
    tuned against."""
    title_lower = title.lower()
    seniority_hit = next((label for pattern, label in SENIORITY_KEYWORDS if re.search(pattern, title_lower)), None)
    if not seniority_hit:
        return False, None

    function_haystack = f"{title} {team or ''}".lower()
    function_hit = next((label for pattern, label in FUNCTION_KEYWORDS if re.search(pattern, function_haystack)), None)
    if not function_hit:
        return False, None

    return True, f"{seniority_hit} + {function_hit}"


def scan_hiring_signals(window_days: int = 100, today: date | None = None) -> list[dict]:
    """Hiring trigger: a live L&D/Training/People-Ops leadership posting on
    a known QSR/fast-casual company's Greenhouse or Lever board.

    Unlike scan_inspections/scan_violations, this can only ever see the
    companies in ATS_BOARDS - neither API offers company discovery, so
    there is no equivalent of OSHA's global NAICS scan here (see
    docs/hiring_signal_scope.md). window_days also means something
    different: OSHA rows are historical events, but a Greenhouse/Lever
    posting with no posted_date (rare, fails open rather than being
    dropped) or one open longer than the window is still a live, real
    signal - a long-open req isn't "stale" the way an old OSHA inspection
    record is.
    """
    today = today or date.today()
    start = today - timedelta(days=window_days)

    signals = []
    for board in ATS_BOARDS:
        jobs = greenhouse_jobs(board["board_token"]) if board["ats"] == "greenhouse" else lever_postings(board["board_token"])
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
