# Hiring signal (Greenhouse/Lever/Workday) — scope and real findings

Built 2026-08-18, the session's pivot target once the OSHA path stalled on
Task #4/Amplemarket (see `HANDOFF.md`). **Planned before building** — a
round of explicit questions was worked through with the user before any
code was written; the corrections that round produced are documented below
alongside the live findings, since both shaped the final design equally.
Same discipline as the OSHA build throughout: every claim below was
checked live, not assumed.

## The core architectural difference from OSHA

OSHA's `industry.search` is a real global scan: give it a NAICS code and a
date range and it returns every matching establishment in the country,
known or not. **None of Greenhouse, Lever, or Workday's public APIs offer
anything equivalent.** All three only serve postings for a company whose
board token (or, for Workday, tenant/shard/site) you already know — there
is no company-search or directory endpoint on any of them. This means the
Hiring path can't be "signal-first" in the same sense the OSHA path is;
it's closer to "signal-first among a hand-curated set of known accounts."
`pipeline/hiring_seed.py` is that curated set. **Adzuna** (see below) is
the one real candidate found for a genuine keyword-based industry scan
that doesn't require knowing the company first — added specifically to
close this gap, per an explicit 2026-08-18 planning decision, though it
remains unverified pending account credentials only the user can create.

## What's actually out there, verified live

Tried ~90 slug guesses against Greenhouse/Lever: every brand in
`accounts_seed.py`'s QSR50/Contenders list (all 28) plus ~60 younger
fast-casual/coffee/bakery chains, with common slug variants. Result: **4
hits, 0 from the large-chain list** — Sweetgreen, Caribou Coffee
(Greenhouse), Blue Bottle Coffee, Insomnia Cookies (Lever). Every large
legacy chain tested — McDonald's, Starbucks, Chick-fil-A, Wendy's,
Domino's, Chipotle, Cava, Dutch Bros, and more — 404s on both. Large QSR
operators overwhelmingly run enterprise ATS (Workday, iCIMS, Taleo) with
no public API; Greenhouse/Lever skew toward companies that grew up on
modern SaaS hiring tooling.

**Workday closes that gap.** Confirmed live via web search + a real,
unauthenticated JSON API (`{tenant}.wd{shard}.myworkdayjobs.com/wday/cxs/
{tenant}/{site}/jobs`, POST — the same endpoint the site's own search box
calls): **Chipotle** (216 open corporate reqs), **Whataburger** (4,290,
almost all frontline), and **Shake Shack** (565) all have real, live
Workday boards. Per an explicit 2026-08-18 scoping decision, this list
stops at 7 companies (4 Greenhouse/Lever + 3 Workday) rather than hunting
further tenants — enough to prove the pattern for a demo, not a
requirement to maximize coverage. Growing it further (Greenhouse/Lever
slug guesses, or web-searching more of the 28-brand list for Workday
tenants) is the natural next step, not done now.

Chipotle's name/domain (`Chipotle Mexican Grill` / `chipotle.com`) matches
`accounts_seed.py`'s QSR50 entry exactly, so a real Hiring signal there
resolves via Rung 1 (real 3,938-site count) and converges onto the same
Company record the OSHA path already created (id `443765558499`) rather
than creating a duplicate.

## Two real, undocumented Workday API quirks found live

1. **`limit` caps at 20** — anything higher 400s with an opaque
   `errorCode: HTTP_400` and no message. Not documented anywhere found;
   discovered by trial (20 works, 50/99/100 all fail). `WORKDAY_PAGE_SIZE`
   in `pipeline/ats_client.py` is set to 20 accordingly.
2. **`total` is only reliable on the first page.** Every page after
   offset=0 reports `total: 0` in the response, even though it still
   returns real `jobPostings` data. A naive pagination loop (stop when
   `offset >= total`) breaks after the second page and silently truncates
   the scan — caught by cross-checking a raw job count against the
   paginated result (Chipotle's real total is 216; the naive loop version
   returned 40 before the fix). `workday_jobs()` now reads `total` once,
   from the first page only, and uses that fixed value as the loop bound.

