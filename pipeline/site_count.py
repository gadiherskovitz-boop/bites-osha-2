from __future__ import annotations

import os
import re
import time
import unicodedata
from datetime import date

import requests

from pipeline.accounts_seed import QSR50_AS_OF_DATE, SEED_ACCOUNTS
from pipeline.company_names import brand_name

WIKIDATA_SEARCH_URL = "https://www.wikidata.org/w/api.php"
WIKIDATA_ENTITY_URL = "https://www.wikidata.org/wiki/Special:EntityData"

# Wikidata property P8368 "number of branches" (aliased "number of
# locations") - verified live to exist and hold real, sourced values (e.g.
# McDonald's Q38076 -> 40,275 branches, preferred rank, as of 2022; Subway
# Q244457 -> 36,821, as of 2021). Coverage is spotty even among huge chains
# (Burger King, KFC, Pizza Hut, Dairy Queen, Waffle House, Denny's, IHOP all
# checked live and have no P8368 claim at all) - "when populated" per
# docs/account_sourcing_methodology.md, not "usually populated."
BRANCH_COUNT_PROPERTY = "P8368"

# Wikimedia's API gateway 403s the default python-requests User-Agent -
# confirmed live. Their API etiquette policy requires a descriptive one.
_HEADERS = {"User-Agent": "BitesQSRProspectingEngine/1.0 (GTM Engineer take-home prototype)"}

def _normalize(name: str) -> str:
    """Lowercases and strips accents/punctuation/legal suffixes, for
    comparing an OSHA establishment name against a known brand name.

    Runs pipeline.company_names.brand_name first, so case-number prefixes,
    DBA franchisee wrappers and store numbers are already gone - without
    that, '111589 - Chipotle Mexican Grill Inc' failed to match Chipotle
    at all (confirmed against live data)."""
    name = brand_name(name)
    name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    name = name.lower()
    name = re.sub(r"[^a-z0-9 ]", "", name)
    name = re.sub(r"\b(llc|inc|incorporated|corp|corporation|co|ltd|lp)\b", "", name)
    return re.sub(r"\s+", " ", name).strip()


def _rung1_lookup(establishment_name: str) -> dict | None:
    """QSR Magazine QSR50 + Contenders static lookup, fuzzy-matched: a known
    brand name is considered a match if the normalized establishment name
    starts with it (handles franchisee legal names like 'Wendy'S Salt Lake
    City Llc' and store numbers like 'Yard House #8379')."""
    normalized_estab = _normalize(establishment_name)
    for seed in SEED_ACCOUNTS:
        normalized_brand = _normalize(seed["name"])
        if normalized_brand and normalized_estab.startswith(normalized_brand):
            return {
                "value": seed["site_count"],
                "source": "QSR Magazine QSR50/Contenders (Rung 1)",
                "confidence": "verified",
                "as_of_date": QSR50_AS_OF_DATE,
                # Only Rung 1 carries a canonical brand identity (name +
                # domain) - Rung 4/unresolved accounts have neither, since
                # OSHA establishment names are franchisee legal names, not
                # brand records. See pipeline/hubspot_client.py:upsert_signal_company.
                "tier_hint": None,
                "brand_name": seed["name"],
                "domain": seed["domain"],
            }
    return None


def _best_branch_count_claim(claims: list[dict]) -> dict:
    """Wikidata rank convention: 'preferred' beats 'normal' regardless of
    date; among equal rank, the claim with the latest point-in-time
    (P585) qualifier wins. A claim with no P585 qualifier sorts last."""

    def sort_key(claim):
        rank_score = 1 if claim["rank"] == "preferred" else 0
        qualifiers = claim.get("qualifiers", {})
        year = 0
        if "P585" in qualifiers:
            year = int(qualifiers["P585"][0]["datavalue"]["value"]["time"][1:5])
        return (rank_score, year)

    return max(claims, key=sort_key)


