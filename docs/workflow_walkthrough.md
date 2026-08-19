# QSR Prospecting Engine — End-to-End Workflow Walkthrough

This walks through the OSHA signal path start to finish, as it actually
exists and was actually run — not the plan, the real thing, with real
company/contact names from real live runs. Each step covers: what it does,
the technology/heuristics/deterministic rules behind it, the files that
implement it, why it was built that way, and (where one exists) a concrete
real result from an actual run.

The Hiring signal path (Greenhouse/Lever/Workday scanning, `pipeline/
hiring_scanner.py`) shares Steps 3–4 unchanged but is otherwise a separate
trigger with its own scope — noted briefly at the end, not walked in full
here.

**A note on ordering:** the steps below are numbered in **build order**
(what got coded across earlier sessions), not strict runtime order. Steps 5
and 6 (sequence enrollment, the Tier 1 email) were built and tested weeks
before contact resolution (Steps 7–11) existed at all — against a
placeholder contact, specifically because nothing else could supply a real
one yet. At runtime, for one real signal today, the true order is: Steps
1–4 fire immediately; Steps 5/6 get *called* right then but return "skipped,
no contact yet" until Steps 7–11 later produce one; Step 12 is really
"Steps 5/6, executed for real, now that a contact exists."

Also worth being precise about up front: the "274 signals," "19-company
Clay batch," and "7 companies actually in HubSpot" numbers that appear
below are **three independent measurements taken at different times from
different sources**, not a funnel that narrows from one to the next. See
Step 4's result and the closing section for the actual relationship between
them.

---

## Step 1: Scan OSHA for triggers

**What it does:** Scans the federal OSHA enforcement database for two kinds
of real-world events at restaurant businesses.

- **Inspection trigger** (fires immediately, no outcome needed yet): a new
  inspection where `insp_type` is **Complaint**, **Accident**, or **Fat/Cat**
  (fatality/3+ hospitalization). Chosen because these three read as "something
  is actively happening here" — the other ten inspection types (Referral,
  Planned, FollowUp, Monitoring, etc.) are administrative/routine and don't
  support a "why now" pitch.
- **Violation trigger** (a citation was actually issued): checked separately,
  across *all* inspection types, not just the three above — a citation can
  result from a Planned or Referral inspection just as easily as a Complaint,
  so this is a broader sweep layered on top, not a filter on the Inspection
  set.
- **Industry scope:** restaurant NAICS codes `722511`, `722513`, `722515`.

**Data source and why:** `osha.gov/ords/imis` (`industry.search` for the
NAICS+date listing, `establishment.inspection_detail` for exact per-violation
dates) — **not** the official `apiprod.dol.gov` API. The official API
rate-limits hard under this kind of cross-referencing (403s on long filters,
sustained 429s under load); the ords/imis endpoint handled the identical
lookups with no throttling. Accuracy wasn't assumed — one real inspection
(Bgs Holdings LLC, Arcadia OK) was cross-checked field-by-field against the
official API: address, dates, all 9 citation line items, same $61,707 total
penalty, exact match.

**Challenges hit and solved:**
- The site's own date-range form has a swapped start/end field — worked
  around once identified.
- NAICS codes are one-per-request only — the scan loops over all three.
- State-plan citations (e.g. Cal/OSHA) use non-federal standard numbering,
  which matters later for the training-relevance filter (Step 4).

**Files:** `pipeline/osha_client.py` (HTTP + HTML parsing), `pipeline/
signal_scanner.py` (`scan_inspections`, `scan_violations`, relevance
filtering). Runnable via `scripts/scan_signals.py`. Full mechanics in
`docs/osha_ords_imis_notes.md`.

**Result:** a live run of the trailing 100-day window across all three NAICS
codes returned **274 real inspection signals**, 0 violation signals in that
particular window (checked, not assumed — real citation line items existed
in the window but none matched the training-relevance filter). This number
moves day to day since it's a live rolling scan, not a fixed dataset — an
earlier run in this same project returned 268. **This 274 is not the source
of the 19-company Clay test batch in Step 9** — that batch was pulled
earlier, from a different, older source (a cache of past tier lookups, see
Step 9) — the two numbers are unrelated measurements, not a before/after of
the same funnel.

