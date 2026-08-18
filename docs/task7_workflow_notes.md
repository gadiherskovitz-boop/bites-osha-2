# Task #7 — HubSpot workflow + Tier 3 sequence

**Verified live end-to-end 2026-08-18.** Investigated and built same-day;
initially blocked the same way Amplemarket was — not a code problem, a
live-account setup problem (private app scopes, a UI-authored sequence, a
connected sending inbox, all things only the portal owner could do) — but
every blocker was cleared in this session and the real enrollment call now
succeeds against the real portal.

**Final proof**: `enroll_in_sequence()` called live, real response:
`{"id": "5546974400", "toEmail": "gordon.penny@spanglercandy.com",
"enrolledAt": "2026-08-18T09:27:22.575Z", ...}` — contact enrolled in
`QSR T3 - OSHA Trigger - Bites Assignment` (id `846865597`), a To-do-only
sequence (no email steps, so nothing was ever at risk of sending).

## What was confirmed live, in order

**First pass — everything 403'd.** The credential (portal EU1, 149021592) is
a **Service Key** (`Settings → Integrations → Service Keys`, not the Private
Apps page — that page has migrated to a "Development" hub that, confusingly,
shows this account's key nowhere; Legacy Apps and Projects were both empty
for it. Service Keys is the actual, correct place for a single-portal
API credential in the current HubSpot UI). Every automation-related endpoint
403'd with a clean `MISSING_SCOPES` error (same shape as the earlier Slack
`chat:write` gap, not a plan/feature-tier error) - a good early signal this
was a scope gap, not a real feature-availability wall, which turned out to
be correct: this portal is on a **Sales Hub Enterprise trial**, which
includes both Workflows and Sequences.

**Scopes added** (Service Keys → the key in use → Edit → Scopes):
- `automation` — workflows/flows
- `crm.objects.custom.sensitive.write` — custom-object-triggered workflows
- `automation.sequences.read` — list sequences
- `automation.sequences.enrollments.write` — enroll a contact
- `crm.objects.owners.read` — look up the HubSpot user id
- `communication_preferences.read_write` — added in a second pass, see
  "Consent/GDPR" below

**Second pass, after scopes** — two more real, live-only findings:
1. `GET /automation/sequences/2026-03/sequences` 400s
   (`"The sequence ID provided is invalid"`, `sequenceId: ["sequences"]` -
   `sequences` gets parsed as a path segment, not a resource collection).
   The real endpoint is `GET /automation/sequences/2026-03` with `userId`
   and `limit` as query params - fixed in `list_sequences()`.
2. Every list/enroll call on this endpoint **requires `userId` as a
   mandatory query param**, not optional - a call without it 400s
   (`"query param userId may not be null"`).

## The Sequences API has no create endpoint — confirmed from HubSpot's own docs

Checked directly against HubSpot's public API reference before writing any
code: the Sequences API is enroll/read only.

- `POST /automation/sequences/2026-03/enrollments` — enroll a contact.
  Requires `contactId`, `sequenceId`, `senderEmail` in the body and a
  `userId` query param. Scope: `automation.sequences.enrollments.write`.
- `GET /automation/sequences/2026-03` (`userId` + `limit` query params) —
  list existing sequences. Scope: `automation.sequences.read`.
- **No `POST` to create one.** Sequences are UI-authored in HubSpot, same as
  email templates — they carry personalization tokens and a sender identity
  the API has no model for. This isn't a scope gap; the endpoint doesn't
  exist.

**So the Tier 3 sequence was built once, by hand, in the HubSpot UI** — same
category of one-time manual setup as the Slack app reinstall. What actually
shipped: `QSR T3 - OSHA Trigger - Bites Assignment` (id `846865597`), one
**To-do** step (a HubSpot task type, not Email — the user chose To-do over
Call, which is even simpler than the architecture doc's "call-task only"
spec but satisfies the same real requirement: no step type in this sequence
can send anything automatically).

**Connected sending inbox** — required to enroll into *any* sequence, even
one with zero email steps, since enrollment is a sequence-level action. The
user connected a secondary Gmail (`gh317627@gmail.com`, not their primary
personal inbox — a deliberate choice made after checking what HubSpot's
inbox connection actually exposes: matched-contact email logging is scoped
to CRM-relevant correspondence, not a wholesale mailbox import, but using a
throwaway address avoided the question entirely).

`.env` now carries the real, live values:
```
HUBSPOT_TIER3_SEQUENCE_ID=846865597
HUBSPOT_SENDER_EMAIL=gh317627@gmail.com
HUBSPOT_SENDER_USER_ID=96528757
```
Read via `os.environ.get()` in `pipeline/signal_handler.py`, same
optional-and-skip-cleanly pattern as `ANTHROPIC_API_KEY` for Rung 5 — if
any were still unset, enrollment would skip and report why rather than
silently no-op or fake success.

## Consent/GDPR — a real finding, not just a test hurdle

