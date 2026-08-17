from __future__ import annotations

from datetime import date

from pipeline.accounts_seed import history_is_complete
from pipeline.brand_history import year_summary
from pipeline.hubspot_client import create_note, upsert_qsr_signal, upsert_signal_company
from pipeline.osha_client import violation_narrative
from pipeline.company_names import brand_name
from pipeline.site_count import lookup_site_count
from pipeline.slack_client import CHANNELS, post_message
from pipeline.tiering import tier_for_lookup

# Real contact resolution needs Amplemarket (Task #4, not yet unblocked) -
# this is shown honestly rather than faked. See HANDOFF.md.
SUGGESTED_CONTACT_PLACEHOLDER = "Pending — contact resolution not yet wired up (Task #4, blocked on Amplemarket)"


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
        data = summary.get(year, {"count": 0, "total_penalty": 0.0})
        lines.append(("📊", label,
                      f"{data['count']}{suffix} inspection(s), "
                      f"${data['total_penalty']:,.0f}{suffix} in fines"))
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


def handle_signal(signal: dict) -> dict:
    """Fires the qsr_signal object + Company Note + Slack alert together for
    one real signal, per docs/signal_first_architecture.md step 5. All three
    fire for every signal, including Fat/Cat - the only Fat/Cat-specific
    behavior is the returned sequence_eligible flag, which a future Task #7
    workflow would gate sequence enrollment on (no sequence exists yet to
    actually enroll into).
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
    return {
        "company_id": company_id,
        "tier": tier,
        "sequence_eligible": not is_fat_cat,
    }
