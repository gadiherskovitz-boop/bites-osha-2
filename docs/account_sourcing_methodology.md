# Account sourcing at scale: the site_count waterfall

Site count is the number that actually drives Bites tiering, but it's not a
field any general-purpose firmographic provider carries — verified live
against Clay's company search (see `docs/clay_api_notes.md`), and the same is
true of comparable tools like Apollo or Cognism, which source company data
from the same kind of LinkedIn/firmographic feeds. It's a specialized retail
data point, not a standard B2B enrichment field.

**What's actually built for this demo:** 28 accounts, tiered using site counts
sourced from QSR Magazine's QSR 50 2026 report and its companion "Contenders"
list (`pipeline/accounts_seed.py`). This covers the top ~100 U.S.
limited-service chains by sales — a real, citable source, but narrow: it
excludes anything outside that ~100-brand ceiling, and it excludes anything
that isn't technically "limited-service" (e.g. IHOP, Applebee's, Denny's,
Waffle House — family/casual dining chains that fit Bites' ICP just as well,
arguably better given their higher staffing complexity, but aren't QSR by
service model and so don't appear in a QSR-specific ranking).

**How this would scale beyond 28 accounts** — a 5-step waterfall, cheapest and
most reliable sources first, each producing `{value, source, confidence,
as_of_date}` rather than a bare number so nobody downstream mistakes a
low-confidence figure for a verified one:

1. **QSR Magazine QSR50 + Contenders** — already built. Cheap, structured,
   annually refreshed, ~100-brand ceiling.
2. **Franchise Disclosure Document (FDD) aggregator data** (e.g. Franchise
   Times Top 200/400, FRANdata). Every U.S. franchisor is legally required to
   file an FDD annually, and Item 20 is a table of unit counts by state for
   the past 3 years. This is the highest-leverage addition beyond QSR50,
   since most multi-unit restaurant brands are franchised, not public — it
   covers the long tail SEC filings and QSR50 both miss.
3. **SEC EDGAR full-text search + 10-K extraction** — public companies only.
   Free, live, queryable API. Caveat: some public parents report combined
   unit counts across multiple owned brands, so a filing doesn't always
   cleanly isolate one concept's number.
4. **Wikidata/Wikipedia infobox** — structured, SPARQL-queryable, decent
   coverage of well-known brands, moderate reliability.
5. **Company website** (store locator count, or an About-page claim) — LLM
   extracts the number from a page actually fetched, not recalled from
   training data. Extraction from a retrieved document is a materially lower
   hallucination risk than free-recall guessing, which is why generic web
   search + LLM guessing was deliberately cut from this waterfall rather than
   included as a fallback.

**What happens when nothing resolves:** rather than guess (e.g. from employee
count — rejected as a step; the employees-per-site ratio varies too much by
service model — QSR counter crew vs. full-service waitstaff — to be reliable,
and it's a free-recall-style estimate with no retrievable source), an account
that clears none of the 5 steps defaults to **Tier 3**.

This default is deliberately safe rather than arbitrary: Bites' tier bands are
wide (6-49 / 50-199 / 200+), so tiering doesn't need much precision, and
reporting quality correlates with company size — a 200+-site chain is very
unlikely to be undiscoverable across all 5 sources, while a genuinely small
or obscure chain is exactly where the waterfall is expected to come up empty.
So the accounts most likely to hit this default are also the lowest-stakes
ones to under-tier. The one caveat worth carrying into the data model: a
Tier-3-by-default account should be flagged separately (e.g.
`tier_confidence: estimated` vs. `verified`) from an account whose Tier 3
status came from a real number — otherwise an unresolved account is
indistinguishable from a confirmed small one, and the rare case of a large
but obscure/under-reported chain would silently under-tier.
