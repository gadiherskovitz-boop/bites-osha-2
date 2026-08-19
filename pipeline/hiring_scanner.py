from __future__ import annotations

import os
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


# Adzuna's `what` does NOT support inline boolean/quoted-OR syntax - a
# combined `'"learning and development" OR "training manager"'` query
# silently returned 0 results, confirmed live 2026-08-18 (no error, just
# nothing - Adzuna's own docs don't call this out). Only `what_phrase`
# (exact phrase) is real, so OR-of-phrases means one call per phrase,
# merged and deduped by job id below - see pipeline/adzuna_client.py.
ADZUNA_PHRASES = ["learning and development", "training manager", "training coordinator", "enablement"]

# Real Adzuna US categories (GET /v1/api/jobs/us/categories), confirmed live
# to surface genuine hits when combined with the phrases above -
# "Learning & Development Manager" at McDonald's, "Training Manager" at
# Dunkin', "Restaurant Training Coordinator" at Chick-fil-A - all three
# already in accounts_seed.py's QSR50 list. Neither category is precise
# alone (hospitality-catering-jobs also surfaces hotels/casinos/gyms;
# hr-jobs surfaces every industry with an HR department, e.g. law firms),
# so is_relevant_hiring_posting() still runs locally afterward, and
# PERSONAL_TRAINING_PATTERN below catches a real false-positive class this
# combination specifically surfaced that the ATS-native scan never did.
ADZUNA_CATEGORIES = ["hospitality-catering-jobs", "hr-jobs"]

# "Personal Training Manager" (fitness gyms - Crunch Fitness, Valley
# Fitness, The Alaska Club all hit live under hospitality-catering-jobs)
# contains "training" and passes the seniority-agnostic function check, but
# is gym/fitness-instruction, not organizational L&D. Not a pattern the
# ATS-native scan ever surfaced (none of those 7 companies are fitness
# chains) - specific to casting a wider net via Adzuna. Kept even though
# _is_restaurant_chain() below also catches most of these (a fitness studio
# isn't a restaurant chain either) - cheap enough to check first and avoids
# spending an LLM call on an obvious case.
PERSONAL_TRAINING_PATTERN = re.compile(r"\bpersonal training\b|\bfitness\b", re.I)

_UNAVAILABLE = "__classifier_unavailable__"  # sentinel key in _is_restaurant_chain's cache dict

# Confirmed-wrong classifications found live, checked before the AI call
# rather than left to a retry hoping for a different answer:
# - "Sam's East"/"Sam's West": real Sam's Club/Walmart legal entities. Sam's
#   Club warehouse stores do sell some prepared food (bakery, food court in
#   some locations) - same failure shape as the original Marriott miss
#   (real secondary food service on a company whose primary business isn't
#   running restaurants).
# - "Copeland": an HVAC/industrial company (posting "Executive Enablement
#   Assistant"), not a restaurant chain at all - the classifier's web
#   search found "Copeland's," a real but UNRELATED Cajun restaurant chain
#   with a similar name, and matched the wrong company. A name-collision
#   failure, different shape than the food-service-adjacent cases above.
KNOWN_NOT_RESTAURANT_CHAINS = {"sam's east", "sam's west", "copeland"}


