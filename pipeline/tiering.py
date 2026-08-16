def tier_for_site_count(site_count: int) -> str | None:
    """Returns the Bites tier for a given site count, or None if disqualified."""
    if site_count <= 5:
        return None
    if site_count <= 49:
        return "Tier 3"
    if site_count <= 199:
        return "Tier 2"
    return "Tier 1"
