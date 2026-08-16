# Clay API — findings (Task #3)

## Two different Clay "API keys" exist — easy to grab the wrong one

Clay's app has **Settings → Your Profile → "API key"** tab (legacy key, used for
things like webhook-based table imports) and a separate **"API keys (beta)"** tab.
Only the beta-tab key (prefixed `clay_scoped_...`) authenticates against Clay's
public REST API at `https://api.clay.com/public/v0` with header `clay-api-key`.
The legacy key (`clay_user_...`) returns 401 against that API.

## Clay's company search has no location-count field

Verified live via `GET /search/filters-mode/fields?source_type=companies` and a
real search run (`mcdonalds.com`). Available company fields: `name`,
`description`, `type` (Public/Private), `size` (employee-count bucket, e.g.
"10,001+ employees"), `country`, `domain`, `linkedin_url`, `location` (HQ),
`industry`, `annual_revenue`, `total_funding_amount_range_usd`. No structured
"number of locations" field exists — this is a specialized retail/restaurant
data point that general firmographic (LinkedIn-sourced) providers like Clay
don't carry. Unstructured mentions sometimes appear in `description` text
(e.g. "over 37,000 locations") but inconsistently across entities and not
reliably parseable.

**Consequence for the account list (Task #3):** `site_count` — the number that
actually drives Bites tiering — is sourced instead from QSR Magazine's QSR 50
2026 report and its companion "50 QSR Contenders for 2026" list, the industry's
own annual census of U.S. chain restaurant unit counts. See
`pipeline/accounts_seed.py` for the sourced data and citations.
`governance_model` (franchise vs. corporate) is derived from the same table's
franchised-units vs. company-units columns, rather than guessed.

Clay is used for what it's actually good at: resolving the canonical company
record per domain and pulling HQ, employee-count band, and company type
(`pipeline/clay_client.py:enrich_company`) — real, structured, live data.

## Multiple Clay records per domain

A domain search can return several LinkedIn-sourced entities for one brand
(e.g. `mcdonalds.com` → "McDonald's" global corp, "Hamburger University",
"McDonald's UAE", "McDonald's Deutschland", "McDonald's Norge", ...). The
current `enrich_company` takes the first result, which was the correct global
parent entity in testing, but this is worth a spot-check for any brand where
that assumption doesn't hold.