---

## Step 2: Collapse establishment names to brand-level accounts

**What it does:** Turns OSHA's raw `estab_name` field into one clean
brand-level account name.

**The problem:** OSHA's establishment names are messy in specific,
measured ways (verified against 258 real names from a live scan):
- 13.6% carry an inspector case-number prefix (`110643 - JONNY POPS LLC`)
- 9 carry a franchisee-legal-name + DBA phrase (`Warmel Management Co Dba
  Mcdonalds`)
- 6 carry a store-number suffix (`Mcdonald'S #5125`)
- Punctuation/legal-suffix noise throughout (`Inc` / `Inc.` / `, Inc`)

**The decision:** the account is the **brand**, not the cited location or
the franchisee operating it — `Ayvaz Pizza Llc Dba Pizza Hut` becomes
"Pizza Hut," not "Ayvaz Pizza LLC." This collapses every location and
franchisee into one brand-level HubSpot company so a rep sees one account
with the full brand-wide story instead of duplicates.

**Tradeoff accepted explicitly, not an oversight:** large franchise
operators are often the actual buyer — they employ the staff, run training,
sign the contract. Brand-only collapsing can point outreach at a corporate
entity that neither operates the cited location nor buys the training. Kept
anyway for this build; flagged as revisit-if-outreach-data-suggests-it.

**Files:** `pipeline/company_names.py` — ported and re-verified from
Assignment 1's version of the same problem against this project's own live
data (10 would-be duplicates collapsed correctly per 100-day window in
testing).

---

## Step 3: Determine site count and tier

**What it does:** Answers "how big is this brand" (`site_count`) and maps
that to a tier, via a waterfall of increasingly expensive lookups — cheap
and deterministic first, LLM only as a last resort.

