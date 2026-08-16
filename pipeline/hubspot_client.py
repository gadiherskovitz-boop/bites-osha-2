import requests

from pipeline.config import HUBSPOT_PRIVATE_APP_TOKEN

BASE_URL = "https://api.hubapi.com"


def _headers():
    return {
        "Authorization": f"Bearer {HUBSPOT_PRIVATE_APP_TOKEN}",
        "Content-Type": "application/json",
    }


def create_property_if_missing(object_type: str, property_def: dict):
    name = property_def["name"]
    check = requests.get(
        f"{BASE_URL}/crm/v3/properties/{object_type}/{name}", headers=_headers()
    )
    if check.status_code == 200:
        return check.json()

    resp = requests.post(
        f"{BASE_URL}/crm/v3/properties/{object_type}",
        headers=_headers(),
        json=property_def,
    )
    resp.raise_for_status()
    return resp.json()


def find_company_by_domain(domain: str):
    resp = requests.post(
        f"{BASE_URL}/crm/v3/objects/companies/search",
        headers=_headers(),
        json={
            "filterGroups": [
                {
                    "filters": [
                        {"propertyName": "domain", "operator": "EQ", "value": domain}
                    ]
                }
            ],
            "limit": 1,
        },
    )
    resp.raise_for_status()
    results = resp.json()["results"]
    return results[0] if results else None


def upsert_company(domain: str, properties: dict):
    existing = find_company_by_domain(domain)
    if existing:
        resp = requests.patch(
            f"{BASE_URL}/crm/v3/objects/companies/{existing['id']}",
            headers=_headers(),
            json={"properties": properties},
        )
        resp.raise_for_status()
        return resp.json()

    resp = requests.post(
        f"{BASE_URL}/crm/v3/objects/companies",
        headers=_headers(),
        json={"properties": {**properties, "domain": domain}},
    )
    resp.raise_for_status()
    return resp.json()


def find_contact_by_email(email: str):
    resp = requests.post(
        f"{BASE_URL}/crm/v3/objects/contacts/search",
        headers=_headers(),
        json={
            "filterGroups": [
                {"filters": [{"propertyName": "email", "operator": "EQ", "value": email}]}
            ],
            "limit": 1,
        },
    )
    resp.raise_for_status()
    results = resp.json()["results"]
    return results[0] if results else None


def create_contact(properties: dict, company_id: str):
    resp = requests.post(
        f"{BASE_URL}/crm/v3/objects/contacts",
        headers=_headers(),
        json={"properties": properties},
    )
    resp.raise_for_status()
    contact = resp.json()
    associate_contact_to_company(contact["id"], company_id)
    return contact


def associate_contact_to_company(contact_id: str, company_id: str):
    resp = requests.put(
        f"{BASE_URL}/crm/v4/objects/contacts/{contact_id}/associations/companies/{company_id}",
        headers=_headers(),
        json=[
            {
                "associationCategory": "HUBSPOT_DEFINED",
                "associationTypeId": 1,  # Contact to Company, label "Primary"
            }
        ],
    )
    resp.raise_for_status()
    return resp.json()


def create_note(company_id: str, note_body: str):
    resp = requests.post(
        f"{BASE_URL}/crm/v3/objects/notes",
        headers=_headers(),
        json={
            "properties": {
                "hs_note_body": note_body,
                "hs_timestamp": _now_ms(),
            },
            "associations": [
                {
                    "to": {"id": company_id},
                    "types": [
                        {
                            "associationCategory": "HUBSPOT_DEFINED",
                            "associationTypeId": 190,  # Note to Company
                        }
                    ],
                }
            ],
        },
    )
    resp.raise_for_status()
    return resp.json()


def _now_ms():
    import time

    return int(time.time() * 1000)