First live enrollment attempts against three of the portal's seed contacts
(`gordon.penny@spanglercandy.com`, `john.carothers@bobevans.com`,
`kori_walker@captainds.com`) all failed with `SequenceError.UNSUBSCRIBED`,
**after** the connected-inbox blocker was already cleared. All three
contacts came back with `hs_marketable_status: null` — these look like
HubSpot's own default seed/sample CRM data (`hs_object_source: INTEGRATION`,
domains unrelated to this project's QSR data), not real people this
pipeline sourced. This portal is EU-hosted, and HubSpot enforces GDPR
consent for Sequences (a sales/one-to-one email channel) regardless of
whether the destination sequence has email steps — every contact defaults
to no legal basis for one-to-one communication until one is explicitly
recorded.

`hs_marketable_status` turned out to be **read-only** through the normal
contacts PATCH endpoint — writing it silently no-ops (200, but the value
never changes). The real fix needs the dedicated consent API:
```
POST /communication-preferences/v3/subscribe
{"emailAddress": ..., "subscriptionId": "3303612298",  # "One to One" (Sales)
 "legalBasis": "CONSENT_WITH_NOTICE", "legalBasisExplanation": "..."}
```
scope `communication_preferences.read_write`, subscription id found via
`GET /communication-preferences/v3/definitions`. Run once, with the user's
explicit go-ahead (a real write to a consent record, even on demo data), on
the one test contact — enrollment succeeded immediately after.

**This is real, load-bearing information for Task #4**, not just a test
workaround: a production build enrolling real signal-derived contacts into
this sequence will hit this exact same check. `resolve_contact()` (blocked
on Amplemarket) should establish a legal basis at contact-creation time,
not leave it to be discovered at first enrollment failure.

## Decision: no native HubSpot workflow object

The architecture doc's original design was "a real HubSpot workflow,
triggered by qsr_signal object creation, auto-enrolls the contact." Built
instead: `pipeline/signal_handler.py:_maybe_enroll_in_sequence()`, called
directly from `handle_signal()` right after the `qsr_signal` object itself is
created.

**Why, not just "couldn't get to it":**

1. A native workflow watching for `qsr_signal` creation would only re-detect
   an event `handle_signal()` itself just caused, a few lines earlier in the
   same function. That's redundant orchestration — the information a
   workflow's trigger would fetch back from the CRM is information this
   function already has in memory.
2. Custom-object-triggered `PLATFORM_FLOW`s via the v4 Flows API are real
   but genuinely more moving parts (a second scope, a beta-flagged event
   trigger shape per HubSpot's own docs) for a benefit that doesn't apply
   here, since nothing *else* creates a `qsr_signal` record that this
   pipeline wouldn't already know about.
3. It matches the pattern already established for the other two things that
   fire on every signal — the Company Note and the Slack post are also
   direct calls from `handle_signal()`, not HubSpot-side automations.

This is a considered call, not a workaround for the scope block — flagging
it explicitly since it's a real deviation from the plan doc's wording, same
as the account-first→signal-first pivot and the Duo-over-Clay switch were.
Worth surfacing when presenting: "we chose direct orchestration over a
native workflow because the signal handler already computes exactly what a
workflow would have to re-derive."

## What's built and verified vs. what's still open

**Built and verified live end-to-end:**
- `pipeline/hubspot_client.py:list_sequences()` / `enroll_in_sequence()` —
  both hit the real API successfully.
- `pipeline/signal_handler.py:_maybe_enroll_in_sequence()` — gates on
  `tier == "Tier 3"`, `sequence_eligible` (excludes Fat/Cat), a resolved
  `contact_id`, and all three env vars being set; unit-verified every skip
  path reports the right reason. The success path is now also live-verified
  via the direct `enroll_in_sequence()` call above (`_maybe_enroll_in_sequence`
  itself wasn't re-run live since it additionally requires a real
  `contact_id`, which doesn't exist yet — see below).
- `handle_signal()` now takes an optional `contact_id` and returns
  `sequence_enrollment: {attempted, reason | sequence_id}` alongside the
  existing fields.
- The real Tier 3 sequence, scopes, connected inbox, and `.env` config all
  exist and are confirmed working.

**Still open — one real dependency, not a setup blocker:**

`_maybe_enroll_in_sequence()` cannot fire for a real signal until Task #4
(`resolve_contact`, blocked on Amplemarket) supplies a real `contact_id` —
`handle_signal()` still passes `contact_id=None` for every actual OSHA
signal today, so it correctly reports `attempted: False,
"reason": "no resolved contact yet"` in production right now. That's the
one remaining wire-up, and it's Task #4's dependency, not Task #7's.

When Task #4 lands, also carry forward the consent finding above: give the
newly-created contact a legal basis (`communication_preferences.subscribe`,
subscription id `3303612298`) at creation time, or enrollment will fail with
`SequenceError.UNSUBSCRIBED` on real signal-derived contacts too.

## Files

- `pipeline/hubspot_client.py` — `list_sequences`, `enroll_in_sequence`.
- `pipeline/signal_handler.py` — `_maybe_enroll_in_sequence`,
  `handle_signal(signal, contact_id=None)`.
- `scripts/handle_signals.py` — prints `sequence_enrollment` per signal.
