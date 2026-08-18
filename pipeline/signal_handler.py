from __future__ import annotations

import os
from datetime import date

from pipeline.accounts_seed import history_is_complete
from pipeline.brand_history import year_summary
from pipeline.hubspot_client import (
    NOTE_TO_CONTACT,
    create_note,
    enroll_in_sequence,
    upsert_qsr_signal,
    upsert_signal_company,
)
from pipeline.osha_client import violation_narrative
from pipeline.company_names import brand_name
from pipeline.personalize import draft_first_touch
from pipeline.site_count import lookup_site_count
from pipeline.slack_client import CHANNELS, post_message
from pipeline.tiering import tier_for_lookup

# Real contact resolution needs Amplemarket (Task #4, not yet unblocked) -
# this is shown honestly rather than faked. See HANDOFF.md.
SUGGESTED_CONTACT_PLACEHOLDER = "Pending — contact resolution not yet wired up (Task #4, blocked on Amplemarket)"

# Sequence enrollment (Task #7 for Tier 3, Task #8 for Tier 1) needs a
# sequence created once by a human in the HubSpot UI (no public
# create-sequence endpoint - see docs/task7_workflow_notes.md) plus a
# connected sender inbox. All unset until that setup happens; enrollment is
# skipped cleanly until then, same pattern as the Rung 5 ANTHROPIC_API_KEY
# gate.
TIER3_SEQUENCE_ID = os.environ.get("HUBSPOT_TIER3_SEQUENCE_ID")
TIER1_SEQUENCE_ID = os.environ.get("HUBSPOT_TIER1_SEQUENCE_ID")
SEQUENCE_SENDER_EMAIL = os.environ.get("HUBSPOT_SENDER_EMAIL")
SEQUENCE_SENDER_USER_ID = os.environ.get("HUBSPOT_SENDER_USER_ID")

# Separate from TIER3_SEQUENCE_ID - that sequence is named "QSR T3 - OSHA
# Trigger" (see HANDOFF.md), so its copy assumes an OSHA context and isn't
# right to auto-enroll a Hiring-triggered contact into. A human creates this
# one the same way they created the OSHA sequences (no create-sequence API -
# see docs/task7_workflow_notes.md); unset until then, skipped cleanly.
HIRING_TIER3_SEQUENCE_ID = os.environ.get("HUBSPOT_HIRING_TIER3_SEQUENCE_ID")


def _signal_subtype(signal: dict) -> str:
    """The granular type for the qsr_signal record and templates - Complaint/
    Accident/Fat-Cat for an Inspection signal, or Violation."""
    return signal["insp_subtype"] if signal["signal_type"] == "Inspection" else "Violation"


def _signal_date(signal: dict):
    return signal["open_date"] if signal["signal_type"] == "Inspection" else signal["issuance_date"]


def _severity(signal: dict) -> str | None:
    return signal.get("citation_type")  # only Violation signals carry this


def _penalty(signal: dict) -> float | None:
    return signal.get("current_penalty")  # only Violation signals carry this


def _event_text(signal: dict) -> str:
    """The real, specific "what happened" text where OSHA's public data
    actually has one.

    Violation: the citation's own hazard narrative when the citation is
    federal (pulled live from establishment.violation_detail's "Text For
    Citation" section) - real, specific text like "Exit access(es) were not
    at least 28 inches wide ... Stewarding Kitchen: a path ... measured 26
    inches." State-plan citations don't carry this section at all (confirmed
    live), so those fall back to standard + classification.

    Inspection: there genuinely is no narrative available - a Complaint/
    Accident/Fat-Cat trigger fires before any citation exists, and OSHA
    doesn't publish complaint narratives (source-protection for whoever
    reported it). Rather than invent a description, this says what's
    actually known: the inspection type and its current case status.
    """
    if signal["signal_type"] == "Violation":
        narrative = violation_narrative(signal["activity_nr"], signal["citation_id"])
        if narrative:
            return narrative
        return (
            f"Standard {signal['standard_cited']} cited - {signal['citation_type']} "
            f"classification (detailed hazard text not published for this citation)."
        )
    return (
        f"{signal['insp_subtype']} inspection opened at {signal['establishment_name']} "
        f"({signal['state']}) - {'still open, ' if signal['is_open'] else 'closed, '}"
        f"no citation on record yet as of this alert."
    )


