# Handoff: QSR Prospecting Engine (Bites GTM Engineer Take-Home)

## Goal

Build a working prototype of a QSR prospecting engine for a GTM Engineer take-home assignment with Bites (mybites.io): signals in, tiered accounts, mapped contacts, signal+tier-specific GTM motions, and one real personalized first-touch — presented live in ~30 minutes as running software, not a deck. Code tracked on GitHub, built per `karpathy-coding-guidelines` (minimal, surgical, no premature abstraction).

## Status

**Read `docs/signal_first_architecture.md` first — it is the current authoritative design**, superseding the account-first framing in the original plan file (see below). Architecture pivoted mid-build from account-first (curate/tier/enrich a static list, then watch for signals) to signal-first (scan OSHA data for real activity, only enrich accounts that hit) — driven by real constraints hit during the build, not a change of mind. `docs/` also has `dol_api_notes.md`, `clay_api_notes.md`, and `account_sourcing_methodology.md` — each documents a real investigation, not a plan; read before re-deriving.

**Done and working:**
- Repo initialized, pushed to `https://github.com/gadiherskovitz-boop/bites-osha-2.git`. `.env` populated (DOL, HubSpot, Slack keys — gitignored, never committed). Standing permission was given to push without asking each commit for *this* session — a new session should re-confirm rather than assume that carries over.
- HubSpot verified working end-to-end: custom Company properties, custom objects, Notes, Contacts all confirmed read/write (portal EU1, 149021592).
- Slack verified working; 3 channels live: `qsr-osha-inspections`, `qsr-osha-violations`, `qsr-hiring-signals` (renamed from complaints/citations to match the Inspection-vs-Violation framing — Accident and Fat/Cat both count as "inspection").
- DOL/OSHA data source resolved: use `osha.gov/ords/imis` (`industry.search` + `establishment.inspection_detail`), not the `apiprod.dol.gov` API — the latter rate-limits hard (403s on long filters, sustained 429s) under the cross-referencing this needs; the former doesn't, and was rigorously cross-validated against the official API on a real record (exact match on every field, including 9 citation line items and penalty amounts).
- Schema resolved: an Inspection has a `type` (13 possible reasons, including Complaint/Accident/Fat-Cat); Violations are a separate, related record (joined by `activity_nr`) that can result from *any* inspection type, not just complaint-originated ones.
- Task #3 (old account-first design) built 28 real QSR brands with real site_count/governance data sourced from QSR Magazine's QSR50 + Contenders lists, tiered, pushed to HubSpot. Under the new architecture this data is **repurposed as Rung 1 of the site_count lookup**, not "the account list" — accounts now come from the signal scanner.
- Clay investigated extensively and **abandoned**: no email field anywhere on its public API (company or people search), no site_count field on companies, Table-based email enrichment blocked (Enterprise-plan-gated), native CRM sync blocked (Growth-plan-gated, $495/mo). Clay's MCP connection *can* get real emails interactively, but MCP tools don't exist for the standalone script at runtime, so that's not a real solution either.
- **Decision: switch to Duo by Amplemarket** for contact/email enrichment (matches Bites' actual real stack, discovered mid-session) — researched only, not yet tested live, no API key yet. Nooks.ai (Bites' other real tool) confirmed to be a dialer/engagement platform, not an enrichment tool — not relevant to this problem.
- `governance_model` dropped entirely per explicit decision — not needed for the demo, nothing depends on it.
- Fat/Cat (fatality/catastrophe) inspections get no special contacts/channel — the only different treatment is they must never auto-enroll into a HubSpot Sequence, regardless of tier.
- Persona tracks finalized: Inspection/Violation triggers → 3 contacts; Hiring trigger → 2 contacts. Details and reasoning in `pipeline/persona_tracks.py`.

## Open items

