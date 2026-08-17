"""Turning OSHA establishment names into brand-level account names.

Adapted from the prior Bites assignment's `osha_signal/company_names.py`
(see `Assignment 1/`), which solved the same problem against the same data
source. Ported deliberately rather than rewritten: the rules below were
derived from real OSHA name artefacts and re-verified against this
project's own live data (258 real restaurant-NAICS establishment names
scanned 2026-08-17).

What OSHA's estab_name actually looks like, from our own scan:

    '111589 - Chipotle Mexican Grill Inc'        inspector case number
    'Cpx2026xtp177x0013 - Hz Ops Holdings...'    state activity number
    'Warmel Management Co Dba Mcdonalds'         franchisee legal name + DBA
    "Mcdonald'S #5125"                           store number
    'Encanto Restaurants, Inc.' / 'Inc'          punctuation variants

Measured on those 258 names: 35 (13.6%) carry case-number prefixes,
9 carry a DBA, 6 carry site suffixes.

DELIBERATE DECISION - the account is the BRAND, not the operator.
'Ayvaz Pizza Llc Dba Pizza Hut' becomes "Pizza Hut", not "Ayvaz Pizza LLC".
This collapses franchisees into their brand so a rep sees one Pizza Hut
account with the full brand-wide story, rather than one account per
franchisee. The tradeoff was raised explicitly and accepted: large
franchise operators are often the party that actually employs the staff,
runs training, and signs a contract, so brand-only collapsing can point
outreach at a corporate entity that neither operates the cited location
nor buys the training. Revisit if outreach reply data suggests it.

Names carrying no brand token at all ('Carolina Restaurant Group Inc',
'Guernsey Holdings Sdi Id Opco Llc') have nothing to collapse to and
necessarily remain under the operator's name.
"""
from __future__ import annotations

import re

# True acronyms: always uppercase, in any position.
_ACRONYMS = {
    "LLC", "LP", "LLP", "PLC", "USA", "US", "DBA", "BBQ", "QSR", "II", "III", "IV",
}

# State abbreviations appear inside establishment names, but many collide
# with ordinary words ('LA Madeleine', 'Fogo DE Chão', 'Lixioy OR Inc').
# Only uppercased when NOT the leading token, so a name that merely starts
# with one of these keeps its normal casing.
_STATE_ABBR = {
    "NY", "NJ", "CA", "TX", "FL", "OH", "PA", "IL", "MI", "GA", "NC", "VA",
    "WA", "MA", "TN", "IN", "MO", "MD", "WI", "MN", "CO", "AL", "SC", "LA",
    "KY", "OR", "OK", "CT", "IA", "MS", "AR", "KS", "UT", "NV", "NM", "NE",
    "WV", "ID", "HI", "ME", "NH", "RI", "MT", "DE", "SD", "ND", "AK", "VT",
    "WY", "PR", "DC",
}

_SUFFIX_FORM = {
    "INC": "Inc.", "INC.": "Inc.", "INCORPORATED": "Inc.",
    "CORP": "Corp.", "CORP.": "Corp.", "CORPORATION": "Corporation",
    "CO": "Co.", "CO.": "Co.", "COMPANY": "Company",
    "LTD": "Ltd.", "LTD.": "Ltd.",
}

_KEEP_LOWER = {"of", "and", "the", "for", "at", "in", "on", "de", "del", "la"}

# Legal-entity tokens dropped from the MATCHING key (not from display).
_NAME_SUFFIX_TOKENS = {
    "INC", "INCORPORATED", "LLC", "LP", "LLP", "CORP", "CORPORATION",
    "CO", "COMPANY", "LTD", "PLC", "THE",
}

# Leading inspector case/activity numbers: '110643 - ', 'WA317992176 - ',
# 'Cpx2026xak176x0009 - '. Alphanumeric run followed by a dash.
_CASE_PREFIX = re.compile(r"^[A-Z0-9][A-Z0-9\-]{3,}\s+-\s+", re.I)

