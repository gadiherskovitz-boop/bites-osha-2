import requests

from pipeline.config import CLAY_API_KEY

BASE_URL = "https://api.clay.com/public/v0"


def _headers():
    return {"clay-api-key": CLAY_API_KEY}


def company_search_fields():
    resp = requests.get(
        f"{BASE_URL}/search/filters-mode/fields",
        params={"source_type": "companies"},
        headers=_headers(),
    )
    resp.raise_for_status()
    return resp.json()


def search_companies(filters: dict, limit: int = 20):
    create = requests.post(
        f"{BASE_URL}/search/filters-mode",
        json={"source_type": "companies", "filters": filters},
        headers=_headers(),
    )
    create.raise_for_status()
    search_id = create.json()["search_id"]

    run = requests.post(
        f"{BASE_URL}/search/filters-mode/{search_id}/run",
        json={"limit": limit},
        headers=_headers(),
    )
    run.raise_for_status()
    return run.json()["data"]


def enrich_company(domain: str):
    """Looks up a company by domain for HQ/employee/type context.

    Returns None if Clay has no record for this domain (a real, expected
    outcome for smaller/regional brands) rather than raising.
    """
    results = search_companies({"include_company_identifiers": [domain]}, limit=1)
    if not results:
        return None
    record = results[0]
    return {
        "hq_location": record.get("location"),
        "employee_size": record.get("size"),
        "company_type": record.get("type"),
        "industry": record.get("industry"),
    }
