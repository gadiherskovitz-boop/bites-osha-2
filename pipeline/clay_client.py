import csv
import re
import unicodedata

import requests

from pipeline.config import CLAY_API_KEY

BASE_URL = "https://api.clay.com/public/v0"

# Corporate-entity noise words seen in real Clay exports (Dunkin' Brands,
# Chick-fil-A Corporate Support Center, Burger King Corporation) - stripped
# before matching a returned "Company" value back to the brand name that
# was actually sent in write_companies_csv().
_CORP_SUFFIXES = {
    "brands", "corporate", "corporation", "corp", "inc", "llc", "ltd",
    "support", "center", "centre", "group", "holdings", "company", "co",
}


def normalize_company_name(name: str) -> str:
    name = unicodedata.normalize("NFKC", name).replace("​", "")
    name = re.sub(r"[^a-z0-9\s]", "", name.lower())
    words = [w for w in name.split() if w not in _CORP_SUFFIXES]
    return "".join(words)


def match_company_name(sent_name: str, returned_name: str) -> bool:
    """True if a Clay-exported "Company" value is plausibly the same brand
    as the name originally sent to Clay - handles corporate-suffix noise
    (see normalize_company_name), not just exact string equality.

    Deliberately does NOT do fuzzy substring matching without the country
    filter already applied by read_contacts_csv() - "McDonald's Deutschland
    LLC" would otherwise prefix-match "McDonald's" (docs/clay_api_notes.md
    already documented Clay returning unrelated regional subsidiaries for a
    US brand search - country filtering handles that, this function assumes
    it already ran).
    """
    a, b = normalize_company_name(sent_name), normalize_company_name(returned_name)
    return a == b or a.startswith(b) or b.startswith(a)

# The Companies table's webhook source needs a paid plan (confirmed live,
# 2026-08-18) - CSV import doesn't. This is the input side of that path:
# company_name is always required (it's what the domain-finder column
# resolves from); company_domain is sent pre-filled whenever the pipeline
# already knows it (Rung 1 seed matches), which lets that column skip the
# lookup and saves Clay credits. Everything else the pipeline needs (tier,
# signal_type, which signals are waiting) stays in a local pending-ledger,
# not in this CSV - Clay only needs enough to do its own job.
CSV_FIELDS = ["company_name", "company_domain"]


def write_companies_csv(companies: list[dict], path: str) -> None:
    """companies: [{"company_name": str, "company_domain": str | None}, ...]"""
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for c in companies:
            writer.writerow({
                "company_name": c["company_name"],
                "company_domain": c.get("company_domain") or "",
            })


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


def read_contacts_csv(path: str) -> list[dict]:
    """Reads a manually-exported Contacts table CSV back into clean records.

    The public API's tables/query endpoint 403s on this plan (confirmed
    live, 2026-08-18) - reading a Clay table back needs a paid tier, same
    as the webhook did on the write side. So this mirrors the CSV-import
    path: a human exports the table (Exports > Download CSV) and this
    reads the file, same manual-loop shape as write_companies_csv().

    "Company Table Data" (the link-back column to the Companies table)
    exports as the literal string "Company" for every row, not a usable
    join value - the plain "Company" column (the real company name) is
    what actually matches back to write_companies_csv()'s company_name.

    Dropped to US-only (this whole build is US-scoped - OSHA is a US
    regulator, the NAICS codes are US-specific) - this also happens to be
    what keeps an unrelated regional subsidiary (a real "McDonald's
    Deutschland LLC" turned up in a real export, 2026-08-18) from being
    treated as the same account as its US brand, matching the known Clay
    behavior already documented in docs/clay_api_notes.md.
    """
    records = []
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            email = (row.get("Work Email") or "").strip()
            company = (row.get("Company") or "").strip()
            country = (row.get("Country") or "").strip()
            if not email or not company or country != "United States":
                continue
            records.append({
                "company_name": company,
                "full_name": row.get("Full Name", "").strip(),
                "job_title": row.get("Job Title", "").strip(),
                "email": email,
                "linkedin_url": row.get("LinkedIn Profile", "").strip(),
            })
    return records


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
