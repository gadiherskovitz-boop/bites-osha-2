"""First real test batch for the Clay Companies table (contact resolution,
Task #4). Hand-picked, not queried - 19 companies pulled from
output/tier_cache/*.json (real Rung 5 results, run against real Rung-1-miss
establishment names from an actual OSHA scan - not synthetic), filtered down
to genuine QSR/food-service brands and prioritizing Tier 1. Institutional
noise in the cache (Yale, Ford, Northrop Grumman - host orgs that a
cafeteria/catering inspection gets filed under) is excluded on purpose.

Domain is pre-filled wherever confidently known (Rung 1 seed matches or
well-known public domains), left blank otherwise, per the credit-saving
decision on 2026-08-18 - Clay's own domain-finder column only needs to run
for the blanks.

Chipotle Mexican Grill and Pizza Hut are also the two real signals live in
HubSpot right now (see HANDOFF.md) - not just cache entries.
"""
from pipeline.clay_client import write_companies_csv

COMPANIES = [
    # --- Tier 1 ---
    {"company_name": "Chipotle Mexican Grill", "company_domain": "chipotle.com"},
    {"company_name": "McDonald's", "company_domain": "mcdonalds.com"},
    {"company_name": "Chick-fil-A", "company_domain": "chick-fil-a.com"},
    {"company_name": "Dunkin'", "company_domain": "dunkindonuts.com"},
    {"company_name": "Popeyes", "company_domain": "popeyes.com"},
    {"company_name": "Burger King", "company_domain": "bk.com"},
    {"company_name": "KFC", "company_domain": "kfc.com"},
    {"company_name": "Pizza Hut", "company_domain": "pizzahut.com"},
    {"company_name": "Dairy Queen", "company_domain": "dairyqueen.com"},
    {"company_name": "Sweetgreen", "company_domain": "sweetgreen.com"},
    {"company_name": "Lettuce Entertain You Restaurants", "company_domain": "leye.com"},
    {"company_name": "Otg", "company_domain": None},
    # --- Tier 2 ---
    {"company_name": "Yoshinoya Companies", "company_domain": "yoshinoyaamerica.com"},
    {"company_name": "Mendocino Farms", "company_domain": "mendocinofarms.com"},
    {"company_name": "Nevada Restaurant Services, Inc.", "company_domain": None},
    # --- Tier 3 ---
    {"company_name": "Buc-ee's", "company_domain": "buc-ees.com"},
    {"company_name": "Dig Inn Support", "company_domain": None},
    {"company_name": "Abby's Pizza", "company_domain": None},
    {"company_name": "Toca", "company_domain": None},
]

if __name__ == "__main__":
    path = "output/clay_test_companies.csv"
    write_companies_csv(COMPANIES, path)
    print(f"wrote {len(COMPANIES)} companies to {path}")
