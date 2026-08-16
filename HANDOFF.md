# Handoff: QSR Prospecting Engine (Bites GTM Engineer Take-Home)

## Goal

Build a working prototype of a QSR prospecting engine for a GTM Engineer take-home assignment with Bites (mybites.io): signals in, a maintained/tiered account list, mapped contacts, signal+tier-specific GTM motions, and one real personalized first-touch — presented live in ~30 minutes as running software, not a deck. Code must be tracked on GitHub and built per `karpathy-coding-guidelines` (minimal, surgical, no premature abstraction).

## Status

A long, deliberate planning conversation (using the `grilling` skill) fully designed the system before any code was written. **The full approved plan is the primary artifact — read it first.**

- **Plan file (read this first):** `/Users/ariherskovitz/.claude/plans/task-build-an-automated-parsed-rocket.md` — contains the complete architecture, account sourcing/tiering logic, both signal definitions (with the exact OSHA-relevance filter, reasoned from real research into which OSHA standards actually have a training-abatement component), the contact-resolution design, HubSpot data model, Slack/Note message templates, the GTM motion matrix, the personalization approach, and a step-by-step build sequence with a verification checklist. Every decision in it was explicitly discussed and reasoned through, not assumed — treat it as authoritative.
- **Facts already gathered during planning** (don't re-research): Bites' actual product/ICP (researched from mybites.io — microlearning for frontline/deskless workers in hospitality/restaurant/retail/FMCG); HubSpot portal is connected (EU1, account 149021592) with standard Company/Contact properties confirmed available; Clay workspace is connected (no custom subroutines exist — use built-in Clay tools); Slack is connected (no pre-existing relevant channels found — 3 new ones need creating: `qsr-osha-complaints`, `qsr-osha-citations`, `qsr-hiring-signals`); DOL Enforcement Data API confirmed to exist and a free key was already obtained; Greenhouse/Lever public job-board APIs confirmed to work with no auth.
- **Task tracking:** 9 tasks were created in this session's task system, IDs #1–#9, mirroring the plan's build sequence (repo scaffold → verify DOL schema → account list/tiering → contact resolution → signal scanners → signal handler → Tier 3 automation → Tier 1 motion/email → end-to-end verification). Task #1 is marked `in_progress`; #2–#9 are `pending`.
- **Nothing has actually been built yet.** A `git init` was attempted as the first build step and was interrupted by the user in favor of writing this handoff first. The local working directory has no repo, no code, no files besides this handoff doc.

## Open items

- Local git repo not yet initialized. Remote already exists and is ready to receive a push: `https://github.com/gadiherskovitz-boop/bites-osha-2.git`
- A DOL Enforcement Data API key was shared in chat during planning but has **not been stored anywhere yet**. It must go directly into a gitignored `.env` on first build step, never be committed, and never be echoed in chat again.
- HubSpot private app token, Slack bot token, and a Clay API key are still needed (the user has these or can generate them easily, but none have been provided yet). These are required because the deliverable is a standalone pipeline that calls these APIs directly — separate from the MCP connections used during planning, which only worked for exploration inside this chat session.
- **Unresolved technical risk** (flagged explicitly in the plan, not yet checked): the DOL Enforcement Data API's real schema for "Complaint" vs "Citation" hasn't been verified — whether they're independently-timestamped events, or two states of one inspection record. This affects whether the "complaint leads citation by 2–5 months" signal design works as designed. Must be checked against the live API before writing OSHA trigger logic.
- `gh` CLI is not installed on this machine; git/GitHub auth hasn't been set up locally.

## Key references

- Approved plan: `/Users/ariherskovitz/.claude/plans/task-build-an-automated-parsed-rocket.md`
- GitHub remote: `https://github.com/gadiherskovitz-boop/bites-osha-2.git`
- Working directory: `/Users/ariherskovitz/Documents/Claude/Projects/Bites Assignment/Assignment 2`
- Task list: 9 tasks (#1–#9) in this session's task tracker — check via `TaskList`/`TaskGet` for current status

## Suggested next steps

1. Resume Task #1: `git init`, create `.gitignore` (must cover `.env`), create `.env` with real credentials (DOL key now, HubSpot/Slack/Clay tokens once obtained), initial commit, add the remote, push.
2. Task #2: call the DOL Enforcement Data API directly and inspect its actual response schema before writing any OSHA trigger logic — resolve the open technical risk above.
3. Continue through Tasks #3–#9 in order, exactly as sequenced in the plan file's "Build sequence" section.

## Suggested skills

- `karpathy-coding-guidelines` — already the agreed coding standard for this build (minimal diffs, no speculative abstraction); keep applying it as implementation proceeds.
