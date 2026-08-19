"""Task #8 driver - drafts the one fully-personalized Tier 1 first-touch
email against a real signal. See docs/task8_email_rules.md.

Hardcoded to the Chipotle Complaint signal live in HubSpot right now
(activity_nr 1905074.015) since that's the flagship demo account per
docs/brand_history_gap.md - 100% company-owned, Tier 1, real live signal.
Contact is a placeholder pending Task #4 (resolve_contact, now pivoting to
Clay) - not faked.
"""
import json

from pipeline.personalize import draft_first_touch

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

PLACEHOLDER_CONTACT = {
    "name": "[First Name] (pending Task #4)",
    "title": "Head of L&D",
}


def main():
    draft = draft_first_touch(CHIPOTLE_SIGNAL, "Chipotle Mexican Grill", PLACEHOLDER_CONTACT)
    print(json.dumps(draft, indent=2))
    print(f"\n{len(draft['body'].split())} words")


if __name__ == "__main__":
    main()
