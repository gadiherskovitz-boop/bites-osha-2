"""Rung 5 of the site_count waterfall: web-grounded tier classification.

⚠️ UNVERIFIED — written against the current Claude API docs but never run
live (no ANTHROPIC_API_KEY available at authoring time). Everything else in
this pipeline was verified against real endpoints before being documented as
working; this module has not been. Do not describe it as working until
`scripts/verify_tier_classifier.py` has been run against a real key.

WHY THIS RUNG EXISTS, AND WHY IT'S ONE RUNG RATHER THAN THREE

docs/account_sourcing_methodology.md narrates Rungs 2 (FDD aggregators),
3 (SEC EDGAR) and 5 (company website) as three separate unbuilt rungs. They
are collapsed into this single rung deliberately: with a web-search tool the
model picks whichever of those sources actually exists for a given brand,
so hard-coding three source-specific rungs would be three brittle
integrations doing one job. The model reports which source it grounded on,
so source attribution — the thing the separate rungs were really for — is
preserved in the result.

WHY WEB-GROUNDED RATHER THAN FREE RECALL

docs/account_sourcing_methodology.md deliberately cut "generic web search +
LLM guessing" from the waterfall, on the grounds that extraction from a
retrieved document is a materially lower hallucination risk than free-recall
guessing. That reasoning still holds and this rung respects it: the model is
required to ground its answer in a page it actually fetched and to return
that URL.

The reframing that makes this rung worth building anyway is that tiering
only needs a BAND, not an exact count. "Is this chain 200+ locations?" is a
far easier and more reliably-answerable question than "exactly how many
locations does it have?" - which is why this returns a tier band directly,
with the exact count as an optional bonus when the source states one.

Confidence is asymmetric by band and the prompt says so: a national chain
being 200+ is near-certain, while 45-vs-55 (Tier 3 vs Tier 2) is genuinely
hard. The model is instructed to return low confidence rather than guess in
that middle range, and low-confidence results fall through to the Tier 3
default like any other unresolved account.
"""
from __future__ import annotations

import json
import os
from datetime import date

from pipeline.company_names import brand_name

# Per the Anthropic API skill's default. This is a coarse classification
# task, so a cheaper model is a legitimate choice - see the cost table in
# docs/tier_classifier_notes.md - but downgrading for cost is the operator's
# call, not a silent default. Switch this one constant to change it.
MODEL = "claude-opus-5"

# Dynamic-filtering web search: the model filters results in a sandbox
# before they hit the context window. Do NOT also declare code_execution -
# it is built into this tool version, and a second execution environment
# confuses the model.
WEB_SEARCH_TOOL = {"type": "web_search_20260209", "name": "web_search"}

# Coarse classification - not intelligence-sensitive, and the search results
# do the real work. Raise if the middle bands prove unreliable in testing.
EFFORT = "low"

CACHE_DIR = os.path.join(os.path.dirname(__file__), "..", "output", "tier_cache")

TIER_BANDS = ["Disqualified", "Tier 3", "Tier 2", "Tier 1"]

_SYSTEM = """You classify US restaurant chains into size bands for a sales \
prospecting pipeline.

Bands, by number of currently-operating US locations:
- "Disqualified": 5 or fewer
- "Tier 3": 6 to 49
- "Tier 2": 50 to 199
- "Tier 1": 200 or more

Search the web and ground your answer in a page you actually retrieved. \
Report the URL you used. Do not answer from memory alone - if searching \
finds nothing usable, say so.

Confidence is not uniform across bands. Whether a large national chain \
clears 200 locations is near-certain and should be "high". Distinguishing \
45 from 55 locations (Tier 3 vs Tier 2) is genuinely hard and should be \
"low" unless a source states a specific number. Return "low" rather than \
guessing - a low-confidence answer is discarded downstream, which is the \
correct outcome when the evidence is weak.

Count US locations of the specific brand asked about. Do not count \
international locations, and do not count sibling brands owned by the same \
parent company.

If the name is a franchisee or holding company rather than a consumer-facing \
brand, and you cannot determine which brand it operates, return \
found=false."""

