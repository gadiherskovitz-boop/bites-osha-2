# osha.gov/ords/imis — mechanics findings (Task #5)

Verified live on 2026-08-17 by inspecting the real form (`industry.html`) and
its rendered results, then cross-checking parsed output against the page.
No API key or auth needed; confirms the earlier finding in `dol_api_notes.md`
and `HANDOFF.md` that this host isn't rate-limited like `apiprod.dol.gov`.

## The date-range fields are internally swapped

`industry.search`'s query params are named `startyear`/`startmonth`/`startday`
and `endyear`/`endmonth`/`endday`, but the field the user sees labeled
**"Start Date"** is actually `endyear` (title attribute reads "Start Year"),
and the one labeled **"End Date"** is actually `startyear` (title attribute
reads "End Year"). Confirmed two ways: reading the live form's `title`
attributes, and round-tripping a query and reading back the "Inspection Date
Range" the results page echoes. `pipeline/osha_client.py:industry_search`
passes the earlier bound to `end*` and the later bound to `start*` -
documented in its docstring since this is very easy to get backwards
silently (no error, just the wrong or an empty range).

## One NAICS per request

`naics=722511,722513,722515` (comma-separated) is silently rejected — the
form re-renders with "Your search did not return any results," not an error.
The scanner issues one request per NAICS code and merges/dedupes results by
`activity_nr` client-side.

## `p_show` returns everything in one page

Pagination is normally `p_start`/`p_finish`/`p_show=20`, but passing a large
`p_show` (e.g. 1000+) up front returns all matching rows in a single request
— confirmed against a 160-result set (`Results 1 - 160 of 160`). No need to
paginate for a 100-day trailing window per NAICS.

## No `<tbody>` on the listing page, but detail pages have one

`industry.search`'s results table has no `<tbody>` in the raw HTML source
(only `<tr>` directly under `<table>`) — `BeautifulSoup`'s `html.parser`
doesn't synthesize one the way a browser DOM does, so `table.find_all("tr")`
is used there. `establishment.inspection_detail`'s tables *do* have an
explicit `<tbody>` in source, so that parsing path uses it.

## State-plan citations don't use the federal 1910.xxxx numbering

Federal citations render as `1910` + a 4-digit zero-padded section, e.g.
`19100036 G02` = 1910.36(g)(2). State-plan citations (verified on California,
Oregon inspections) use each state's own scheme entirely — e.g. Cal/OSHA's
`3203(A)`, `4650(E)`, `6151(E)(2)`, Oregon's `OAR 437-002-0022(4)(F)`. These
never match the `1910` prefix, so `_federal_section()` in
`pipeline/signal_scanner.py` correctly returns `None` for them rather than
misparsing — they still get a chance to trigger the Violation signal via the
Willful/Repeat/FTA check, just not the standard-number check.

## No separate Failure-to-Abate classification field

The Violation Items table has an "FTA Penalty" column but no separate FTA
issuance-date or classification field on this data source (unlike the
`apiprod.dol.gov` schema's `fta_issuance_date` etc., see `dol_api_notes.md`).
`is_relevant_violation()` treats a nonzero FTA Penalty as the
Failure-to-Abate signal — a real FTA follow-up citation was issued against
that line item — rather than leaving Failure-to-Abate unimplemented.

## Verified live results (trailing 100-day window, all 3 restaurant NAICS)

- Inspection triggers: 268 (248 Complaint, 14 Accident, 6 Fat/Cat) — real
  establishments including In-N-Out Burger (Fat/Cat, ID), Pappas Restaurants
  (Fat/Cat, TX), El Pollo Loco, Fogo de Chão.
- Violation triggers: 0 in this specific window — 10 inspections had
  citations (16 line items total), but none matched the relevance filter:
  all were `Other`/`Serious` classification on non-training-linked standards
  (1910.36 Exit Routes, 1910.22 General Requirements, 1910.303 Electrical) or
  state-plan standards. This is a real, checked result, not a bug — confirmed
  by unit-testing `is_relevant_violation()` directly against synthetic
  known-relevant (1910.1200, Repeat classification, nonzero FTA penalty) and
  known-irrelevant (non-training federal standard, state-plan standard)
  inputs, all of which classified correctly.

## Files

- `pipeline/osha_client.py` — HTTP + HTML parsing (`industry_search`,
  `inspection_detail`).
- `pipeline/signal_scanner.py` — `scan_inspections()`, `scan_violations()`,
  `is_relevant_violation()`.
- `scripts/scan_signals.py` — runnable verification script.
