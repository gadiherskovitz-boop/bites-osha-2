"""Known Greenhouse/Lever board tokens for QSR/fast-casual brands.

Neither API offers a "search all companies" endpoint (confirmed live,
2026-08-18 - see docs/hiring_signal_scope.md), so unlike the OSHA path's
global NAICS scan, this scanner can only ever see companies whose board
token is already known here. This list is that discovery step, done by
hand - the direct analog of accounts_seed.py's role for Rung 1 of the
site_count waterfall, and the same kind of "highest-leverage next step" to
expand over time.

Verified live 2026-08-18: tried ~90 slug guesses (every brand in
accounts_seed.py's QSR50/Contenders list, plus ~60 younger fast-casual/
coffee/bakery chains, on both APIs, with common slug variants). Only 4 real
boards found - none of them among the large legacy chains (McDonald's,
Starbucks, Wendy's, Domino's, etc. all 404 on both APIs), all among newer,
VC-backed, tech-forward chains. This is a real finding, not a sampling gap:
large QSR operators overwhelmingly run enterprise ATS (Workday, iCIMS,
Taleo) with no public API, while Greenhouse/Lever skew toward companies
that grew up on modern SaaS tooling. None of these 4 are in the QSR50
Rung-1 seed list, so they'll resolve tier via Rung 4 (Wikidata) or Rung 5
(LLM) or default to Tier 3, same as any other newly-discovered signal
source account - no changes needed to pipeline/site_count.py.
"""
from __future__ import annotations

ATS_BOARDS = [
    {"name": "Sweetgreen", "domain": "sweetgreen.com", "ats": "greenhouse", "board_token": "sweetgreen"},
    {"name": "Caribou Coffee", "domain": "cariboucoffee.com", "ats": "greenhouse", "board_token": "caribou"},
    {"name": "Blue Bottle Coffee", "domain": "bluebottlecoffee.com", "ats": "lever", "board_token": "bluebottlecoffee"},
    {"name": "Insomnia Cookies", "domain": "insomniacookies.com", "ats": "lever", "board_token": "insomniacookies"},
]
