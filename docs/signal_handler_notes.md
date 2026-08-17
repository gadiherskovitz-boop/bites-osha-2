# Signal handler — findings (Task #6)

Verified live on 2026-08-17 against the real HubSpot portal (EU1, 149021592)
and the real Slack workspace ("GH VC").

## Custom object CRUD/search needs objectTypeId, not the schema name

`POST /crm/v3/schemas` accepts `"name": "qsr_signal"` to *create* the schema,
but the object read/write/search endpoints
(`/crm/v3/objects/qsr_signal`, `/crm/v3/objects/qsr_signal/search`, the v4
associations endpoint) all 400 with `"Unable to infer object type from:
qsr_signal"` against that same bare name — confirmed live, including on
`GET /crm/v3/schemas/qsr_signal` for a schema that doesn't exist yet (400, not
404, which also broke the naive "check via GET, 404 means missing" existence
check). Both the fully-qualified name (`p149021592_qsr_signal`) and the
`objectTypeId` (`2-252022394`) work. `pipeline/hubspot_client.py` hardcodes
`QSR_SIGNAL_OBJECT_TYPE = "2-252022394"`, same pattern as
`pipeline/slack_client.py`'s `CHANNELS` dict — created once via
`scripts/setup_qsr_signal_schema.py`, stable, not re-looked-up per call.
Existence-checking now lists all schemas and filters client-side
(`find_schema()`) instead of GETting by name.

## Signal-sourced companies often have no domain

OSHA gives an establishment name — frequently a franchisee's legal entity
name ("Wendy'S Salt Lake City Llc"), not a canonical brand record. Only a
Rung 1 (QSR50 static list) match carries a real domain; Rung 4 (Wikidata) and
unresolved accounts don't. `pipeline/site_count.py:lookup_site_count()` now
also returns `brand_name`/`domain` (populated only for Rung 1).
`pipeline/hubspot_client.py:upsert_signal_company()` falls back to a
name-based dedup when no domain is known. Accepted, documented limitation: a
name-only match could end up as a separate Company record from the same
brand's domain-keyed company created elsewhere (e.g. Task #3's
`scripts/build_accounts.py`) if the two names don't match exactly —
reconciling that for real needs domain enrichment, the same Clay/Amplemarket
problem this project already hit, so it's accepted rather than solved here.

## The Slack bot token was missing `chat:write`

Live `auth.test` showed a valid token for the right bot user
(`bites_qsr_signals`, workspace "GH VC") but scoped to only
`calls:write, channels:manage` — posting failed with `missing_scope`. Fixed
by the user adding `chat:write` under **OAuth & Permissions → Bot Token
Scopes** in the app's *developer* console (`api.slack.com/apps` — distinct
from the workspace's read-only app-management page, which is where the
confusion happened) and reinstalling to the workspace. Worth knowing for
next time: this workspace's reinstall did *not* rotate the token value.

## `qsr_signal` "Year to date / 2025 / 2024" fields — not built

The architecture doc's Slack/Note template includes historical count/fine
fields that need a full-history OSHA pull per account, not just the 100-day
trigger-window scan. `pipeline/signal_handler.py` renders these as an
explicit `HISTORY_UNAVAILABLE` string rather than computing a number from the
narrow window, which would understate real totals and look verified when
it isn't.

## Fully verified live, including idempotency