- **Rung 1 — QSR50/Contenders seed list** (`pipeline/accounts_seed.py`):
  a static, sourced dict of ~28 real brands with real site counts (QSR
  Magazine's own annual census), fuzzy-matched against the noisy OSHA name.
  Instant, deterministic, no external call.
- **Rung 4 — Wikidata**: a free, no-auth SPARQL query for the brand's
  "number of locations" property (`P8368`), when populated.
- **Rung 5 — LLM + web search** (`pipeline/tier_classifier.py`): **Claude
  Haiku 4.5**, run once per brand (not per signal) and permanently cached,
  only for brands Rungs 1/4 miss. Reframed to classify a **tier band**
  rather than demand an exact count — the reframing that makes an LLM rung
  cheap enough to be worth it (~$5 one-time for the full backlog measured).
  Round-up-at-band-boundary rule: under-tiering a real prospect costs more
  than over-tiering, so a brand near a boundary rounds up rather than being
  discarded.
- **Rungs 2/3 (FDD data, SEC EDGAR)** and the website-scraping variant of
  Rung 5 are documented but not built — all need an LLM read of unstructured
  prose, deferred as real additional scope, not a gap in reasoning.
- **Default:** anything no rung resolves defaults to **Tier 3** — tier bands
  are wide and reporting quality correlates with size, so accounts a cheap
  lookup can't find are also the lowest-stakes to under-tier.

**Tiering itself** (`pipeline/tiering.py`): Disqualified (≤5 sites), Tier 3
(6–49), Tier 2 (50–199), Tier 1 (200+).

**Files:** `pipeline/site_count.py` (waterfall orchestration), `pipeline/
tier_classifier.py` (Rung 5), `pipeline/accounts_seed.py` (Rung 1 data),
`pipeline/tiering.py` (band thresholds).

**Result (measured against a real 258-establishment scan):** 13 resolved via
Rung 1/4 (12 seed-list hits, one genuine Wikidata catch — 7 Brew Coffee, 604
sites), 245 defaulted to Tier 3 **at that point** — this is the Rung 1/4-only
figure, not a claim that Rung 5 was run against all 245 and still found
nothing. Rung 5 was only ever validated against a 14-name sample of the
Rung-1 misses (not the full backlog), where it resolved ~29%, extrapolating
to roughly 70 brands and ~50 additional Tier 1 accounts sitting in the long
tail if it were run at full scale — which it hasn't been yet.

**Why no Tier 2s among the 13 that did resolve:** likely a sampling
artifact of real inspection *incidence*, not a system bias. Rung 1's
seed-list matches and the one Rung 4 catch all happen to be large brands
(hundreds to thousands of sites) — and a chain with thousands of locations
generates far more real OSHA inspections in any given 100-day window than a
100-location regional chain does, so big brands are naturally overrepresented
among which signals actually fire. Tier 2-sized brands are exactly the kind
of thing Rung 5 exists to catch, and Rung 5 hasn't run at scale yet.

---

## Step 4: Push the signal — Company, `qsr_signal` object, Slack, Note

**What it does:** The moment a signal clears Steps 1–3, three things fire
together, every time, for every signal including Fat/Cat:

1. **Company upsert** in HubSpot (`upsert_signal_company`) — resolves by
   domain first, then exact brand name, adopting and backfilling a
   domain-less pre-existing record rather than creating a shadow duplicate
   (this exact bug happened once, to a pre-existing "Wendy's" record).
2. **`qsr_signal` custom object** — the system of record, idempotent per
   `(source_activity_nr, source_citation_id)` so re-running the scanner over
   the same real event never duplicates it.
3. **Slack alert + Company Note** — human-readable, including a brand-wide
   history line (floors, not totals, labelled honestly — OSHA has no brand
   field, so history search only catches locations whose *name* contains the
   brand string; a near-100%-company-owned brand like Chipotle gets a real
   total instead of a floor, since there are no franchisees hiding behind a
   different legal name).

**Why no native HubSpot workflow:** `handle_signal()` itself, called
directly from the scanner, *is* the trigger — a separate workflow watching
for `qsr_signal` creation would only re-detect an event this same call just
caused. Documented explicitly in `docs/task7_workflow_notes.md`.

**Why Fat/Cat still gets full visibility:** the one place Fat/Cat differs is
it's never auto-enrolled into a sequence (Step 5) — the Company/Note/Slack
push happens identically, so a human always sees it and decides what happens
next, rather than a fatality/catastrophe inspection silently sitting
unprocessed.

**Files:** `pipeline/signal_handler.py` (`handle_signal`), `pipeline/
hubspot_client.py`, `pipeline/slack_client.py`.

**Result (live, verified 2026-08-19):** **7 distinct companies** currently
carry a real OSHA `qsr_signal` in this HubSpot portal — Fogo de Chão, In-N-Out
Burger, El Pollo Loco, Eagles Landing Restaurants LLC, Chipotle Mexican
Grill, Wendy's, Pizza Hut. (Separately, 17 distinct companies carry a real
Hiring signal, zero overlap with the OSHA set.)

**This 7 is not "the 19 from Step 9, narrowed down."** It's an independent
count of every signal ever actually pushed through `handle_signal()` across
this whole project's history, checked live against the current portal — the
19-company Clay batch (Step 9) was built later and separately, from a
different source, and only **2 of those 19** (Chipotle, Pizza Hut) happen to
also be in this 7. The other 5 of the 7 were never part of the Clay batch at
all, and the other 17 of the 19 aren't part of this 7 at all.

---

## Step 5: Auto-enroll Tier 3 into a call-task sequence

**What it does:** A Tier 3, non-Fat/Cat signal with a resolved contact
auto-enrolls that contact into a real HubSpot Sequence — one To-do step, no
automated email steps, so nothing is ever sent to a real person without a
human clicking send.

