# Hiring trigger — Tier 1 personalized email rules

Built 2026-08-18 per explicit request: start from the OSHA rules
(`docs/task8_email_rules.md`, Task #8) as the template, adapt only what
genuinely needs to change for the Hiring trigger. First-pass draft was
reviewed and substantially amended by the user; **finalized version is
below, both `REFERENCE_DRAFT` and `SYSTEM_PROMPT` in
`pipeline/hiring_personalize.py` now reflect it.** Still not wired into
`pipeline/signal_handler.py:handle_hiring_signal` (`tier1_first_touch`
still reports not-yet-built) — that's the remaining step, not a copy
question.

## What changed in review (first draft → finalized)

The user rewrote the body directly rather than commenting on the first
pass — real, substantive corrections, not wording polish:

1. **Subject line: short and blunt, not a sentence.** "Saw the L&D opening
   at {company}" → **"L&D role"**. New explicit rule 3.
2. **The "what it means" beat needed a real diagnosis, not a vague
   gesture.** First draft: "a hire like this usually means training is
   being rebuilt from scratch or has outgrown what's currently holding it
   together" - abstract, says nothing specific. Replaced with a concrete,
   correct insight: L&D is rolling out **desktop/computer-centered
   training to a deskless workforce** - a real format/channel mismatch,
   not a guess about the company's internal state.
3. **Failure modes needed to be causally chained, not listed.** First
   draft flatly listed four symptoms. Finalized version chains two causes
   (boring/dated content + front-loaded timing) into an explicit
   either/or effect (low completion, or low retention even when
   completion isn't the problem) - an argument, not a list. Also restored
   "(no offence)" after the "boring" line - a small human aside that's in
   the *original* OSHA reference too and was dropped by mistake in the
   first Hiring pass.
4. **A real correction to my design assumption: stakes belong in the
   email.** I had written an explicit rule forbidding any risk/compliance
   language, on the theory that a Hiring signal is a growth moment, not a
   risk moment. The user's rewrite added a stakes beat naming real
   downstream consequences directly - "workplace injuries, quality
   suffers, violations rise." **The corrected rule (now rule 4's stakes
   beat)**: the opening still shouldn't imply hiring for this role means
   the company is currently failing - that's an assumption we don't get
   to make. But the real, general consequences of bad frontline training
   are exactly the kind of concrete "sell the problem" content this copy
   style is built on, and shouldn't have been excluded. I'd over-corrected
   in the first pass by conflating "don't accuse this prospect" with
   "don't name real stakes at all" - those are different things.
5. **Bites-as-answer reframed around fixing existing training, not
   equipping a future hire.** First draft: "gives whoever fills this role
   training crews actually watch." Finalized: "helps turn your existing
   training into the right format, at the right time, on the right
   channel" - a cleaner three-part structure, and doesn't lean on an
   assumption about a specific not-yet-hired person.
6. **Video reference simplified.** "I had our team put together a short
   ... video showing how that plays out on the floor" → "I put together a
   {company}-branded training video example" - more personal (first
   person, not "our team"), no elaborate justification needed.
7. **New explicit closing structure: end on a question.** First draft
   ended on the proof-point sentence with no distinct call-to-action.
   Finalized version closes with a separate beat that calls back to the
   hiring signal ("your next hire would love...") and ends on a short,
   direct question ("Open to seeing more?"). New explicit rule: always end
   on a question.
8. **Minor language fix**: "computer-centred" → "computer-centered" (US
   spelling, matching the US audience) - same category of small fix
   Task #8's own doc logged (the "helped Unilever reached" → "reach" grammar
   correction), noted rather than silently changed.

## What carries over unchanged from the OSHA rules

- **Sell the problem, not the product.** No feature lists, no app/login/
  format mechanics.
- **Structure skeleton**: signal → what it means for the recipient → the
  real training failure modes (heart of the email) → Bites as the answer →
  proof point + soft offer.
- **Tone discipline**: peer-to-peer, calm, specific, no exclamation
  points, no hype adjectives.
- **Word cap**: 140, hard ceiling — and the same tuning finding applies:
  a stated word-count rule alone wasn't trusted to hold on its own, so
  `REFERENCE_DRAFT` is embedded directly in the system prompt as a worked
  example, same as Task #8.
- **Don't invent facts** — only the supplied signal, company, and approved
  proof points.
- `PROOF_POINTS` (Unilever 90%+ engagement, 67% faster onboarding) —
  imported from `pipeline/personalize.py`, not duplicated. These are
  durable Bites facts, not trigger-specific.
- **No sign-off line** — the SDR's signature is added separately.

## What changes, and why

