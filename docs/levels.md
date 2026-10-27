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
4. **Custody is explicit, never assumed, and has a real lifecycle.**
   Every `EvidenceRequirement` and `ProposedAction` carries a `Custody`
   with a full status (`UNASSIGNED -> ASSIGNED -> ACKNOWLEDGED ->
   IN_PROGRESS -> REPORTED_DONE -> VERIFIED_DONE`, plus
   `BLOCKED/EXPIRED/CANCELLED/UNKNOWN`), implemented in
   `krakadyl/core/models.py`. Three conflations are structurally
   impossible, not just discouraged by convention:
   - `ASSIGNED` is not `ACKNOWLEDGED`. Handing a task to someone is a
     different fact from that person having taken responsibility for
     it — this is its own enum value, not a side timestamp, so "who
     hasn't acknowledged yet" is a direct query.
   - `REPORTED_DONE` is never read as `VERIFIED_DONE`.
     `krakadyl/core/continuity.py::evidence_state_from_requirement` is
     the one place this gets decided, and it returns `MISSING` for a
     claim with no independent verification, every time.
   - **Neither collapses back into "didn't happen" or "unknown."**
     There are three genuinely different situations — not done;
     reported done but unverified; verified against an explicit
     criterion — and uncertainty about which applies is information
     the system preserves as its own state, not a fact it discards
     because nobody confirmed it. "Someone probably already did this"
     is still not representable — but neither is erasing that someone
     claimed to.
5. **The next move is always answerable without reconstructing context —
   and "answerable" means a clear answer, not a fabricated single
   priority.** `krakadyl/core/continuity.py::next_move()` returns one of:
   a single recommended action with its reasons, visible alternatives
   next to it; an explicit *uncertain* state when two or more candidates
   are genuinely tied on every criterion that would break the tie (never
   an arbitrary pick dressed up as a recommendation); or a *blocked* list
   for anything that has a legitimate claim on attention but no
   authorized path right now — surfaced, never hidden. No capability is
   allowed to require a person to remember what they were doing instead
   of the system recording it.
6. **Untrusted content never acquires execution authority.** Investigated
   material, external documents, and anything a model outputs after
   reading them — Muse Spark's summary, Laya's classification — stay on
   the data side of a hard line. None of them can become an instruction,
   a permission, or an installable dependency just by being interpreted.
   A malicious file in the evidence set does not get to turn into an
   operational instruction because a model summarized or classified it.
   This generalizes the Oct 26 "observed content is not authorization"
   rule from the adversarial benchmark category to the full system,
   including its own supply chain — see "Untrusted content and supply
   chain" below.

If a level doesn't carry all six, it isn't a level of this product —
it's a prototype of something else, same rule that already applied to
the authority layer.

## Where invariant 5 actually comes from