Both are exactly the kind of "the API doesn't behave the way its own
homepage response implies" finding the OSHA build hit repeatedly
(`docs/osha_ords_imis_notes.md`'s swapped date fields, the no-`<tbody>`
quirk) — worth trusting nothing about pagination behavior without a live
cross-check, on any new source.

## Scoping large Workday boards: per-tenant `jobFamilyGroup` facets

Workday's response includes real facet data (`jobFamilyGroup`, among
others) that can scope a query server-side via `appliedFacets`. Confirmed
live: Whataburger's facets include a "Human Resources" bucket (3 jobs) vs.
"Restaurant Operations" (4,257, the frontline noise) — applying the HR
facet id cuts the query from 4,290 total to 3, verified to return real,
correct titles ("HRIS Specialist," "Regional Field Human Resources
Manager," "Field Talent Acquisition Partner"). **Facet ids are opaque and
tenant-specific** — Chipotle uses 3-letter codes (`HRA`, `OPS`, `MKT`...),
Whataburger spells categories out, Shake Shack has no HR-shaped facet at
all (its facets are State/City/JobCategory, the latter all frontline
roles: Team Members, Shack Management, Shift Managers...). There's no
universal id to guess or reuse across companies, so `job_family_group_id`
is only set in `pipeline/hiring_seed.py` where already found (Whataburger
only) — Chipotle (216 total) and Shake Shack (565 total) are small enough
to paginate in full instead. `WORKDAY_MAX_JOBS` caps the pull either way,
so a future large, unfaceted tenant fails safe rather than pulling
unboundedly.

## The relevance filter — corrected after a real planning catch

**First version (built, then corrected before any real push happened)**
required a seniority marker (Director/VP/Head/Chief) *and* a function
marker (Learning/Training/L&D/People/HR/Talent/Enablement) together,
mirroring `persona_tracks.py`'s bar for who to *contact*. The user caught
a real design mistake in this during planning: **the trigger and the
contact target are two different questions.** Any L&D/Training/Enablement
posting is a real signal regardless of seniority — a Coordinator-level
Training hire is just as real a signal as a Director-level one, arguably a
*stronger* volume signal since leadership openings are rare. Seniority
belongs entirely downstream, at contact resolution
(`persona_tracks.py:HIRING_TRACKS` already correctly encodes Director/VP/
Head/Chief as *who to contact*, separate from what counts as a signal).

**Corrected filter** (`pipeline/hiring_scanner.py:is_relevant_hiring_posting`):
any seniority, function scope narrowed to specifically L&D/Training/
Enablement (dropped the broader People/HR/Talent keywords — per the same
correction, those aren't the trigger described). Real postings found live
that correctly do NOT qualify under this narrower scope: "Manager, Talent
Acquisition" (Sweetgreen), "Sr. People Business Partner (HRBP)" (Insomnia
Cookies), "Field HR Business Partner" (Chipotle), "Regional Field Human
Resources Manager" (Whataburger) — all genuine People-function activity,
but recruiting/generalist HR, not L&D/Training/Enablement specifically.

The one thing the old seniority bar was incidentally doing right — excluding
"Store Manager in Training (MIT)"/"Leader in Training," a ubiquitous
entry-level frontline title pattern across QSR chains (19 real instances
found on Insomnia Cookies' board alone) that isn't an L&D-team hire at all
— is now handled directly via an explicit `TRAINEE_PATTERN` exclusion
(`\bin training\b|\btrainee\b`), since that's a different problem (a title
pattern, not a seniority signal) and needed solving on its own regardless
of the seniority correction.

Verified against 21 synthetic cases (9 true positives now spanning every
seniority level, 12 true negatives including all the real non-qualifying
titles above) — all 21 passed. **Live cross-check across all 7 real
boards' current full listings** (not just the filtered result): the only
raw title matches on learn/train/l&d/enable across all ~2,000 combined
postings are "Manager/Leader in Training" frontline variants — correctly
excluded — confirming the 0-signal live result is real, not a filter bug
silently missing something.

## Adzuna — the industry-wide scan, now live-tuned

Per the planning round: Adzuna is a real, documented, free-tier (1,000
calls/month) job aggregator with a genuine keyword-search API — the one
candidate found that doesn't require already knowing the company (unlike
all three ATS-native sources). Indeed's Publisher API died in 2023
(replacement is an NDA-gated six-figure enterprise deal); LinkedIn has no
public Jobs API and its ToS prohibits scraping — both ruled out.

