"""Populates HubSpot from the user's own Clay-enriched Hiring signal
contacts export: creates/associates contacts, drafts the Tier 1 first-touch
email, writes it as a Note, and enrolls the contact in the single "QSR
Hiring Signal" sequence (id 847727806) - per explicit user direction that
Tier 1 and Tier 3 contacts share one sequence for this demo, unlike the
OSHA path's separate Tier 1/Tier 3 sequences.

Generalized 2026-08-19 - the first version hardcoded a CSV-company-name ->
canonical-name map and a canonical-name -> representative-job-posting map,
both scoped to exactly the 5 companies that happened to be in the first
CSV. Neither was a Clay-automation problem (Clay's trial expiring is why
this whole step is a manual CSV rather than an automated resolve_contact()
call) - they were just not-yet-generalized code, worth fixing regardless
of Clay's plan tier since a second CSV with different companies would
otherwise need script edits every time:

- Company resolution now goes through domain match first (reliable,
  already worked), then HubSpot's own fuzzy name search
  (find_company_by_name_fuzzy) instead of a fixed synonym dict - handles
  "Chick-fil-A Corporate Support Center" vs. "Chick-fil-A" for any company,
  not just the ones seen so far.
- The representative signal used to draft each email is pulled from the
  real qsr_signal record already associated with that company in HubSpot
  (pipeline/hubspot_client.py:get_company_qsr_signal) - the real data this
  pipeline already wrote when the signal was first pushed, not a literal
  copied into this script by hand.
"""
from __future__ import annotations

import csv
import os

from dotenv import load_dotenv

load_dotenv()

from pipeline.hiring_personalize import draft_first_touch
from pipeline.hubspot_client import (
    NOTE_TO_CONTACT,
    create_contact,
    create_note,
    enroll_in_sequence,
    find_company_by_domain,
    find_company_by_name,
    find_company_by_name_fuzzy,
    find_contact_by_email,
    get_company_qsr_signal,
    subscribe_contact,
    upsert_signal_company,
)

CSV_PATH = "output/output:clay_hiring_signal_contacts.csv"
SEQUENCE_ID = "847727806"  # "QSR Hiring Signal" - one sequence, both tiers, per explicit demo-scoping decision

SENDER_EMAIL = os.environ["HUBSPOT_SENDER_EMAIL"]
SENDER_USER_ID = os.environ["HUBSPOT_SENDER_USER_ID"]


def _render_note_body(subject: str, body: str) -> str:
    paragraphs = body.split("\n\n")
    return f"<strong>Subject:</strong> {subject}<br><br>" + "<br><br>".join(
        p.replace("\n", "<br>") for p in paragraphs
    )


def resolve_company(raw_name: str, domain: str | None) -> tuple[str, str]:
    """Returns (company_id, real_name). Domain match first (most reliable,
    already worked before this rewrite); falls back to an exact name match,
    then a fuzzy one, since an enrichment tool's display string for a
    company routinely differs from our own canonical name. Backfills the
    domain onto whatever's found - {"disqualified": "false"} rather than
    {} because an empty properties dict 400s when there's nothing else to
    change (confirmed live - see git history)."""
    existing = find_company_by_domain(domain) if domain else None
    if existing is None:
        existing = find_company_by_name(raw_name)
    if existing is None:
        existing = find_company_by_name_fuzzy(raw_name)

    if existing:
        real_name = existing["properties"]["name"]
        company = upsert_signal_company(real_name, domain, {"disqualified": "false"})
        return company["id"], real_name

    # Genuinely new company, not one this pipeline has seen before - create
    # fresh using the CSV's own name, the only one available.
    company = upsert_signal_company(raw_name, domain, {"disqualified": "false"})
    return company["id"], raw_name


def build_signal_from_company(company_id: str, real_name: str) -> dict | None:
    """Reconstructs a signal-shaped dict (job_title, location, posted_date)
    from the real qsr_signal record already associated with this company -
    real CRM data, not a hardcoded literal. Returns None if the company has
    no associated Hiring signal (shouldn't happen for companies sourced via
    this pipeline, but a manually-imported CSV could reference one that
    isn't)."""
    props = get_company_qsr_signal(company_id, signal_type="Hiring")
    if props is None:
        return None

    # signal_summary is always "Hiring - {job_title} - {account_name}"
    # (pipeline/signal_handler.py:handle_hiring_signal composes it exactly
    # this way) - stripping the known prefix/suffix recovers job_title
    # exactly even when the title itself contains " - " (several real
    # postings do, e.g. "Field Training Manager - Arby's(...)"), which a
    # naive split() on " - " would get wrong.
    summary = props.get("signal_summary", "")
    job_title = summary.removeprefix("Hiring - ").removesuffix(f" - {real_name}")
    return {"job_title": job_title or summary, "location": None, "posted_date": props.get("signal_date")}


def main():
    with open(CSV_PATH) as f:
        rows = list(csv.DictReader(f))

    for row in rows:
        name = row["Full Name"]
        raw_company = row["Company"].strip()
        email = row["Work Email"].strip()
        domain = email.split("@")[-1] if email else None

        company_id, real_name = resolve_company(raw_company, domain)

        existing = find_contact_by_email(email) if email else None
        already_processed = bool(existing)
        if existing:
            contact_id = existing["id"]
        else:
            props = {"firstname": row["First Name"], "lastname": row["Last Name"], "jobtitle": row["Job Title"]}
            if email:
                props["email"] = email
            contact_id = create_contact(props, company_id)["id"]

        if not email:
            print(f"CONTACT ONLY (no email): {name} -> {contact_id} ({real_name})")
            continue

        if already_processed:
            print(f"SKIP (already exists, not re-drafting/re-enrolling): {name} -> {contact_id}")
            continue

        signal = build_signal_from_company(company_id, real_name)
        if signal is None:
            print(f"SKIP {name} ({real_name}) - no Hiring qsr_signal associated with this company")
            continue

        draft = draft_first_touch(signal, real_name, {"name": name, "title": row["Job Title"]})
        create_note(contact_id, _render_note_body(draft["subject"], draft["body"]), NOTE_TO_CONTACT)

        subscribe_contact(email)
        try:
            enroll_in_sequence(contact_id, SEQUENCE_ID, SENDER_EMAIL, SENDER_USER_ID)
            enrolled = True
        except Exception as e:
            enrolled = False
            print(f"  enrollment failed for {email}: {e}")

        print(f"DONE: {name} ({real_name}) -> contact {contact_id}, draft='{draft['subject']}', enrolled={enrolled}")


if __name__ == "__main__":
    main()