# Site suffixes - a store number describes WHERE the citation happened,
# which belongs on the signal, not in the company name.
_SITE_SUFFIX = re.compile(
    r"[,\s\-]+("
    r"store\s*(no\.?|number|#)?\s*\d+"
    r"|#\s*\d+"
    r"|plant\s*(no\.?|#)?\s*\d+"
    r"|facility\s*(no\.?|#)?\s*\d+"
    r"|unit\s*(no\.?|#)?\s*\d+"
    r"|branch\s*(no\.?|#)?\s*\d+"
    r"|location\s*(no\.?|#)?\s*\d+"
    r"|restaurant\s*(no\.?|#)?\s*\d+"
    r")\s*$",
    re.I,
)

# A bare trailing number, e.g. 'Burger King 6046' (a real case from our
# scan, which the keyword/# patterns above miss). Requires 3+ digits so
# genuine names keep theirs - 'Cafe 21', 'Taco 5', '3 Brothers' are all
# unaffected.
_BARE_STORE_NUMBER = re.compile(r"[,\s\-]+\d{3,}\s*$")


def _title_token(token: str, first: bool) -> str:
    trailing = ""
    while token and token[-1] in ",;":
        trailing = token[-1] + trailing
        token = token[:-1]

    upper = token.upper()
    bare = token.strip(".")

    if token.count(".") >= 2:  # dotted acronyms (U.S.A.) stay as written
        return upper + trailing
    if upper in _SUFFIX_FORM:
        return _SUFFIX_FORM[upper] + trailing
    if bare.upper() in _ACRONYMS:
        return bare.upper() + token[len(bare):] + trailing
    # Particles beat state abbreviations mid-name ('Fogo de Chão', not
    # 'Fogo DE Chão'), and neither applies to the leading token.
    if not first and bare.lower() in _KEEP_LOWER:
        return bare.lower() + token[len(bare):] + trailing
    if not first and bare.upper() in _STATE_ABBR:
        return bare.upper() + token[len(bare):] + trailing

    return _cap_word(bare) + token[len(bare):] + trailing


def _cap_word(bare: str) -> str:
    """MCDONALD'S -> McDonald's, IN-N-OUT -> In-N-Out, O'BRIEN -> O'Brien.

    Hyphen parts are capitalised independently, and the Mc/Mac rule is
    applied before the apostrophe split - checking apostrophes first
    yields "Mcdonald's", which looks wrong on a CRM record.
    """
    if "-" in bare and len(bare) > 2:
        return "-".join(_cap_word(part) if part else "" for part in bare.split("-"))

    upper = bare.upper()
    if upper.startswith("MC") and len(bare) > 3:
        return "Mc" + _cap_word(bare[2:])
    if upper.startswith("MAC") and len(bare) > 4:
        return "Mac" + _cap_word(bare[3:])
    if "'" in bare and len(bare) > 2:
        head, _, tail = bare.partition("'")
        return head.capitalize() + "'" + (tail.capitalize() if len(tail) > 1 else tail.lower())
    return bare.capitalize()


def brand_name(raw: str) -> str:
    """The brand-level account name a rep would actually say out loud."""
    if not raw:
        return ""

    name = _CASE_PREFIX.sub("", raw.strip()).strip()

    # Prefer the trading name when a DBA is present - this is the
    # franchisee -> brand collapse.
    dba = re.search(r"\bD/?B/?A\b\s*(.+)$", name, re.I)
    if dba and dba.group(1).strip():
        name = dba.group(1).strip()

    # Applied repeatedly for names carrying more than one ('Store 12 #4').
    for _ in range(3):
        stripped = _SITE_SUFFIX.sub("", name).strip(" ,-")
        stripped = _BARE_STORE_NUMBER.sub("", stripped).strip(" ,-")
        if stripped == name:
            break
        name = stripped

    if name.isupper() or name.islower() or name.istitle():
        tokens = name.split()
        name = " ".join(_title_token(t, i == 0) for i, t in enumerate(tokens))

    return name.strip(" ,-")


def match_key(raw: str) -> str:
    """Dedup/matching key: brand name, uppercased, punctuation and
    legal-suffix tokens dropped, so 'Encanto Restaurants Inc',
    'Encanto Restaurants, Inc.' and 'Encanto Restaurants Inc.' are one
    account rather than three."""
    name = brand_name(raw)
    tokens = "".join(c if c.isalnum() else " " for c in name.upper()).split()
    return " ".join(t for t in tokens if t not in _NAME_SUFFIX_TOKENS)
