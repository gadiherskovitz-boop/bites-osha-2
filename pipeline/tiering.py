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

    An unresolved lookup (value=None - neither waterfall rung found the
    brand) defaults to Tier 3, per docs/account_sourcing_methodology.md -
    NOT the same as a real, resolved small count, which can still be
    Disqualified (returns None) like tier_for_site_count always has.
    """
    if site_count_lookup["value"] is None:
        return "Tier 3"
    return tier_for_site_count(site_count_lookup["value"])


def governance_model(franchised_units: int, company_units: int) -> str:
    """Classifies ownership structure from real franchised-vs-company unit counts."""
    total = franchised_units + company_units
    company_share = company_units / total
    if company_share >= 0.85:
        return "Corporate"
    if company_share <= 0.15:
        return "Franchise"
    return "Mixed"
