"""Populates HubSpot from the user's own Clay-enriched Hiring signal
contacts export: creates/associates contacts, drafts the Tier 1 first-touch
email, writes it as a Note, and enrolls the contact in the single "QSR
Hiring Signal" sequence (id 847727806) - per explicit user direction that
Tier 1 and Tier 3 contacts share one sequence for this demo, unlike the
OSHA path's separate Tier 1/Tier 3 sequences.

Company matching is by email domain, not the CSV's free-text company
name (which doesn't match what was used when these companies were first
pushed live - e.g. "Chick-fil-A Corporate Support Center" vs. "Chick-fil-A",
"DineEquity" vs. "Dine Brands Global") - upsert_signal_company's existing
adopt-and-backfill logic finds the already-existing domain-less company by
its canonical name and fills in the real domain, rather than creating a
duplicate.
"""
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
    find_contact_by_email,
    subscribe_contact,
    upsert_signal_company,
)

CSV_PATH = "output/output:clay_hiring_signal_contacts.csv"
SEQUENCE_ID = "847727806"  # "QSR Hiring Signal" - one sequence, both tiers, per explicit demo-scoping decision

SENDER_EMAIL = os.environ["HUBSPOT_SENDER_EMAIL"]
SENDER_USER_ID = os.environ["HUBSPOT_SENDER_USER_ID"]

# CSV company string -> canonical name already used when these companies
# were pushed live today (pipeline/hiring_scanner.py's establishment_name).
COMPANY_NAME_MAP = {
    "Chick-fil-A Corporate Support Center": "Chick-fil-A",
    "Inspire": "Inspire Brands",
    "Inspire Brands": "Inspire Brands",
    "DineEquity": "Dine Brands Global",  # DineEquity was IHOP's holding co. name pre-2018 rebrand - same company
    "Dine Brands Global": "Dine Brands Global",
    "Lettuce Entertain You": "Lettuce Entertain You Restaurants",
    "popeyes": "Popeyes",
}

# One representative real posting per company from today's live push -
# grounds the draft in an actual signal rather than a generic one.
COMPANY_SIGNALS = {
    "Chick-fil-A": {"job_title": "Restaurant Training Coordinator", "location": None, "posted_date": "2026-07-21"},
    "Inspire Brands": {"job_title": "Field Training Manager - Arby's", "location": None, "posted_date": "2026-07-18"},
    "Dine Brands Global": {"job_title": "Field Training Coordinator", "location": None, "posted_date": "2026-07-11"},
    "Lettuce Entertain You Restaurants": {
        "job_title": "Divisional Training Manager",
        "location": None,
        "posted_date": "2026-08-12",
    },
    "Popeyes": {"job_title": "Restaurant Training Manager", "location": None, "posted_date": "2026-08-18"},
}


def _render_note_body(subject: str, body: str) -> str:
    paragraphs = body.split("\n\n")
    return f"<strong>Subject:</strong> {subject}<br><br>" + "<br><br>".join(
        p.replace("\n", "<br>") for p in paragraphs
    )


def main():
    with open(CSV_PATH) as f:
        rows = list(csv.DictReader(f))

    for row in rows:
        name = row["Full Name"]
        raw_company = row["Company"].strip()
        canonical = COMPANY_NAME_MAP.get(raw_company)
        if canonical is None:
            print(f"SKIP {name} - unmapped company {raw_company!r}")
            continue

        email = row["Work Email"].strip()
        domain = email.split("@")[-1] if email else None

        # A real property, not {} - an empty properties dict 400s
        # ("No properties found to update") whenever the company is found
        # directly by domain (nothing left to backfill) rather than
        # adopted via the name-fallback path. Confirmed live against the
        # already-domained Chick-fil-A record (it already has chick-fil-a.com
        # from the OSHA path's earlier push).
        company = upsert_signal_company(canonical, domain, {"disqualified": "false"})
        company_id = company["id"]

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
            print(f"CONTACT ONLY (no email): {name} -> {contact_id} ({canonical})")
            continue

        if already_processed:
            print(f"SKIP (already exists, not re-drafting/re-enrolling): {name} -> {contact_id}")
            continue

        signal = COMPANY_SIGNALS[canonical]
        draft = draft_first_touch(signal, canonical, {"name": name, "title": row["Job Title"]})
        create_note(contact_id, _render_note_body(draft["subject"], draft["body"]), NOTE_TO_CONTACT)

        subscribe_contact(email)
        try:
            enroll_in_sequence(contact_id, SEQUENCE_ID, SENDER_EMAIL, SENDER_USER_ID)
            enrolled = True
        except Exception as e:
            enrolled = False
            print(f"  enrollment failed for {email}: {e}")

        print(f"DONE: {name} ({canonical}) -> contact {contact_id}, draft='{draft['subject']}', enrolled={enrolled}")


if __name__ == "__main__":
    main()
