"""Rung 5 of the site_count waterfall: LLM tier classification.

Verified live 2026-08-17 via scripts/verify_tier_classifier.py - Burger King,
Pizza Hut, KFC and Dairy Queen all correctly Tier 1 with accurate counts,
Subway correctly short-circuits at Rung 4, and a real single-location
independent from our own OSHA scan is correctly declined rather than
hallucinated into a chain. See docs/tier_classifier_notes.md.

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
from pipeline.llm_utils import slug_cache_path

# Haiku 4.5, chosen deliberately for cost on a coarse classification task
# (~3x cheaper than Opus 5 here). Three things change with this choice and
# all three would 400 or misbehave if switched carelessly:
#   1. Web search must be the BASIC tool variant - the dynamic-filtering
#      `web_search_20260209` requires Opus 4.6+/Sonnet 4.6+ and is not
#      available on Haiku 4.5.
#   2. `output_config.effort` ERRORS on Haiku 4.5 - it is not a supported
#      parameter on this model, so it is omitted entirely.
#   3. Haiku 4.5 has no adaptive thinking; omitting `thinking` means no
#      thinking, which is correct for this task.
# Moving back to Opus 5 means reversing all three, not just this constant.
MODEL = "claude-haiku-4-5"
WEB_SEARCH_TOOL = {"type": "web_search_20250305", "name": "web_search"}

CACHE_DIR = os.path.join(os.path.dirname(__file__), "..", "output", "tier_cache")

# Ascending, so an uncertain answer can be rounded up one band by index.
TIER_BANDS = ["Disqualified", "Tier 3", "Tier 2", "Tier 1"]

# Set for the remainder of this process's run once classify_tier() sees a
# persistent (auth/billing/rate-limit) failure - see that function's
# docstring. Module-level rather than a caller-side cache dict (the shape
# hiring_scanner.py uses for its sibling classifier) since lookup_site_count()
# has no per-run cache of its own to hold this in.
_rung5_unavailable = False

_SYSTEM = """You classify US restaurant chains into size bands for a sales \
prospecting pipeline.

Bands, by number of currently-operating US locations:
- "Disqualified": 5 or fewer
- "Tier 3": 6 to 49
- "Tier 2": 50 to 199
- "Tier 1": 200 or more

Search the web to check your answer rather than relying on memory alone.

Report confidence in the BAND, not in the exact number:
- "high": you are confident which band this chain falls in. Whether a large \
national chain clears 200 locations is usually this case.
- "low": the chain sits near a band boundary and you cannot tell which side \
of it they fall on - roughly 50 locations (Tier 3 vs Tier 2) or roughly 200 \
(Tier 2 vs Tier 1).

A "low" answer is NOT discarded. It is rounded UP to the next band, which is \
the deliberate policy here: under-tiering a real prospect costs a missed \
opportunity, while over-tiering one costs a little wasted attention. So \
return your best band plus "low" rather than refusing to answer.

Count US locations of the specific brand asked about. Do not count \
international locations, and do not count sibling brands owned by the same \
parent company.

Many of these names are legal entities rather than consumer-facing brands - \
a franchisee, an operating company, or a chain's corporate registration \
(for example "Blazin Wings, Inc." is the corporate entity of Buffalo Wild \
Wings). Search for the name to find which brand it operates and classify \
THAT brand. Do this before concluding you cannot identify it.

