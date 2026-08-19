from __future__ import annotations

import re

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


def _normalize_company_name(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def find_company_by_name_fuzzy(name: str):
    """Fallback for when find_company_by_name's exact match misses - a real
    gap external enrichment data hits routinely, not a hypothetical: Clay
    returned "Chick-fil-A Corporate Support Center" (its LinkedIn-sourced
    display name) for the exact same company this pipeline already knows
    as "Chick-fil-A". An exact match would silently create a duplicate.

    Searches HubSpot's own companies via CONTAINS_TOKEN on `name`'s first
    significant word (cheap way to get a short candidate list rather than
    scanning the whole portal), then only accepts a candidate whose
    normalized name is a true prefix of the other's - not just "shares a
    token" (which would also match an unrelated company that happens to
    share a common word). No AI, no hardcoded per-company synonym list -
    same normalize-and-compare approach pipeline/site_count.py's Rung 1
    already uses for OSHA establishment names, applied to a live HubSpot
    search here instead of a static seed list.
    """
    first_token = re.split(r"[\s,.\-]+", name.strip())[0]
    if not first_token:
        return None

    resp = requests.post(
        f"{BASE_URL}/crm/v3/objects/companies/search",
        headers=_headers(),
        json={
            "filterGroups": [
                {"filters": [{"propertyName": "name", "operator": "CONTAINS_TOKEN", "value": first_token}]}
            ],
            "limit": 10,
            "properties": ["name"],
        },
    )
    resp.raise_for_status()
    results = resp.json()["results"]

    target = _normalize_company_name(name)
    for candidate in results:
        candidate_name = candidate["properties"].get("name") or ""
        candidate_norm = _normalize_company_name(candidate_name)
        if candidate_norm and (target.startswith(candidate_norm) or candidate_norm.startswith(target)):
            return candidate
    return None


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


# "One to One" (Sales) subscription - found live via the subscriptions list
# endpoint while building Task #7. Needed before enroll_in_sequence(): a
# contact with no recorded legal basis 400s with SequenceError.UNSUBSCRIBED
# on this EU-hosted portal, confirmed live twice (Task #7 and #8 testing).
# See docs/task7_workflow_notes.md.
ONE_TO_ONE_SUBSCRIPTION_ID = "3303612298"


def subscribe_contact(email: str, subscription_id: str = ONE_TO_ONE_SUBSCRIPTION_ID):
    """legalBasis/legalBasisExplanation are undocumented as required in the
    v3 guide (marked optional there) but this portal 400s without them:
    "Legal Basis is required for resubscribing a contact on GDPR enabled
    portals" - confirmed live, 2026-08-18, not caught in the earlier Task #7
    investigation. LEGITIMATE_INTEREST_CLIENT, not CONSENT_WITH_NOTICE - this
    contact never opted in; the honest basis for cold B2B outreach to a
    business role via public professional information is legitimate
    interest, not consent."""
    resp = requests.post(
        f"{BASE_URL}/communication-preferences/v3/subscribe",
        headers=_headers(),
        json={
            "emailAddress": email,
            "subscriptionId": subscription_id,
            "legalBasis": "LEGITIMATE_INTEREST_CLIENT",
            "legalBasisExplanation": (
                "B2B sales outreach to a corporate role, identified via public "
                "professional information, in connection with a public OSHA "
                "regulatory signal at the contact's employer."
            ),
        },
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


def get_company_qsr_signal(company_id: str, signal_type: str | None = None):
    """Fetches one real qsr_signal record associated with a company -
    verified live 2026-08-18 (GET .../companies/{id}/associations/{type}
    returns `{"results": [{"toObjectId": ...}]}`). Built so a later process
    (e.g. drafting an email for a contact that arrived via a manual Clay
    CSV import, not a live signal-handler run) can recover the real
    signal that originally justified the account, instead of that data
    needing to be hardcoded per company at the call site. Returns the
    first match if `signal_type` is given (e.g. "Hiring", to avoid
    accidentally picking up an OSHA signal on a company that has both),
    else the first associated signal regardless of type. None if the
    company has no associated qsr_signal at all."""
    resp = requests.get(
        f"{BASE_URL}/crm/v4/objects/companies/{company_id}/associations/{QSR_SIGNAL_OBJECT_TYPE}",
        headers=_headers(),
    )
    resp.raise_for_status()
    signal_ids = [r["toObjectId"] for r in resp.json()["results"]]

    for signal_id in signal_ids:
        detail = requests.get(
            f"{BASE_URL}/crm/v3/objects/{QSR_SIGNAL_OBJECT_TYPE}/{signal_id}",
            headers=_headers(),
            params={"properties": "signal_summary,signal_date,signal_type"},
        )
        detail.raise_for_status()
        props = detail.json()["properties"]
        if signal_type and props.get("signal_type") != signal_type:
            continue
        return props
    return None


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


# Association type IDs, verified live 2026-08-18 via
# GET /crm/v4/associations/notes/contacts/labels (Note-to-Contact) - same
# constant-not-relooked-up-per-call pattern as QSR_SIGNAL_OBJECT_TYPE above.
NOTE_TO_COMPANY = 190
NOTE_TO_CONTACT = 202


def create_note(object_id: str, note_body: str, association_type_id: int = NOTE_TO_COMPANY):
    """Defaults to Note-to-Company (existing Task #6 behavior, unchanged for
    all current call sites). Pass NOTE_TO_CONTACT for a Contact - added for
    Task #8's first-touch draft, which lives on the contact it's addressed
    to, not the company."""
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
                    "to": {"id": object_id},
                    "types": [
                        {
                            "associationCategory": "HUBSPOT_DEFINED",
                            "associationTypeId": association_type_id,
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