Two real signals run end-to-end (El Pollo Loco Complaint, In-N-Out Burger
Fat/Cat): Company + `qsr_signal` object + Note + Slack alert all fired
correctly. Re-run multiple times each — exactly one `qsr_signal` record per
`source_activity_nr` both times (`upsert_qsr_signal`'s dedup confirmed live,
not just unit-tested), and the same Company record reused rather than
duplicated. Fat/Cat correctly returned `sequence_eligible: False`, the
Complaint correctly returned `True` — no sequence exists yet to actually
enroll into (that's Task #7), this is just the flag a future workflow would
gate on.

One asymmetry worth knowing: HubSpot-side writes (Company, `qsr_signal`,
Note) are all idempotent per signal, but the Slack post itself isn't — a
re-run of `handle_signal` on an already-fired signal sends a second Slack
message. Not deduped, since a real deployment scanning a moving window
wouldn't normally re-fire the same signal twice; only matters for repeated
manual test runs like today's.

## Backlog vs. real deployment cadence

A fresh `scan_inspections()` over the full 100-day window returns the whole
backlog (268 signals as of 2026-08-17), not "what's new." A real deployment
would run `scripts/handle_signals.py` frequently against that same trailing
window, so each run only ever touches genuinely new signals — there's no
"already scanned" checkpoint built (out of scope for Task #6). Running the
full backlog in one go would push 268+ real Slack messages at once, so the
script defaults to handling only the first 3 signals per run
(`DEFAULT_LIMIT`); pass a number as the first argument to process more.

## Account grain: the account is the BRAND (decided, with a known tradeoff)

Every location and every franchisee collapses into one brand-level company
record - one "McDonald's", not one per store or per operator.
`pipeline/company_names.py` does the collapsing; rules were ported from the
prior Bites assignment (`Assignment 1/osha_signal/company_names.py`), which
solved the same problem on the same data, and re-verified against this
project's own 258 live establishment names:

- **35 of 258 (13.6%)** carry inspector case-number prefixes
  (`'111589 - Chipotle Mexican Grill Inc'`). We stripped none of these before,
  so `'111589 - Chipotle...'` silently failed the Rung 1 brand match entirely.
- **9** carry a DBA (`'Warmel Management Co Dba Mcdonalds'` → McDonald's) -
  this is the franchisee→brand link, free and deterministic.
- **6** carry site suffixes; we previously handled only a trailing `#123`.
- Collapsing these merges **10 would-be duplicate company records** in a
  single 100-day window (`'Mcdonald'S'` + `'Mcdonald'S #5125'`;
  `'317744408 - Papa Bend Inc'` + `'317744758 - Papa Bend Inc'`;
  three `Encanto Restaurants` punctuation variants; etc.). That understates
  the steady-state effect - brands recur far more often over a full year.

**The accepted tradeoff**, raised explicitly and decided: large franchise
operators (`'Ayvaz Pizza Llc Dba Pizza Hut'` ≈250 units, `'Hz Ops Holdings'`)
are frequently the party that actually employs the staff, runs the training
and signs the contract. Collapsing them into the brand can point outreach at
a corporate entity that neither operates the cited location nor buys the
training. Chosen anyway for one clean account per brand and a coherent
brand-wide story. Revisit if reply data suggests it. The alternative
considered was a brand-parent / operator-child company hierarchy.

Names with no recoverable brand token (`'Carolina Restaurant Group Inc'`,
`'Guernsey Holdings Sdi Id Opco Llc'`) have nothing to collapse to and stay
under the operator's name by necessity.

**Rung 1's 28-brand dictionary is now the binding constraint.** Cleaning
correctly yields "Pizza Hut", "Burger King", "Baskin Robbins", "In-N-Out
Burgers", "Pizza Ranch" - none are in the seed list, so they collapse
correctly but still resolve no domain or site count. Expanding that list is
offline work with zero runtime cost and is where the remaining leverage is.

## Brand history is brand-wide, and cached

`pipeline/brand_history.py:year_summary()` reports YTD / prior-2-years
inspection counts and fine totals across **every location of the brand
nationally**, via `establishment.search`'s substring name match - the
pattern ("22 inspections in 3 years across the chain") is the sales story,
not one site's record. Restaurant-NAICS filtering happens client-side
because the endpoint silently ignores its own `NAICS` param when a name is
given (a `NAICS=722511` filter still returned 339113/423830 rows - "Team
Wendy, Llc.", a helmet maker).

Results are cached per brand per day (`output/history_cache/`, gitignored):
a cold lookup costs ~6.8s and N+1 detail fetches, a warm one 0.00s, verified
identical. Brand-collapsing is what makes this pay - many signals converge
on few brands.

## data.dol.gov bulk downloads - evaluated, not adopted

Verified live: both zips exist, need no auth, were rebuilt 2026-08-16, carry
`ESTAB_NAME`/`NAICS_CODE`/`OPEN_DATE`/`INSP_TYPE`/`SITE_STATE`, and reach
back to **1979**. Members are STORED (uncompressed), so a byte-range request
reads CSV directly without downloading the whole archive - which is how this
was checked without paying 1.4GB.

Not adopted, for one decisive reason: the bulk `ACTIVITY_NR` is a bare
integer (`311633507`) and **does not match** the IMIS id (`1910993.015`)
this pipeline keys signal records and source URLs on - confirmed live, and
independently documented in `Assignment 1/DOL-DATA-BRIEF.md`. Adopting bulk
would mean running two ingestion paths, so it powers history aggregation
only. At 3.5GB (1.4 inspections + 2.0 violations) for a demo whose history
need is satisfied by a day-cached scrape, it isn't worth it yet. It IS the
right architecture at scale, and the range-read trick above makes it
cheaper to adopt later than it looks.

## Known: one orphaned duplicate company in the portal

A `Wendy's` record (id `441829807307`, created 2026-08-03, no domain, no
tier, no associated signals) predates this project and shadows the correct
domain-keyed record (`443738643685`). `upsert_signal_company` now adopts and
backfills a domain-less name match so this can't recur, but it cannot reach
this one - the domain-keyed record already exists, so the name branch never
runs. Merging two existing companies is destructive and was left for a
human to decide.

## Files

- `pipeline/hubspot_client.py` — `upsert_signal_company`, `create_schema_if_missing`/`find_schema`, `upsert_qsr_signal`/`find_qsr_signal`.
- `pipeline/signal_handler.py` — `handle_signal()`, the message template.
- `pipeline/company_names.py` — brand collapsing (`brand_name`, `match_key`).
- `pipeline/brand_history.py` — `year_summary()`, brand-wide + day-cached.
- `pipeline/osha_client.py` — `establishment_search()`, `violation_narrative()`.
- `scripts/setup_qsr_signal_schema.py` — one-time schema creation (idempotent).
- `scripts/handle_signals.py` — the runnable driver.

## Alert template (rebuilt)

Emoji + bolded labels, and field sets that differ by signal type:

- **Penalty/Severity appear only on Violation signals** - an Inspection
  trigger fires before any citation exists, so those fields were always
  empty and looked broken.
- **Event text is real where OSHA publishes it.** Federal citations carry a
  "Text For Citation" hazard narrative, pulled live (e.g. *"the employer
  failed to ensure the rear of the MS1910 Meat Slicer was guarded..."*).
  State-plan citations have no such section at all (confirmed live) and fall
  back to standard + classification. Inspections genuinely have no narrative
  - OSHA doesn't publish complaint details (source protection) - so those
  state the inspection type and case status rather than inventing detail.
- **`Company:` is omitted from the HubSpot Note** (redundant on the record
  it's attached to) but kept in Slack, which has no surrounding context.
- **`Cited as:`** shows the raw OSHA establishment name and state whenever
  brand-collapsing changed it, so the specific site isn't lost.
- Every alert links to the official OSHA record.
