"""Driver for the Hiring trigger's first-touch draft - drafts against a
real signal already live in HubSpot from today's Adzuna push. See
docs/hiring_email_rules.md.

Hardcoded to the McDonald's "Learning & Development Manager" signal -
the most recognizable account among today's real hits, same flagship-demo
reasoning Chipotle got for the OSHA equivalent. Contact is a placeholder
pending Task #4 (resolve_contact) - not faked, same honesty pattern as
scripts/draft_first_touch.py.
"""
import json

from dotenv import load_dotenv

load_dotenv()

from pipeline.hiring_personalize import draft_first_touch

MCDONALDS_SIGNAL = {
    "signal_type": "Hiring",
    "establishment_name": "McDonald's",
    "job_title": "Learning & Development Manager",
    "location": None,
    "posted_date": "2026-06-11",
    "source_url": "https://www.adzuna.com/land/ad/5760781260",
}

PLACEHOLDER_CONTACT = {
    "name": "[First Name] (pending Task #4)",
    "title": "Head of L&D",
}


def main():
    draft = draft_first_touch(MCDONALDS_SIGNAL, "McDonald's", PLACEHOLDER_CONTACT)
    print(json.dumps(draft, indent=2))
    print(f"\n{len(draft['body'].split())} words")


if __name__ == "__main__":
    main()
