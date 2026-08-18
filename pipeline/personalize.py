"""Task #8 - the one fully-drafted GTM motion: a Tier 1 personalized
first-touch email, tied to a real OSHA signal.

Adapted from Assignment 1's osha_signal/personalize.py - the prompt is the
proprietary asset here, not the LLM call. See docs/task8_email_rules.md for
what changed from that version and why (Fat/Cat excluded upstream rather
than tone-softened, a citation-less opening for Complaint/Accident signals,
a required video reference, and the finalized reference draft this prompt
is measured against).
"""
from __future__ import annotations

# Durable Bites facts, not scoped to any one account or assignment - reused
# verbatim from Assignment 1.
FRONTLINE_TRAINING_FAILURE_MODES = [
    "timing: training is front-loaded onto day one and then never revisited",
    "completion: it simply doesn't get done",
    "channel: it lands in an email address frontline staff never check",
    "content: it's boring, outdated, and not useful in the moment it's needed",
]

PROOF_POINTS = [
    "Unilever reached 90%+ training engagement with Bites",
    "67% faster new-hire onboarding",
]

# Claude Sonnet 5, not Haiku - the opposite tradeoff from Rung 5
# (pipeline/tier_classifier.py). Rung 5 is a coarse classification task run
# hundreds of times, where cost dominates. This runs once and its entire
# output IS the deliverable a prospect reads - copywriting quality, not
# cost, is what matters here.
MODEL = "claude-sonnet-5"

# The approved reference output - the standard every generated draft is
# measured against. Finalized 2026-08-18; generic, no real account. Defined
# here (not lower in the file) because SYSTEM_PROMPT embeds it directly as a
# worked example - a concrete anchor for length and register did more to
# keep generated drafts on-spec than the word-count rule alone (verified:
# without it, drafts ran 155-165 words despite an explicit "140 words, hard
# ceiling, count before finishing" instruction).
REFERENCE_DRAFT = {
    "subject": "OSHA complaint at your Ohio location",
    "body": """Hi Alex,

I saw OSHA opened a complaint inspection at your Ohio location last month.

Even before any citation is decided, that puts training documentation on record.

The challenge we see with training is that it's often not completed. It's usually boring (no offence). It's mostly front-loaded on day one and never revisited. Plus it lands in an email account front-line staff never check.

Bites redesigned training to address those gaps. Your training modules become short on-brand videos they'll actually watch exactly when they need it. That helps ensure complaints and accidents decline, and they don't become violations.

I had our team put together a 90-second {company} branded video on what that would look like for you: INSERT VIDEO HERE

We've helped Unilever reach 90%+ training engagement and I'd be happy to walk through how.""",
}

SYSTEM_PROMPT = """You draft a cold first-touch email for a Bites SDR, for a Tier 1 QSR \
account that just had a real OSHA signal fire.

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
   - Open with the specific, verifiable signal in one plain sentence. If a \
citation was actually issued, open on it directly (what standard, roughly \
when). If not - a Complaint or Accident inspection was opened but no \
citation exists yet, which is the more common case - open on the \
inspection itself, not an invented citation.
   - One sentence on what that practically means for the person receiving \
the email (scrutiny, documentation now on record), calibrated to what's \
actually true - don't claim a citation's worth of certainty for a still-open \
inspection.
   - Name the real training failure modes: not completed, boring/outdated \
content, poor timing, sent to inboxes frontline staff don't check. This is \
the heart of the email.
   - ONE to two sentences on Bites as the answer to those failures, framed \
as meeting the team where they are with training they'll actually use when \
they need it - and tie it back to the signal type: this is what keeps a \
complaint or accident from becoming a violation.
   - Introduce the attached video with a specific reason tied to the \
failure mode you just named - never drop the placeholder cold with no \
explanation. The video is branded to the prospect's own company. End this \
sentence with the literal placeholder text INSERT VIDEO HERE.
   - Close with an offer to show a named peer outcome (prefer Unilever's \
90%+ engagement) tied to reducing OSHA exposure.
   - No sign-off line ("Best," / a name). End on the closing offer sentence \
- the SDR's own signature block is added separately, outside this draft.

4. TONE: peer-to-peer, calm, specific. No exclamation points. No hype \
adjectives. Never sensationalize the signal. Never surface OSHA's internal \
case/report number - it means nothing to the reader. A cited standard \
number (e.g. 1910.147) is fine to name; a bare case ID is not.

5. NEVER include the account's repeat-offender / brand-wide history in the \
email body. It is internal SDR context for urgency, not something to \
confront a prospect with.

6. Do not invent facts. Use only the supplied signal details, company \
facts, and the approved proof points. Never draft this for a Fat/Cat \
signal - if one reaches you, that is a caller error, not something to \
soften tone for.

EXAMPLE OF THE RIGHT LENGTH, STRUCTURE, AND REGISTER (generic placeholder \
account - match this closely, do not exceed its length by more than a \
handful of words):

Subject: """ + REFERENCE_DRAFT["subject"] + """

""" + REFERENCE_DRAFT["body"] + """
"""


def build_user_prompt(signal: dict, account_name: str, contact: dict) -> str:
    """Assembles the data the model is allowed to use.

    `signal` is the same dict shape pipeline/signal_handler.py consumes -
    an Inspection signal (insp_subtype, open_date, is_open) or a Violation
    signal (standard_cited, citation_type, current_penalty, issuance_date).
    """
    is_violation = signal["signal_type"] == "Violation"
    return f"""Draft the first touch.

CONTACT: {contact['name']}, {contact['title']}
COMPANY: {account_name}
SIGNAL TYPE: {"Violation" if is_violation else signal["insp_subtype"]}
CITATION ISSUED: {"Yes - " + signal["standard_cited"] + ", " + signal["citation_type"] if is_violation else "No - inspection only, no citation on record yet"}
DATE: {signal["issuance_date"] if is_violation else signal["open_date"]}
LOCATION: {signal["establishment_name"]} ({signal["state"]})
APPROVED PROOF POINTS: {PROOF_POINTS[0]}
"""


def draft_first_touch(signal: dict, account_name: str, contact: dict) -> dict:
    """Calls Claude to draft the email. Returns {"subject": ..., "body": ...}.

    Raises if called on a Fat/Cat signal - see rule 6. That's a caller bug
    (Fat/Cat is already excluded from sequence enrollment everywhere else in
    this pipeline, see pipeline/signal_handler.py), not something this
    function should silently paper over.
    """
    if signal.get("insp_subtype") == "Fat/Cat":
        raise ValueError("draft_first_touch() must never be called on a Fat/Cat signal")

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