def _history_lines(brand_candidate: str) -> list[tuple[str, str, str]]:
    """Brand-wide inspection/fine history by year.

    These are FLOORS, not totals, and are labelled as such. OSHA has no
    brand field, so year_summary() can only find locations whose
    establishment name contains the brand string. Locations inspected under
    a franchisee's own legal name are invisible to it - 'Carrols Llc'
    (~1,000 Burger Kings) and 'Sizzling Platter, Llc' (hundreds of Little
    Caesars) both appear in OSHA with no brand in the name, verified live.
    Pizza Hut, a ~6,400-location chain, returns only 12 inspections across
    2.5 years this way.

    A rep quoting these to a prospect must not state them as totals, hence
    the "+" and the caveat line. Closing the gap for real needs
    establishment-name -> brand resolution across a full historical scan;
    see docs/brand_history_gap.md.
    """
    today = date.today()
    summary = year_summary(brand_candidate, today)

    # A near-entirely company-owned brand has no franchisees operating under
    # their own legal names, so the name-based search finds essentially every
    # location and the figures are real totals. Chipotle (100% company-owned)
    # is the clearest case. Anything else - including brands we have no
    # ownership data for - is reported as a floor.
    complete = history_is_complete(brand_candidate)
    suffix = "" if complete else "+"

    lines = []
    for offset, label in [(0, f"Year to date ({today.year})"), (1, str(today.year - 1)), (2, str(today.year - 2))]:
        year = today.year - offset
        data = summary.get(year, {"count": 0, "violation_count": 0,
                                   "training_violation_count": 0, "total_penalty": 0.0})
        training_note = (
            f", {data['training_violation_count']}{suffix} training-related"
            if data["violation_count"] > 0 else ""
        )
        lines.append(("📊", label,
                      f"{data['count']}{suffix} inspection(s), "
                      f"{data['violation_count']}{suffix} citation(s)"
                      f"{training_note}, ${data['total_penalty']:,.0f}{suffix} in fines"))
    if not complete:
        lines.append((
            "ℹ️", "History caveat",
            f'Counts OSHA records naming "{brand_candidate}". Locations inspected under a '
            "franchisee's own legal name are not included, so these are floors, not totals.",
        ))
    return lines


def _build_lines(signal: dict, tier: str, lookup: dict, account_name: str) -> list[tuple[str, str, str]]:
    subtype = _signal_subtype(signal)
    lines = [
        ("🏢", "Company", account_name),
        ("🚨", "Signal", subtype),
        ("📅", "When", str(_signal_date(signal))),
    ]
    if signal["signal_type"] == "Violation":
        penalty = _penalty(signal)
        lines.append(("💰", "Penalty", f"${penalty:,.0f}" if penalty else "$0"))
        lines.append(("⚠️", "Severity", _severity(signal) or "n/a"))
    lines.append(("📝", "Event" if signal["signal_type"] == "Violation" else "Details", _event_text(signal)))

    # History is brand-wide across every location nationally, keyed on the
    # same collapsed brand the account uses.
    lines.extend(_history_lines(account_name))

    # Where the collapse actually changed the name, show the raw OSHA
    # establishment string too - a rep needs to know which site was cited,
    # and that detail is otherwise lost by design.
    if account_name != signal["establishment_name"]:
        lines.append(("📍", "Cited as", f"{signal['establishment_name']} ({signal['state']})"))

    lines.append(("🏷️", "Tier", tier))
    lines.append(("👤", "Suggested Contact", SUGGESTED_CONTACT_PLACEHOLDER))
    lines.append(("🔗", "Source", signal["source_url"]))
    return lines


def _render_slack(lines: list[tuple[str, str, str]]) -> str:
    return "\n".join(f"{emoji} *{label}:* {value}" for emoji, label, value in lines)


