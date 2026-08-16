# Curated seed list of ~28 multi-unit QSR/fast-casual brands, spanning all
# four Bites tiers (Disqualified/Tier3/Tier2/Tier1), assembled from industry
# knowledge for brand selection.
#
# site_count, franchised_units, and company_units are sourced directly from
# QSR Magazine's QSR 50 2026 report (2025 US units,
# https://www.qsrmagazine.com/story/qsr-50-2026-top-50-fast-food-chains-ranked-by-sales/)
# and its companion "50 QSR Contenders for 2026" list
# (https://www.qsrmagazine.com/reports/the-50-qsr-contenders-for-2026/).
# This is a deliberate substitute for Clay here: Clay's company search has no
# location-count field (verified live against api.clay.com/public/v0 — its
# firmographic data covers employee-count bands, revenue, HQ, and industry,
# not physical unit counts), so site_count — the number that actually drives
# tiering — comes from the industry-standard census instead, and
# franchised_units/company_units (governance_model's real source, see
# pipeline/tiering.py) come from the same table. Clay is used separately to
# enrich HQ, employee count, and company type for HubSpot context.

SEED_ACCOUNTS = [
    # Tier 1 candidates (200+ sites)
    {"name": "McDonald's", "domain": "mcdonalds.com", "site_count": 13706, "franchised_units": 13062, "company_units": 644},
    {"name": "Starbucks", "domain": "starbucks.com", "site_count": 16860, "franchised_units": 6813, "company_units": 10047},
    {"name": "Chick-fil-A", "domain": "chick-fil-a.com", "site_count": 3287, "franchised_units": 3219, "company_units": 68},
    {"name": "Taco Bell", "domain": "tacobell.com", "site_count": 7784, "franchised_units": 7124, "company_units": 660},
    {"name": "Wendy's", "domain": "wendys.com", "site_count": 5969, "franchised_units": 5546, "company_units": 423},
    {"name": "Dunkin'", "domain": "dunkindonuts.com", "site_count": 9999, "franchised_units": 9963, "company_units": 36},
    {"name": "Domino's Pizza", "domain": "dominos.com", "site_count": 7186, "franchised_units": 6924, "company_units": 262},
    {"name": "Chipotle Mexican Grill", "domain": "chipotle.com", "site_count": 3938, "franchised_units": 0, "company_units": 3938},
    {"name": "Popeyes", "domain": "popeyes.com", "site_count": 3196, "franchised_units": 3101, "company_units": 95},
    {"name": "Panera Bread", "domain": "panerabread.com", "site_count": 2214, "franchised_units": 1106, "company_units": 1108},
    {"name": "Sonic Drive-In", "domain": "sonicdrivein.com", "site_count": 3412, "franchised_units": 3120, "company_units": 292},
    {"name": "Jersey Mike's", "domain": "jerseymikes.com", "site_count": 3227, "franchised_units": 3201, "company_units": 26},
    {"name": "Firehouse Subs", "domain": "firehousesubs.com", "site_count": 1276, "franchised_units": 1234, "company_units": 42},
    {"name": "Cinnabon", "domain": "cinnabon.com", "site_count": 1339, "franchised_units": 1311, "company_units": 28},
    # Tier 2 candidates (50-199 sites)
    {"name": "Portillo's", "domain": "portillos.com", "site_count": 102, "franchised_units": 0, "company_units": 102},
    {"name": "Black Rock Coffee Bar", "domain": "blackrockcoffeebar.com", "site_count": 181, "franchised_units": 0, "company_units": 181},
    {"name": "Donatos", "domain": "donatos.com", "site_count": 179, "franchised_units": 128, "company_units": 51},
    {"name": "PJ's Coffee", "domain": "pjscoffee.com", "site_count": 180, "franchised_units": 167, "company_units": 13},
    {"name": "Handel's Ice Cream", "domain": "handelsicecream.com", "site_count": 173, "franchised_units": 166, "company_units": 7},
    {"name": "Bubbakoo's Burritos", "domain": "bubbakoosburritos.com", "site_count": 145, "franchised_units": 135, "company_units": 10},
    {"name": "La Madeleine", "domain": "lamadeleine.com", "site_count": 84, "franchised_units": 57, "company_units": 27},
    {"name": "Great Greek Mediterranean Grill", "domain": "thegreatgreek.com", "site_count": 83, "franchised_units": 74, "company_units": 9},
    # Tier 3 candidates (6-49 sites)
    {"name": "Smalls Sliders", "domain": "smallssliders.com", "site_count": 45, "franchised_units": 43, "company_units": 2},
    {"name": "Detroit Wing Co.", "domain": "detroitwingco.com", "site_count": 22, "franchised_units": 18, "company_units": 4},
    {"name": "Original ChopShop", "domain": "originalchopshop.com", "site_count": 27, "franchised_units": 0, "company_units": 27},
    {"name": "Angry Chickz", "domain": "angrychickz.com", "site_count": 34, "franchised_units": 2, "company_units": 32},
    {"name": "Urban Plates", "domain": "urbanplates.com", "site_count": 22, "franchised_units": 0, "company_units": 22},
    {"name": "Zaza Cuban Comfort Food", "domain": "zazacuban.com", "site_count": 15, "franchised_units": 1, "company_units": 14},
]
