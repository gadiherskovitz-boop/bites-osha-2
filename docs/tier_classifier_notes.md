# Rung 5 — LLM tier classification (Haiku + web search)

**Verified live on 2026-08-17** via `scripts/verify_tier_classifier.py`.

## The reframing that makes this rung cheap

Tiering needs a **band**, not an exact count. "Is this chain 200+ locations?"
is far easier and more reliably answerable than "exactly how many locations
does it have?" — so this asks for the band directly, with the exact count as
a bonus when the model knows it.

That also removes the latency objection to putting an LLM in the pipeline.
This runs once per *brand* (not per signal), only for brands the two free
rungs miss, and caches permanently in `output/tier_cache/` (gitignored).
Measured: **2.8–4.4s cold, 0.003s cached.**

## Three operator decisions baked in

**1. No source attribution.** Deliberately not requested — the operator
doesn't need provenance for this build, so `source_url`/`source_kind`/
`as_of_year`/`reasoning` were dropped from the schema. The model is still
told to search rather than answer from memory (it's what keeps the counts
accurate), but nothing tracks which page it used. Reinstating provenance
means adding those fields back to `_SCHEMA`.

**2. Round up at band boundaries, don't discard.** An earlier draft threw
away low-confidence answers. The operator's explicit rule replaced that:
if a chain sits near ~50 locations (Tier 3/Tier 2) or ~200 (Tier 2/Tier 1)
and the model can't tell which side, it returns its best band plus
`confidence: "low"`, and `round_up_band()` bumps it one band up. Rationale:
under-tiering a real prospect costs a missed opportunity, over-tiering costs
a little wasted attention, and the bands are wide enough that edge cases are
genuinely low-stakes.

*Implementation note:* when a rounded band is returned, `value` is set to
`None`. Keeping the exact count would let `tier_for_lookup()` recompute the
un-rounded tier from it and silently defeat the rounding rule.

**3. Haiku 4.5, not Opus 5** — ~3× cheaper on a coarse classification task.
**This switch required three model-specific changes, any one of which would
have failed on first run:**

| Change | Why |
|---|---|
| `web_search_20250305`, not `_20260209` | The dynamic-filtering variant requires Opus 4.6+/Sonnet 4.6+. Not available on Haiku 4.5. |
| No `output_config.effort` | `effort` **errors** on Haiku 4.5 — it isn't a supported parameter on that model. |
| No `thinking` | Haiku 4.5 has no adaptive thinking; omitting it means none, which suits this task. |

Moving back to Opus 5 means reversing all three, not just the `MODEL`
constant. Both are noted in the code.

## Cost

Per brand: ~1 web search ($10/1,000 = $0.01) + ~6K input + ~500 output.

| Model | Input | Output | ≈ per brand | 246-brand backlog |
|---|---|---|---|---|
| **`claude-haiku-4-5`** (in use) | $1/MTok | $5/MTok | **~$0.02** | **~$5 one-time** |
| `claude-opus-5` | $5/MTok | $25/MTok | ~$0.06 | ~$15 one-time |

One-time because of the permanent per-brand cache. The web search now
dominates the per-call cost on Haiku — dropping search would roughly halve
it again, at the cost of the grounding that keeps the counts accurate.

## Verified results

`scripts/verify_tier_classifier.py`, all passing:

| Check | Result |
|---|---|
| Burger King → Tier 1 | ✅ 7,739 US locations, `web_high` |
| Pizza Hut → Tier 1 | ✅ 6,408, `web_high` |
| KFC → Tier 1 | ✅ 4,267, `web_high` |
| Dairy Queen → Tier 1 | ✅ 4,175, `web_high` |
| Subway short-circuits at Rung 4 | ✅ resolved by `wikidata`, Rung 5 never called (no wasted spend) |
| `Master Pho 1 Llc` (real single-location independent from our own scan) | ✅ declined — did not hallucinate a chain |
| Round-up rule, all four bands | ✅ pure logic, tested without API |
| Cache hit | ✅ 0.003s |

All four counts are accurate against public figures, and all four are brands
Rung 1's 28-name list misses **and** Wikidata has no `P8368` claim for — the
exact gap this rung was built to close.

## Measured coverage against the real backlog

Sampled 14 of the 243 establishment names (of 258) that Rung 1 misses:

| Outcome | Count | Examples |
|---|---|---|
| Resolved | 4/14 (~29%) | `Ayvaz Pizza Llc Dba Pizza Hut` → **Tier 1** (6,408); `Dutch Bros Coffee` → Tier 1 (1,266); `Tim Hortons 7479` → Tier 1 (691); `Friends Winder Grill, Llc` → Tier 3 (9) |
| Declined → Tier 3 default | 10/14 | `Blazin Wings, Inc.`, `Ssb Eastern, Llc`, `Restaurant Management Group, Llc`, … |

Extrapolated: ~70 of 243 brands resolvable, roughly 50 of them Tier 1
accounts currently sitting at Tier 3.

**Two results worth noting.** `Ayvaz Pizza Llc Dba Pizza Hut` resolving to
Tier 1 is `company_names.py` and Rung 5 working together — the DBA rule
collapses the franchisee to "Pizza Hut", then Rung 5 tiers the brand.
`Tim Hortons 7479` came back 691, correctly **excluding** its ~3,500
Canadian locations: the US-only instruction in the prompt is doing real work.

## Known limitation: opaque legal-entity names

The 10 declines are almost all franchisee or operating-company names with no
brand signal (`Ssb Eastern, Llc`, `Central Coast Star, Llc`). Rung 5
**declines rather than guessing**, which is the correct failure mode — they
land on the Tier 3 default — but it means this rung does *not* solve the
franchisee-identity problem.

A prompt fix was added after the first sample (telling the model to search
for the brand behind a legal entity, with `Blazin Wings, Inc.` given as a
worked example) and recovered 1 of the 10: `Nevada Restaurant Services, Inc.`
→ Tier 1.

**Unresolved anomaly, worth knowing before extending this:** asked in
free-form, Haiku correctly identifies `Blazin Wings, Inc.` as Buffalo Wild
Wings with ~1,451 US locations. Under the constrained structured-output call
it still returns `found=false` — *even with that exact company named as an
example in the system prompt.* The model has the knowledge and won't emit it
through the schema. If this gap matters, the fix is probably a two-step call
(resolve entity → brand in a free-form call, then classify the brand), at
roughly double the cost and latency. Not built — the Tier 3 default is a
safe landing place, and these are the lowest-stakes accounts to under-tier.

## Integration

- `lookup_site_count()`: Rung 1 (free/instant) → Rung 4 (free/fast) →
  **Rung 5 (paid/slow)** → unresolved. Cheapest-first, so the paid rung only
  fires on brands the free rungs miss — verified by the Subway case.
- Results carry `tier_hint`: a band with no exact number behind it.
  `tier_for_lookup()` resolves exact count → `tier_hint` → Tier 3 default.
  A `tier_hint` of `Disqualified` returns `None`, not Tier 3.
- **Rung 5 is skipped entirely when `ANTHROPIC_API_KEY` is unset** — verified;
  the pipeline still runs and degrades to the Tier 3 default. The `anthropic`
  import is deferred so the SDK stays an optional dependency.

## Resolved risk

The one flagged unknown — whether structured outputs (`output_config.format`)
would 400 alongside the web-search tool, since structured outputs are
documented as incompatible with *citations* and search results carry their
own — **did not materialize.** Confirmed working together on Haiku 4.5.
