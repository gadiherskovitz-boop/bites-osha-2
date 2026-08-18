# Hiring signal (Greenhouse/Lever) — scope and real findings

Built 2026-08-18, the session's pivot target once the OSHA path stalled on
Task #4/Amplemarket (see `HANDOFF.md`). Same discipline as the OSHA build:
every claim below was checked live, not assumed. Mirrors
`docs/osha_ords_imis_notes.md`'s role for this signal source.

## The core architectural difference from OSHA

OSHA's `industry.search` is a real global scan: give it a NAICS code and a
date range and it returns every matching establishment in the country, known
or not. **Neither Greenhouse's nor Lever's public API offers anything
equivalent.** Both only serve postings for a company whose board
token/slug you already know (`boards-api.greenhouse.io/v1/boards/{token}/jobs`,
`api.lever.co/v0/postings/{slug}`) — there is no company-search or directory
endpoint on either public API. This means the Hiring path can't be
"signal-first" in the same sense the OSHA path is; it's closer to
"signal-first among a hand-curated set of accounts known to be on one of
these two ATSs." `pipeline/hiring_seed.py` is that curated set, and growing
it is the single highest-leverage next step on this thread — the exact
role `accounts_seed.py`'s 28-brand list plays for Rung 1 of the site_count
waterfall.

## What's actually out there, verified live

Tried ~90 slug guesses 2026-08-18: every brand in `accounts_seed.py`'s
QSR50/Contenders list (all 28, tried on both APIs) plus ~60 younger
fast-casual/coffee/bakery chains, with common slug variants (plain,
hyphenated, `-coffee`/`-inc` suffixes). Real result: **4 hits, 0 from the
large-chain list.**

| Brand | ATS | Board token |
|---|---|---|
| Sweetgreen | Greenhouse | `sweetgreen` |
| Caribou Coffee | Greenhouse | `caribou` |
| Blue Bottle Coffee | Lever | `bluebottlecoffee` |
| Insomnia Cookies | Lever | `insomniacookies` |

Every large legacy chain tested — McDonald's, Starbucks, Chick-fil-A, Taco
Bell, Wendy's, Dunkin', Domino's, Chipotle, Popeyes, Panera, Sonic, Jersey
Mike's, Firehouse Subs, Cinnabon, Portillo's, Cava, Dutch Bros, Wingstop,
Shake Shack, Bojangles, Culver's, Raising Cane's, Whataburger, and more —
404s on both APIs. This isn't a sampling gap, it's a real pattern: large QSR
operators overwhelmingly run enterprise ATS (Workday, iCIMS, Taleo, SAP
SuccessFactors) with no public read API, while Greenhouse/Lever skew toward
companies that grew up on modern SaaS hiring tooling — younger, often
VC-backed, tech-forward brands. All 4 hits fit that profile. None of the 4
are in the QSR50 Rung-1 seed list either, so their tier comes from Rung 4
(Wikidata) or Rung 5 (LLM + web search) or the Tier 3 default — no changes
needed to `pipeline/site_count.py`, confirmed live: Sweetgreen resolves via
Rung 5 to Tier 1 (887 sites, `web_high` confidence).

**Implication for the demo**: the Hiring path's coverage is real but
narrow. Worth saying explicitly when presenting rather than letting the
OSHA path's "real global scan" framing bleed over — this is closer to a
target-account watchlist than a census.

## The relevance filter — a real false positive worth knowing about

`pipeline/hiring_scanner.py:is_relevant_hiring_posting()` requires a
seniority marker (Director, Head of, VP, Vice President, Chief, CLO, CHRO)
**and** a function marker (Learning, Training, L&D, People, Human
Resources, HR, Talent, Enablement, Organizational Development) together,
deliberately matching `pipeline/persona_tracks.py`'s own bar for
"leadership" (vp/director/head/c-suite — not "senior" ICs, not bare
"Manager").

That bar exists because of a real hit found live scanning Sweetgreen's and
Insomnia Cookies' actual boards:

- **"Store Manager in Training (MIT)"**, **"Leader in Training"** — a
  ubiquitous entry-level frontline title pattern across QSR hiring (MIT =
  "Manager in Training"). A naive substring match on "training" alone would
  flag these on nearly every QSR company's board, constantly. Correctly
  excluded — no seniority marker.
- **"Manager, Talent Acquisition"**, **"Sr. People Business Partner
  (HRBP)"** — real People-function roles, genuinely relevant-adjacent, but
  IC/manager-level, not leadership. Correctly excluded for the same reason
  `persona_tracks.py` doesn't treat a bare "Manager" title as a leadership
  contact either.
- **"Senior Field HRBP" tagged under Lever's `categories.team: "People
  Team"`** — this is the case that motivated checking the team field at
  all (Greenhouse has no equivalent field), but "Senior" isn't a seniority
  marker here by design, so it's still excluded. Function-only matches
  never fire alone.

