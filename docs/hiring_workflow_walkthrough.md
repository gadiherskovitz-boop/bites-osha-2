# Hiring Signal — End-to-End Workflow Walkthrough

This walks through the Hiring signal path start to finish, as it actually
exists and was actually run — not the plan, the real thing, with real
company/contact names and real HubSpot object IDs from actual live runs.
It's independent of the OSHA signal path's own walkthrough — even where
code is genuinely shared (tiering), this document describes it fresh, on
its own terms, for how it behaves in the Hiring context specifically.

**Ordering: strict runtime chronology**, not build order. When a real
Hiring signal moves through this system today, the true order is: scan two
sources for a live posting (Steps 1–2) → tier the account (Step 3) → push
Company/signal/Slack/Note (Step 4) → export companies for enrichment
(Step 5) → a human enriches contacts in Clay, outside this codebase
(Step 6) → the enriched contacts get populated back into HubSpot with a
drafted email, consent record, and sequence enrollment (Step 7). This is
also the order these pieces were actually exercised for real, which
happens to line up with build order this time — unlike the OSHA path,
nothing here was built and tested against a placeholder for weeks before
the step before it existed.

---

## Step 1: Scan known job boards (Greenhouse, Lever, Workday)

**What it does:** Polls a hand-curated list of 7 companies' public job
boards for a live posting in Learning & Development, Training, or
Enablement — the trigger is a company actively hiring to build out that
function, at any seniority level.

**Technology and why:** Three separate unauthenticated JSON APIs, all
using the same endpoint the site's own search box calls:
- **Greenhouse**: `boards-api.greenhouse.io/v1/boards/{token}/jobs`
- **Lever**: `api.lever.co/v0/postings/{slug}?mode=json`
- **Workday**: `{tenant}.wd{shard}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs` (POST)

**The core constraint driving this whole step's shape:** none of the three
offer a "search all companies" endpoint — each only returns postings for a
company whose board identifier you already know. There is no way to
discover a new company this way; `pipeline/hiring_seed.py`'s 7-entry list
*is* the entire discoverable universe for this step, and it's a hand-built
list, not a query result.

**Deterministic relevance filter** (`is_relevant_hiring_posting` in
`pipeline/hiring_scanner.py`): a posting qualifies if its title (or, for
Lever, its `categories.team` field) matches `learning`, `training`, `l&d`,
`enablement`, or `organizational development` (word-boundary regex) — at
**any** seniority — and does **not** match `\bin training\b|\btrainee\b`.
No AI involved in this step at all; pure regex.

**Challenges hit, in the order they happened:**
1. **Board discovery was mostly a dead end.** Tried ~90 candidate slugs
   against Greenhouse and Lever — every brand in `accounts_seed.py`'s
   28-brand QSR50 list, plus ~60 younger fast-casual/coffee chains. Only 4
   hit: Sweetgreen, Caribou Coffee (Greenhouse), Blue Bottle Coffee,
   Insomnia Cookies (Lever) — zero from the large-chain list. Large QSR
   operators run enterprise ATS (Workday, iCIMS, Taleo) with no public API;
   Greenhouse/Lever skew toward companies built on modern SaaS tooling.
2. **Workday added specifically to close that gap** for large chains —
   found via targeted web search (not slug-guessing, since Workday needs
   three pieces of config: tenant, shard, and site) — Chipotle, Whataburger,
   and Shake Shack all confirmed to have real, live Workday boards.
3. **Two real, undocumented Workday API bugs, both found live:**
   - `limit` silently 400s above 20 — the site's own UI paginates in
     chunks of 20, and nothing documents this anywhere. `WORKDAY_PAGE_SIZE`
     in `pipeline/ats_client.py` is hardcoded to 20 because of this.
   - `total` in the response is only correct on the *first* page — every
     later page reports `total: 0`, even though real job data still loads.
     A naive "stop when `offset >= total`" loop breaks after the second
     page and silently truncates the scan; this was caught by
     cross-checking a raw title count against the paginated result and
     finding Chipotle's real total (216) didn't match what the loop
     returned (40). Fixed by reading `total` once, from the first page
     only, and using that as the fixed loop bound.
   - Whataburger also needed per-tenant `jobFamilyGroup` facet scoping —
     its board has 4,290 total postings, almost all frontline "Restaurant
     Operations" reqs; scoping to its "Human Resources" facet id cuts that
     to 3. Facet ids are opaque and tenant-specific (Chipotle uses 3-letter
     codes, Shake Shack has no HR-shaped facet at all), so this is only
     hardcoded for the one tenant it was actually found for.