**Why a human builds the Sequence, not the API:** HubSpot's public Sequences
API has no create-sequence endpoint — sequences carry personalization tokens
and a sender identity the API has no model for, so this is authored once in
the HubSpot UI (`QSR T3 - OSHA Trigger - Bites Assignment`, id `846865597`),
same as the Tier 1 sequence in Step 6.

**Real constraint found here, not anticipated:** this EU-hosted portal
enforces GDPR consent on *any* sequence enrollment, regardless of whether
the sequence has email steps — a contact needs a recorded legal basis or
enrollment 400s with `SequenceError.UNSUBSCRIBED`. This is what Step 7's
`subscribe_contact()` exists to satisfy.

**Files:** `pipeline/hubspot_client.py` (`list_sequences`,
`enroll_in_sequence`), `pipeline/signal_handler.py`
(`_maybe_enroll_in_sequence`).

---

## Step 6: Draft the Tier 1 personalized first-touch email

**What it does:** For Tier 1, non-Fat/Cat signals, generates one fully
personalized cold email tied to the real signal, attaches it as a Note on
the resolved Contact, and enrolls that contact in a separate Tier 1
sequence.

**Model choice and why it's the opposite of Step 3's:** **Claude Sonnet 5**,
not Haiku — this runs once and its entire output *is* the deliverable a
prospect reads, so copywriting quality dominates, not cost (the reverse
tradeoff from Rung 5's per-brand classification, which runs hundreds of
times and needs to stay cheap).

**Copy rules** (`docs/task8_email_rules.md`), enforced via system prompt:
sell the problem not the product; 140-word hard cap; if no citation exists
yet (the common case — Complaint/Accident), open on the inspection itself,
never an invented citation; name the real training failure modes (not
completed, boring, bad timing, wrong channel); a required, reasoned,
company-branded video reference; never surface OSHA's internal case number;
never draft for Fat/Cat at all (raises, doesn't soften tone). A concrete
reference draft is embedded in the system prompt as a worked example — a
stated word-count rule alone wasn't enough (drafts ran 155–165 words despite
an explicit "140, hard ceiling" instruction until a real example was added).

**Why a Note, not an actual sent email:** HubSpot Sequences don't support
per-contact custom step content via the API — confirmed against HubSpot's
own docs. So the draft lives as a Note on the Contact, and the Sequence's
To-do step is what points the AE at it to review and send personally
("manual" for Tier 1 describes the AE sending, not the enrollment).

**Files:** `pipeline/personalize.py` (`draft_first_touch`), `pipeline/
signal_handler.py` (`_maybe_draft_and_note_first_touch`).

---

## Step 7: Pivot to Clay for contact resolution

**What it does:** Steps 1–6 all assume a resolved contact already exists —
this is where one actually gets found. `contact = {"id", "name", "title"}`
was `None` everywhere until this step existed.

The idea was to use **Amplemarket** to match Bites' actual real enrichment
stack, but the trial signup was blocked on business-domain verification.
Fallback was **Clay**, but Clay's real-time, script-callable path (a
webhook data source) turned out to need a paid plan on this workspace, and
upgrading wasn't on the table for an assignment. So the mechanism became a
manual **CSV-in/CSV-out loop** around the Clay app instead — a deliberate
tradeoff to avoid a paid upgrade, not a technical dead end.

**Files:** `pipeline/clay_client.py`.

---

## Step 8: Build the Clay Companies table (domain resolution)

**What it does:** A Clay Table, seeded via CSV import, that resolves a
brand name to a domain.

- **Input CSV** (`write_companies_csv`): two columns only — `company_name`
  and `company_domain` (pre-filled wherever already known from Rung 1, blank
  otherwise). Everything else the pipeline needs (tier, signal type, which
  signal is waiting) deliberately stays out of this file and lives in the
  pipeline's own bookkeeping instead — Clay only needs enough to do its own
  job, not a copy of business logic that would drift out of sync with the
  Python side.
- **Domain-finder column:** a Claygent (AI web-search) waterfall column,
  configured to run **only on rows where `company_domain` is blank** — a
  conditional-run formula, saving credits on the ~14 rows the pipeline
  already had an answer for.
