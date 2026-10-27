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
4. **Task responsibility and evidence custody are explicit, never
   assumed, and never the same thing.** Correction from the Oct 27
   review: an earlier version of `models.py` had one `Custody` object
   doing both jobs — tracking whether a *task* got done, and standing in
   for whether an *artifact* was properly chain-of-custodied. Completing
   a task does not, by itself, demonstrate custody of what it produced,
   so these are now two separate contracts:
   - **`TaskResponsibility`** (on `EvidenceRequirement`, `Claim`): owner,
     acceptance, and a full status (`UNASSIGNED -> ASSIGNED ->
     ACKNOWLEDGED -> IN_PROGRESS -> REPORTED_DONE -> VERIFIED_DONE`,
     plus `BLOCKED/EXPIRED/CANCELLED/UNKNOWN`). Reaching `VERIFIED_DONE`
     requires `verified_by` and `verification_method` — a status label
     alone is rejected by a validator, not just discouraged by
     convention — and requires genuine independence: `verified_by` must
     differ from `reported_done_by`, unless `verification_method` names
     an automated check (prefixed `tool:`), since "independent" doesn't
     have to mean "a second human," it has to mean "not the same act as
     the self-report."
   - **`EvidenceCustody`** (on `Observation`): acquisition, who has held
     the artifact and when it changed hands, what transformations were
     performed on it, and its integrity digest — the actual
     chain-of-custody concept, tracked on its own.

   What's enforced today, stated at the precision it deserves: the
   validator above runs at construction time for `TaskResponsibility`,
   and `krakadyl/core/continuity.py::evidence_state_from_requirement` is
   the one place `REPORTED_DONE` gets turned into an evidence state
   (always `MISSING`, never `SUFFICIENT`). That is narrower than
   "structurally impossible" (a corrected overclaim from an earlier
   version of this doc): a full structural guarantee would also need a
   persistence/serialization audit and coverage of every code path that
   can write either object, neither of which exists yet. Three things
   this is designed to refuse, not yet proven against every mutation
   path:
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
repeated interruption, which is most people working in this field most
of the time, not an edge case. See the sourced incident list at the end
of "Untrusted content and supply chain" below for why that's not a
rhetorical claim.

## Anticipating irreversible evidence loss

A requirement's `RecoveryWindow` (`krakadyl/core/models.py`) makes six
questions explicit instead of leaving them to be inferred, for every
piece of evidence that could still be lost:

| Concept | Question | Field |
|---|---|---|
| Recovery window | Until when (if known/estimated) can this still be obtained? | `until`, gated by `kind` |
| Investigative dependency | Which hypotheses need this source? | `depends_on_hypothesis_ids` |
| Uncertainty | What's unknown about its relevance? | `uncertainty_note` |
| Acquisition cost | What does preserving it require? | `acquisition_cost` |
| Irreversibility | What's lost if we wait? | `what_is_lost_if_missed` |
| Authority | Is it allowed right now? | *not a field here* — comes from `Decision`/`decide()`, the single place that fact lives |

**`kind` exists because not every window is a known deadline.**
Correction from the Oct 27 review: a single optional `until` datetime
can't distinguish "no known expiry" from "closes on an event, timing
unknown" (the device gets powered off, a log rotates, a session is
lost) without silently treating both as equally non-urgent.
`RecoveryWindowKind` has four values — `KNOWN`, `ESTIMATED` (requires
`estimate_basis`: the source and confidence behind the number),
`CONDITIONAL` (requires `condition`: the event that closes it), and
`UNKNOWN` — and `next_move()` keeps anything `CONDITIONAL`/`UNKNOWN`
visible in a separate `conditional_watch` list instead of letting it
sink to the bottom of a time-ranked list it can't honestly be ranked
against.