def _render_note(lines: list[tuple[str, str, str]]) -> str:
    # No Company line - it's redundant on the company record it's attached to.
    filtered = [line for line in lines if line[1] != "Company"]
    rendered = []
    for emoji, label, value in filtered:
        if label == "Source":
            value = f'<a href="{value}">{value}</a>'
        rendered.append(f"{emoji} <strong>{label}:</strong> {value}")
    return "<br>".join(rendered)


def _maybe_enroll_in_sequence(tier: str | None, sequence_eligible: bool, contact_id: str | None) -> dict:
    """Tier 3, non-Fat/Cat signals auto-enroll their resolved contact into the
    Tier 3 to-do sequence - the one behavior Task #7 adds. Tier 1's
    enrollment is separate (_maybe_draft_and_note_first_touch) since it
    also has to draft and attach the personalized email first - "manual"
    for Tier 1 (per docs/signal_first_architecture.md) describes the AE
    sending the email personally, not the enrollment itself; the to-do task
    step in either sequence is harmless to auto-enroll into.

    No native HubSpot workflow object watches for qsr_signal creation and
    triggers this separately - this function IS that trigger. A workflow
    would only re-detect the object creation this same call performed a few
    lines up; that's redundant orchestration, not a capability gap. See
    docs/task7_workflow_notes.md for the fuller reasoning and the real API
    constraints (no public create-sequence endpoint; scopes not yet granted)
    that also fed this decision.

    Returns a status dict instead of enrolling silently or raising, since
    every real precondition here - a resolved contact, a configured
    sequence, a connected sender - is currently unmet and that must stay
    visible rather than fail quietly.
    """
    if tier != "Tier 3" or not sequence_eligible:
        return {"attempted": False, "reason": "not Tier 3 / not sequence-eligible"}
    if not contact_id:
        return {"attempted": False, "reason": "no resolved contact yet (Task #4, blocked on Amplemarket)"}
    if not (TIER3_SEQUENCE_ID and SEQUENCE_SENDER_EMAIL and SEQUENCE_SENDER_USER_ID):
        return {"attempted": False, "reason": "Tier 3 sequence not configured (see docs/task7_workflow_notes.md)"}

    enroll_in_sequence(contact_id, TIER3_SEQUENCE_ID, SEQUENCE_SENDER_EMAIL, SEQUENCE_SENDER_USER_ID)
    return {"attempted": True, "sequence_id": TIER3_SEQUENCE_ID}


def _render_note_body(subject: str, body: str) -> str:
    paragraphs = body.split("\n\n")
    return f"<strong>Subject:</strong> {subject}<br><br>" + "<br><br>".join(
        p.replace("\n", "<br>") for p in paragraphs
    )


def _maybe_draft_and_note_first_touch(
    signal: dict, account_name: str, tier: str | None, sequence_eligible: bool, contact: dict | None
) -> dict:
    """Tier 1, non-Fat/Cat signals get the one fully-drafted GTM motion
    (Task #8): a personalized first-touch email, written by
    pipeline/personalize.py:draft_first_touch() and attached as a Note on
    the resolved Contact - not the Company, since it's addressed to a
    specific person. The contact is then auto-enrolled in the Tier 1
    to-do sequence, whose task points the AE at that Note to review and
    send personally (see docs/task8_email_rules.md and the design
    discussion that led here - HubSpot sequences don't support per-contact
    custom step content, so a Note is where the draft actually lives).

    `contact` is {"id", "name", "title"} once Task #4 (resolve_contact)
    exists - None until then, in which case this is skipped and reported,
    same honesty pattern as _maybe_enroll_in_sequence.
    """
    if tier != "Tier 1" or not sequence_eligible:
        return {"attempted": False, "reason": "not Tier 1 / not sequence-eligible"}
    if not contact:
        return {"attempted": False, "reason": "no resolved contact yet (Task #4, blocked on Amplemarket)"}
    if not (TIER1_SEQUENCE_ID and SEQUENCE_SENDER_EMAIL and SEQUENCE_SENDER_USER_ID):
        return {"attempted": False, "reason": "Tier 1 sequence not configured (see docs/task8_email_rules.md)"}

    draft = draft_first_touch(signal, account_name, contact)
    create_note(contact["id"], _render_note_body(draft["subject"], draft["body"]), NOTE_TO_CONTACT)
    enroll_in_sequence(contact["id"], TIER1_SEQUENCE_ID, SEQUENCE_SENDER_EMAIL, SEQUENCE_SENDER_USER_ID)
    return {"attempted": True, "sequence_id": TIER1_SEQUENCE_ID, "draft_subject": draft["subject"]}