4. **The relevance filter's first version was wrong, caught before it
   shipped.** It originally required a seniority marker (Director/VP/
   Head/Chief) *and* a function marker together, mirroring the persona
   track used for contact resolution. This conflated two different
   questions: what counts as a signal vs. who to contact. Corrected to
   drop the seniority requirement entirely — a Coordinator-level Training
   hire is just as real a signal as a Director-level one. The one thing
   the seniority bar had accidentally been catching — "Store Manager in
   Training (MIT)," a ubiquitous frontline title, not an L&D hire at all —
   needed its own fix regardless, via the explicit `TRAINEE_PATTERN`
   exclusion.

**Files:** `pipeline/ats_client.py` (the three HTTP clients),
`pipeline/hiring_seed.py` (the 7-board list), `pipeline/hiring_scanner.py`
(`scan_hiring_signals`, `is_relevant_hiring_posting`). Runnable via
`scripts/scan_hiring_signals.py`.

**Why built this way — the trade-off:** the seed list is deliberately kept
small (7 companies) rather than expanded further, an explicit scoping
decision — enough to prove the pattern for a demo, not a claim of
maximizing coverage. Growing it (more Greenhouse/Lever slug guesses, more
Workday tenant searches) is real, available, offline work, just not done.

**Real result, live, 2026-08-19:** **0 signals** across all 7 boards right
now — cross-checked against the raw job data, not just the filtered
output, to make sure this is a real result and not a filter bug: across
all 7 boards' current listings (~2,000 combined postings the day this was
last measured), the only titles matching `learn/train/l&d/enable` at all
are "Manager/Leader in Training" frontline variants, correctly excluded.
Leadership- and Coordinator-level L&D openings are genuinely rare events;
0 on a given day at 7 companies is not surprising.

---

## Step 2: Discover via Adzuna keyword search (industry-wide layer)

**What it does:** The one mechanism in this pipeline that can find a
company *without already knowing it* — a keyword search across Adzuna's
aggregated job listings for the same L&D/Training/Enablement signal Step 1
looks for, scoped by Adzuna's own occupational categories, then filtered
down to real restaurant/QSR chains.

**Why this exists at all:** Step 1's board-token requirement means it can
never discover a new company. LinkedIn has no public Jobs API and its ToS
prohibits scraping; Indeed's Publisher API was discontinued in 2023
(replacement is an NDA-gated enterprise deal). Adzuna is genuinely
free, documented, and doesn't require knowing the company first — the only
real candidate found.

**Technology and the real query shape, after live tuning:**
- `GET api.adzuna.com/v1/api/jobs/us/search/{page}` with `what_phrase`
  (exact phrase match) — one call per phrase (`"learning and
  development"`, `"training manager"`, `"training coordinator"`,
  `"enablement"`) crossed with two real Adzuna categories
  (`hospitality-catering-jobs`, `hr-jobs`, from `GET .../categories`),
  merged and deduped by job id.