- **A formula column** (`resolved_domain`) coalesces `company_domain` and
  the waterfall's `Domain` output into one column, since downstream steps
  need a single identifier and the two source columns are each only
  partially populated.

**Real bugs hit and fixed, in order:** a case-sensitivity mismatch on the
conditional-run column reference (silently made the condition always true);
confirming via the formula's own "Preview" tool that the fix actually
evaluated correctly per row rather than trusting a static-looking UI label.

**Files:** `pipeline/clay_client.py` (`write_companies_csv`).

**Result:** 19 real companies (see Step 9 for how they were chosen) with
domain correctly pre-filled for known brands and correctly resolved by
Claygent for the rest — one real miss caught and left unfixed (Nevada
Restaurant Services, Inc. → `gamingdirectory.com`, plausibly a "Nevada ⇒
gaming" drift, worth a manual check before relying on it).

---

## Step 9: Build the Clay Contacts table (people + email enrichment)

**What it does:** Linked off the Companies table, finds people at each
resolved domain and enriches their work email.

- **"Find People at These Companies"**, referencing `resolved_domain` as the
  company identifier — deliberately **not** filtered by the OSHA/Hiring
  persona-track title lists (`pipeline/persona_tracks.py`) at the Clay
  level; that matching happens in Python on read-back instead, so the same
  "what counts as an L&D title" decision doesn't live in two places that can
  drift apart.
- **Email enrichment column** on the resulting People table.

**The 19-company test batch, and what it actually was:** hand-picked from
`output/tier_cache/*.json` — the *cached tier classifications* from Step 3's
Rung 5, which is populated by real establishment names encountered during
real scans. **Important correction made mid-build:** this cache doesn't
record which trigger (OSHA or Hiring) produced each entry, since tiering
logic is shared by both paths — so "in `tier_cache`" only proves "seen in
some real scan," not specifically an OSHA one. This was initially
overclaimed, then caught: Sweetgreen was in the batch purely via its real
Hiring/Greenhouse signal, not OSHA. Filtered down to genuine QSR/food-service
brands (excluding institutional noise like Yale, Ford, Northrop Grumman —
host organizations that a cafeteria inspection gets filed under),
prioritizing Tier 1: **Chipotle Mexican Grill, McDonald's, Chick-fil-A,
Dunkin', Popeyes, Burger King, KFC, Pizza Hut, Dairy Queen, Sweetgreen,
Lettuce Entertain You Restaurants, Otg** (Tier 1); **Yoshinoya Companies,
Mendocino Farms, Nevada Restaurant Services, Inc.** (Tier 2); **Buc-ee's,
Dig Inn Support, Abby's Pizza, Toca** (Tier 3).

**Real bugs hit and fixed, in order, on this table:**
- Job-title filter set to match **all** (AND) conditions instead of **any**
  (OR) — briefly caused zero results across every real company.
- Target-companies reference still pointed at the waterfall's raw `Domain`
  column instead of the coalesced `resolved_domain` — silently excluded
  every company that already had a pre-filled domain (14 of 19), so results
  only ever came from the 4–5 companies that needed Claygent.
- The live "Preview" panel itself proved unreliable mid-edit (showing junk
  results, then losing legitimate ones, on successive edits) — stopped
  trusting it and switched to inspecting real committed run output instead.

**Files:** built entirely in the Clay app UI (no pipeline code) — read back
in Step 10.

---

## Step 10: Read enrichment results back, filter, and match

**What it does:** Since reading a Clay Table back via the public API 403s
on this plan (same paid-tier gate as the webhook, confirmed live), a human
exports the Contacts table to CSV and the pipeline reads that file.

- **`read_contacts_csv`**: parses the export, keeps only rows with both an
  email and a company, and **drops non-US rows** — this build is US-scoped
  by construction (OSHA is a US regulator), and it happens to be exactly
  what filters out a real false positive (`McDonald's Deutschland LLC`
  turned up in a real export, a known Clay behavior — searching a US brand
  can return unrelated regional subsidiaries).
- **`normalize_company_name` / `match_company_name`**: Clay's own `Company`
  values didn't exactly match what was sent (`Dunkin'` → `Dunkin' Brands` /
  `DunkinBrands` / a zero-width-space variant; `Chick-fil-A` → `Chick-fil-A
  Corporate Support Center`). Strips corporate-suffix noise (Brands,
  Corporate, Corporation, LLC, etc.) before matching, rather than requiring
  exact string equality.
