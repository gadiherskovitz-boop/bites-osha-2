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


def governance_model(franchised_units: int, company_units: int) -> str:
    """Classifies ownership structure from real franchised-vs-company unit counts."""
    total = franchised_units + company_units
    company_share = company_units / total
    if company_share >= 0.85:
        return "Corporate"
    if company_share <= 0.15:
        return "Franchise"
    return "Mixed"