This is not probabilistic planning, and isn't meant to be yet —
`next_move()` ranks open requirements on recovery-window urgency alone.
**Correction from the Oct 27 review**: hypothesis-dependent count used
to be a silent secondary ranking key; it no longer is. A source tied to
five trivial hypotheses is not more important than one decisive for a
single hypothesis, and the old behavior could have let an agent that
generates more hypotheses silently inflate a source's priority. The
count is still computed (deduplicated — a repeated hypothesis id no
longer inflates it) and exposed as `dependents_count`, but purely as
information for a human to weigh, never as something that picks the
primary recommendation. **Known, tracked gap, not claimed solved**: it
still counts whatever hypothesis ids are listed, not only ones marked
"accepted" — doing that needs `Hypothesis` objects passed into
`next_move()`, which it doesn't take yet. It's a real, verifiable
capability from Level 1 (`tests/test_continuity.py`), with explicit room
to grow into planning under uncertainty later if a measurable model for
that ever earns its way in — not before.

## Untrusted content and supply chain

Investigated material, documents, and model outputs are data, never
instructions, permissions, or installable code — invariant 6. Concretely:
evidence content, the agent's own instructions, execution permissions,
and installable dependencies are four separate categories that never
merge. A malicious document in a case does not become an operational
instruction by being summarized by Muse Spark or classified by Laya.

This is not abstract caution. In the ten days before this hackathon's
building period began, four independently confirmed critical
vulnerabilities hit widely used dev infrastructure — sourced, not
asserted:

