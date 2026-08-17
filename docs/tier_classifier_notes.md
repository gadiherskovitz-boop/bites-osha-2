# Rung 5 — web-grounded tier classification (LLM)

⚠️ **Built but NOT yet verified live** — no `ANTHROPIC_API_KEY` was available
when this was written. Every other integration in this project was confirmed
against real endpoints before being called working; this one has not been.
Run `scripts/verify_tier_classifier.py` with a real key before relying on it.

## The reframing that makes this rung cheap

Tiering needs a **band**, not an exact count. "Is this chain 200+ locations?"
is far easier and far more reliably answerable than "exactly how many
locations does it have?" — so `pipeline/tier_classifier.py` asks for the band
directly and treats an exact count as an optional bonus when a source states
one.

That also inverts the usual latency objection to putting an LLM in a
pipeline. This rung is **not** per-signal: it runs once per *brand*, only for
brands the two free rungs miss, and the result is cached permanently
(`output/tier_cache/`, gitignored). Site counts move on the order of years.

## Why one rung, not three

`docs/account_sourcing_methodology.md` narrates Rungs 2 (FDD aggregators),
3 (SEC EDGAR) and 5 (company website) as three separate unbuilt rungs. They
are collapsed into this single rung deliberately: with a web-search tool the
model picks whichever of those sources actually exists for a given brand, so
three source-specific integrations would be three brittle code paths doing
one job. The model reports `source_kind` and `source_url`, so source
attribution — what the separate rungs were really for — survives the merge.

## Why web-grounded, not free recall

`docs/account_sourcing_methodology.md` explicitly cut "generic web search +
LLM guessing" from the waterfall: extraction from a retrieved document is a
materially lower hallucination risk than free-recall guessing. That still
holds, and this rung respects it — the model must ground its answer in a page
it actually fetched and return the URL.

**Confidence is asymmetric by band, and the prompt says so.** Whether a
national chain clears 200 locations is near-certain; distinguishing 45 from
55 (Tier 3 vs Tier 2) is genuinely hard. The model is told to return `low`
rather than guess in that middle range, and **a `low` result is discarded** —
it falls through to the Tier 3 default like any other unresolved account.
This is the trust hierarchy the methodology doc asks for: `verified` (QSR50)
> `wikidata` > `web_high`/`web_medium` > `estimated` (default).

## Cost — the actual numbers

Per brand: ~1 web search ($10 per 1,000 = $0.01) + ~6K input + ~800 output.

| Model | Input | Output | ≈ per brand | 245 unresolved brands |
|---|---|---|---|---|
| `claude-opus-5` (default) | $5/MTok | $25/MTok | ~$0.06 | **~$15 one-time** |
| `claude-haiku-4-5` | $1/MTok | $5/MTok | ~$0.02 | ~$5 one-time |

One-time because of the permanent per-brand cache. `MODEL` in
`pipeline/tier_classifier.py` is a single constant — Opus 5 is the default
per Anthropic's guidance; downgrading for cost is a deliberate operator
choice, not a silent default. For a coarse band classification grounded in
retrieved text, Haiku is a defensible call.

## Integration

- `lookup_site_count()` runs Rung 1 → Rung 4 → **Rung 5** → unresolved,
  cheapest-first, so the paid rung only fires on brands the free rungs miss.
- Results carry a new `tier_hint` key: a band with no exact number behind it.
  `tier_for_lookup()` resolves exact count → `tier_hint` → Tier 3 default.
  A `tier_hint` of `Disqualified` correctly returns `None`, not Tier 3.
- **Rung 5 is skipped entirely when `ANTHROPIC_API_KEY` is unset** — verified:
  the pipeline still runs and degrades to the Tier 3 default. The `anthropic`
  SDK import is deferred so it stays an optional dependency.

## What verification must show

`scripts/verify_tier_classifier.py` checks four things against
independently-known answers:

1. **Burger King / Pizza Hut / KFC → Tier 1.** These are precisely the brands
   Rung 1's 28-brand list misses and Wikidata has no `P8368` claim for
   (verified live) — the real target of this rung.
2. **Subway short-circuits at Rung 4** (36,821 via Wikidata) and never reaches
   the paid rung.
3. **`Master Pho 1 Llc`** — a real single-location independent from our own
   OSHA scan — must NOT resolve to a tier. Confidently tiering it means the
   model is hallucinating.
4. **Cache hit on re-run** — instant, no API calls.

## Untested risks

- **Structured outputs + web search together.** `output_config.format` is
  documented as incompatible with *citations*; web search results carry
  citations of their own. If this 400s, the fallback is to drop
  `output_config.format` and parse JSON out of the response text. This is the
  single most likely thing to break on first run — and it fails loudly, not
  silently.
- **`effort: "low"`** is set for a coarse task. If the middle bands prove
  unreliable in testing, raise it before adding prompt scaffolding.
