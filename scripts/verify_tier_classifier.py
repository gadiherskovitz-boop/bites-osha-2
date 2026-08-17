"""Live verification for Rung 5 (pipeline/tier_classifier.py).

Run this before treating Rung 5 as working. Needs ANTHROPIC_API_KEY set.

The cases below are chosen so the ANSWERS ARE KNOWN INDEPENDENTLY, which is
the only way this proves anything:

- Burger King / Pizza Hut / KFC: national chains, unambiguously Tier 1.
  These are exactly the brands our 28-brand Rung 1 list misses today and
  that Wikidata has no P8368 claim for (verified live), so they are the
  real target of this rung.
- Subway: Rung 4 already resolves it to 36,821 via Wikidata, so this run
  should never reach Rung 5 - included to confirm the waterfall short-
  circuits and we don't pay for a call we don't need.
- Master Pho 1 Llc: a real single-location independent from our own OSHA
  scan. Correct answer is Disqualified or not-found, NOT a tier. A model
  that confidently tiers this is hallucinating.
"""
import os
import sys

from pipeline.site_count import lookup_site_count
from pipeline.tier_classifier import classify_tier
from pipeline.tiering import tier_for_lookup

KNOWN_TIER_1 = ["Burger King", "Pizza Hut", "KFC"]
SHOULD_SHORT_CIRCUIT = "Subway"
SHOULD_NOT_RESOLVE = "Master Pho 1 Llc"


def main():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit("ANTHROPIC_API_KEY not set - cannot verify Rung 5.")

    print("=== Known Tier 1 chains (Rung 1 and Rung 4 both miss these) ===")
    for brand in KNOWN_TIER_1:
        result = classify_tier(brand)
        if result is None:
            print(f"  {brand:15} -> NOT RESOLVED  (expected Tier 1 - investigate)")
            continue
        tier = tier_for_lookup(result)
        flag = "ok" if tier == "Tier 1" else "MISMATCH - expected Tier 1"
        print(f"  {brand:15} -> {tier:6} count={result['value']} "
              f"conf={result['confidence']}  [{flag}]")
        print(f"      source: {result['source']}")

    print(f"\n=== Waterfall short-circuit: {SHOULD_SHORT_CIRCUIT} ===")
    result = lookup_site_count(SHOULD_SHORT_CIRCUIT)
    reached_rung5 = result["confidence"].startswith("web_")
    print(f"  resolved by: {result['confidence']} (value={result['value']})")
    print(f"  {'MISMATCH - paid for a call Rung 4 could answer' if reached_rung5 else 'ok - Rung 4 answered, Rung 5 never called'}")

    print(f"\n=== Should NOT resolve: {SHOULD_NOT_RESOLVE} ===")
    result = classify_tier(SHOULD_NOT_RESOLVE)
    if result is None:
        print("  -> not resolved  [ok - correctly declined to guess]")
    else:
        tier = tier_for_lookup(result)
        flag = "ok" if tier is None else "MISMATCH - hallucinated a tier for an independent"
        print(f"  -> {tier} conf={result['confidence']}  [{flag}]")
        print(f"      source: {result['source']}")

    print("\nRe-run to confirm the cache is being hit (should be instant, no API calls).")


if __name__ == "__main__":
    main()
