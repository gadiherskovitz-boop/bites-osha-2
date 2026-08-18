"""Tier 1 personalized first-touch email for the Hiring trigger - adapted
from pipeline/personalize.py (Task #8, the OSHA equivalent) per an explicit
request to start from that standard, not invent a new one. See
docs/hiring_email_rules.md for what changes and why.

Separate file rather than branching pipeline/personalize.py, same
"don't touch OSHA-critical, already-verified code" boundary already
applied to pipeline/hiring_industry_classifier.py - the two triggers need
a genuinely different emotional register (growth/investment vs.
compliance-risk), not a shared prompt with an if-branch. Durable, trigger-
agnostic Bites facts (FRONTLINE_TRAINING_FAILURE_MODES, PROOF_POINTS) are
imported from pipeline.personalize rather than duplicated - reading those
constants doesn't touch or risk that file.

This is a first draft awaiting approval, not yet wired into
pipeline/signal_handler.py:handle_hiring_signal - that still reports
tier1_first_touch as not-yet-built until the rules below are signed off.
"""
from __future__ import annotations

from pipeline.personalize import PROOF_POINTS

# Same model tradeoff as OSHA's Task #8: this runs once and its output IS
# the deliverable a prospect reads, so quality dominates over cost -
# Sonnet 5, not Haiku.
MODEL = "claude-sonnet-5"

# Generic placeholder account, first draft - pending approval per the
# user's request. Embedded directly in SYSTEM_PROMPT as a worked example,
# same reason OSHA's REFERENCE_DRAFT is: a concrete length/register anchor
# did more to keep generated drafts on-spec than a word-count rule stated
# abstractly (verified finding from Task #8's own tuning pass).
REFERENCE_DRAFT = {
    "subject": "Saw the L&D opening at {company}",
    "body": """Hi Alex,

I saw {company} is hiring for a Learning & Development Manager.

That kind of hire usually means training is either being rebuilt from scratch or has outgrown whatever's currently holding it together.

The gap we see most often isn't intent, it's execution: training goes uncompleted, it's front-loaded onto day one and never revisited, and it ships to an inbox frontline staff never open.

Bites gives whoever fills this role training crews actually watch, on-brand and built to be revisited on the job, not just assigned once and forgotten.

I had our team put together a 90-second {company}-branded video showing what that looks like in practice: INSERT VIDEO HERE

We've helped Unilever reach 90%+ training engagement, and teams see 67% faster onboarding - happy to walk through how that applies here.""",
}

SYSTEM_PROMPT = """You draft a cold first-touch email for a Bites SDR, for a Tier 1 QSR \
account that just posted a real Learning & Development / Training / Enablement job opening.

NON-NEGOTIABLE RULES:

1. SELL THE PROBLEM, NOT THE PRODUCT. Do not describe how Bites works. No \
feature lists. No mention of video format, mobile delivery, app/login \
mechanics, authoring speed, or tracking dashboards. If a sentence could \
appear in a product brochure, cut it.

2. LENGTH: 140 words maximum for the entire body, including the greeting \
and sign-off. This is a hard ceiling, not a target - count your words \
before finishing, and if you are over, cut a sentence rather than \
shortening every sentence a little. Short paragraphs, one to two sentences \
each, with line breaks between them. Every sentence must earn its place.

3. STRUCTURE:
   - Start with a plain greeting line: "Hi {first name}," on its own line.
   - Open with the specific, verifiable signal in one plain sentence: this \
company is hiring for this specific role. Name the role. Do not editorialize \
about why they're hiring - state the fact.
   - One sentence on what that practically means: a hire like this usually \
means training is being rebuilt from scratch, or has outgrown what's \
currently in place. This is a GROWTH/INVESTMENT framing, not a risk or \
compliance framing - never imply the company is failing, in trouble, or \
under scrutiny. They are actively building something; the email should \
read as arriving at the right moment for that build, not pointing out a \
problem they're in denial about.
   - Name the real training failure modes: not completed, boring/outdated \
content, poor timing, sent to inboxes frontline staff don't check. This is \
the heart of the email, and it should read as "here's what the person \
filling this role is about to run into," not an accusation.
   - ONE to two sentences on Bites as the answer to those failures, framed \
as equipping whoever fills this role (or the team already doing this work) \
with training crews actually use, not something they have to build from \
scratch themselves.
   - Introduce the attached video with a specific reason tied to the \
failure mode you just named - never drop the placeholder cold with no \
explanation. The video is branded to the prospect's own company. End this \
sentence with the literal placeholder text INSERT VIDEO HERE.
   - Close with an offer to show a named peer outcome (prefer Unilever's \
90%+ engagement, or the 67% faster onboarding stat if it fits the sentence \
better) - tie it to what a new L&D hire or team would want to hear, not to \
avoiding a penalty.
   - No sign-off line ("Best," / a name). End on the closing offer sentence \
- the SDR's own signature block is added separately, outside this draft.

4. TONE: peer-to-peer, calm, specific. No exclamation points. No hype \
adjectives. Never imply the company's current training is a failure they \
should be embarrassed by - the tone is "you're building this, here's a \
head start," not "you're behind."

5. Do not invent facts. Use only the supplied signal details (company, \
role, location if given), company facts, and the approved proof points. \
Never reference a job posting's internal listing ID, source URL, or ATS \
platform name (Greenhouse/Lever/Workday/Adzuna) - none of that means \
anything to the reader.

EXAMPLE OF THE RIGHT LENGTH, STRUCTURE, AND REGISTER (generic placeholder \
account - match this closely, do not exceed its length by more than a \
handful of words):

Subject: """ + REFERENCE_DRAFT["subject"] + """

""" + REFERENCE_DRAFT["body"] + """
"""


def build_user_prompt(signal: dict, account_name: str, contact: dict) -> str:
    """Assembles the data the model is allowed to use. `signal` is the same
    dict shape pipeline/hiring_scanner.py produces (job_title, location,
    posted_date, ...)."""
    return f"""Draft the first touch.

CONTACT: {contact['name']}, {contact['title']}
COMPANY: {account_name}
ROLE POSTED: {signal['job_title']}
LOCATION: {signal.get('location') or 'not specified'}
POSTED: {signal.get('posted_date') or 'recently'}
APPROVED PROOF POINTS: {PROOF_POINTS[0]}; {PROOF_POINTS[1]}
"""


def draft_first_touch(signal: dict, account_name: str, contact: dict) -> dict:
    """Calls Claude to draft the email. Returns {"subject": ..., "body": ...}."""
    import anthropic

    client = anthropic.Anthropic()
    response = client.messages.create(
        model=MODEL,
        max_tokens=2048,
        system=SYSTEM_PROMPT,
        output_config={
            "format": {
                "type": "json_schema",
                "schema": {
                    "type": "object",
                    "properties": {
                        "subject": {"type": "string"},
                        "body": {"type": "string"},
                    },
                    "required": ["subject", "body"],
                    "additionalProperties": False,
                },
            }
        },
        messages=[{"role": "user", "content": build_user_prompt(signal, account_name, contact)}],
    )

    import json

    text = next((b.text for b in response.content if b.type == "text"), None)
    if not text:
        raise RuntimeError(f"draft_first_touch: no text content in response (stop_reason={response.stop_reason})")
    return json.loads(text)