- Passed through the same `is_relevant_hiring_posting` filter as Step 1,
  plus an Adzuna-specific `PERSONAL_TRAINING_PATTERN` exclusion (fitness
  studios' "Personal Training Manager" postings), plus an AI
  industry-precision gate (below).
- **The industry-precision gate**: `pipeline/hiring_industry_classifier.py`
  — Claude **Haiku 4.5** with web search, asked exactly one narrow
  question: "is this company's primary business running restaurant/QSR
  locations?" Permanently cached per company name on disk
  (`output/restaurant_chain_cache/`).

**Challenges hit, in the order they happened:**
1. **Combined boolean-OR query syntax silently returns nothing.** A single
   `what` query like `'"learning and development" OR "training manager"'`
   returned 0 results with no error — only `what_phrase` (one exact phrase
   per call) is real. Adzuna's own docs don't call this out.
2. **The first full live run (4 phrases × 2 categories) returned 401 raw
   results, and manual inspection showed only ~4% were genuine QSR/
   restaurant hits.** The rest: hotels/casinos (Marriott, Four Seasons,
   Wynn Las Vegas), banks, law firms, food *manufacturers* (Georgia-Pacific,
   Reser's Fine Foods), retail (Walmart ×6), security firms (GardaWorld
   ×7), aerospace/defense, and a boutique fitness chain ("[solidcore]")
   whose plain "Training Manager" titles slipped past the personal-training
   pattern.
3. **First fix attempt reused `pipeline/tier_classifier.py`'s
   `classify_tier()` (the OSHA path's own Rung 5 classifier) as the
   precision filter — and it was live-verified to be wrong.** Fed
   "Marriott Hotels Resorts," it found a real, correct 321-US-location
   count and accepted it as satisfying the question, because its prompt
   *presupposes* the input already is a restaurant chain ("how many
   locations does the restaurant chain X operate?") — correct for OSHA,
   where every establishment name is restaurant-NAICS-scoped by
   construction, wrong here.
4. **Explicit decision: don't fix that prompt in place.** `classify_tier`
   is shared, already-verified, presentation-critical OSHA infrastructure;
   changing it to fix an Adzuna-specific problem was judged not worth the
   regression risk. `pipeline/hiring_industry_classifier.py` was built as
   a small, separate, single-purpose classifier instead — its own prompt,
   its own cache, zero changes to the OSHA file (confirmed via `git diff`
   showing no changes to `tier_classifier.py`).
5. **The new classifier fixed the cases it was built for, live-verified**
   (Marriott, Circle K, "[solidcore]" all correctly excluded; McDonald's,
   Chick-fil-A, DIG INN still correctly included) **but a fresh full run
   surfaced two more wrong ones**: "Sam's East" (a real Sam's Club/Walmart
   legal entity — Sam's Club does sell some prepared food, same
   food-service-adjacent failure shape as Marriott) and "Copeland" (an
   HVAC company posting "Executive Enablement Assistant" — the
   classifier's web search found "Copeland's," a real but *unrelated*
   Cajun restaurant chain with a similar name, and matched the wrong
   company). Fixed with an explicit, small, documented denylist
   (`KNOWN_NOT_RESTAURANT_CHAINS`) checked before the AI call, rather than
   hoping a retry would land differently.
6. **A real operational bug, found running the classifier against the
   full ~150-company backlog: an exhausted Anthropic API credit balance
   crashed the whole script.** `_is_restaurant_chain` only checked whether
   `ANTHROPIC_API_KEY` was *set*, not whether calls to it actually
   *succeeded* — a persistent billing failure would have retried
   identically for every remaining company before finally dying. Fixed to
   catch `anthropic.APIStatusError` specifically and short-circuit all
   remaining lookups in that run (`_UNAVAILABLE` sentinel) — but a
   *different*, one-off failure (a malformed-JSON response for one
   specific company, "Bonita Bay Club") is deliberately handled
   differently: only that one company gets excluded, the run continues,
   since a transient glitch on one request doesn't mean every other
   request will fail the same way.

**Files:** `pipeline/adzuna_client.py` (HTTP client),
`pipeline/hiring_industry_classifier.py` (the precision gate),
`pipeline/hiring_scanner.py` (`scan_adzuna_hiring_signals`,
`_is_restaurant_chain`, `KNOWN_NOT_RESTAURANT_CHAINS`).

**Why built this way — the trade-offs accepted:** fails **closed**, not
open, when the classifier can't run (no key, or a real call failure) —
the opposite of Step 3's Rung 5 gate, and deliberately so: there, a
missing key means "fall through to a safe Tier 3 default"; here, the
entire point of the function is cutting real noise, so "can't classify"
must not silently mean "include everything." The denylist is a pragmatic,
small patch for confirmed-wrong cases rather than building a bigger
semantic company-resolution system — accepted as a residual, ongoing risk
(a case not yet in the denylist could still slip through) rather than
solved generally.

**Real result:** **22 real signals were pushed live to HubSpot** from this
step on 2026-08-18 (see Step 4's IDs). A **fresh re-run today, 2026-08-19,
returns 20** — the two "Steak 'n Shake" postings from the original run no
longer appear (Adzuna is a live rolling scan of currently-open postings;
these are not the same kind of permanent historical record OSHA's data
is, so a re-scan can genuinely return fewer results than an earlier one,
not a sign of a bug). The 20 companies currently returned: DIG INN Support
(×2 postings), McDonald's (×3), Abby's Pizza (×2), Dunkin' (×1), Lettuce
Entertain You Restaurants (×3), Popeyes (×1), Yoshinoya Companies (×1),
Otg (×2), Mendocino Farms (×1), Inspire Brands (×2), Chick-fil-A (×1),
Dine Brands Global (×1).

(One small, verified naming quirk worth knowing: the real airport-dining
operator OTG renders as **"Otg"** throughout this pipeline's output,
including in HubSpot. Adzuna's own company field returns it in all caps;
the shared brand-name-cleaning function this path reuses title-cases
unrecognized acronyms rather than preserving them — confirmed live,
`brand_name("OTG")` returns `"Otg"`. Cosmetic, not a functional bug.)

---

## Step 3: Tier the account (site_count waterfall)

**What it does:** Turns a company name into a `site_count` and a tier
(Disqualified / Tier 3 / Tier 2 / Tier 1), via the same cheap-first
waterfall used elsewhere in this project — described here on its own
terms for what it actually resolved for real Hiring-sourced companies.

**The waterfall, cheapest first:**
- **Rung 1**: a static, sourced dict of ~28 real QSR brands with real site
  counts (`pipeline/accounts_seed.py`), fuzzy-matched against the company
  name. Instant, deterministic, no external call.
- **Rung 4**: Wikidata's "number of branches" property (`P8368`), free,
  no-auth.
- **Rung 5**: Claude **Haiku 4.5** with web search
  (`pipeline/tier_classifier.py:classify_tier`), run once per brand and
  permanently cached, only for brands Rungs 1/4 miss. Classifies a tier
  *band*, not an exact count, and rounds up at a band boundary rather than
  discarding an uncertain answer.
- Anything no rung resolves defaults to **Tier 3**.

Confirmed live: this waterfall needed **zero code changes** to work for
Hiring — ATS board names are already clean canonical brand names (unlike
OSHA's noisy establishment strings), so no name-collapsing step is needed
before tiering runs.

**Real result, verified live against the companies this path actually
pushed:**

| Company | Tier | site_count | Rung |
|---|---|---|---|
| McDonald's | Tier 1 | 13,706 | 1 (QSR50 seed) |
| Dunkin' | Tier 1 | 9,999 | 1 (QSR50 seed) |
| Chick-fil-A | Tier 1 | 3,287 | 1 (QSR50 seed) |
| Popeyes | Tier 1 | 3,196 | 1 (QSR50 seed) |
| DIG INN Support | Tier 3 | 36 | 5 (LLM) |
| Abby's Pizza | Tier 3 | 35 | 5 (LLM) |
| Mendocino Farms | Tier 2 | 99 | 5 (LLM) |
| Yoshinoya Companies | Tier 2 | — | 5 (LLM, band only, no count) |
| Steak 'n Shake (one duplicate record) | Tier 1 | 392 | 5 (LLM) |
| Steak 'n Shake (other duplicate record) | Tier 1 | — | 5 (LLM, band only) |
| Lettuce Entertain You Restaurants | Tier 1 | — | 5 (LLM, band only) |
| Otg | Tier 1 | — | 5 (LLM, band only) |
| Dine Brands Global | Tier 1 | — | 5 (LLM, band only) |
| Inspire Brands | **Tier 3** | — | 5 (LLM, band only) |

**A real, honestly-surprising result worth calling out**: Inspire Brands —
the real corporate parent of Arby's, Buffalo Wild Wings, Sonic, and Jimmy
John's, unambiguously a large, multi-thousand-location operator — resolved
to **Tier 3**, not Tier 1. The likely cause: Rung 5's prompt asks about
"the restaurant chain X," and Inspire Brands isn't itself a single
consumer-facing restaurant chain, it's a multi-brand holding company — the
model most likely under-counted or declined to find a clean location
figure for the parent entity itself, rather than summing its brands. Not
fixed; noted as a real limitation of feeding a multi-brand parent company
name into a classifier built around single-brand chains.

**Files:** `pipeline/site_count.py`, `pipeline/tier_classifier.py`,
`pipeline/accounts_seed.py`, `pipeline/tiering.py` — none modified for
this path.

---

## Step 4: Push — Company, `qsr_signal` object, Slack, Note

**What it does:** For every signal that clears Steps 1–3, three things
fire together: the Company is created or updated in HubSpot, a `qsr_signal`
custom object is written as the system of record, and a Slack alert +
Company Note go out.

**Fields, Hiring-specific** (`_build_hiring_lines` in
`pipeline/signal_handler.py`) — different from what a citation/inspection
signal carries: Company, Signal ("Hiring"), Posted date, Role (the job
title), Team (Lever only, when present), Location (when present), Tier,
Source URL.

**Deterministic dedup key**: `qsr_signal`'s idempotency check
(`source_activity_nr`) is reused rather than adding a new schema field —
populated as `"{ats_source}:{posting_id}"` (e.g.
`"adzuna:5760781260"`), giving every real posting a stable, unique key the
same way an OSHA activity number does.

**Challenges hit — a real, live duplicate-company problem, found by
re-querying HubSpot directly rather than trusting the original push log:**
pushing 22 signals in one script run, several for the same company back
to back, created **duplicate Company records for 4 of the 13 real
companies**:

| Company | Duplicate IDs | Real cause |
|---|---|---|
| DIG INN Support | `444241594609`, `444192278754` | Same race-condition pattern as below |
| Steak 'n Shake | `444224675019`, `444194153688` | Adzuna returned two *different* location-suffixed names for the same brand ("...Edwardsville" vs. "...S Orange Blossom Trail Orlando"); the name-cleaning logic (built for OSHA's franchisee-suffix patterns) doesn't recognize this pattern |
| Lettuce Entertain You Restaurants | `444186889437`, `444186889439` | Same exact name string on all 3 postings, but pushed rapidly back-to-back — HubSpot's company search likely hadn't finished indexing the just-created record before the next lookup ran, so the dedup check missed it |
| Otg | `444250530030`, `444206690537` | Same race-condition pattern |

This wasn't fully caught and reported at push time — only the Steak 'n
Shake and Lettuce Entertain You cases were flagged in the moment; DIG INN
and Otg's duplication was only confirmed by re-querying HubSpot directly
while writing this document. All four are cosmetic (no data loss, no
wrong tier/site_count on either copy of a pair), left for manual merge —
same category of issue as two known pre-existing orphaned duplicates this
path is unrelated to but ran into: a domain-less, tier-less "McDonald's"
record (`441333328089`) and a domain-less, tier-less "Chick-fil-A" record
(`441827909872`), both predating this project's Hiring work; every real
Hiring push correctly resolved to the *other*, properly-domained record
for both brands instead.

**Files:** `pipeline/signal_handler.py` (`handle_hiring_signal`,
`_build_hiring_lines`, `_maybe_enroll_hiring_tier3`), `pipeline/
hubspot_client.py`, `pipeline/slack_client.py`. Runnable via
`scripts/push_adzuna_hiring_signals.py` (no default batch limit, unlike
the OSHA equivalent — an explicit choice to push the whole clean result
set at once for this one real run).

**Real result, live, verified 2026-08-19:** **22 real `qsr_signal` records
with `signal_type = "Hiring"`** exist in this HubSpot portal right now —
confirmed by direct query, exact IDs range from `446419817666` to
`446508676309`. Counting every Company record associated with one of
these 22 signals (including the 4 duplicate pairs above) gives **17
distinct company records** carrying a real Hiring signal — **13 real,
distinct brands** once the 4 duplicate pairs are collapsed back to one
each. Zero overlap with the OSHA path's own signal-bearing companies.

Each `handle_hiring_signal()` call also attempts Tier 3 sequence
enrollment (`_maybe_enroll_hiring_tier3`) — every one of these 22 pushes
returned `{"attempted": False, "reason": "no resolved contact yet"}`,
since no automated contact resolution exists yet (see Steps 5–7).

---

## Step 5: Export companies for enrichment

**What it does:** Reads the current Adzuna scan result and writes the
unique company names to a CSV, ready for a human to take into Clay.

**Why this step exists at all — the real constraint:** Task #4 (automated
contact resolution) was originally scoped around **Amplemarket**, then
**Clay**, but Clay's real-time, script-callable enrichment path needs a
paid plan on this workspace, and the trial expired mid-project. Upgrading
wasn't something the user was willing to pay for on an assignment. So the
mechanism is a deliberate, cost-driven **manual CSV-out/CSV-in loop**
around the Clay app instead of an automated API call — a scope decision,
not a technical dead end. If a paid plan existed, this step and Step 7's
company/contact resolution would be one automated call instead of a
human-triggered export/import; the filtering and matching logic
downstream wouldn't need to change.

**Format**: two columns, `company_name` and `company_domain` — domain left
blank for every row, since Adzuna-sourced signals never carry one (unlike
the 7 ATS-native boards, which have a known domain from
`pipeline/hiring_seed.py`).

**Files:** `scripts/export_hiring_companies_csv.py`.

**Real result:** `output/hiring_companies_for_clay.csv`, **14 unique
company names** (13 real brands, plus the Steak 'n Shake naming split from
Step 4 counted as two separate rows since the export runs off the same
uncollapsed Adzuna names): Abby's Pizza, Chick-fil-A, DIG INN Support,
Dine Brands Global, Dunkin', Inspire Brands, Lettuce Entertain You
Restaurants, McDonald's, Mendocino Farms, Otg, Popeyes, Steak 'n Shake
Edwardsville, Steak 'n Shake S Orange Blossom Trail Orlando, Yoshinoya
Companies.

---

## Step 6: Manual Clay enrichment (outside this codebase)

**What it does:** The user takes the Step 5 CSV into their own Clay
workspace, resolves each company's domain, finds real people at each
company, and enriches their work email — entirely in the Clay app UI, no
pipeline code involved.

**Real result** (`output/output:clay_hiring_signal_contacts.csv`, verified
by direct read, 16 real rows): people found at 5 of the 14 exported
companies —

- **Chick-fil-A** (8 people): Kramer J. (Director of Learning and
  Development), Darya Fields, SPHR (Director, Learning and Development),
  Kelley Sorrow (Sr Director, L&D Operations and Transformation), Courtney
  Y. (Learning and Development, TDP), Kaity Scanlan, SHRM-CP
  (Administrative Coordinator for L&D Operations), Callie Whigham
  (Principal Learning and Development Lead), Rachel Bath (Sr. Experience
  Lead, Staff Learning and Development), Bryan Kelly (Project Lead - EHS
  Manager, no email found)
- **Inspire Brands** (4 people): Melissa McCornack (Sr. Manager Learning
  and Development), Renee Malone (Training Enablement, Manager), Abbey
  Sattele (Senior Executive Assistant to the COO of Arby's), Jessica
  Carreon, MS, CHST, EMT (EHS Manager, no email found)
- **Dine Brands Global**, found under its pre-2018 name "DineEquity"
  (2 people): Sonia Harris (Senior Manager, Learning and Development, no
  email found), and separately Tyler Heid at "Dine Brands Global" directly
  (Manager, Learning and Development, real email at applebees.com)
- **Lettuce Entertain You** (1 person): Cheryl Symank (Learning and
  Development Manager)
- **"popeyes"** (1 person): Duan Garner (Senior Learning and Development
  Manager, no email found)

**A real CSV data-quality artifact worth flagging**: one row's name,
"Jessica Carreon, MS, CHST, EMT," got split by Clay/LinkedIn's own name
parsing into First Name "Jessica" and Last Name **"EMT"** — the trailing
credential, not her actual surname. This propagated into the HubSpot
contact created in Step 7 (verified live: contact `847936000235` is
recorded as "Jessica EMT").

**4 of the 16 rows have no email at all** (Bryan Kelly, Jessica
Carreon/EMT, Sonia Harris, Duan Garner) — real, normal prospecting
attrition, not a bug.

**9 of the 14 exported companies got zero contacts** in this batch: DIG
INN Support, McDonald's, Abby's Pizza, both Steak 'n Shake rows, Dunkin',
Yoshinoya Companies, Otg.

---

## Step 7: Populate HubSpot — contact, draft, Note, consent, sequence

**What it does:** Reads the Step 6 CSV and, for each contact with a usable
email: resolves the correct existing Company (or creates one), creates
the Contact, drafts a personalized first-touch email, writes it as a Note
on the Contact, records a GDPR consent basis, and enrolls the contact in
a real HubSpot Sequence.

**Technology:**
- **Company resolution** (`resolve_company`): domain match first (via the
  contact's own email domain — reliable, since a company only needs its
  domain backfilled once), then an exact name match, then a **fuzzy** name
  match (`find_company_by_name_fuzzy` — HubSpot's own `CONTAINS_TOKEN`
  search on the name's first word, accepted only if one name is a
  normalized prefix of the other). No hardcoded per-company synonym list.
- **Email draft**: `pipeline/hiring_personalize.py:draft_first_touch`,
  Claude **Sonnet 5** (not Haiku — this runs once and its output *is* the
  deliverable, so copywriting quality matters more than cost, the same
  trade-off as the OSHA path's own Tier 1 email). Copy rules in
  `docs/hiring_email_rules.md`: sell the problem not the product, 140-word
  cap, opens on the specific role posted (not an invented incident), one
  sentence on the real diagnostic tension (desktop-built training vs. a
  deskless workforce), failure modes chained causally rather than listed,
  one sentence naming real downstream stakes (injuries, quality,
  compliance — allowed here, same as OSHA, as long as it's a general truth
  and not an accusation aimed at the specific prospect), a required
  company-branded video reference, and a close that always ends on a
  direct question.
- **Signal reconstruction for the draft** (`build_signal_from_company`):
  pulls the real originating job posting from the `qsr_signal` record
  already associated with that company in HubSpot
  (`pipeline/hubspot_client.py:get_company_qsr_signal`, a new function),
  rather than a value hardcoded per company. `signal_summary` is always
  formatted `"Hiring - {job_title} - {account_name}"`
  (`handle_hiring_signal`'s own composition), so the job title is
  recovered exactly by stripping the known prefix/suffix — safe even when
  the title itself contains " - " internally (several real ones do, e.g.
  "Field Training Manager - Arby's(Western US Remote)").
- **Consent**: `subscribe_contact` — `POST
  communication-preferences/v3/subscribe`, `legalBasis:
  LEGITIMATE_INTEREST_CLIENT` (a cold-outreach contact never opted in, so
  "legitimate interest" is the honest basis, not fabricated consent).
  Required before enrollment or it 400s with `SequenceError.UNSUBSCRIBED`.
- **Sequence enrollment**: `enroll_in_sequence`, into a single real
  sequence, **"QSR Hiring Signal"** (id `847727806`) — both Tier 1 and
  Tier 3 contacts go into the same one, an explicit demo-scoping decision
  (the OSHA path uses two separate sequences per tier; this one doesn't).

**Challenges hit, in the order they happened:**
1. **A real 400 the first time this ran**: `upsert_signal_company(name,
   domain, {})` — an empty properties dict — 400s with `"No properties
   found to update, please provide at least one"` whenever the company
   was found directly by domain (nothing left to backfill). Hit on
   Chick-fil-A, which already had a domain from the OSHA path's earlier,
   unrelated work. Fixed by always passing a real, if redundant, property
   (`{"disqualified": "false"}`).
2. **No guard against re-processing an already-created contact.** The
   first real run crashed partway through (the bug above); re-running
   from the top would have written a second, duplicate Note for the one
   contact that had already succeeded. Fixed with an explicit
   `already_processed` check before drafting/enrolling again.
3. **A cross-session shadowing bug, found and fixed on request.** A
   *second* `subscribe_contact()` function had been added to
   `pipeline/hubspot_client.py` elsewhere (the parallel OSHA-side session,
   working in the same file) and was being silently shadowed by this
   path's own version — Python just uses whichever definition comes last
   in the file. The other version was judged more correct (it uses
   `LEGITIMATE_INTEREST_CLIENT`, the honest legal basis for cold outreach,
   where this path's original version had used `CONSENT_WITH_NOTICE` —
   consent that was never actually given). Resolved by deleting this
   path's duplicate and keeping the other one; `subscribe_contact`'s
   current signature and behavior in `pipeline/hubspot_client.py` is that
   surviving version.
4. **Generalization pass, done on request** ("build it right" rather than
   leave two hardcoded dicts in place): the first working version mapped
   CSV company-name strings to canonical names via a fixed dict scoped to
   exactly the 5 companies in the first CSV, and looked up each
   company's representative job posting from a second fixed dict of the
   same 5. Both were replaced with the general mechanisms described above.
   Verified live against the real cases: "Chick-fil-A Corporate Support
   Center," "Inspire," "popeyes," and "Lettuce Entertain You" all
   correctly fuzzy-matched to their real HubSpot records. One real,
   honestly-reported limit found in the same pass: **"DineEquity" could
   not be fuzzy-matched to "Dine Brands Global"** — that's a 2018
   corporate rebrand, not a name variant, and no string-similarity
   heuristic can bridge it without either a domain to match on (Sonia
   Harris, the one contact with that company string, has no email) or
   hardcoded historical knowledge. Left as a known limitation rather than
   solved.
5. **A real Python-version bug caught immediately by testing**: the
   rewritten script used bare `str | None` syntax without `from __future__
   import annotations`, which crashes on this project's Python 3.9 (that
   syntax needs 3.10+ unless annotations are postponed). One-line fix.
6. **A real HubSpot deliverability block, correctly left alone**: Rachel
   Bath's enrollment (`rachel@chick-fil-a.com`) failed with
   `SequenceError.RECIPIENT_PREVIOUSLY_BOUNCED` — HubSpot's own
   bounce-protection refusing to send to an address with a prior bounce
   on file. Not overridden; her contact, draft, and Note were all created
   successfully, only the sequence enrollment is blocked.

**Files:** `scripts/populate_hiring_contacts_from_clay.py`, `pipeline/
hubspot_client.py` (`find_company_by_name_fuzzy`, `get_company_qsr_signal`,
`subscribe_contact`, `create_contact`, `enroll_in_sequence`), `pipeline/
hiring_personalize.py` (`draft_first_touch`).

**Real result, live, verified 2026-08-19** (re-queried directly from
HubSpot, not read from the original run log):

| Contact | Company | Title | Contact ID | Enrolled? |
|---|---|---|---|---|
| Melissa McCornack | Inspire Brands | Sr. Manager Learning and Development | `848026402031` | Yes |
| Kramer J. | Chick-fil-A | Director of Learning and Development | `847953494233` | Yes |
| Courtney Y. | Chick-fil-A | Learning and Development, TDP | `847899297997` | Yes |
| Kaity Scanlan | Chick-fil-A | Admin. Coordinator, L&D Operations | `847904697553` | Yes |
| Renee Malone | Inspire Brands | Training Enablement, Manager | `847937295557` | Yes |
| Cheryl Symank | Lettuce Entertain You Restaurants | Learning and Development Manager | `848040271046` | Yes |
| Abbey Sattele | Inspire Brands | Sr. Exec. Assistant to the COO of Arby's | `847967140086` | Yes |
| Darya Fields | Chick-fil-A | Director, Learning and Development | `847971236048` | Yes |
| Tyler Heid | Dine Brands Global | Manager, Learning and Development | `847896240334` | Yes |
| Kelley Sorrow | Chick-fil-A | Sr Director, L&D Operations and Transformation | `847967141085` | Yes |
| Callie Whigham | Chick-fil-A | Principal Learning and Development Lead | `848137037007` | Yes |
| Rachel Bath | Chick-fil-A | Sr. Experience Lead, Staff L&D | `848136820985` | **No — bounce block** |
| Bryan Kelly | Chick-fil-A | Project Lead - EHS Manager | `847902892244` | No email |
| Jessica "EMT" | Inspire Brands | EHS Manager | `847936000235` | No email |
| Sonia Harris | Dine Brands Global | Sr. Manager, Learning and Development | `847946288326` | No email |
| Duan Garner | Popeyes | Sr. Learning and Development Manager | `847901155535` | No email |

**11 of 16 contacts fully live**: real HubSpot Contact, a real generated
draft on file as a Note, a recorded consent basis, and confirmed
enrollment (`hs_sequences_enrolled_count = 1` on every one, verified by
direct query). 1 has everything except enrollment (bounce-blocked). 4
exist as Contact records only, with no further action possible without a
real email address.

---

## What's still open

- **4 duplicate Company records** from Step 4's race condition (DIG INN
  Support, Steak 'n Shake, Lettuce Entertain You Restaurants, Otg) — not
  merged; cosmetic, left for a human, same category as the pre-existing
  McDonald's/Chick-fil-A orphans this path happened to run into but didn't
  create.
- **Rachel Bath's sequence enrollment is blocked** by HubSpot's own
  bounce-protection on her email — would need a verified, corrected
  address before it could go through; not something to override.
- **9 of the 13 real Hiring-signal companies have zero contacts**: DIG INN
  Support, McDonald's, Abby's Pizza, Steak 'n Shake, Dunkin', Yoshinoya
  Companies, Otg, Mendocino Farms, and Popeyes (Duan Garner exists but has
  no email). Getting them contacts needs another round of the Step
  5→6→7 loop.
- **Contact resolution is not automated.** Clay's script-callable path
  needs a paid plan this project doesn't have; the whole Step 5→6→7 loop
  is a real, working, but manual bridge. If a paid Clay plan (or
  Amplemarket, the original target) existed, this would collapse into one
  automated call from `handle_hiring_signal()` — same filtering logic,
  no human export/import step.
- **The Tier 1 email/Note/enrollment logic is not wired into the
  automated signal-handling path.** Everything in Step 7 ran through the
  standalone `scripts/populate_hiring_contacts_from_clay.py`, not through
  `pipeline/signal_handler.py:handle_hiring_signal`. That function's
  return value still hardcodes `tier1_first_touch: {"attempted": False,
  "reason": "Hiring Tier 1 copy rules not yet designed"}` — stale wording
  (the copy rules *are* designed and finalized, see Step 7), but the
  wiring itself genuinely isn't there. A fresh live signal today, even
  with a real resolved contact, would not automatically draft or enroll
  anyone.
- **`_maybe_enroll_hiring_tier3` still only gates on `tier == "Tier 3"`**
  and points at `HUBSPOT_HIRING_TIER3_SEQUENCE_ID`. The "one sequence for
  both tiers" decision that Step 7 actually implements only exists in the
  standalone population script; the core automated pipeline doesn't
  reflect it.
- **Adzuna precision is much improved but not proven complete.** The
  denylist catches the specific wrong cases found so far (Marriott, Circle
  K, "[solidcore]," Sam's East, Copeland); a new company-name collision or
  food-service-adjacent business not yet seen could still slip through
  undetected until it does.
- **5 commits implementing this whole path are sitting locally unpushed**
  (`9365016` down through `54074e1`) — `git push` fails with a GitHub
  credential error unrelated to any of this pipeline's own code, still
  waiting on the user to refresh their token.