- **Title relevance filter**: a hand-checked keyword list (`training`,
  `learning and development`, `l&d`, `talent development`, `talent
  acquisition`, `environmental health and safety`, `ehs`, `safety`, plus the
  Operations/HR-executive phrases from `persona_tracks.py`) — deliberately
  **not** a bare match on `enablement` or `development`, both of which
  turned out to be generic corporate buzzwords in the real data
  (`Financial Enablement`, `AI Enablement`, `Business Development Manager`,
  `Product Development Manager` — all irrelevant, all would have false-
  positived on a loose match).
- **Corporate-vs-location-level filter**: excludes `Certified Training
  Manager` (Chipotle's real in-restaurant crew-trainer certification — a
  frontline title, not a corporate one, confirmed by dozens of duplicate
  people across different cities under that exact title), `Field`/`Regional`
  qualifiers, `Restaurateur`, `Participant`, and the bare literal title
  `Talent Development Program` (9 different Chick-fil-A people shared that
  exact title with no other qualifier — almost certainly an early-career
  rotational-program cohort, not corporate staff).

**The scope decision behind this whole step:** the original design (3
senior contacts per OSHA persona track, 2 for Hiring) was deliberately
dropped mid-build in favor of "any relevant, corporate-level title" — no
per-track slot selection.

**Mechanically:** all of this is plain Python string matching (lowercase +
substring checks against curated keyword lists) run on the in-memory list
parsed from the CSV, entirely before anything touches HubSpot — no ML, no
API calls. **Honest gap:** `normalize_company_name`/`match_company_name` are
real functions saved in the codebase; the title-relevance and
corporate-vs-location filters were only ever tested live in throwaway
snippets during this build and were never actually committed as reusable
pipeline code.

**If Clay had no plan restrictions (webhook + API read available):** this
filtering logic wouldn't change at all — only the automation around it
would. A script would push each signal's company row to Clay's webhook the
moment it fires, and either poll the Clay API or receive a completion
webhook back, instead of a human clicking Export/Import. The same
normalize/match/relevance/corporate-level checks would still run in Python
on whatever came back.

**Files:** `pipeline/clay_client.py` (`read_contacts_csv`,
`normalize_company_name`, `match_company_name`).

**Result:** 200 raw exported rows → 107 with a usable US email → **18 final
corporate-level, relevant contacts**, spanning Dunkin' Brands, Chipotle
Mexican Grill, Chick-fil-A, Sweetgreen, and Yoshinoya America.

---

## Step 11: Reconcile resolved contacts against real signals

**What it does:** Before pushing anything further, checked which of the 18
contacts' companies actually have a real, current, specific OSHA signal —
since the Tier 1 email draft (Step 6) has a hard "never invent facts" rule,
and a company merely appearing in a tier-classification cache (Step 9) does
not mean its specific signal details are still on hand.

**Why this check has to happen at all: Clay has no concept of OSHA vs.
Hiring, or of a signal, at all.** Clay only ever received a bare
`company_name` string and returns "person + title + email" for that
company — nothing in its output links a contact back to any specific
signal record, or even says which of our two trigger types (if either) is
currently active for that brand. That disconnect is exactly the gap this
step exists to close: reconnecting a Clay-resolved contact to a real,
verified signal by checking HubSpot's actual data and a live OSHA re-scan,
rather than assuming one exists because the company showed up somewhere in
the pipeline before.

