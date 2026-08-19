from __future__ import annotations


def tier_for_site_count(site_count: int) -> str | None:
    """Returns the Bites tier for a given site count, or None if disqualified."""
    if site_count <= 5:
        return None
    if site_count <= 49:
        return "Tier 3"
    if site_count <= 199:
        return "Tier 2"
    return "Tier 1"


def tier_for_lookup(site_count_lookup: dict) -> str | None:
    """Tiers a pipeline.site_count.lookup_site_count() result.

    Resolution order: an exact count wins; failing that, a `tier_hint` (a
    band with no exact number behind it - what Rung 5's web-grounded
    classifier returns when a source confirms the size band but states no
    figure); failing both, Tier 3 by default per
    docs/account_sourcing_methodology.md.

    An unresolved lookup defaulting to Tier 3 is NOT the same as a real,
    resolved small count, which can still be Disqualified (returns None)
    like tier_for_site_count always has. A tier_hint of "Disqualified"
    likewise returns None rather than Tier 3.
    """
    if site_count_lookup["value"] is not None:
        return tier_for_site_count(site_count_lookup["value"])
    hint = site_count_lookup.get("tier_hint")
    if hint:
        return None if hint == "Disqualified" else hint
    return "Tier 3"
