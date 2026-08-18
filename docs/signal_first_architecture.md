# Signal-first architecture (supersedes the account-first design)

This replaces the original plan's account-first sequencing (curate/tier/enrich
15-20 accounts, then watch for signals) with a signal-first flow: scan OSHA
data for real activity first, then only spend enrichment effort on accounts
that actually hit. Rationale and the conversation that led here: Clay's
100-record/month API quota and plan-gated CRM sync made pre-enriching a
static account list impractical, and signal-first is also a more realistic
GTM motion (don't spend enrichment budget on accounts with no current signal).

## 1. Scan for triggers

Restaurant NAICS codes: `722511`, `722513`, `722515`.

Two categories of trigger, not four:

- **Inspection** (fires immediately, no outcome needed yet): any new OSHA
  inspection record where `insp_type` is `Complaint` (B), `Accident` (A), or
  `Fat/Cat` (M) - a fatality or 3+ hospitalization event. These three are the
  "early, pre-outcome" signals worth acting on; the other 10 `insp_type`
  codes (Referral, Planned, FollowUp, Monitoring, Variance, and the
  Unprog/Prog administrative variants) don't map to a compelling "something
  happened here" narrative and aren't scanned.
- **Violation** (a citation was actually issued): checked across *all*
  restaurant-NAICS inspections regardless of what `insp_type` opened them - a
  citation can result from a Planned or Referral inspection just as easily as
  a Complaint, so this is a separate, broader sweep, not a filter on the
  three Inspection-trigger types above.

**Fat/Cat gets no special contacts, channel, or messaging for this demo** -
only one behavioral difference downstream: it never gets auto-enrolled into a
sequence (see step 5). A real Fat/Cat-specific motion would be designed
later; for now, exclusion from automation is enough.

**Data source: `osha.gov/ords/imis`** (`industry.search` for NAICS+date-range
listing, `establishment.inspection_detail` for exact per-violation issuance
dates), not the `apiprod.dol.gov` API - the latter rate-limits hard under the
kind of cross-referencing this needs (hit both 403s on long filters and
sustained 429s under load), while `osha.gov/ords/imis` handled the same
lookups cleanly with no throttling observed.

**Accuracy verified, not assumed**: cross-checked one real inspection (Bgs
Holdings, LLC, Arcadia OK) independently against both `osha.gov/ords/imis`
and the official `apiprod.dol.gov` API. Every field matched exactly -
address, open date, report ID, close-conference date, and on the citation
side all 9 violation line items, same standards, same citation IDs, same
$61,707 total penalty, same issuance date.

Slack channels renamed to reflect the Inspection/Violation distinction
(replaces the old Complaint/Citation framing): `qsr-osha-inspections`,
`qsr-osha-violations`. `qsr-hiring-signals` unchanged.

## 2. Enrich

Companies discovered in step 1 are pushed to **Duo by Amplemarket** (replaces
Clay) for contact discovery and email enrichment - matches Bites' actual
stack. Not yet verified against a live Amplemarket API key; to confirm once
available: whether it provides real email addresses via API (the whole
reason Clay didn't work), and whether its company-level enrichment includes
`site_count` (probably not - this appears to be a general gap across
B2B firmographic tools, not a Clay-specific limitation, so don't assume
Amplemarket solves it without testing).

`site_count` - the number that actually drives tiering - does **not** come
from the enrichment tool. It comes from a separate waterfall
(`docs/account_sourcing_methodology.md`), scoped down to two rungs for this
build:

- **Rung 1 - QSR Magazine QSR50 + Contenders**: a static lookup dict (brand
  name -> site count), fuzzy-matched against the OSHA `estab_name`. Instant,
  deterministic, no external call. (`pipeline/accounts_seed.py`'s role
  changes here - it's no longer "the account list," it's the source data for
  this lookup dict.)
- **Rung 4 - Wikidata**: free, public, no-auth SPARQL query for the brand's
  "number of locations" property, when populated. Deterministic API call, no
  LLM involved.
- Anything neither rung resolves **defaults to Tier 3**, per the earlier
  reasoning: tier bands are wide, reporting quality correlates with company
  size, so accounts a cheap lookup can't find are also the lowest-stakes ones
  to under-tier. Every `site_count` gets `{value, source, confidence,
  as_of_date}`, not a bare number, so a Tier-3-by-default account is
  distinguishable from a verified one.
- Rungs 2 (FDD data), 3 (SEC EDGAR), 5 (company website) are documented but
  not built for this demo - all three need an LLM read to extract a number
  from prose (a 10-K, a website), not just an API call. That's genuinely
  automatable without a live Claude session (the standalone script could call
  Claude's own API directly, the same way it calls HubSpot or Slack - unlike
  MCP, which cannot be invoked outside a live session), but it's real
  additional build work, deferred for now.

`governance_model` is dropped entirely - nothing else in the pipeline
depends on it, so it's not computed or pushed going forward. (The HubSpot
property and the 28 already-pushed values from the old account-first build
are left alone rather than deleted.)

## 3. Tier

Unchanged: `tier_for_site_count()` - Disqualified (<=5), Tier 3 (6-49),
Tier 2 (50-199), Tier 1 (200+).

## 4. Resolve contacts

Unchanged persona structure: Inspection and Violation triggers -> 3 contacts
(one senior each: Operations VP/COO, Safety/EHS senior, L&D/Enablement
Head/CLO; double up on another track if one comes back empty). Hiring
trigger -> 2 contacts (prefer two L&D/Enablement leadership contacts; fall
back to one L&D + one HR/People if only one L&D match exists). Fat/Cat
inspections still get contacts resolved normally - the "no special handling"
decision only affects sequence enrollment in step 5, not contact resolution.

Email enrichment moves from the blocked Clay path (no email on the public
search API; Table-based enrichment gated behind Clay's Growth plan; MCP
proved emails are gettable but only interactively, not from the standalone
script) to Duo by Amplemarket, pending live verification.

## 5. Push

Company and Contact records pushed to HubSpot. On every trigger: the
`qsr_signal` custom object (system of record), a Company Note (human-readable
summary), and the Slack message all fire together - every trigger gets all
three, including Fat/Cat.

Sequence enrollment varies by tier and is the one place Fat/Cat differs:
- Tier 3: auto-enrolled into a call-task-only sequence.
- Tier 1: sequence exists, email steps are manual, AE sends personally.
- **Fat/Cat: never auto-enrolled into any sequence**, regardless of tier -
  the contact and signal are still fully visible (object + note + Slack), a
  human decides what happens next.

**Task #7 update (2026-08-18):** "Real HubSpot workflow, triggered by
`qsr_signal` object creation" (below) is superseded - built instead as a
direct call from `pipeline/signal_handler.py:handle_signal()` right after it
creates the `qsr_signal` object, with no separate native HubSpot workflow
watching for that creation. A workflow trigger would only re-detect an event
the same function just caused. `docs/task7_workflow_notes.md` has the full
reasoning plus the real API constraints found along the way (no scopes
granted yet on this portal's private app; the Sequences API has no
create-sequence endpoint, so the sequence itself is still human-authored in
the HubSpot UI, same as before).

## Hiring trigger

Built 2026-08-18, picked specifically because it doesn't depend on Task #4
(`resolve_contact`, blocked on Amplemarket - see `HANDOFF.md`). Full detail
and real findings in `docs/hiring_signal_scope.md` - summary below.

**Step 1 differs from OSHA in a real, structural way**: neither Greenhouse's
nor Lever's public API offers company discovery, only per-company postings
for a board token you already know. So step 1 here is "scan a hand-curated
list of known boards" (`pipeline/hiring_seed.py`, `pipeline/ats_client.py`,
`pipeline/hiring_scanner.py`), not a global scan the way OSHA's NAICS search
is. Verified live: of the 28 QSR50/Contenders chains plus ~60 other
fast-casual/coffee/bakery brands tried, only 4 have a public board at all
(Sweetgreen, Caribou Coffee - Greenhouse; Blue Bottle Coffee, Insomnia
Cookies - Lever), all younger/tech-forward chains, none from the large-chain
list. Growing that seed list is this path's equivalent of expanding Rung 1's
28-brand list - real, valuable, offline work.