**What was found, live:**
- **Chipotle** — already had a real live signal in HubSpot from earlier
  work (Complaint, Minnesota).
- **Dunkin', Chick-fil-A, Yoshinoya** — re-scanning the live OSHA source
  just now found real *current* signals for all three (Dunkin': Complaint;
  Chick-fil-A: Accident; Yoshinoya Beef Bowl: Complaint) — but none of these
  had been ingested into HubSpot yet via `handle_signal()`.
- **Sweetgreen** — genuinely no OSHA signal; its contact exists purely via
  the Hiring path.

**Files:** re-run of `pipeline/signal_scanner.py` filtered to these four
brand names; live HubSpot query against the `qsr_signal` object.

**Result:** of 18 resolved contacts, exactly **one** — Chipotle / Katie
Dake — was ready for the full downstream flow without either fabricating
signal facts or first running a separate signal-ingestion step for the
other three brands.

---

## Step 12: Push the real contact through, end to end

**What it does:** The actual completion of Task #4 (contact resolution)
and Task #9 (end-to-end dry run) — for one real signal, one real
Clay-resolved contact, no placeholders.

**Deliberately did *not* re-run `handle_signal()`** for Chipotle's existing
signal — that would have re-fired the Company Note and Slack alert a second
time for an event already live in HubSpot (those two writes aren't
idempotency-guarded the way the `qsr_signal`/Company upserts are). Instead,
reused the already-tested `_maybe_draft_and_note_first_touch()` function
directly, adding only the contact-creation pieces on top.

**Real API constraint found and fixed on the spot:** HubSpot's
`communication-preferences/v3/subscribe` endpoint documents
`legalBasis`/`legalBasisExplanation` as optional, but this GDPR-enabled
portal 400s without them ("Legal Basis is required for resubscribing a
contact"). Used **`LEGITIMATE_INTEREST_CLIENT`**, not `CONSENT_WITH_NOTICE`
— the contact never opted in; the honest basis for cold B2B outreach to a
business role via public professional information is legitimate interest,
not fabricated consent.

**Files:** `scripts/push_chipotle_contact.py` (new), `pipeline/
hubspot_client.py` (`subscribe_contact`, new).

**Real result, live, 2026-08-19:**

| Field | Value |
|---|---|
| Company | Chipotle Mexican Grill (`443765558499`) |
| Contact | Katie Dake — Director, Learning and Development (`847939678427`) |
| Email | kdake@chipotle.com |
| Legal basis | Subscribed — One to One, Legitimate Interest (Client) |
| Draft subject | "OSHA complaint at your Minnesota location" |
| Draft note | Attached to the Contact |
| Sequence | Enrolled — Tier 1 sequence (`846871794`) |

---

## What's still open

- **Dunkin', Chick-fil-A, Yoshinoya**: real current OSHA signals confirmed
  live on osha.gov, not yet ingested into HubSpot — would need
  `handle_signal()` run for each before their already-resolved Clay contacts
  could get the same full treatment.
- **Pizza Hut**: has a real live signal in HubSpot already, but none of its
  people survived the corporate-level contact filter in the current Clay
  batch.
- **Sweetgreen**: has a resolved contact (Ian Paz) but no OSHA signal — it's
  a Hiring-only brand, out of scope for this path.
- **The other 17 of 18 resolved contacts** (mostly at Chick-fil-A, plus 3
  more at Chipotle itself) haven't been pushed to HubSpot at all yet — Step
  12 was deliberately scoped to the one company with a complete real
  signal+contact pair, per the "one contact end to end" framing for this
  demo, not processed further. No hard technical blocker either way:
  pushing the ones with no HubSpot-ingested signal yet means a generic Note
  instead of a personalized one (a real deviation from this project's
  signal-first principle, not just a cosmetic downgrade); pushing Chipotle's
  other 3 contacts (same real signal as Katie Dake, no technical barrier)
  risks 4 different personalized cold emails landing across one company
  about the same event — the actual reason the original per-track
  contact-selection design existed before it was dropped for simplicity.
