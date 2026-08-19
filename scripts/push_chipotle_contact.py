"""Task #4/#9 - the real end-to-end contact push, for the one company that
currently has both a real live OSHA signal AND a real resolved Clay contact:
Chipotle Mexican Grill / Katie Dake (Director, Learning and Development).

Deliberately does NOT call signal_handler.handle_signal() - that would
re-fire the Company Note and Slack alert for a signal that's already live in
HubSpot (create_note/post_message aren't idempotency-guarded the way the
qsr_signal/Company upserts are). Instead this does just the contact-side
work: find the existing company, create/subscribe the contact, then reuse
_maybe_draft_and_note_first_touch() directly - the same tested function
Task #8 already verified, just with a real Clay-resolved contact instead of
the placeholder.
"""
from pipeline.hubspot_client import (
    find_company_by_domain,
    find_contact_by_email,
    create_contact,
    subscribe_contact,
)
from pipeline.signal_handler import _maybe_draft_and_note_first_touch

CHIPOTLE_SIGNAL = {
    "signal_type": "Inspection",
    "insp_subtype": "Complaint",
    "activity_nr": "1905074.015",
    "establishment_name": "111589 - Chipotle Mexican Grill Inc",
    "state": "MN",
    "naics": "722513",
    "open_date": "2026-07-14",
    "is_open": False,
    "source_url": "https://www.osha.gov/ords/imis/establishment.inspection_detail?id=1905074.015",
}

CONTACT = {
    "email": "kdake@chipotle.com",
    "full_name": "Katie Dake",
    "title": "Director, Learning and Development",
    "linkedin_url": "https://www.linkedin.com/in/katie-dake-00749a14/",
}


def main():
    company = find_company_by_domain("chipotle.com")
    if not company:
        raise RuntimeError("No Chipotle company found by domain chipotle.com")
    print(f"Company: {company['properties'].get('name')} ({company['id']})")

    existing = find_contact_by_email(CONTACT["email"])
    if existing:
        contact_id = existing["id"]
        print(f"Contact already exists: {contact_id}")
    else:
        first, _, last = CONTACT["full_name"].partition(" ")
        created = create_contact(
            {
                "email": CONTACT["email"],
                "firstname": first,
                "lastname": last,
                "jobtitle": CONTACT["title"],
            },
            company["id"],
        )
        contact_id = created["id"]
        print(f"Contact created: {contact_id}")

    subscribe_contact(CONTACT["email"])
    print("Legal basis subscribed (One to One)")

    result = _maybe_draft_and_note_first_touch(
        CHIPOTLE_SIGNAL,
        "Chipotle Mexican Grill",
        "Tier 1",
        True,
        {"id": contact_id, "name": CONTACT["full_name"], "title": CONTACT["title"]},
    )
    print(result)


if __name__ == "__main__":
    main()
