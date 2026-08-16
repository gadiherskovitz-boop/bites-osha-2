# DOL Enforcement Data API — schema findings (Task #2)

Verified against the live API (`apiprod.dol.gov/v4`) on 2026-08-16, using the OSHA
`inspection` and `violation` datasets (ids 10334, 10338 in `/v4/datasets`).

## Resolves the residual risk from the plan

Complaint and Citation are **not** independently-timestamped events on separate
records, and **not** two states of one mutable record. They're a **parent-child
relationship across two tables**, joined by `activity_nr`:

- **`osha/inspection`**: one row per inspection. `insp_type` classifies why the
  inspection happened — `B = Complaint` is one of 13 values (others: A=Accident,
  C=Referral, D=Monitoring, E=Variance, F=FollowUp, G=Unprog Rel, H=Planned,
  I=Prog Related, J=Unprog Other, K=Prog Other, L=Other-L, M=Fat/Cat). Has `open_date`.
- **`osha/violation`**: one row per citation, linked to its parent inspection via the
  same `activity_nr`. Has its own `issuance_date`, `standard` (OSHA standard cited),
  `viol_type`, `current_penalty`, `abate_date`, and separate `fta_*` fields
  (`fta_insp_nr`, `fta_issuance_date`, `fta_penalty`, ...) tracking a
  Failure-to-Abate follow-up on that same citation.

**Implication for the signal scanners:**
- OSHA Complaint signal → poll `inspection` for `insp_type = "B"`, trigger window on `open_date`.
- OSHA Citation signal → poll `violation` for recent `issuance_date`. To attribute a
  citation back to "this account had a complaint that led to a citation," join back to
  `inspection` via `activity_nr` and check if that parent inspection's `insp_type = "B"`.
- A single inspection can have zero, one, or many linked violation rows.

## Correction to the plan's suppression list

`viol_type` (the field this maps most directly to "classification") only has 5
allowed values: `S=Serious, W=Willful, R=Repeat, O=Other, U=Unclassified`. There is
**no "De Minimis" value in this field** — the plan's suppression rule for De Minimis
citations doesn't map to any real data here and is a no-op as written. Failure-to-Abate
is not a `viol_type` value either — it's tracked via the separate `fta_issuance_date`
etc. fields being non-null on a violation row.

## Useful field found: `hazcat`

`violation.hazcat` (General Industry Standard Hazard Category) includes a value
`LACKTRAIN` alongside `BLOODBORNE`, `GUARDING`, `LOCKOUT`, etc. This is a more direct
relevance signal than parsing `standard` numbers alone and should be used together with
the standard-number filter in the OSHA relevance filter (Task #5).

## Confirmed: live data is current and QSR-rich

Querying `naics_code like "7225%"` (restaurants) returned real complaint-type
inspections (`insp_type=B`) dated as recently as 2026-08-11 — Church's Texas Chicken,
Denny's, Panera Bread, Fogo de Chão all appear as real, recent records. Of the 200
most recent QSR inspections pulled, 154 were complaint-type. Good signal density for
the live-demo risk mitigation in the plan.

## API mechanics (for the scanner build)

- Base: `https://apiprod.dol.gov/v4/get/<agency>/<endpoint>/<format>?...&X-API-KEY=<key>`
- Agency/endpoint for this project: `osha/inspection`, `osha/violation`
- `filter_object` takes a JSON string with `field`/`operator`/`value` (operators: eq,
  neq, gt, lt, in, not_in, like), combinable via `and`/`or`. Must be URL-encoded.
- `limit` max 10,000 records or 5MB per request, default 10. Use `offset` to page.
- **Rate limit observed**: after ~15 requests in quick succession the free-tier key
  started returning HTTP 429 and stayed rate-limited for several minutes. Build the
  scanner with request throttling/backoff and avoid tight query loops — batch
  `activity_nr` lookups with the `in` operator rather than one request per account.
- Legacy `enforcedata.dol.gov` is fully retired (redirects to `data.dol.gov`) — this
  v4 API is the only live path.

## Not found in the modernized dataset catalog

No standalone "Complaint" table exists (as of this check, catalog has 42 total
datasets, 11 under OSHA). Complaints only exist as `inspection.insp_type = "B"` rows,
not a separate feed.
