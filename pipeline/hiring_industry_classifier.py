"""Industry-type classifier for the Hiring signal's Adzuna discovery layer -
answers exactly one question: is this company's PRIMARY business running
restaurant/QSR locations?

Deliberately separate from pipeline/tier_classifier.py's classify_tier(),
not an adaptation of it, per an explicit 2026-08-18 decision: classify_tier
is OSHA-critical, already-verified infrastructure (Rung 5 of the
site_count waterfall) whose prompt presupposes the input already IS a
restaurant chain - correct there, since OSHA establishment names are
restaurant-NAICS-scoped by construction, but exactly the wrong assumption
for Adzuna's general industry search, where most company names are NOT
restaurants at all. Confirmed live: classify_tier gave "Marriott Hotels
Resorts" a real, correct 321-US-location count and accepted it as
satisfying "how many locations does the restaurant chain X operate" -
because the prompt never asked whether Marriott IS a restaurant chain in
the first place, only how many locations "the restaurant chain" has.

This file exists instead of fixing that prompt in place because
classify_tier is shared with the OSHA path and changing it risks
regressing already-verified, presentation-critical behavior there for a
problem that's specific to Hiring's Adzuna layer. A separate function
asking one narrow, non-presupposing question is small enough that
duplicating a little infrastructure (its own cache, its own prompt) is
cheaper than the risk of touching shared code.

Once a real signal from here reaches pipeline/signal_handler.py:
handle_hiring_signal, tiering still goes through the normal, untouched
site_count waterfall (including classify_tier at Rung 5) exactly as it
always has - this file only gates "should this even be considered," not
"what tier is it."
"""
from __future__ import annotations

import json
import os

from pipeline.company_names import brand_name
from pipeline.llm_utils import slug_cache_path

MODEL = "claude-haiku-4-5"
WEB_SEARCH_TOOL = {"type": "web_search_20250305", "name": "web_search"}

CACHE_DIR = os.path.join(os.path.dirname(__file__), "..", "output", "restaurant_chain_cache")

_SYSTEM = """You determine whether a company name refers to a restaurant \
or QSR (quick-service restaurant) chain - a business whose core operation \
is selling prepared food/drink to consumers at physical locations (fast \
food, fast casual, coffee/bakery cafes, etc.).

Search the web to check your answer rather than relying on memory alone.

Answer true only for businesses whose PRIMARY business is running \
restaurant/food-service locations. Answer false for anything else, even \
if it operates some food service as a secondary function - hotels, \
casinos, gyms, movie theaters, gas stations/convenience stores, retail or \
warehouse clubs, and any company in an unrelated industry (finance, \
manufacturing, technology, healthcare, real estate, etc.) are all false, \
regardless of whether they happen to have an on-site restaurant, \
cafeteria, or food court.

If the name is a legal entity or franchisee rather than a consumer brand, \
search to find which brand it operates and classify THAT brand."""

_SCHEMA = {
    "type": "object",
    "properties": {
        "is_restaurant_chain": {
            "type": "boolean",
            "description": "True only if the company's PRIMARY business is running restaurant/QSR locations.",
        },
        "resolved_brand": {
            "type": ["string", "null"],
            "description": "The consumer-facing brand name, if different from the name asked about.",
        },
    },
    "required": ["is_restaurant_chain", "resolved_brand"],
    "additionalProperties": False,
}


def classify_restaurant_chain(company_name: str) -> dict:
    """Permanently cached per name - a company's industry doesn't change
    day to day, same reasoning as classify_tier's cache.

    Returns {"is_restaurant_chain": bool, "resolved_brand": str | None} -
    resolved_brand is the schema's own field for the LLM's web-grounded
    canonical brand name (already requested by _SYSTEM/_SCHEMA above, but
    previously discarded by the caller). Exposing it lets
    pipeline/hiring_scanner.py collapse a franchise-location-suffixed
    Adzuna employer name (e.g. "Steak 'n Shake Edwardsville") down to its
    real brand ("Steak 'n Shake") the same way company_names.py's
    brand_name() collapses OSHA's franchisee-legal-name patterns -
    brand_name() alone can't do this, since Adzuna's pattern (brand +
    freeform location text, no case-number/DBA/store-number marker) isn't
    one of the patterns it strips. Always {"is_restaurant_chain": False,
    "resolved_brand": None} on any failure/skip path below.

    Skipped with no ANTHROPIC_API_KEY - see pipeline/hiring_scanner.py's
    caller for why failing closed (not open) is correct here: this
    function exists specifically to cut noise, so "can't classify" must
    not silently mean "include everything."
    """
    candidate = brand_name(company_name)
    if not candidate:
        return {"is_restaurant_chain": False, "resolved_brand": None}

    cache_path = slug_cache_path(CACHE_DIR, candidate)
    if os.path.exists(cache_path):
        with open(cache_path) as f:
            return json.load(f)

    if not os.environ.get("ANTHROPIC_API_KEY"):
        return {"is_restaurant_chain": False, "resolved_brand": None}

    import anthropic

    client = anthropic.Anthropic()
    response = client.messages.create(
        model=MODEL,
        max_tokens=2048,
        system=_SYSTEM,
        tools=[WEB_SEARCH_TOOL],
        output_config={"format": {"type": "json_schema", "schema": _SCHEMA}},
        messages=[{"role": "user", "content": f'Is "{candidate}" a restaurant or QSR chain?'}],
    )
    if response.stop_reason == "refusal":
        return {"is_restaurant_chain": False, "resolved_brand": None}
    text = next((b.text for b in response.content if b.type == "text"), None)
    if not text:
        return {"is_restaurant_chain": False, "resolved_brand": None}
    parsed = json.loads(text)

    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(cache_path, "w") as f:
        json.dump(parsed, f)
    return parsed


def is_restaurant_chain(company_name: str) -> bool:
    """Boolean-only convenience wrapper around classify_restaurant_chain()."""
    return classify_restaurant_chain(company_name)["is_restaurant_chain"]
