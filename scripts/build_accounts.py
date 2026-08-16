from pipeline.accounts_seed import SEED_ACCOUNTS
from pipeline.clay_client import enrich_company
from pipeline.hubspot_client import upsert_company
from pipeline.tiering import governance_model, tier_for_site_count


def build_account_list():
    """Tiers the seed list and enriches each qualifying account via Clay.

    Disqualified accounts (<=5 sites) are dropped entirely, per the plan.
    Returns the list of qualifying accounts with tier/governance/enrichment
    data attached, ready to push to HubSpot.
    """
    accounts = []
    for seed in SEED_ACCOUNTS:
        tier = tier_for_site_count(seed["site_count"])
        if tier is None:
            continue

        enrichment = enrich_company(seed["domain"]) or {}
        accounts.append(
            {
                **seed,
                "tier": tier,
                "governance_model": governance_model(
                    seed["franchised_units"], seed["company_units"]
                ),
                **enrichment,
            }
        )
    return accounts


def push_to_hubspot(accounts):
    for account in accounts:
        upsert_company(
            account["domain"],
            {
                "name": account["name"],
                "bites_tier": account["tier"],
                "site_count": account["site_count"],
                "governance_model": account["governance_model"],
                "disqualified": "false",
            },
        )
        print(f"{account['name']}: {account['tier']} ({account['site_count']} sites) -> HubSpot ok")


if __name__ == "__main__":
    accounts = build_account_list()
    print(f"{len(accounts)} qualifying accounts (of {len(SEED_ACCOUNTS)} seeded)")
    push_to_hubspot(accounts)