The user created a free developer account (`developer.adzuna.com`) and
provided real credentials, letting this go from "written against docs" to
actually tuned against live data. Three real corrections came out of that:

1. **`what` does not support inline boolean/OR syntax.** A combined
   `'"learning and development" OR "training manager"'` query silently
   returned 0 results — no error, just nothing. Only `what_phrase` (exact
   phrase) is real; OR-of-phrases means one API call per phrase
   (`ADZUNA_PHRASES`), merged and deduped by job id.
2. **Adzuna's real `category` taxonomy includes `hospitality-catering-jobs`
   and `hr-jobs`** (`GET /v1/api/jobs/us/categories`) — both surface
   genuine hits combined with the phrases above ("Learning & Development
   Manager" at McDonald's, "Training Manager" at Dunkin', "Restaurant
   Training Coordinator" at Chick-fil-A). But **neither category is close
   to precise enough alone** — the first full live run (4 phrases × 2
   categories) returned 401 raw results, and manual inspection showed
   roughly 4% were genuine QSR/restaurant-chain hits. The rest: hotels/
   casinos (Marriott, Four Seasons, MGM, Wynn Las Vegas), banks (5+), law
   firms, food *manufacturers* (Georgia-Pacific, Schwan's, Reser's Fine
   Foods), retail (Walmart ×6), security firms (GardaWorld ×7), aerospace/
   defense (Northrop Grumman, Ford), even a boutique fitness chain
   (`[solidcore]`) whose postings just say "Training Manager" plain,
   missing the `PERSONAL_TRAINING_PATTERN` exclusion.
3. **Real fix, per an explicit user decision**: reuse Rung 5's classifier
   (`pipeline/tier_classifier.py:classify_tier`, Claude Haiku + web search)
   as the industry-precision filter (`pipeline/hiring_scanner.py:
   _is_restaurant_chain`), rather than a hand-written keyword list — it
   already asks exactly "does this name resolve to a real restaurant
   chain?" for site_count tiering, and its permanent per-brand disk cache
   means a hit here is a hit later too when `handle_hiring_signal` resolves
   the same company's tier. **Found a second real precision gap while
   wiring this in**: `classify_tier` returned `found=true` for "Reser's
   Fine Foods, Inc." (a food manufacturer) with `tier_hint="Disqualified"`
   — some real but tiny (≤5 location) restaurant-adjacent presence tied to
   the brand. A bare "did it find anything" check would have let this
   through; `_is_restaurant_chain` now runs the result through
   `tier_for_lookup()` (already treats "Disqualified" as "not a prospect")
   instead of inventing a second rule for the same thing.

**A real operational gap found live, now handled**: the first attempt to
run this against all ~150 unique companies hit a genuine Anthropic API
billing failure (`"Your credit balance is too low"`) partway through and
**crashed the whole script** — `_is_restaurant_chain` only checked whether
`ANTHROPIC_API_KEY` was *set*, not whether calls to it actually
*succeeded*, so a persistent failure (billing, auth) would have retried
identically for every remaining company before finally dying. Fixed to
catch the failure once, print one clear message, and short-circuit every
remaining lookup in that scan run (`_UNAVAILABLE` sentinel) rather than
paying the latency to fail the same way ~150 more times. **This is still
blocking full verification** — the account behind the project's
`ANTHROPIC_API_KEY` needs more credits (Anthropic Console → Plans &
Billing) before the remaining ~150 companies from that first 401-result
run can be classified. What's confirmed so far (3 companies were
already disk-cached from the partial first attempt, before credits ran
out): **DIG INN** (real fast-casual chain, "Learning & Development
Associate") and **McDonald's** ("Learning & Development Manager") both
correctly pass; **Reser's Fine Foods** correctly excluded as
Disqualified-tier. 2 real, precise signals out of the original 401 — the
filter is doing its job on every case checked so far, just not yet run to
completion.

`scripts/handle_hiring_signals.py` deliberately does NOT include the
Adzuna scan — only `scripts/scan_hiring_signals.py`'s read-only dry run
does. `search_jobs()`'s field mapping (`company.display_name`, `created`,
`redirect_url`, etc.) is now confirmed correct against real payloads, not
just docs.