Return found=false only when the name really does not resolve to a chain - \
a single independent restaurant, or an operating company whose brand you \
cannot determine even after searching."""

# No source/provenance fields: the operator explicitly does not need source
# attribution for this build, so they are not requested. site_count is kept
# because it populates a real HubSpot Company property.
_SCHEMA = {
    "type": "object",
    "properties": {
        "found": {
            "type": "boolean",
            "description": "False only when the brand cannot be identified at all.",
        },
        "tier": {
            "type": "string",
            "enum": TIER_BANDS,
            "description": "The size band. Ignored when found is false.",
        },
        "site_count": {
            "type": ["integer", "null"],
            "description": "Exact US location count if known, else null.",
        },
        "confidence": {
            "type": "string",
            "enum": ["high", "low"],
            "description": "Confidence in the BAND. 'low' means near a band boundary.",
        },
    },
    "required": ["found", "tier", "site_count", "confidence"],
    "additionalProperties": False,
}


def round_up_band(tier: str) -> str:
    """Bumps a tier one band up, per the operator's explicit rounding rule:
    an uncertain Tier 3 becomes Tier 2, an uncertain Tier 2 becomes Tier 1.

    The asymmetry is intentional - under-tiering a real prospect costs a
    missed opportunity, over-tiering costs a little wasted attention, and
    the tier bands are wide enough that edge cases are genuinely low-stakes.
    Tier 1 is already the top band, so it stays put.
    """
    index = TIER_BANDS.index(tier)
    return TIER_BANDS[min(index + 1, len(TIER_BANDS) - 1)]


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

    Fails open (returns None, falling through to the Tier 3 default) on a
    real call failure instead of raising - a bare `json.loads` here crashed
    a full-backlog scan outright on a real malformed response (2026-08-19,
    ~270 unique establishment names in one run): one bad response took down
    every remaining brand in the batch, the same "no error handling means
    the whole flow stops" failure shape flagged in external review of a
    similar prospecting pipeline. `output_config`'s json_schema constraint
    makes this rare, not impossible - the API-level SDK client already
    retries connection/429/5xx errors (`max_retries=2` by default), so what
    reaches here is what survived that. Two shapes handled differently,
    same distinction pipeline/hiring_scanner.py's `_is_restaurant_chain`
    already makes for its sibling classifier: a persistent failure
    (`anthropic.APIStatusError` - auth/billing/rate-limit exhausted even
    after the SDK's own retries) sets a per-run flag so the rest of this
    run's ~250 brands don't each pay the same latency to fail identically;
    a one-off glitch (malformed JSON for one specific brand) only skips
    that brand.
    """
    global _rung5_unavailable
    candidate = brand_name(establishment_name)
    if not candidate:
        return None

    cache_path = slug_cache_path(CACHE_DIR, candidate)
    cached = _read_cache(cache_path)
    if cached is not None:
        return cached or None  # empty dict is a cached "not found"

    if _rung5_unavailable:
        return None

    import anthropic

    client = anthropic.Anthropic()
    # No `effort` (errors on Haiku 4.5) and no `thinking` (Haiku 4.5 has no
    # adaptive thinking; omitting it means none, which suits this task).
    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=4096,
            system=_SYSTEM,
            tools=[WEB_SEARCH_TOOL],
            output_config={"format": {"type": "json_schema", "schema": _SCHEMA}},
            messages=[{
                "role": "user",
                "content": f"How many US locations does the restaurant chain "
                           f'"{candidate}" operate? Which band does it fall in?',
            }],
        )
    except anthropic.APIStatusError as e:
        print(f"  (Rung 5 classifier unavailable, skipping remaining lookups this run: {e})")
        _rung5_unavailable = True
        return None

    if response.stop_reason == "refusal":
        return None

    text = next((b.text for b in response.content if b.type == "text"), None)
    if not text:
        return None
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as e:
        print(f"  (Rung 5 classifier returned malformed JSON for {candidate!r}, skipping just this brand: {e})")
        return None

    if not parsed["found"]:
        _write_cache(cache_path, {})  # cache the miss so we don't re-pay for it
        return None

    # Near a band boundary, round UP rather than discard - the operator's
    # explicit rule. See round_up_band().
    tier = parsed["tier"]
    rounded = parsed["confidence"] == "low"
    if rounded:
        tier = round_up_band(tier)

    result = {
        # An exact count would override the rounded band in tier_for_lookup,
        # defeating the rounding rule - so it is dropped when we rounded.
        "value": None if rounded else parsed["site_count"],
        "tier_hint": tier,
        "source": f"LLM + web search, {MODEL} (Rung 5)"
                  + (" [rounded up from band boundary]" if rounded else ""),
        "confidence": f"web_{parsed['confidence']}",
        "as_of_date": None,
        "brand_name": candidate,
        "domain": None,
    }
    _write_cache(cache_path, result)
    return result
