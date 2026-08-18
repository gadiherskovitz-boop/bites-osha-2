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

# Finalized 2026-08-18 from the user's own amended draft (see
# docs/hiring_email_rules.md's "what changed in review" section for the
# full diff against the first-pass version) - not a generic placeholder
# built from scratch this time, the user's real copy genericized back to
# a {company} token and "Alex," matching REFERENCE_DRAFT's role as a
# worked example rather than a real send. Embedded directly in
# SYSTEM_PROMPT for the same reason OSHA's REFERENCE_DRAFT is: a concrete
# length/register anchor did more to keep generated drafts on-spec than a
# word-count rule stated abstractly (verified finding from Task #8's own
# tuning pass).
REFERENCE_DRAFT = {
    "subject": "L&D role",
    "body": """Hi Alex,

I saw {company} is hiring for a Learning & Development Manager.

What makes life so tricky for L&D is they're rolling out computer-centered training to a deskless workforce.

The content is often boring (no offence). And it's usually front-loaded into the first few days. So either completion rate is low, or knowledge retention is even lower.

The real issue surfaces down the track - workplace injuries, quality suffers, violations rise.

Bites helps turn your existing training into the right format, at the right time, on the right channel.

I put together a {company}-branded training video example: INSERT VIDEO HERE

We've helped Unilever reach 90%+ training engagement, and teams see 67% faster onboarding.

I'm sure your next hire would love to have a solution like this. Open to seeing more?""",
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

3. SUBJECT LINE: short and blunt, 2-4 words (e.g. "L&D role"). Not a full \
sentence, not the company name, not "Saw your posting at X."

4. STRUCTURE:
   - Start with a plain greeting line: "Hi {first name}," on its own line.
   - Open with the specific, verifiable signal in one plain sentence: this \
company is hiring for this specific role. Name the role. Do not editorialize \
about why they're hiring - state the fact.
   - One sentence naming the SPECIFIC operational tension this role exists \
to solve - the mismatch between how training is typically built/delivered \
(desktop/computer-centered content, authored for people who sit at a desk) \
and the reality of a deskless, frontline workforce. This is a diagnostic \
insight, not a generic "you're rebuilding from scratch" line - it should \
read as "here's the real shape of the problem," not an assumption about \
why they're hiring.
   - The failure modes, chained causally rather than listed flatly: content \
is boring/dated (a light aside like "no offence" is fine, keeps the tone \
human) AND it's front-loaded early (day one, first few days) - and THEREFORE \
either completion is low, or retention is low even when completion isn't. \
Show the cause leading to the effect, don't just list symptoms.
   - One sentence naming the REAL downstream stakes of that failure - \
workplace injuries, quality problems, compliance violations. This is \
allowed and expected here, same as the OSHA email: the goal is honest, \
concrete "sell the problem" copy. What's NOT allowed is implying the act \
of hiring for this role itself means the company is currently failing or \
behind - the stakes are a general truth about what bad frontline training \
causes, not an accusation aimed at this specific prospect.
   - ONE sentence on Bites as the answer, framed around fixing/transforming \
their EXISTING training (right format, right time, right channel - a \
parallel three-part structure), not "equipping whoever gets hired." The \
prospect may not have made the hire yet; don't write as if a Bites-shaped \
gap will get filled by a specific new employee.
   - Introduce the attached video simply and personally ("I put together a \
{company}-branded training video example") - no elaborate justification \
needed, don't over-explain why it exists. The video is branded to the \
prospect's own company. End this sentence with the literal placeholder text \
INSERT VIDEO HERE.
   - State the proof points plainly (prefer both Unilever's 90%+ engagement \
and the 67% faster onboarding stat if they both fit) - a flat statement of \
fact, not "happy to walk through how" tacked onto the same sentence.
   - Close with a short, separate final beat: one line connecting back to \
the hiring signal (e.g. framing the offer as something their next hire \
would want), then a short direct QUESTION as the call to action (e.g. \
"Open to seeing more?"). Always end on a question, not a flat statement.
   - No sign-off line ("Best," / a name) - the SDR's own signature block is \
added separately, outside this draft.

5. TONE: peer-to-peer, calm, specific. No exclamation points. No hype \
adjectives. The opening/trigger framing should never imply the company is \
currently failing or embarrassingly behind just because they're hiring for \
this role - but naming the real, general stakes of bad frontline training \
(rule 4's stakes beat) is not the same thing as accusing this prospect, \
and should not be softened away.

6. Do not invent facts. Use only the supplied signal details (company, \
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
