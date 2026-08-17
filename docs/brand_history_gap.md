# Brand-level history is a floor, not a total

Found 2026-08-18, investigating why Pizza Hut's CRM history showed only 6
inspections YTD for a ~6,400-location chain.

## What was NOT wrong

The history figures were already **brand-wide**, not scoped to the one
franchisee that triggered the signal. Verified: `establishment_search("Pizza
Hut")` over 2024→now returns 2026: 6, 2025: 2, 2024: 4 — exactly what the
CRM note showed. Ayvaz alone is 2024: 2, 2026: 3. So the brand rollup was
working as designed.

## What IS wrong

**OSHA has no brand field.** `establishment.search` matches on the
establishment *name*, so the rollup can only find locations whose OSHA name
happens to contain the brand string. Every location inspected under a
franchisee's own legal name is invisible.

Verified live, restaurant-NAICS inspections 2024→2026-08:

| OSHA establishment name | Actually operates | Found by a brand-name search? |
|---|---|---|
| `Carrols Llc` | ~1,000 Burger Kings (largest BK franchisee) | ❌ never |
| `Sizzling Platter, Llc` | hundreds of Little Caesars / Wingstop / Jamba | ❌ never |
| `Tri-Arc Food Systems Inc Dba Bojangles` | Bojangles | ✅ only via the DBA |
| `Restaurant Management Group, Llc` | Little Caesars | ❌ never |
| `Blazin Wings, Inc.` | Buffalo Wild Wings (~1,451 US) | ❌ never |

The nine distinct names that *did* match "Pizza Hut" all literally contain
the string — `Pizza Hut`, `Charlevoix Pizza Hut #1205`, `Pizza Hut Of
America, Llc`, and so on. That is the entire population the rollup can see.

**Scale of the undercount is unknown but large.** Pizza Hut returning 12
inspections across 2.5 years for 6,400 locations is not credible.

## Interim fix (shipped)

`pipeline/signal_handler.py:_history_lines()` now renders these as floors —
`6+ inspection(s), $0+ in fines` — plus an explicit caveat line naming the
limitation. A rep must not quote these to a prospect as totals. This does
not fix the number; it stops the CRM asserting a wrong one.

## The real fix, and the discovery that makes it viable

Closing the gap needs **establishment-name → brand resolution**, applied
across a full historical scan, aggregating locally instead of relying on
OSHA name search.

The blocker was that our tier classifier declines opaque operating-company
names. But that turns out to be **task interference, not missing
knowledge** — asking one call to both identify the brand *and* size it makes
the model bail on the whole thing. A narrow "which brand does this entity
operate?" call succeeds where the combined call refused:

| Entity | Combined tier call | Narrow brand-only call |
|---|---|---|
| `Carrols Llc` | — | ✅ Burger King |
| `Restaurant Management Group, Llc` | ❌ declined | ✅ Little Caesars |
| `Blazin Wings, Inc.` | ❌ declined *(even named as a worked example in the prompt)* | ✅ Buffalo Wild Wings |
| `Tri-Arc Food Systems Inc Dba Bojangles` | — | ✅ Bojangles |
| `Sizzling Platter, Llc` | ❌ declined | ❌ still declines |
| `Ssb Eastern, Llc` | ❌ declined | ❌ still declines |

4 of 6, including both entities the tier classifier refused. This also
explains the `Blazin Wings` anomaly recorded in
`docs/tier_classifier_notes.md` — the fix is to split the question, not to
push harder on the prompt.

### What the rebuild would involve

1. `resolve_brand(establishment_name) -> brand | None` — a narrow,
   permanently-cached classifier call, separate from tier classification.
2. Scan restaurant-NAICS inspections over the full history window (the
   scanner already does this for 100 days; widen it), resolve each distinct
   establishment name once, and aggregate counts and penalties **by resolved
   brand** locally.
3. Point `year_summary()` at that local aggregate instead of
   `establishment_search()`.

Rough cost: a 3-year restaurant-NAICS scan is ~11× the current 100-day
window (~3,000 inspections, maybe ~2,000 distinct names). At ~$0.02 per
resolution that is **~$40 one-time**, permanently cached — after which
history becomes a fast local lookup with no per-signal web search at all,
which also removes the current 6.8s cold-cache cost per brand.

It would additionally fix **company dedup** and **tiering** for
franchisee-named accounts, since the same resolved brand keys all three.
`Carrols Llc` signals would roll into the Burger King account and tier as
Tier 1 instead of landing at the Tier 3 default under their own name.

Not built — this is a real chunk of work and spend, and it needs an explicit
go-ahead.

## Why brand-level rollup is the right frame anyway

Recorded because it motivates the rebuild: corporate can compel franchisee
remediation and often funds it, brand reputation is the corporate entity's
exposure, and brands operate significant company-owned estates where the
same failures likely recur. So aggregating a franchisee's citation up to the
brand is not a modelling convenience — it is the actual sales thesis.