**1. The opening frames growth, not risk — but the stakes still get named
honestly.** OSHA's email opens *and stays* in regulatory-exposure territory
throughout. A Hiring signal starts differently: the company is *investing*,
actively building capability, and the opening/trigger framing should never
imply they're currently failing or in trouble just because they're hiring
— that's an assumption we don't get to make. But (corrected after review,
see "What changed in review" below) that doesn't mean avoiding real stakes
altogether: the email still names the genuine downstream consequences of
bad frontline training (injuries, quality, compliance violations) as the
concrete "problem" being sold. The distinction that matters is *accusing
this specific prospect* (never) vs. *naming a real, general consequence*
(expected, and part of what makes the copy honest rather than vague).

**2. No exclusion-trigger or citation-branching logic needed.** OSHA's
prompt has real branching complexity: Fat/Cat is excluded upstream, and the
opening branches on whether a citation exists yet. Hiring has one signal
shape (a job posting) and no severity tiers to exclude — simpler prompt,
nothing lost by not having that complexity.

**3. Opens on the role, not an incident.** "I saw {company} is hiring for
a {role}" replaces "I saw OSHA opened a complaint inspection." Same
one-sentence, plainly-stated, verifiable-fact discipline as OSHA's opening
rule — just a different kind of fact.

**4. The video's justification changes.** OSHA's video answers "what would
better training look like given this citation/inspection." Hiring's video
answers "here's what the person filling this role is about to inherit" —
same required beat (never dropped cold, always tied to the failure mode
just named, company-branded), different framing sentence.

**5. Explicit new rule: never surface the sourcing mechanics.** Job
postings carry things a citation doesn't — a listing ID, a source URL, the
ATS platform name (Greenhouse/Lever/Workday/Adzuna). None of that means
anything to a reader and all of it reads as "we scraped this," which is
exactly what shouldn't be legible in the email. Explicit rule 5 forbids it.

**6. Persona default: same as OSHA — L&D/Enablement.** Matches
`pipeline/persona_tracks.py:HIRING_TRACKS`' own first-choice track.

## Reference draft (finalized, generic — no real account)

The user's own amended copy, genericized back to a `{company}` token and
"Alex," (matching this section's role as a worked example, not a real
send) rather than left McDonald's-specific.

```
Subject: L&D role

Hi Alex,

I saw {company} is hiring for a Learning & Development Manager.

What makes life so tricky for L&D is they're rolling out computer-centered training to a deskless workforce.

The content is often boring (no offence). And it's usually front-loaded into the first few days. So either completion rate is low, or knowledge retention is even lower.

The real issue surfaces down the track - workplace injuries, quality suffers, violations rise.

Bites helps turn your existing training into the right format, at the right time, on the right channel.

I put together a {company}-branded training video example: INSERT VIDEO HERE

We've helped Unilever reach 90%+ training engagement, and teams see 67% faster onboarding.

I'm sure your next hire would love to have a solution like this. Open to seeing more?
```

## Real generated output — McDonald's live Hiring signal, finalized rules (2026-08-18)

Regenerated by `scripts/draft_hiring_first_touch.py` against the finalized
`SYSTEM_PROMPT`/`REFERENCE_DRAFT`, same real "Learning & Development
Manager" signal pushed to HubSpot today (McDonald's being the most
recognizable of that day's real hits, same flagship-account reasoning
Chipotle got for OSHA). Contact is an explicit placeholder, same honesty
pattern as `scripts/draft_first_touch.py` — real contact resolution is
still Task #4, blocked on Amplemarket. 131 words.

```
Subject: L&D role

Hi [First Name],

I saw McDonald's is hiring for a Learning & Development Manager.

What makes life so tricky for L&D is rolling out computer-centered training to a deskless workforce.

The content is often boring (no offence). And it's usually front-loaded into the first few days. So either completion rate is low, or knowledge retention is even lower.

The real issue surfaces down the track - workplace injuries, quality suffers, violations rise.

Bites helps turn your existing training into the right format, at the right time, on the right channel.

I put together a McDonald's-branded training video example: INSERT VIDEO HERE

We've helped Unilever reach 90%+ training engagement, and teams see 67% faster onboarding.

I'm sure your next hire would love to have a solution like this. Open to seeing more?
```

## Files

`pipeline/hiring_personalize.py` (`SYSTEM_PROMPT`, `REFERENCE_DRAFT`,
`build_user_prompt`, `draft_first_touch`), `scripts/draft_hiring_first_touch.py`
(driver, hardcoded to the real McDonald's signal). **Still not wired into**
`pipeline/signal_handler.py:handle_hiring_signal` — the copy is finalized,
but the actual auto-draft-and-Note-and-enroll wiring (mirroring
`_maybe_draft_and_note_first_touch()` for OSHA) hasn't been built yet.
