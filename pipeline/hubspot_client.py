from __future__ import annotations

import requests

from pipeline.config import HUBSPOT_PRIVATE_APP_TOKEN

BASE_URL = "https://api.hubapi.com"

# The bare schema name ("qsr_signal") 400s ("Unable to infer object type")
# against the actual object read/write/search endpoints - confirmed live -
# even though it's what schema creation itself takes. Only the objectTypeId
# or fully-qualified name (p<portalId>_qsr_signal) work there. Created once
# via scripts/setup_qsr_signal_schema.py; objectTypeId is stable, so
# hardcoded here rather than looked up on every call (same pattern as
# pipeline/slack_client.py's CHANNELS).
QSR_SIGNAL_OBJECT_TYPE = "2-252022394"


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


def find_company_by_name(name: str):
    resp = requests.post(
        f"{BASE_URL}/crm/v3/objects/companies/search",
        headers=_headers(),
        json={
            "filterGroups": [
                {"filters": [{"propertyName": "name", "operator": "EQ", "value": name}]}
            ],
            "limit": 1,
        },
    )
    resp.raise_for_status()
    results = resp.json()["results"]
    return results[0] if results else None


def upsert_signal_company(name: str, domain: str | None, properties: dict):
    """Company upsert for signal-sourced accounts, which often have no known
    domain - OSHA gives an establishment name (frequently a franchisee's
    legal name), not a canonical brand domain.

    Resolution order: domain (authoritative) -> exact brand name. When a
    domain IS known but only a domain-less record with the same brand name
    exists, that record is adopted and backfilled with the domain rather
    than creating a second one. Without this, a company created by another
    source before this pipeline ran (a manual entry, an earlier import)
    permanently shadows the signal-sourced record and a rep sees the brand
    twice - which is exactly what happened to a pre-existing "Wendy's"
    record in this portal.

    Names still have to match exactly to converge. A residual gap remains
    for brands whose OSHA establishment name never resolves to a canonical
    brand (see pipeline/company_names.py) - closing that needs real domain
    enrichment, the Clay/Amplemarket problem this project already hit.
    """
    existing = find_company_by_domain(domain) if domain else None
    adopt_domain = False
    if existing is None:
        existing = find_company_by_name(name)
        adopt_domain = existing is not None and bool(domain)

    if existing:
        patch = {**properties, "domain": domain} if adopt_domain else properties
        resp = requests.patch(
            f"{BASE_URL}/crm/v3/objects/companies/{existing['id']}",
            headers=_headers(),
            json={"properties": patch},
        )
        resp.raise_for_status()
        return resp.json()

    create_properties = {**properties, "name": name}
    if domain:
        create_properties["domain"] = domain
    resp = requests.post(
        f"{BASE_URL}/crm/v3/objects/companies",
        headers=_headers(),
        json={"properties": create_properties},
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


def find_schema(name: str):
    """GET /crm/v3/schemas/{name} 400s ('Unable to infer object type') for a
    name that was never registered, rather than 404ing - confirmed live -
    so existence is checked by listing all schemas instead."""
    resp = requests.get(f"{BASE_URL}/crm/v3/schemas", headers=_headers())
    resp.raise_for_status()
    return next((s for s in resp.json()["results"] if s["name"] == name), None)


def create_schema_if_missing(schema_def: dict):
    existing = find_schema(schema_def["name"])
    if existing:
        return existing
    resp = requests.post(f"{BASE_URL}/crm/v3/schemas", headers=_headers(), json=schema_def)
    resp.raise_for_status()
    return resp.json()


def find_qsr_signal(activity_nr: str, citation_id: str | None = None):
    filters = [{"propertyName": "source_activity_nr", "operator": "EQ", "value": activity_nr}]
    filters.append(
        {"propertyName": "source_citation_id", "operator": "EQ", "value": citation_id}
        if citation_id
        else {"propertyName": "source_citation_id", "operator": "NOT_HAS_PROPERTY"}
    )
    resp = requests.post(
        f"{BASE_URL}/crm/v3/objects/{QSR_SIGNAL_OBJECT_TYPE}/search",
        headers=_headers(),
        json={"filterGroups": [{"filters": filters}], "limit": 1},
    )
    resp.raise_for_status()
    results = resp.json()["results"]
    return results[0] if results else None


def upsert_qsr_signal(company_id: str, properties: dict):
    """Idempotent per (source_activity_nr, source_citation_id) - re-running
    the scanner/handler over the same real OSHA event won't create a
    duplicate qsr_signal record, matching the dedup pattern
    upsert_company/find_contact_by_email already use elsewhere."""
    existing = find_qsr_signal(
        properties["source_activity_nr"], properties.get("source_citation_id")
    )
    if existing:
        resp = requests.patch(
            f"{BASE_URL}/crm/v3/objects/{QSR_SIGNAL_OBJECT_TYPE}/{existing['id']}",
            headers=_headers(),
            json={"properties": properties},
        )
        resp.raise_for_status()
        return resp.json()

    resp = requests.post(
        f"{BASE_URL}/crm/v3/objects/{QSR_SIGNAL_OBJECT_TYPE}",
        headers=_headers(),
        json={"properties": properties},
    )
    resp.raise_for_status()
    signal = resp.json()

    assoc = requests.put(
        f"{BASE_URL}/crm/v4/objects/{QSR_SIGNAL_OBJECT_TYPE}/{signal['id']}/associations/default/companies/{company_id}",
        headers=_headers(),
    )
    assoc.raise_for_status()
    return signal


def list_sequences(user_id: str):
    """GET /automation/sequences/2026-03 (NOT .../sequences - that 400s,
    "sequences" gets parsed as a path-segment sequenceId; confirmed live
    2026-08-18) - read access only. There is no public endpoint to CREATE a
    sequence (confirmed against HubSpot's own docs while building Task #7 -
    sequences are UI-authored, same as email templates, since they carry
    personalization tokens and a sender identity the API has no model for).
    Used to look up the id of the Tier 3 call-task sequence a human creates
    once in the HubSpot UI. `user_id` is a required query param, not
    optional - a call without it 400s. Needs automation.sequences.read.
    See docs/task7_workflow_notes.md.
    """
    resp = requests.get(
        f"{BASE_URL}/automation/sequences/2026-03",
        headers=_headers(),
        params={"userId": user_id, "limit": 100},
    )
    resp.raise_for_status()
    return resp.json()


def enroll_in_sequence(contact_id: str, sequence_id: str, sender_email: str, user_id: str):
    """POST /automation/sequences/2026-03/enrollments - the one write
    operation the public Sequences API actually offers (see list_sequences).

    Needs automation.sequences.enrollments.write, plus a HubSpot user
    (`user_id`) with a connected sending inbox matching `sender_email` -
    the scope is confirmed live (2026-08-18), the connected-inbox
    requirement is not yet confirmed. Not called by signal_handler.py until
    a real contact exists to enroll (Task #4, blocked on Amplemarket) and
    the sequence/inbox prerequisites are confirmed. See
    docs/task7_workflow_notes.md.
    """
    resp = requests.post(
        f"{BASE_URL}/automation/sequences/2026-03/enrollments",
        headers=_headers(),
        params={"userId": user_id},
        json={
            "contactId": contact_id,
            "sequenceId": sequence_id,
            "senderEmail": sender_email,
        },
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