_SCHEMA = {
    "type": "object",
    "properties": {
        "found": {
            "type": "boolean",
            "description": "Whether a usable, sourced answer was found.",
        },
        "tier": {
            "type": "string",
            "enum": TIER_BANDS,
            "description": "The size band. Ignored when found is false.",
        },
        "site_count": {
            "type": ["integer", "null"],
            "description": "Exact US location count if a source states one, else null.",
        },
        "source_url": {
            "type": ["string", "null"],
            "description": "URL of the page the answer is grounded in.",
        },
        "source_kind": {
            "type": ["string", "null"],
            "description": "What kind of source: FDD, SEC filing, company website, news, industry report, other.",
        },
        "as_of_year": {
            "type": ["integer", "null"],
            "description": "Year the source's figure refers to, if stated.",
        },
        "confidence": {
            "type": "string",
            "enum": ["high", "medium", "low"],
            "description": "Confidence in the BAND, not the exact count.",
        },
        "reasoning": {
            "type": "string",
            "description": "One or two sentences on what the source said.",
        },
    },
    "required": ["found", "tier", "site_count", "source_url", "source_kind",
                 "as_of_year", "confidence", "reasoning"],
    "additionalProperties": False,
}


def _cache_path(brand: str) -> str:
    safe = "".join(c if c.isalnum() else "_" for c in brand.lower())[:80]
    return os.path.join(CACHE_DIR, f"{safe}.json")


def _read_cache(path: str) -> dict | None:
    if not os.path.exists(path):
        return None
    with open(path) as f:
        cached = json.load(f)
    # as_of_date is stored as an ISO string; callers expect a date.
    if cached.get("as_of_date"):
        cached["as_of_date"] = date.fromisoformat(cached["as_of_date"])
    return cached


def _write_cache(path: str, result: dict) -> None:
    os.makedirs(CACHE_DIR, exist_ok=True)
    serializable = {**result}
    if isinstance(serializable.get("as_of_date"), date):
        serializable["as_of_date"] = serializable["as_of_date"].isoformat()
    with open(path, "w") as f:
        json.dump(serializable, f)


def classify_tier(establishment_name: str) -> dict | None:
    """Asks Claude to search the web and place this brand in a tier band.

    Returns a site_count-waterfall result dict (same shape the other rungs
    return, plus `tier_hint`), or None when nothing usable was found.

    Cached permanently per brand rather than per day: a chain's size band
    changes on the order of years, and the whole point of this rung is that
    it runs once per brand and never again. Delete output/tier_cache/ to
    re-run.
    """
    candidate = brand_name(establishment_name)
    if not candidate:
        return None

    cache_path = _cache_path(candidate)
    cached = _read_cache(cache_path)
    if cached is not None:
        return cached or None  # empty dict is a cached "not found"

    import anthropic

    client = anthropic.Anthropic()
    response = client.messages.create(
        model=MODEL,
        max_tokens=4096,
        system=_SYSTEM,
        tools=[WEB_SEARCH_TOOL],
        output_config={
            "effort": EFFORT,
            "format": {"type": "json_schema", "schema": _SCHEMA},
        },
        messages=[{
            "role": "user",
            "content": f"How many US locations does the restaurant chain "
                       f'"{candidate}" operate? Which band does it fall in?',
        }],
    )

    if response.stop_reason == "refusal":
        return None

    text = next((b.text for b in response.content if b.type == "text"), None)
    if not text:
        return None
    parsed = json.loads(text)

    # A low-confidence answer is treated as no answer: it falls through to
    # the Tier 3 default, which is the documented behavior for an account
    # the waterfall can't resolve.
    if not parsed["found"] or parsed["confidence"] == "low":
        _write_cache(cache_path, {})
        return None

    result = {
        "value": parsed["site_count"],
        "tier_hint": parsed["tier"],
        "source": f"{parsed['source_kind']}: {parsed['source_url']} (Rung 5, LLM+web search)",
        "confidence": f"web_{parsed['confidence']}",
        "as_of_date": date(parsed["as_of_year"], 1, 1) if parsed["as_of_year"] else None,
        "brand_name": candidate,
        "domain": None,
    }
    _write_cache(cache_path, result)
    return result