def _rung4_wikidata_lookup(establishment_name: str) -> dict | None:
    """Wikidata P8368 ('number of branches') for the brand implied by
    establishment_name. Implemented via Wikidata's search + entity-data REST
    API rather than a literal SPARQL query - simpler for a single-brand point
    lookup than standing up a SPARQL query for this shape of question, same
    live/no-auth/deterministic result the architecture doc calls for.

    Known simplification, same tradeoff Clay's enrich_company already made
    for domain search: takes the top search hit for the noise-stripped brand
    candidate without verifying it's actually a restaurant chain. This is
    fairly safe in practice - an accidental match on an unrelated Wikidata
    item (a person, a small local business) is very likely to simply lack
    P8368, so it falls through to the Tier 3 default rather than returning a
    wrong number.
    """
    candidate = brand_name(establishment_name)
    if not candidate:
        return None

    # Wikidata's anonymous API rate-limits under a batch of back-to-back
    # calls (confirmed live: a 268-establishment scan hit a 429 partway
    # through). A 429 here just means this rung didn't resolve this account
    # this run - it fails open to the Tier 3 default rather than raising,
    # same as "brand not found."
    try:
        time.sleep(0.3)  # basic throttling - see the 429 note above
        search = requests.get(
            WIKIDATA_SEARCH_URL,
            params={
                "action": "wbsearchentities",
                "search": candidate,
                "language": "en",
                "type": "item",
                "format": "json",
                "limit": 1,
            },
            headers=_HEADERS,
            timeout=15,
        )
        search.raise_for_status()
        hits = search.json().get("search", [])
        if not hits:
            return None
        qid = hits[0]["id"]

        entity = requests.get(f"{WIKIDATA_ENTITY_URL}/{qid}.json", headers=_HEADERS, timeout=15)
        entity.raise_for_status()
    except requests.exceptions.HTTPError as e:
        if e.response is not None and e.response.status_code == 429:
            return None
        raise

    claims = entity.json()["entities"][qid]["claims"]
    if BRANCH_COUNT_PROPERTY not in claims:
        return None

    best = _best_branch_count_claim(claims[BRANCH_COUNT_PROPERTY])
    value = int(best["mainsnak"]["datavalue"]["value"]["amount"])
    qualifiers = best.get("qualifiers", {})
    as_of = None
    if "P585" in qualifiers:
        year = int(qualifiers["P585"][0]["datavalue"]["value"]["time"][1:5])
        as_of = date(year, 1, 1)

    return {
        "value": value,
        "source": f"Wikidata {qid} (P8368)",
        "confidence": "wikidata",
        "as_of_date": as_of,
        "tier_hint": None,
        "brand_name": None,
        "domain": None,
    }


def _rung5_llm_lookup(establishment_name: str) -> dict | None:
    """Web-grounded tier classification via Claude + the web_search tool.

    Skipped entirely when ANTHROPIC_API_KEY isn't set - this rung is the
    only part of the pipeline that costs money per call, so it fails open
    rather than making a missing key a hard error. Import is deferred so
    the anthropic SDK stays an optional dependency.
    """
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return None
    from pipeline.tier_classifier import classify_tier

    return classify_tier(establishment_name)


# In-run memo on top of Rung 5's own permanent on-disk cache - keyed on the
# same brand-collapsed, punctuation-stripped string _rung4_wikidata_lookup
# already normalizes establishment names to, so franchisee-name variants of
# the same brand ('Ayvaz Pizza Llc Dba Pizza Hut', 'Wendy'S Salt Lake City
# Llc') share one entry. Without this, a scan/handler run that sees the same
# brand across multiple signals (common - several real brands in this
# portal have 2-3 signals in one window) re-pays Rung 4's live Wikidata
# call, and potentially Rung 5's paid Claude+web-search call, once per
# signal instead of once per brand.
_LOOKUP_CACHE: dict[str, dict] = {}


def lookup_site_count(establishment_name: str) -> dict:
    """The site_count waterfall: Rung 1 (QSR50/Contenders, free/instant) ->
    Rung 4 (Wikidata, free/fast) -> Rung 5 (LLM + web search, paid/slow) ->
    unresolved. Always returns a dict - never a bare number - per
    docs/account_sourcing_methodology.md, so a Tier-3-by-default account
    (value=None, tier_hint=None) is distinguishable from a verified one.

    Ordered cheapest-first, so the paid rung only runs for brands the two
    free rungs miss. Rung 5 also subsumes the separately-narrated Rungs 2
    (FDD) and 3 (SEC EDGAR) - with a web-search tool the model picks
    whichever source exists and reports which one it used. See
    pipeline/tier_classifier.py.

    Rung 5 is skipped when no ANTHROPIC_API_KEY is configured, so the
    pipeline still runs (degrading to the Tier 3 default) without one.
    """
    key = _normalize(establishment_name)
    if key in _LOOKUP_CACHE:
        return _LOOKUP_CACHE[key]

    result = (
        _rung1_lookup(establishment_name)
        or _rung4_wikidata_lookup(establishment_name)
        or _rung5_llm_lookup(establishment_name)
        or {
            "value": None,
            "source": None,
            "confidence": "estimated",
            "as_of_date": None,
            "tier_hint": None,
            "brand_name": None,
            "domain": None,
        }
    )
    _LOOKUP_CACHE[key] = result
    return result