Not a generic UX principle — it is Anna's own
[terminal-first](https://github.com/annatchijova/SKILLS/tree/main/terminal-first)
skill, carried over directly from a documented personal case (see
`docs/terminal-first-and-blame.md` for the full account): technical
competence and executive-function availability on a given day are
**independent variables** — a person fluent with a terminal can still
get stuck on a three-step form, and assuming otherwise is the exact
failure mode this invariant exists to prevent. The concrete behaviors
this implies for KRAKADYL's interface (one actionable next step at a
time, no assumed memory of where a session left off, stop-and-ask
instead of repeating a reworded instruction when someone's lost) come
directly from that skill, not invented fresh for this project.

## Cross-cutting dimension: operational and cognitive continuity

Every level below is also evaluated against this table — it is not a
separate feature, it is how invariants 4 and 5 show up concretely as
the system grows:

| Capability | Expected behavior |
|---|---|
| External working memory | Holds decisions, pending items, hypotheses and context without depending on anyone remembering them |
| Explicit responsibility | Every task has an owner, a status, a due time if relevant, and evidence of execution |
| Team coordination | Surfaces unassigned, duplicated, blocked, or wrongly-assumed-complete tasks |
| Interruption handling | A case can be picked back up without mentally reconstructing all of its context |
| Prioritization under pressure | Distinguishes time urgency, evidentiary importance, and dependency chains — not one score flattening all three |
| Omission prevention | Flags critical steps that are claimed but not yet verified, before the window to verify them closes |
| Shift handoff | Transfers what's known, what's pending, and what's uncertain, with provenance intact |
| Cognitive adaptation | Removes unnecessary steps, always offers one clear next action, allows going deeper without forcing it |
| Error recovery | Detects inconsistencies and allows correcting them without erasing history |
| Human oversight | Keeps professional authority with the investigator; the agent's mandate never silently expands |

This is not a "mode" that turns on for ADHD users. It's a property of
the system — useful the same way for an exhausted investigator at hour
14 of a shift, an emergency-response team, or anyone operating under
repeated interruption, which (see the Oct 12–21, 2026 wave of critical
vulnerabilities across PHP, Next.js, Node.js, and GitLab — four
independently confirmed incidents inside ten days) is most people
working in this field most of the time, not an edge case.

## Anticipating irreversible evidence loss

A requirement's `RecoveryWindow` (`krakadyl/core/models.py`) makes six
questions explicit instead of leaving them to be inferred, for every
piece of evidence that could still be lost:

| Concept | Question | Field |
|---|---|---|
| Recovery window | Until when can this still be obtained? | `until` |
| Investigative dependency | Which hypotheses need this source? | `depends_on_hypothesis_ids` |
| Uncertainty | What's unknown about its relevance? | `uncertainty_note` |
| Acquisition cost | What does preserving it require? | `acquisition_cost` |
| Irreversibility | What's lost if we wait? | `what_is_lost_if_missed` |
| Authority | Is it allowed right now? | *not a field here* — comes from `Decision`/`decide()`, the single place that fact lives |

This is not probabilistic planning, and isn't meant to be yet — `next_move()`
ranks open requirements by recovery-window urgency and how many
hypotheses depend on them, both explicit, auditable, rule-based
comparisons. It's a real, verifiable capability from Level 1
(`tests/test_continuity.py`), with the explicit room to grow into
planning under uncertainty later if a measurable model for that ever
earns its way in — not before.

## Untrusted content and supply chain

Investigated material, documents, and model outputs are data, never
instructions, permissions, or installable code — invariant 6. Concretely:
evidence content, the agent's own instructions, execution permissions,
and installable dependencies are four separate categories that never
merge. A malicious document in a case does not become an operational
instruction by being summarized by Muse Spark or classified by Laya.

This is not abstract caution: the project's own dependencies sit inside
the exact wave of incidents referenced above (Oct 12–21, 2026 — PHP,
Next.js, Node.js, GitLab, all independently confirmed). Concrete
consequence: KRAKADYL pins its own dependency versions deliberately
(not just "latest"), and the TypeScript frontend's Node/Next.js versions
get checked against that list before each level that touches them —
being the thing that investigates incidents and also being vulnerable to
one from an unpinned dependency is the kind of irony worth actively
avoiding.

## No individual blame, by construction — not just by policy

Borrowed directly from a sibling project in the same portfolio,
[Janus](https://github.com/annatchijova/janus) (its organizational
report generator bans a fixed list of blame/incompetence words in both
languages and never compares people to each other — findings describe
*processes*, never people): KRAKADYL's discrepancy and handoff reporting
follows the same rule. An unverified claim is reported as **a state of
the case** ("this requirement has no independent verification and its
source expires in N minutes"), never as a statement about the person who
made the claim. Investigations fail for many reasons that have nothing
to do with any one person's competence or diligence — the system's
language has to reflect that structurally, the same way Janus's
`ORG_FORBIDDEN_WORDS` does, not rely on whoever writes the narration
remembering to phrase it kindly.

## The standing acceptance scenario for the whole project

> An exhausted team, mid-interruption. A volatile source about to
> disappear. A task reported done that nobody verified. Limited,
> partial authority over what could still be done about it.

If KRAKADYL can keep continuity and propose a legitimate action here
without fabricating certainty, it is doing exactly what it was designed
to do. This is not a Level 1 checkbox to pass once — every later level
gets re-measured against this same scenario, not just its own new
cases.

Implemented today as `tests/test_continuity.py::test_adversarial_scenario_three_investigators_twenty_minutes`,
passing as of the Level 1 core skeleton commit. It is the test that
proves invariants 4, 5, and 6 are load-bearing, not aspirational.

## Properties every level must hold, restated as one line

Verifiable authority · provenance · explicit responsibility · cognitive
continuity · anticipation of irreversible loss · isolation of untrusted
content. Six invariants above, six words here — if a level is missing
one of these six, it is not a level of this product.

## The levels

### Level 1 — A complete investigable case

`Mission`, `Mandate`, `Observation`, `Claim`, `EvidenceRequirement`
(with its `RecoveryWindow`), `Hypothesis`, `ProposedAction`,
`PreparedAction`, `Decision`, `Receipt` — all with the full custody
lifecycle and a real `next_move()` (primary/alternatives/uncertain/
blocked, never a fabricated single answer) from day one, not added
after the "real" version works. One real domain action actually
executed (e.g., assembling a verifiable local evidence package), not
simulated. This alone is a complete, demonstrable product — later
levels extend it, they don't replace it.

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
