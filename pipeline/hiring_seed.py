"""Known ATS board tokens for QSR/fast-casual brands - Greenhouse, Lever,
and Workday.

None of the three offer a "search all companies" endpoint (confirmed live,
2026-08-18 - see docs/hiring_signal_scope.md), so unlike the OSHA path's
global NAICS scan, this scanner can only ever see companies whose board
config is already known here. This list is that discovery step, done by
hand - the direct analog of accounts_seed.py's role for Rung 1 of the
site_count waterfall.

**Deliberately kept small.** Confirmed live 2026-08-18: Greenhouse/Lever
coverage among large QSR chains is real but thin (4 hits out of ~90 tried,
none from the 28-brand QSR50 list - younger/VC-backed chains only). Workday
closes that gap for large chains specifically (Chipotle, Whataburger, Shake
Shack all confirmed live) - large QSR operators overwhelmingly run
enterprise ATS (Workday, iCIMS, Taleo), not Greenhouse/Lever. Per an
explicit 2026-08-18 scoping decision, this list stops here rather than
hunting further Workday tenants - 7 companies across 3 ATSs is enough to
prove the pattern for a demo; growing it further is the natural next step,
not a requirement now.

Chipotle's name/domain match accounts_seed.py's QSR50 entry exactly
("Chipotle Mexican Grill" / "chipotle.com") so a real Hiring signal there
resolves via Rung 1 (real 3,938-site count) and converges onto the same
Company record the OSHA path already created (id 443765558499, see
HANDOFF.md) rather than creating a duplicate. Whataburger/Shake Shack
aren't in the QSR50 list, so they'll resolve via Rung 4/5 like any other
newly-discovered account - no changes needed to pipeline/site_count.py.

Workday's `job_family_group_id` (Whataburger only) scopes the scan
server-side to that tenant's "Human Resources" facet - verified live to
cut Whataburger's total from 4,290 (almost all frontline "Restaurant
Operations" reqs) to 3. Facet ids are opaque and tenant-specific (no id
works across companies), so this is only set where already found; Chipotle
(216 total) and Shake Shack (561 total) are small enough to paginate in
full without one - see pipeline/ats_client.py:workday_jobs.
"""
from __future__ import annotations

ATS_BOARDS = [
    {"name": "Sweetgreen", "domain": "sweetgreen.com", "ats": "greenhouse", "board_token": "sweetgreen"},
    {"name": "Caribou Coffee", "domain": "cariboucoffee.com", "ats": "greenhouse", "board_token": "caribou"},
    {"name": "Blue Bottle Coffee", "domain": "bluebottlecoffee.com", "ats": "lever", "board_token": "bluebottlecoffee"},
    {"name": "Insomnia Cookies", "domain": "insomniacookies.com", "ats": "lever", "board_token": "insomniacookies"},
    {
        "name": "Chipotle Mexican Grill",
        "domain": "chipotle.com",
        "ats": "workday",
        "tenant": "chipotle",
        "shard": "wd5",
        "site": "ChipotleCareers",
    },
    {
        "name": "Whataburger",
        "domain": "whataburger.com",
        "ats": "workday",
        "tenant": "whataburger",
        "shard": "wd5",
        "site": "WAB_CAREERS",
        "job_family_group_id": "482bc6fc5d0310061a698499a47f0000",  # "Human Resources" facet
    },
    {
        "name": "Shake Shack",
        "domain": "shakeshack.com",
        "ats": "workday",
        "tenant": "shakeshack",
        "shard": "wd5",
        "site": "External",
    },
]
