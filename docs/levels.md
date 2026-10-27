# KRAKADYL — levels (the full destination, defined before writing code)

Per `destination-driven-construction`: the target is the final, ambitious
product, known from day one. Time decides how many of these levels get
reached in the hackathon window (Oct 27 – Nov 4, 2026) and after. It
never decides how complete the levels actually attempted are, and it
never decides which invariants are present from Level 1.

## Why this matters, stated plainly (so no later decision contradicts it)

KRAKADYL exists for investigations under real pressure: time pressure,
missing people, shift changes, and — just as common and more dangerous —
**coordination failure**: Investigator B assumes Investigator A already
preserved an artifact or already checked a source, because nobody wrote
down that it was still open. The cost of that assumption being wrong is
not symmetric with the cost of checking.

It is also built, explicitly, to manage executive-function load — Anna
has ADHD, and designed this for herself first: a case should never
require anyone to hold "what's done, what's pending, what's assumed but
not verified, and what do I do right now" in their own head. The system
is the external memory. This is not a feature for a later level — it is
why the product exists at all.

## Invariants present from Level 1 — never bolted on later

1. **Authority layer (ALLOWED / CONFIRM / GATHER_EVIDENCE / FORBIDDEN +
   chained receipts)**, decided outside the model — established 2026-10-26.
2. **Laya as a typed semantic sensor** that informs what to check; it
   never grants authority by itself — established 2026-10-26.
3. **Evidence state and authority state are separate dimensions**
   (`SUFFICIENT/MISSING/CONFLICTING/STALE` × `GRANTED/NEEDS_CONSENT/
   DENIED/EXPIRED`) — established 2026-10-26.
4. **Custody is explicit, never assumed.** Every `EvidenceRequirement`
   and `ProposedAction` has a named owner and a status that distinguishes
   *claimed done* from *verified done*. "Someone probably already did
   this" is not a system state — it doesn't exist as an option. If it
   wasn't verified, it's open, full stop, regardless of what anyone
   believes.
5. **The next move is always answerable without reconstructing context.**
   At any point — after an interruption, a shift change, a context
   switch — the system can state, from recorded state alone, what the
   single next useful action is and why. No capability is allowed to
   require a person to remember what they were doing instead of the
   system recording it. This generalizes Anna's own
   [non-overwhelming-ux](https://github.com/annatchijova/SKILLS/tree/main/non-overwhelming-ux)
   and [terminal-first](https://github.com/annatchijova/SKILLS/tree/main/terminal-first)
   skills from individual cognitive-load design into a structural product
   invariant, not just an interface style.

If a level doesn't carry all five, it isn't a level of this product —
it's a prototype of something else, same rule that already applied to
the authority layer.

## The levels

### Level 1 — A single investigable case, one investigator, end to end

`Mission`, `Mandate`, `Observation`, `Claim`, `EvidenceRequirement`,
`Hypothesis`, `ProposedAction`, `PreparedAction`, `Decision`, `Receipt` —
all with the custody fields (owner, claimed/verified status) and the
next-move surface from day one, not added after the "real" version
works. One real domain action actually executed (e.g., assembling a
verifiable local evidence package), not simulated. This alone is a
complete, demonstrable product — later levels extend it, they don't
replace it.

### Level 2 — The case stays alive: contradictions, staleness, recovery

A dependency-invalidation engine: when an observation, a permission, or
a destination changes, the system identifies exactly which prepared
actions and hypotheses depended on the stale fact, invalidates them, and
proposes a still-legitimate route forward — or closes honestly with
"this can no longer be resolved." This engine is general — Level 4
reuses it rather than inventing a second one.

### Level 3 — Active perception

SAM 3.1 for regions/tracking in photos and video tied to the case's
observations and their provenance; requesting a new, specific capture
when that's the only way to resolve a discriminating question — never
treating a mask as verified identity, custody, or causation.

### Level 4 — Shared custody, team investigations

More than one investigator on the same case. This is Level 2's
invalidation engine applied to the case where "what changed" is a
teammate's action, not just time or new evidence: if Investigator B
claims to have preserved something, it's recorded as *claimed*, not
*verified*, until independently confirmed or until B explicitly marks it
with evidence attached. Conflicting claims surface loudly, not silently.
A shift handoff view answers "what do I need to know to pick this up"
from recorded state — not from scrolling messages.

### Level 5 — Comparable routes

"What would this case allow under a different evidence or authority
limit?" as a measured counterfactual, kept visibly separate from the
real case state — never silently merged back into it.

### Level 6 — Investigations that span real time

Work that spans days or weeks of actual investigation time, not
compressed into a demo window — persistent missions, sub-mandates,
revisiting a case after a long gap without having lost the thread.

### Level 7 — Ecosystem

Real adapters to Velociraptor, SIFT, i2, and VIGÍA with explicit
contracts per adapter; an exportable SDK; an independent verifier
anyone can run without trusting KRAKADYL's own code; the benchmark
published as an open, documented dataset.

## What the hackathon window reaches is decided later, by the clock, not by this document

This file does not say which levels Oct 27 – Nov 4 reaches. It says what
each level *is*, so that whichever one the clock stops at is complete
and correct, not approximated. See `docs/language-decision.md` for the
Python/TypeScript split and why, and the project root `README.md` for
why this continues past the hackathon regardless of outcome.