def handle_signal(signal: dict, contact: dict | None = None) -> dict:
    """Fires the qsr_signal object + Company Note + Slack alert together for
    one real signal, per docs/signal_first_architecture.md step 5. All three
    fire for every signal, including Fat/Cat - the only Fat/Cat-specific
    behavior is the returned sequence_eligible flag, which gates both Tier 3
    sequence enrollment (Task #7) and the Tier 1 drafted-email + enrollment
    (Task #8).

    `contact` is {"id", "name", "title"} once Task #4 (resolve_contact)
    lands - None until then, in which case both Tier 3 enrollment and the
    Tier 1 draft are skipped and reported honestly rather than faked.
    """
    lookup = lookup_site_count(signal["establishment_name"])
    tier = tier_for_lookup(lookup)

    # The account is the BRAND, not the cited location or the franchisee
    # operating it - so every McDonald's location rolls into one McDonald's
    # record. lookup["brand_name"] (Rung 1's canonical name, when it hit)
    # wins over the derived one; brand_name() collapses the rest.
    # See pipeline/company_names.py for the decision and its tradeoff.
    account_name = lookup["brand_name"] or brand_name(signal["establishment_name"])

    company = upsert_signal_company(
        account_name,
        lookup["domain"],
        {
            "bites_tier": tier,
            "site_count": lookup["value"],
            "disqualified": "false",
        },
    )
    company_id = company["id"]

    subtype = _signal_subtype(signal)
    signal_date = _signal_date(signal)
    qsr_signal_properties = {
        "signal_summary": f"{subtype} - {signal['establishment_name']} - {signal_date}",
        "signal_type": subtype,
        "signal_date": signal_date.isoformat(),
        "source_url": signal["source_url"],
        "severity": _severity(signal),
        "penalty_amount": _penalty(signal),
        "description": _event_text(signal),
        "source_activity_nr": signal["activity_nr"],
        "source_citation_id": signal.get("citation_id"),
    }
    upsert_qsr_signal(company_id, qsr_signal_properties)

    lines = _build_lines(signal, tier, lookup, account_name)
    post_message(
        CHANNELS["osha_inspections" if signal["signal_type"] == "Inspection" else "osha_violations"],
        _render_slack(lines),
    )
    create_note(company_id, _render_note(lines))

    is_fat_cat = subtype == "Fat/Cat"
    sequence_eligible = not is_fat_cat
    contact_id = contact["id"] if contact else None
    enrollment = _maybe_enroll_in_sequence(tier, sequence_eligible, contact_id)
    first_touch = _maybe_draft_and_note_first_touch(signal, account_name, tier, sequence_eligible, contact)
    return {
        "company_id": company_id,
        "tier": tier,
        "sequence_eligible": sequence_eligible,
        "sequence_enrollment": enrollment,
        "tier1_first_touch": first_touch,
    }


def _build_hiring_lines(signal: dict, tier: str | None) -> list[tuple[str, str, str]]:
    lines = [
        ("🏢", "Company", signal["establishment_name"]),
        ("🚨", "Signal", "Hiring"),
        ("📅", "Posted", str(signal["posted_date"]) if signal["posted_date"] else "unknown"),
        ("💼", "Role", signal["job_title"]),
    ]
    if signal.get("team"):
        lines.append(("🧭", "Team", signal["team"]))
    if signal.get("location"):
        lines.append(("📍", "Location", signal["location"]))
    lines.append(("🏷️", "Tier", tier))
    lines.append(("👤", "Suggested Contact", SUGGESTED_CONTACT_PLACEHOLDER))
    lines.append(("🔗", "Source", signal["source_url"]))
    return lines