Trigger: an L&D/Training/People-Ops leadership role posted
(`is_relevant_hiring_posting()` - requires a seniority marker AND a
function marker together, tuned against a real false positive: "Store
Manager in Training (MIT)" is a ubiquitous frontline title, not a
leadership signal, and a naive "training" keyword match would flag it
constantly).

Steps 2-3 (site_count/tiering) are reused unchanged - confirmed live, no
code changes needed. Step 5 (push) reuses the `qsr_signal` object's
pre-existing `Hiring` type and the pre-existing `hiring_signals` Slack
channel; `pipeline/signal_handler.py:handle_hiring_signal` is a separate
function from `handle_signal()` rather than a shared branch, since the two
signal shapes only share the tiering/company-upsert/object/Slack/Note
steps, not the OSHA-specific ones (franchisee-name collapsing, brand-wide
history). Persona tracks (`pipeline/persona_tracks.py:HIRING_TRACKS`) are
defined but not yet wired to a real `resolve_contact` - blocked on the same
Task #4 dependency as OSHA. The Tier 1 personalized first-touch email
(the Hiring equivalent of Task #8) is deliberately not built yet - it needs
its own copy-rules pass, not a reuse of OSHA's citation-framed copy.

## What this changes from the original plan

The original plan's "maintained account list" was explicitly a standing
deliverable, independent of any signal (Task #3's 28 QSR50-sourced accounts,
tiered and pushed to HubSpot before any signal check). Under signal-first,
the account list becomes dynamically signal-derived instead - accounts only
enter the system because a real trigger fired on them. This is a deliberate,
discussed tradeoff (driven by the Clay quota/plan-gating constraints), not an
oversight, but it is a real departure from the original plan worth being
explicit about when presenting.