def _is_restaurant_chain(company_name: str, cache: dict[str, dict]) -> bool:
    """Adzuna's real categories (hospitality-catering-jobs, hr-jobs) are
    nowhere near precise enough to mean "restaurant chain" - confirmed live,
    first real run: hotels/casinos (Marriott, MGM, Wynn), banks, law firms,
    security firms (GardaWorld), aerospace/defense (Northrop Grumman), and
    food MANUFACTURERS (Georgia-Pacific, Schwan's) all passed the
    category+phrase filter. Real signal was ~15 genuine QSR hits out of 401
    raw results (~4%).

    Calls pipeline/hiring_industry_classifier.py:classify_restaurant_chain -
    a small, dedicated classifier built specifically for this question,
    deliberately NOT pipeline/tier_classifier.py's classify_tier (Rung 5 of
    the OSHA path's site_count waterfall). classify_tier's prompt
    presupposes the input already IS a restaurant chain (correct for OSHA,
    where every establishment name is restaurant-NAICS-scoped by
    construction) and was confirmed live to wrongly accept "Marriott Hotels
    Resorts" - it found a real 321-US-location count and reported it,
    since the prompt never asked whether Marriott is a restaurant chain in
    the first place. Fixing that in place would mean changing shared,
    already-verified, presentation-critical OSHA infrastructure to solve a
    problem that's specific to this Adzuna layer - not worth that risk for
    a small, separable question. `cache` is an in-run memo on top of
    classify_restaurant_chain's own permanent disk cache, since a handful
    of companies (GardaWorld, Four Seasons, Walmart) appeared 3-7 times in
    the first real run. `cache` now stores the classifier's full result
    dict (not just the bool), so the resolved brand name is also available
    afterward via _resolved_brand_name() - see its docstring.

    Fails CLOSED (excludes) rather than open when the classifier can't run
    - either no ANTHROPIC_API_KEY, or a real call failure (confirmed live:
    an exhausted credit balance 400s every call identically) - the opposite
    of pipeline/site_count.py's Rung 5 gate, and deliberately so: there, a
    missing key means "fall through to a Tier 3 default," a safe default.
    Here, the whole point of this function is cutting real noise, so
    "can't classify" should not silently mean "include everything" - it
    would just reproduce the 401-result problem this was built to fix.

    Two different failure shapes are handled differently, a distinction
    found necessary live: an exhausted credit balance (`anthropic.
    APIStatusError` - auth/billing/rate-limit, everything the SDK raises
    for a real API-level rejection) is PERSISTENT - every subsequent call
    will fail identically, so `_UNAVAILABLE` short-circuits every
    remaining lookup in this `cache` rather than paying the same latency
    ~150 times to fail the same way. A one-off response glitch (confirmed
    live: a single malformed-JSON response broke json.loads for one
    specific company, unrelated to any of the others) is NOT persistent -
    retrying it wouldn't help, but nor should it be treated as if every
    other company would fail too. Only that one company is excluded; the
    scan continues.
    """
    if cache.get(_UNAVAILABLE):
        return False
    if company_name not in cache:
        if company_name.lower() in KNOWN_NOT_RESTAURANT_CHAINS:
            cache[company_name] = {"is_restaurant_chain": False, "resolved_brand": None}
        elif not os.environ.get("ANTHROPIC_API_KEY"):
            cache[company_name] = {"is_restaurant_chain": False, "resolved_brand": None}
        else:
            import anthropic

            from pipeline.hiring_industry_classifier import classify_restaurant_chain

            try:
                cache[company_name] = classify_restaurant_chain(company_name)
            except anthropic.APIStatusError as e:
                print(f"  (restaurant-chain classifier unavailable, excluding remaining Adzuna results: {e})")
                cache[_UNAVAILABLE] = True
                cache[company_name] = {"is_restaurant_chain": False, "resolved_brand": None}
            except Exception as e:
                print(f"  (restaurant-chain classifier failed for {company_name!r}, excluding just this one: {e})")
                cache[company_name] = {"is_restaurant_chain": False, "resolved_brand": None}
    return cache[company_name]["is_restaurant_chain"]


def _resolved_brand_name(company_name: str, cache: dict[str, dict]) -> str:
    """The classifier's web-grounded canonical brand name when it found one -
    collapses a franchise-location-suffixed Adzuna employer name (e.g.
    "Steak 'n Shake Edwardsville") down to its real brand ("Steak 'n
    Shake"), which company_names.py's brand_name() alone can't do (see
    _is_restaurant_chain's docstring). Falls back to brand_name(company_name)
    when the classifier didn't resolve one. Only meaningful after
    _is_restaurant_chain() has populated `cache` for this company_name."""
    resolved = cache.get(company_name, {}).get("resolved_brand")
    return resolved or brand_name(company_name)


def scan_adzuna_hiring_signals(window_days: int = 100, today: date | None = None) -> list[dict]:
    """Discovery scan via Adzuna - complements scan_hiring_signals() rather
    than replacing it (see docs/hiring_signal_scope.md): this is the only
    candidate found for a genuine industry-wide scan, since Adzuna doesn't
    require knowing the company first. Returns [] with no error if
    ADZUNA_APP_ID/ADZUNA_APP_KEY aren't set (pipeline/adzuna_client.py).

    Verified live 2026-08-18 once real credentials existed - see the
    ADZUNA_PHRASES/ADZUNA_CATEGORIES comments above for the two real
    corrections that first live run produced, and _is_restaurant_chain for
    the industry-precision fix that same run showed was needed.
    """
    today = today or date.today()
    start = today - timedelta(days=window_days)

    raw_jobs = {}
    for phrase in ADZUNA_PHRASES:
        for category in ADZUNA_CATEGORIES:
            for job in adzuna_search_jobs(phrase, category=category):
                raw_jobs[job["posting_id"]] = job  # dedupe - the same posting can match multiple phrase/category pairs

    restaurant_chain_cache: dict[str, bool] = {}
    signals = []
    for job in raw_jobs.values():
        if job["posted_date"] and job["posted_date"] < start:
            continue
        if PERSONAL_TRAINING_PATTERN.search(job["title"]):
            continue
        relevant, reason = is_relevant_hiring_posting(job["title"])
        if not relevant:
            continue
        if not job["company_name"] or not _is_restaurant_chain(job["company_name"], restaurant_chain_cache):
            continue
        signals.append(
            {
                "signal_type": "Hiring",
                "establishment_name": _resolved_brand_name(job["company_name"], restaurant_chain_cache)
                if job["company_name"]
                else "Unknown",
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