def _maybe_enroll_hiring_tier3(tier: str | None, contact_id: str | None) -> dict:
    """Hiring's own Tier 3 gate - same shape as _maybe_enroll_in_sequence but
    against HIRING_TIER3_SEQUENCE_ID, since the OSHA Tier 3 sequence's copy
    doesn't fit a Hiring trigger. Hiring has no Fat/Cat-equivalent exclusion,
    so tier is the only gate."""
    if tier != "Tier 3":
        return {"attempted": False, "reason": "not Tier 3"}
    if not contact_id:
        return {"attempted": False, "reason": "no resolved contact yet (Task #4, blocked on Amplemarket)"}
    if not (HIRING_TIER3_SEQUENCE_ID and SEQUENCE_SENDER_EMAIL and SEQUENCE_SENDER_USER_ID):
        return {"attempted": False, "reason": "Hiring Tier 3 sequence not configured (see docs/hiring_signal_scope.md)"}

    enroll_in_sequence(contact_id, HIRING_TIER3_SEQUENCE_ID, SEQUENCE_SENDER_EMAIL, SEQUENCE_SENDER_USER_ID)
    return {"attempted": True, "sequence_id": HIRING_TIER3_SEQUENCE_ID}


def handle_hiring_signal(signal: dict, contact: dict | None = None) -> dict:
    """Hiring's counterpart to handle_signal() - kept as a separate function
    rather than branching handle_signal() itself, since the two signal
    shapes only share the site_count/tiering/company-upsert/qsr_signal/Slack/
    Note steps, not the OSHA-specific ones (brand collapsing, brand-wide
    history, violation narrative). See docs/hiring_signal_scope.md.

    Tier 1 personalized first-touch (Task #8's Hiring equivalent) isn't
    built this session - copy rules need their own design pass the way
    docs/task8_email_rules.md got for OSHA, not a rushed reuse of OSHA's
    citation-framed copy. Reported honestly as not-yet-built, same pattern
    as the contact-resolution gaps above.
    """
    # ATS board names come from pipeline/hiring_seed.py's hand-verified
    # list, already the canonical brand name - unlike OSHA's establishment
    # strings, there's no franchisee-legal-name noise to collapse.
    account_name = signal["establishment_name"]
    lookup = lookup_site_count(account_name)
    tier = tier_for_lookup(lookup)
    domain = lookup["domain"] or signal["domain"]

    company = upsert_signal_company(
        account_name,
        domain,
        {
            "bites_tier": tier,
            "site_count": lookup["value"],
            "disqualified": "false",
        },
    )
    company_id = company["id"]

    qsr_signal_properties = {
        "signal_summary": f"Hiring - {signal['job_title']} - {account_name}",
        "signal_type": "Hiring",
        "signal_date": (signal["posted_date"] or date.today()).isoformat(),
        "source_url": signal["source_url"],
        "severity": None,
        "penalty_amount": None,
        "description": f"{signal['job_title']} posted"
        + (f" ({signal['team']})" if signal.get("team") else "")
        + (f", {signal['location']}" if signal.get("location") else ""),
        # Reuses the OSHA-named source_activity_nr/source_citation_id pair
        # for idempotent dedup (find_qsr_signal/upsert_qsr_signal, see
        # pipeline/hubspot_client.py) rather than adding a schema migration
        # for one new field - "{ats_source}:{posting_id}" is a unique key
        # the same way an OSHA activity_nr is. Known naming debt, same
        # precedent as leaving the unused governance_model property alone.
        "source_activity_nr": f"{signal['ats_source']}:{signal['posting_id']}",
        "source_citation_id": None,
    }
    upsert_qsr_signal(company_id, qsr_signal_properties)

    lines = _build_hiring_lines(signal, tier)
    post_message(CHANNELS["hiring_signals"], _render_slack(lines))
    create_note(company_id, _render_note(lines))

    contact_id = contact["id"] if contact else None
    enrollment = _maybe_enroll_hiring_tier3(tier, contact_id)
    return {
        "company_id": company_id,
        "tier": tier,
        "sequence_eligible": True,
        "sequence_enrollment": enrollment,
        "tier1_first_touch": {"attempted": False, "reason": "Hiring Tier 1 copy rules not yet designed"},
    }