- **PHP** — CVE-2026-109618 (OOM memory corruption) and CVE-2026-109619
  (use-after-free), unauthenticated RCE, CVSS 9.2. Affected 8.2 before
  8.2.35, 8.3 before 8.3.36, 8.4 before 8.4.27, 8.5 before 8.5.12;
  exploited in the wild from Oct 17, patched Oct 21, 2026.
  ([Unit 42 threat brief](https://unit42.paloaltonetworks.com/cve-2026-109618-cve-2026-109619/))
- **Next.js** — two critical unauthenticated RCEs, CVSS 9.5: a `use
  cache` flaw (App Router, Cache Components) and a `librsvg`/`sharp` SVG
  memory-safety bug reached via the Image Optimization API. Affected
  10.0.0–15.5.27 and 16.0.0–16.4.0; patched in 16.4.1 / 15.5.28, Oct 14,
  2026. ([The Hacker News](https://thehackernews.com/2026/10/nextjs-ships-out-of-band-patch-for-two.html))
- **Node.js** — CVE-2026-111497, an out-of-bounds write in the bundled
  Brotli decoder, RCE via malformed compressed input. Affected all
  supported branches (22.x/24.x/26.x); patched in 22.23.4, 24.22.1,
  26.12.1 as part of a 10-CVE security release, Oct 21, 2026.
  ([The Hacker News](https://thehackernews.com/2026/10/nodejs-brotli-decoder-bug-could-allow.html))
- **GitLab** — CVE-2026-110264, integer overflow in regex compilation,
  unauthenticated RCE, CVSS 10.0, affecting code dating back to GitLab
  7.0 (2014). Patched Oct 21, 2026 (19.5.1, 19.4.3, 19.3.6, 19.2.9,
  19.1.9, 19.0.10, 18.11.13) — note servers patched Oct 12 for an
  earlier, related regex flaw (CVE-2026-97229) still needed this second
  update. ([The Hacker News](https://thehackernews.com/2026/10/critical-gitlab-flaw-cvss-100-could.html))

Concrete consequence for this project: KRAKADYL pins its own dependency
versions deliberately (not just "latest"), and the TypeScript frontend's
Node/Next.js versions get checked against the patched versions above
before each level that touches them — being the thing that investigates
incidents and also being vulnerable to one from an unpinned dependency
is the kind of irony worth actively avoiding.

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
passing as of the Level 1 core skeleton commit. Correction from the
Oct 27 review: this test exercises coordination and continuity — it is
real evidence for invariants 4 and 5, not for invariant 6. A
coordination/custody scenario does not test content isolation; nothing
in it attempts a prompt injection, a contaminated proposal, an authority
escalation, or an unauthorized execution, so it cannot stand as evidence
that invariant 6 holds.

**Invariant 6's actual coverage today is narrow and should be stated as
such**: `tests/test_policy.py::test_a_classification_signal_alone_never_grants_authority`
confirms that `decide()`'s signature has no parameter shaped to accept
raw content — a real, if small, structural fact. It does not test
prompt-injection resistance, proposal contamination, authority
escalation, or unauthorized execution, because there is no agent/LLM-
calling code yet for any of those to attack. Writing that suite is
explicit, tracked work for whichever level first wires in Muse Spark and
Laya for real — not a claim to make before that code exists.

## Properties every level must hold, restated as one line

Verifiable authority · provenance · explicit responsibility · cognitive
continuity · anticipation of irreversible loss · isolation of untrusted
content. Six invariants above, six words here — if a level is missing
one of these six, it is not a level of this product.

## The levels

### Level 1 — A complete investigable case

`Mission`, `Mandate`, `Observation` (with `EvidenceCustody`),
`Claim`/`EvidenceRequirement` (with `TaskResponsibility`), `Hypothesis`,
`ProposedAction`, `PreparedAction`, `Decision`, `Receipt` — all with the
full task-responsibility lifecycle, a separate evidence-custody record,
and a real `next_move()` (primary/alternatives/uncertain/blocked/
conditional-watch, never a fabricated single answer) from day one, not
added after the "real" version works. One real domain action actually
executed (e.g., assembling a verifiable local evidence package), not
simulated. This alone is a complete, demonstrable product — later
levels extend it, they don't replace it.

**Status as of 2026-10-27, stated precisely, not rounded up**: the
contracts, the policy engine, the receipt chain + independent verifier,
the continuity/task-responsibility mechanism, and now
`krakadyl/core/executor.py` are implemented and tested (30/30 passing).
**This level's own stated acceptance criterion — one real domain action
executed end-to-end, not simulated — is met**: `demo/run_case_001.py`
runs a synthetic two-device case through the real policy engine and
executor, with real files on disk, real SHA-256 integrity checks, and a
real chained receipt. Device B is excluded from the package because the
mandate says so, not because the demo was scripted to leave it out; a
tampered file is caught because its digest is recomputed, not assumed.

**Still not done**: no Meta Model API call has been made from this
codebase, and there is no agent loop proposing actions — the executor
above is wired to run on a `ProposedAction` built by hand in the demo,
not one a model generated. That's the one piece left before Level 1 is
fully complete, not a re-opening of the acceptance criterion above.

### Level 2 — The case stays alive: contradictions, staleness, recovery

A dependency-invalidation engine: when an observation, a permission, or
a destination changes, the system identifies exactly which prepared
actions and hypotheses depended on the stale fact, invalidates them, and
proposes a still-legitimate route forward — or closes honestly with
"this can no longer be resolved." This engine is general — Level 4
reuses it rather than inventing a second one.

**Status as of 2026-10-27**: the core piece of this — staleness
detection for a `PreparedAction` — is implemented and tested
(`krakadyl/core/invalidation.py`, `krakadyl/core/executor.py`'s
`prepare_evidence_package`/`execute_prepared_action` split, 42/42 tests
passing). `execute_prepared_action` revalidates against the *current*
mandate and resource digests immediately before acting — a mandate
revoked or a file changed in the gap between prepare and execute is
caught, not trusted from the earlier ALLOWED verdict.

**Found by self-red-teaming this build, fixed in the same pass, not
carried forward**: `TaskResponsibility`'s independent-verification
validator and `RecoveryWindow`'s kind-consistency validator only ran at
construction — a plain attribute assignment after the fact bypassed
both entirely (`validate_assignment=True` now closes this). `Mandate`
could be mutated in place (`mandate.revoked = True`) without bumping
`revision`, which would have silently defeated the invalidation engine
this level depends on (`frozen=True` now forces a new object, and
therefore a real revision bump, for any change). `PreparedAction` itself
was a mutable "snapshot" (also now `frozen=True`). All four have
regression tests in `tests/test_model_invariants.py` proving the bypass
stays closed, not just that it was closed once.

**Follow-up review, same day (2026-10-27), both of the limitations above
closed**: `execute_prepared_action` now takes a required `consumed_nonces`
set and refuses to execute a `PreparedAction` whose `nonce` is already in
it — the caller owns the set's lifetime (in-memory today; backed by
storage once persistence exists, not yet), so forgetting to pass one is a
loud signature error, not a silent gap. The TOCTOU window is not
eliminated — a file can still change in the instant between the digest
recheck and the copy — but it is now *caught rather than ignored*: the
copy's own digest is verified against the expected one immediately after
copying, and the whole package is assembled in a temp directory and only
`rename()`d into `out_dir` if every file matches; a mismatch aborts with
nothing published, never a half-written package mistaken for a complete
one. `execute_prepared_action` also now fully re-runs `check_mandate`
(catching revocation, scope, and a validity window that moved — not just
a revision-string diff) and `check_evidence` (catching a requirement that
regressed from `VERIFIED_DONE` after prepare) against current state, and
confirms `prepared`/`decision`/`proposed_action` all name the same
action before doing anything. 51/51 tests passing.

**What's still deliberately deferred, not claimed solved**: nonce
consumption lives in a caller-supplied in-memory set — nothing persists
it across a process restart, so replay protection does not survive a
crash between execute calls. That's real work for whichever level adds
persistence, not silently assumed away.

**Cycle 2 (same session, 2026-10-27)**: hypothesis invalidation is now
built — `invalidation.py::find_hypotheses_needing_review` flags a
`Hypothesis` whose `discriminating_requirement_id` points at a
requirement that stopped being resolved, became unresolvable, or no
longer exists. Deliberately **not** exempting `accepted` hypotheses
(only `rejected` ones are skipped): a hypothesis accepted on grounds
that later turn out unresolvable is exactly the case this exists to
catch, not a case to ignore because it was already decided.

**Found by self-red-teaming this build, fixed in the same pass**:
`EvidenceRequirement` used to accept `resolved=True` and
`unresolvable=True` simultaneously — a logical contradiction that would
have made `find_hypotheses_needing_review`'s unresolvable-first check
report the requirement as permanently dead while it also claimed to be
resolved. Fixed with a validator making the two mutually exclusive.
`Hypothesis.status` was a plain, unvalidated string — a typo or case
mismatch (`"Rejected"` vs `"rejected"`) would have silently failed to
match the skip check, flagging an already-dismissed hypothesis as
needing review. Fixed by turning it into a real `HypothesisStatus` enum
with `validate_assignment=True`. Both have regression tests in
`tests/test_model_invariants.py`.

50/50 tests passing. Demo re-run end-to-end after both cycles, confirmed
still working.

**Still not built**: the "propose a still-legitimate route forward"
half — today, staleness stops at "don't execute / needs review,
re-propose" for both PreparedActions and Hypotheses; neither yet
suggests what the re-proposal should look like. That's the natural
Cycle 3 target, not started in this session.

**Cross-module red team (same session, 2026-10-27) — found, decided, and
fixed**: `krakadyl/core/executor.py` and the custody/continuity
mechanism built across Level 1 and this level's two cycles were two
parallel systems that had never actually been wired together.
`prepare_evidence_package()` used to compute `evidence_state` purely by
recomputing an `Observation`'s file digest — it never consulted
`EvidenceRequirement`, its `TaskResponsibility` lifecycle, or
`continuity.py::evidence_state_from_requirement` at all. Concretely: a
file matching its stored digest would have been packaged even if the
`EvidenceRequirement` tracking its acquisition was still sitting in
`REPORTED_DONE`, never independently verified — exactly the gap the
three-investigators scenario in the README exists to close.

**Anna's decision on the approach**: the executor stays strictly
read-only with respect to verification — it refuses to execute unless
an observation's `EvidenceRequirement` is already independently
`VERIFIED_DONE` by something else, never marks one verified itself.
Strongest separation: the thing that proposes/executes an action is
never the same act as the thing that verifies the evidence behind it.

**Implemented**: `EvidenceRequirement` gained `observation_id`, linking
it to the `Observation` whose custody it governs.
`prepare_evidence_package()` now requires both independently, for every
included observation — neither substitutes for the other: digest
integrity proves the file wasn't altered since acquisition, not that
the acquisition was verified; `VERIFIED_DONE` proves the acquisition was
verified, not that the file wasn't swapped afterward. `demo/run_case_001.py`
gained a fourth, literal run of the three-investigators scenario: an
intact file whose requirement is only `REPORTED_DONE` — `FORBIDDEN`,
confirmed by actually running it. 51/51 tests passing.

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