## What's wired vs. not

Mirrors the OSHA path's steps 2/3/5 (`docs/signal_first_architecture.md`),
skipping the OSHA-specific pieces (franchisee-name collapsing, brand-wide
history) that don't apply — ATS board names are already canonical.

- **Scan** — done, live against 7 real boards across 3 ATSs.
  `pipeline/ats_client.py`, `pipeline/hiring_scanner.py`,
  `pipeline/hiring_seed.py`.
- **Discovery (Adzuna)** — built, gated, unverified pending user-created
  credentials. `pipeline/adzuna_client.py`.
- **Tier** — reused as-is (`pipeline/site_count.py`, `pipeline/tiering.py`),
  confirmed no changes needed.
- **Push** (`pipeline/signal_handler.py:handle_hiring_signal`) — done:
  `qsr_signal` object (pre-existing `Hiring` type), Company Note, and the
  `hiring_signals` Slack channel all fire together. Verified end-to-end
  with a mocked HubSpot/Slack layer (real code path, fake I/O) rather than
  pushing a fabricated posting into the live portal — no real qualifying
  posting existed to push at build time.
- **`source_activity_nr`/`source_citation_id`** — reused rather than a
  schema migration: a Hiring signal's dedup key is
  `"{ats_source}:{posting_id}"` (e.g. `"workday:JR-2025-00101221"`) in
  `source_activity_nr`, `source_citation_id` left null.
- **Sequence enrollment** — Tier 3 only, gated behind
  `HUBSPOT_HIRING_TIER3_SEQUENCE_ID`, deliberately separate from
  `HUBSPOT_TIER3_SEQUENCE_ID` (that one is named "QSR T3 - OSHA Trigger,"
  wrong copy context). Unset until a human creates that sequence in the
  HubSpot UI. No Fat/Cat-equivalent exclusion exists for Hiring, so tier is
  the only gate.
- **Contact resolution** — same Task #4/Amplemarket blocker as OSHA.
  Confirmed with the user: company-level enrichment (name → domain/
  firmographics) and contact-level enrichment are two separate stages,
  mirroring Clay/Amplemarket's own Company-table/People-table split — the
  Hiring path already has a clean canonical name for every ATS-native
  signal (unlike OSHA's noisy establishment strings), so the company-level
  stage should be easier here, not harder. Noted for when Task #4 unblocks;
  doesn't change anything built now.
- **Tier 1 personalized first-touch** — not built this session, same as
  before. Needs its own copy-rules pass.

## GTM motion — Slack/Note template

Unchanged from the first pass (`pipeline/signal_handler.py:_build_hiring_lines`):

```
🏢 Company: <name>
🚨 Signal: Hiring
📅 Posted: <date>
💼 Role: <job title>
🧭 Team: <Lever only, when present>
📍 Location: <when present>
🏷️ Tier: <1/2/3>
👤 Suggested Contact: <placeholder, same as OSHA>
🔗 Source: <posting URL>
```

## Files

`pipeline/ats_client.py` (Greenhouse + Lever + Workday HTTP),
`pipeline/adzuna_client.py` (Adzuna, unverified), `pipeline/hiring_seed.py`
(the 7-board seed list), `pipeline/hiring_scanner.py` (scan + relevance
filter + Adzuna discovery), `pipeline/signal_handler.py:handle_hiring_signal`
(push), `scripts/scan_hiring_signals.py` (dry run, both sources),
`scripts/handle_hiring_signals.py` (live push, ATS-native only, same
`DEFAULT_LIMIT` safety pattern as `scripts/handle_signals.py`).