Verified against 16 synthetic cases (8 true positives spanning the title
patterns above, 8 true negatives including all three real ones above) — all
16 passed. Live scan against the 4 real boards on 2026-08-18 found 0 current
matches — a real result, not a bug: leadership L&D/HR reqs are rare and
none of the 4 companies happened to have one open that day. Same
"filter verified correct, this window just came back empty" pattern the
OSHA Violations scanner hit once already.

**Known limitation, not solved**: Lever's `team` field is coarse. A generic
"Regional Director" title tagged under a "People Team" department would
pass the filter even if the specific role is more operational than
strategic — no live example of this hit yet, flagged rather than
over-engineered around.

## What's wired vs. not

Mirrors the OSHA path's steps 2/3/5 (`docs/signal_first_architecture.md`),
skipping the OSHA-specific pieces (franchisee-name collapsing, brand-wide
history) that don't apply — ATS board names are already canonical, sourced
from the hand-verified seed list, not noisy establishment strings.

- **Scan** (`pipeline/hiring_scanner.py:scan_hiring_signals`) — done, live
  against real boards.
- **Tier** — reused as-is (`pipeline/site_count.py`, `pipeline/tiering.py`),
  confirmed no changes needed.
- **Push** (`pipeline/signal_handler.py:handle_hiring_signal`) — done:
  `qsr_signal` object (already has a `Hiring` option on `signal_type`,
  confirmed via `scripts/setup_qsr_signal_schema.py`), Company Note, and
  the `hiring_signals` Slack channel (pre-existing, unchanged) all fire
  together, matching the OSHA path's "all three, every trigger" rule.
  Verified end-to-end with a mocked HubSpot/Slack layer (real code path,
  fake I/O) rather than pushing a fabricated posting into the live
  portal — no real relevant posting existed to push at build time (see
  "0 current matches" above), and inventing one would misrepresent a real
  record. `scripts/handle_hiring_signals.py` is ready to run for real the
  moment a real qualifying posting appears; `scripts/scan_hiring_signals.py`
  is a read-only dry run for checking in the meantime.
- **`source_activity_nr`/`source_citation_id`** — reused rather than
  migrating the schema for one new field: a Hiring signal's dedup key is
  `"{ats_source}:{posting_id}"` (e.g. `"greenhouse:8106821"`) in
  `source_activity_nr`, `source_citation_id` left null. Same idempotent
  upsert path as OSHA (`pipeline/hubspot_client.py:find_qsr_signal`/
  `upsert_qsr_signal`), no code changes needed there. Known naming debt,
  same precedent as leaving the unused `governance_model` property alone
  rather than a mid-build migration.
- **Sequence enrollment** — Tier 3 only, gated behind a new
  `HUBSPOT_HIRING_TIER3_SEQUENCE_ID` env var, deliberately separate from
  `HUBSPOT_TIER3_SEQUENCE_ID` (that sequence is literally named "QSR T3 -
  OSHA Trigger," wrong copy context for a Hiring-triggered contact). Unset
  until a human creates that sequence in the HubSpot UI, same as the OSHA
  Tier 3/Tier 1 sequences were — skipped cleanly and reported, not faked.
  No Fat/Cat-equivalent exclusion exists for Hiring, so tier is the only
  gate.
- **Contact resolution** — same Task #4/Amplemarket blocker as OSHA, per
  `HANDOFF.md`. `handle_hiring_signal(signal, contact=None)` takes the same
  `{"id", "name", "title"}` shape once it lands.
- **Tier 1 personalized first-touch (Task #8's Hiring equivalent)** — not
  built this session. `docs/task8_email_rules.md`'s copy rules are framed
  around a cited OSHA standard/inspection; a Hiring trigger needs its own
  rules pass (the natural angle: the account is actively building out
  L&D/People-Ops capability, which is a different opening than "we saw an
  OSHA citation"), not a rushed reuse. `handle_hiring_signal()` reports this
  honestly (`{"attempted": False, "reason": "Hiring Tier 1 copy rules not
  yet designed"}`) rather than faking it.

## GTM motion — Slack/Note template

Real template that shipped (`pipeline/signal_handler.py:_build_hiring_lines`),
adapted from the original plan's sketch (see the plan file's superseded
"Hiring" block) the same way the OSHA template diverged from its own
pre-build sketch — added Team/Location fields since Lever's `categories`
carry real, useful context Greenhouse's response doesn't:

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

`pipeline/ats_client.py` (Greenhouse + Lever HTTP), `pipeline/hiring_seed.py`
(the 4-board seed list), `pipeline/hiring_scanner.py` (scan +
relevance filter), `pipeline/signal_handler.py:handle_hiring_signal` (push),
`scripts/scan_hiring_signals.py` (dry run), `scripts/handle_hiring_signals.py`
(live push, same `DEFAULT_LIMIT` safety pattern as `scripts/handle_signals.py`).
