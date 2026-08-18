# Task #8 — Tier 1 personalized email rules

Adapted 2026-08-18 from `Assignment 1/osha_signal/personalize.py`. That
file's opening comment records its own origin worth repeating here: the
first draft of these rules was feature-led ("short branded video, no app,
no logins, built in 14 minutes"); it was rewritten problem-first, and *that*
became the standard. Nothing about the core standard changed for this
assignment — only the deltas below did, each for a real reason found while
building this project, not a stylistic preference.

## What carries over unchanged from Assignment 1

- **Sell the problem, not the product.** No feature lists, no app/login/
  format mechanics. If a sentence could appear in a product brochure, cut it.
- **Structure**: signal → what it means for the recipient → the real
  training failure modes (heart of the email) → Bites as the answer → proof
  point + soft offer.
- **Tone**: peer-to-peer, calm, specific, no exclamation points, no hype
  adjectives, never sensationalize the trigger.
- **Never include repeat-offender/brand-history numbers in the body** —
  internal SDR context for urgency, not something to confront a prospect
  with (this build's equivalent: never quote `_history_lines()`'s
  floor/total figures from `pipeline/signal_handler.py` in the email).
- **Don't invent facts** — only the supplied signal, company facts, and
  approved proof points.
- `FRONTLINE_TRAINING_FAILURE_MODES` (timing / completion / channel /
  content) and `PROOF_POINTS` (Unilever 90%+ engagement, 67% faster
  onboarding) — reused verbatim. These are durable Bites facts, not
  Assignment 1-specific output.

## What changes for this assignment, and why

**1. Fat/Cat is a hard exclusion upstream, not a tone rule.** Assignment
1's rule 4 softened tone for fatality-related triggers inside the prompt
itself. This build doesn't need that branch: Fat/Cat signals never reach
personalization at all — excluded unconditionally at the tier layer
(`sequence_eligible: False` regardless of tier, `pipeline/signal_handler.py`).
`draft_first_touch()` asserts this rather than handling it stylistically —
being called with a Fat/Cat signal is a caller bug, not a copy decision.

**2. The opening has to work without a citation.** Every one of Assignment
1's six examples opened on a real citation. This build's real Tier 1
signals don't have that luxury: both signals currently live in this portal
(Chipotle, Pizza Hut/Ayvaz) are Complaint-type Inspections with **no
citation yet** — Complaint/Accident triggers fire on the inspection opening,
before any citation is decided. So the opening now branches:
- **Citation exists (Violation)**: open on it directly, as Assignment 1 did.
- **No citation yet (Complaint/Accident)**: open on the inspection itself,
  and let the practical-meaning beat carry the stakes instead ("puts
  training documentation on record" - not "gets a hard look at re-inspection").

**3. The video needs a reason, not a bare tag.** New required beat: one
sentence tying the video directly to the failure mode just named, ending in
the placeholder - never dropped cold. Also **branded per-account**: the
reference draft uses a `{company}` token, meaning the video reference itself
is templated per company, not a generic Bites clip.

**4. Word cap: ~140, not 120.** The video beat doesn't fit the old budget
without cutting something structural. The finalized reference draft below
runs ~130 words with every sentence still earning its place, so 140 is a
ceiling, not a target.

**5. Persona default: L&D/Enablement.** Matches `pipeline/persona_tracks.py`
`OSHA_TRACKS` and this project's own framing of Bites' buyer (`HANDOFF.md`).
Assignment 1 defaulted to a Training Coordinator/VP Training contact for the
same reason under a different persona model.

## Reference draft (finalized 2026-08-18, generic — no real account)

This is the standard every generated draft is measured against, same role
Assignment 1's `REFERENCE_DRAFT` played. One slip from the drafting pass
fixed here rather than kept verbatim: "helped Unilever reached" → "helped
Unilever **reach**."

```
Subject: OSHA complaint at your Ohio location

Hi Alex,

I saw OSHA opened a complaint inspection at your Ohio location last month.

Even before any citation is decided, that puts training documentation on record.

The challenge we see with training is that it's often not completed. It's usually boring (no offence). It's mostly front-loaded on day one and never revisited. Plus it lands in an email account front-line staff never check.

Bites redesigned training to address those gaps. Your training modules become short on-brand videos they'll actually watch exactly when they need it. That helps ensure complaints and accidents decline, and they don't become violations.

I had our team put together a 90-second {company} branded video on what that would look like for you: INSERT VIDEO HERE

We've helped Unilever reach 90%+ training engagement and I'd be happy to walk through how.
```

## Built and verified live: `draft_first_touch()`

Unlike Assignment 1 — where `personalize.py`'s prompt was fed to an
interactive session (Clay's MCP connector) to hand-produce six static
drafts, never called as a standalone function in that codebase — this
version is real, callable code: `pipeline/personalize.py:draft_first_touch()`
calls Claude Sonnet 5 directly, same pattern Rung 5 established for calling
Claude from the pipeline (`pipeline/tier_classifier.py`), but with the
opposite model tradeoff. Rung 5 runs hundreds of times on a coarse
classification task, so cost dominates and Haiku wins. This runs once and
its entire output IS the deliverable a prospect reads, so quality dominates
instead — Sonnet 5, not Haiku.

**One real tuning finding**: an explicit word-count instruction alone
wasn't enough. "140 words maximum, hard ceiling, count before finishing"
still produced 155–165 word drafts across several live test runs. What
fixed it was embedding `REFERENCE_DRAFT` directly in `SYSTEM_PROMPT` as a
worked example ("match this closely, do not exceed its length by more than
a handful of words") — a concrete length/register anchor did more than the
rule stated abstractly. Two smaller live findings from the same tuning
pass, both now encoded as explicit rules: the model surfaced OSHA's
internal case/report number in the copy unprompted (e.g. "your location
(111589)") until told explicitly that a cited standard number is fine but a
bare case ID means nothing to the reader; and it appended an unprompted
"Best, [SDR Name]" sign-off with no name to put there until told the
signature block is added separately, outside this draft.

## Real output — Chipotle's live Complaint signal (2026-08-18)

Generated by `scripts/draft_first_touch.py` against the actual signal live
in HubSpot right now (`activity_nr 1905074.015`, `qsr_signal` id
`446312855784`) — not a hypothetical. Contact is an explicit placeholder,
same honesty pattern as `SUGGESTED_CONTACT_PLACEHOLDER` in
`pipeline/signal_handler.py`: real contact resolution is Task #4, blocked
on Amplemarket. 140 words exactly.

```
Subject: OSHA complaint at your Minnesota location

Hi [First Name],

I saw OSHA opened a complaint inspection at your Minnesota location on July 14.

No citation yet, but it puts training documentation on record and under a closer look.

The usual gap we see isn't a lack of intent, it's execution. Training goes uncompleted, the content is outdated and easy to tune out, and it's often sent to an email frontline staff never open.

Bites closes that gap by meeting crews where they are, with training they'll actually watch when it matters. That's what keeps a complaint from turning into a violation.

I had our team put together a short Chipotle-branded video showing what that would look like at your locations: INSERT VIDEO HERE

We've helped Unilever reach 90%+ training engagement, and I'd be glad to walk through how that translates to reducing OSHA exposure for you.
```

**What's still open**: swap the placeholder contact for a real one once
Task #4 (`resolve_contact`) lands. Everything else — the real signal, the
real account, the rules, the generation call — is real and verified now.

## Files

- `pipeline/personalize.py` — `SYSTEM_PROMPT` (embeds `REFERENCE_DRAFT` as a
  worked example), `FRONTLINE_TRAINING_FAILURE_MODES`, `PROOF_POINTS`,
  `REFERENCE_DRAFT`, `build_user_prompt()`, `draft_first_touch()`.
- `scripts/draft_first_touch.py` — runnable driver, hardcoded to the real
  Chipotle Complaint signal.
