from __future__ import annotations

from datetime import date, timedelta

from pipeline.osha_client import BASE_URL, industry_search, inspection_detail

RESTAURANT_NAICS = ["722511", "722513", "722515"]

# Fires immediately, no outcome needed - see docs/signal_first_architecture.md.
INSPECTION_TRIGGER_TYPES = {"Complaint", "Accident", "Fat/Cat"}

# Zero-padded 1910.xxxx section numbers with a training-abatement component.
# Only matches federal standards - see _federal_section.
TRAINING_LINKED_SECTIONS = {
    "1200": "Hazard Communication",
    "0132": "PPE program/training",
    "1030": "Bloodborne Pathogens",
    "0147": "Lockout/Tagout",
    "0038": "Emergency Action Plan",
    "0157": "Fire Safety",
    "0212": "Machine Guarding",
}


def _federal_section(standard_cited: str) -> str | None:
    """Extracts the 1910.xxxx section from a 'Standard Cited' value like
    '19100147 A' -> '0147'.

    Returns None for state-plan citations (e.g. California Cal/OSHA's
    '3203(A)' or '43000032 A'), which use their own numbering and don't match
    this pattern at all - confirmed live against a CA (Monrovia District
    Office) inspection. This filter can only recognize federal-standard
    citations; state-plan citations still get a chance to match via the
    Willful/Repeat/FTA classification check below.
    """
    token = standard_cited.split()[0] if standard_cited.split() else ""
    if len(token) >= 8 and token[:4] == "1910" and token[:8].isdigit():
        return token[4:8]
    return None


def is_relevant_violation(item: dict) -> tuple[bool, str | None]:
    """Applies the Violation relevance filter from
    docs/signal_first_architecture.md. Returns (is_relevant, reason).

    Failure-to-Abate isn't exposed as its own classification on this data
    source (osha.gov/ords/imis) - only an "FTA Penalty" amount per citation
    line item. A nonzero FTA penalty means an FTA follow-up was actually
    issued against that citation, so it's used as the FTA signal.
    """
    section = _federal_section(item["standard_cited"])
    if section in TRAINING_LINKED_SECTIONS:
        return True, f"standard 1910.{section} ({TRAINING_LINKED_SECTIONS[section]})"
    if item["citation_type"] in {"Willful", "Repeat"}:
        return True, item["citation_type"]
    if item["fta_penalty"] > 0:
        return True, "Failure-to-Abate"
    return False, None


def scan_inspections(window_days: int = 100, today: date | None = None) -> list[dict]:
    """Inspection trigger: any new Complaint/Accident/Fat-Cat inspection in the
    trailing window, across all three restaurant NAICS codes. Fires off the
    listing row alone - no detail-page call needed, per the architecture doc.
    """
    today = today or date.today()
    start = today - timedelta(days=window_days)

    seen_activity_nrs = set()
    signals = []
    for naics in RESTAURANT_NAICS:
        for row in industry_search(naics, start, today):
            if row["insp_type"] not in INSPECTION_TRIGGER_TYPES:
                continue
            if row["activity_nr"] in seen_activity_nrs:
                continue
            seen_activity_nrs.add(row["activity_nr"])
            signals.append(
                {
                    "signal_type": "Inspection",
                    "insp_subtype": row["insp_type"],
                    "activity_nr": row["activity_nr"],
                    "establishment_name": row["establishment_name"],
                    "state": row["state"],
                    "naics": row["naics"],
                    "open_date": row["date_opened"],
                    "is_open": row["is_open"],
                    "source_url": f"{BASE_URL}/establishment.inspection_detail?id={row['activity_nr']}",
                }
            )
    return signals


def scan_violations(window_days: int = 100, today: date | None = None) -> list[dict]:
    """Violation trigger: checked across ALL inspection types (not just the
    Inspection-trigger three), since a citation can result from any inspection
    type. Listing rows are pre-filtered to violations_count > 0 to avoid a
    detail-page call per inspection; only citation line items that pass
    is_relevant_violation become signals.
    """
    today = today or date.today()
    start = today - timedelta(days=window_days)

    seen_citations = set()
    signals = []
    for naics in RESTAURANT_NAICS:
        for row in industry_search(naics, start, today):
            if row["violations_count"] == 0:
                continue
            detail = inspection_detail(row["activity_nr"])
            for item in detail["violations"]:
                key = (row["activity_nr"], item["citation_id"])
                if key in seen_citations:
                    continue
                relevant, reason = is_relevant_violation(item)
                if not relevant:
                    continue
                seen_citations.add(key)
                signals.append(
                    {
                        "signal_type": "Violation",
                        "activity_nr": row["activity_nr"],
                        "citation_id": item["citation_id"],
                        "establishment_name": row["establishment_name"],
                        "state": row["state"],
                        "naics": row["naics"],
                        "opening_insp_type": row["insp_type"],
                        "standard_cited": item["standard_cited"],
                        "citation_type": item["citation_type"],
                        "issuance_date": item["issuance_date"],
                        "current_penalty": item["current_penalty"],
                        "relevance_reason": reason,
                        "source_url": (
                            f"{BASE_URL}/establishment.violation_detail"
                            f"?id={row['activity_nr']}&citation_id={item['citation_id']}"
                        ),
                    }
                )
    return signals