- **Amplemarket/Duo**: no API key yet, nothing tested. Blocked on the user obtaining a business-domain trial account (Amplemarket rejects a plain Gmail signup) — in progress in a separate session using the `wizard` skill. Needs the same verification rigor Clay got — does it actually return emails via API, does its company enrichment include site_count (probably not — assume no until tested), what's the auth/endpoint shape.
- **Task #5 (signal scanners) — done.** `pipeline/osha_client.py` (HTTP + HTML parsing) and `pipeline/signal_scanner.py` (`scan_inspections`, `scan_violations`, `is_relevant_violation`) built and verified live against `osha.gov/ords/imis` — see `docs/osha_ords_imis_notes.md` for the real mechanics found (a swapped start/end date-field quirk on the site's own form, NAICS is one-per-request only, state-plan citations use non-federal standard numbering). Live run over the trailing 100-day window across all 3 restaurant NAICS: 268 Inspection triggers (248 Complaint/14 Accident/6 Fat-Cat), 0 Violation triggers this window (checked — 16 real citation line items existed, none matched the relevance filter; filter logic itself verified correct against synthetic known-relevant/known-irrelevant cases). Runnable via `scripts/scan_signals.py`.
- **Site_count waterfall**: only Rung 1 (QSR50 static lookup) exists, and even that needs refactoring out of `accounts_seed.py`'s account-list shape into a plain lookup function. Rung 4 (Wikidata SPARQL) not built. Rungs 2/3/5 are deliberately narrated-not-built (need LLM-extraction from prose; deferred, see `account_sourcing_methodology.md`).
- **Task #4 (contact resolution) never completed** — was blocked on Clay, now pivoting to Amplemarket; `resolve_contact` orchestration itself isn't built yet.
- **`scripts/build_accounts.py` is stale** — written for the old account-first flow; needs replacing with a signal-first driver (accounts now come from the scanner, not a fixed seed list).
- **Task #6 (signal handler)**: `qsr_signal` custom object creation isn't built yet (only Notes exists in `pipeline/hubspot_client.py`). Needs the "fire object+note+Slack together, skip sequence enrollment only for Fat/Cat" logic.
- Hiring scanner (Greenhouse/Lever): persona tracks defined, nothing else started.
- Tasks #7, #8, #9 not started.
- An early system-map Artifact (`https://claude.ai/code/artifact/c18827bf-781f-42be-9cc2-56a66c7188e7`) reflects the **old, now-superseded** account-first architecture — stale, not updated. Worth redoing once the signal-first build has real code behind it, but not yet requested.

## Key references

- **Current architecture (read first):** `docs/signal_first_architecture.md`
- Site-count waterfall design: `docs/account_sourcing_methodology.md`
- DOL/OSHA API findings: `docs/dol_api_notes.md`
- osha.gov/ords/imis mechanics (the live scanner data source): `docs/osha_ords_imis_notes.md`
- Clay investigation (historical — explains why Amplemarket): `docs/clay_api_notes.md`
- Original plan (**partially superseded** — architecture/account-list/signal sections are stale, rest still mostly valid): `/Users/ariherskovitz/.claude/plans/task-build-an-automated-parsed-rocket.md`
- Pipeline code: `pipeline/*.py` (config, hubspot_client, slack_client, clay_client, tiering, persona_tracks, accounts_seed), `scripts/*.py`
- GitHub remote: `https://github.com/gadiherskovitz-boop/bites-osha-2.git`
- Working directory: `/Users/ariherskovitz/Documents/Claude/Projects/Bites Assignment/Assignment 2`
- Task tracker: 9 tasks (#1–#9), check via `TaskList`/`TaskGet` for current status (as of this handoff: #1–#3 completed, #4 in progress, #5–#9 pending)

## Suggested next steps

1. Get an Amplemarket (Duo) API key from the user and verify it the same way Clay was verified — real endpoints, real auth, does it actually return emails.
2. Build the site_count waterfall for real: refactor Rung 1 out of `accounts_seed.py`, add Rung 4 (Wikidata).
3. Build `resolve_contact` (Task #4) once Amplemarket access is confirmed, using the existing persona track definitions.
4. Build the `qsr_signal` object creation + signal handler (Task #6), including the Fat/Cat sequence-exclusion rule, feeding off `scan_inspections()`/`scan_violations()`.
5. Continue through Tasks #7–#9.

## Suggested skills

- `karpathy-coding-guidelines` — already the agreed coding standard; keep applying (minimal diffs, no speculative abstraction) as the signal-first rebuild proceeds.
