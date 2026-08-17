"""Live verification for Rung 5 (pipeline/tier_classifier.py).

Needs ANTHROPIC_API_KEY (read from .env). Cases are chosen so the answers
are known independently - the only way this proves anything:

- Burger King / Pizza Hut / KFC / Dairy Queen: national chains,
  unambiguously Tier 1. These are exactly the brands our 28-brand Rung 1
  list misses and that Wikidata has no P8368 claim for (verified live), so
  they are the real target of this rung.
- Subway: Rung 4 already resolves it via Wikidata, so the waterfall should
  short-circuit and never pay for a Rung 5 call.
- Master Pho 1 Llc: a real single-location independent from our own OSHA
  scan. Must NOT come back as a tiered chain.
"""
import os
import sys
import time

from dotenv import load_dotenv

load_dotenv()

from pipeline.site_count import lookup_site_count  # noqa: E402
from pipeline.tier_classifier import MODEL, classify_tier, round_up_band  # noqa: E402
from pipeline.tiering import tier_for_lookup  # noqa: E402

KNOWN_TIER_1 = ["Burger King", "Pizza Hut", "KFC", "Dairy Queen"]
SHOULD_SHORT_CIRCUIT = "Subway"
SHOULD_NOT_RESOLVE = "Master Pho 1 Llc"


def main():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit("ANTHROPIC_API_KEY not set - cannot verify Rung 5.")
    print(f"model: {MODEL}\n")

    print("=== Round-up rule (pure logic, no API) ===")
    for src, want in [("Disqualified", "Tier 3"), ("Tier 3", "Tier 2"),
                      ("Tier 2", "Tier 1"), ("Tier 1", "Tier 1")]:
        got = round_up_band(src)
        print(f"  {'ok  ' if got == want else 'FAIL'} {src:13} -> {got}")

    print("\n=== Known Tier 1 chains (Rung 1 and Rung 4 both miss these) ===")
    for brand in KNOWN_TIER_1:
        t0 = time.time()
        result = classify_tier(brand)
        elapsed = time.time() - t0
        if result is None:
            print(f"  FAIL {brand:14} -> NOT RESOLVED (expected Tier 1)")
            continue
        tier = tier_for_lookup(result)
        ok = "ok  " if tier == "Tier 1" else "FAIL"
        count = f"{result['value']:,}" if result["value"] else "band only"
        print(f"  {ok} {brand:14} -> {tier:6} {count:>10}  "
              f"{result['confidence']:9} ({elapsed:.1f}s)")

    print(f"\n=== Waterfall short-circuit: {SHOULD_SHORT_CIRCUIT} ===")
    result = lookup_site_count(SHOULD_SHORT_CIRCUIT)
    paid = result["confidence"].startswith("web_")
    print(f"  {'FAIL' if paid else 'ok  '} resolved by {result['confidence']} "
          f"(value={result['value']}) - "
          f"{'paid for a call Rung 4 could answer' if paid else 'Rung 5 never called'}")

    print(f"\n=== Must NOT tier an independent: {SHOULD_NOT_RESOLVE} ===")
    result = classify_tier(SHOULD_NOT_RESOLVE)
    if result is None:
        print("  ok   -> not resolved (correctly declined)")
    else:
        tier = tier_for_lookup(result)
        ok = "ok  " if tier is None else "FAIL"
        print(f"  {ok} -> {tier} value={result['value']} {result['confidence']}"
              f"  {'(hallucinated a chain)' if tier else ''}")

    print("\n=== Cache (re-run of the first brand, should be ~0.00s) ===")
    t0 = time.time()
    classify_tier(KNOWN_TIER_1[0])
    elapsed = time.time() - t0
    print(f"  {'ok  ' if elapsed < 0.1 else 'FAIL'} {elapsed:.3f}s")


if __name__ == "__main__":
    main()
