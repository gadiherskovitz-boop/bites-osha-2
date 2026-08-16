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
