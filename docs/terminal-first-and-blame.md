# Where invariants 4 and 5 actually come from

Not invented for this project — carried over from two things Anna had
already built and documented before KRAKADYL existed.

## Technical competence and executive-function availability are independent variables

From Anna's own documented case (the design rationale behind her
[SIN MIEDO](https://github.com/annatchijova/sin-miedo) project and the
[terminal-first](https://github.com/annatchijova/SKILLS/tree/main/terminal-first)
skill, written for her own day-to-day use before either project existed):
a person can be fluent with a terminal, SSH, APIs, and still get stuck on
a three-step form on a given day — not from lack of knowledge, but
because holding a multi-step sequence in mind while a screen changes
under you draws on an executive-function resource that varies day to
day, independent of technical skill.

The failure mode this guards against, stated as a rule: never infer that
someone needs less step-by-step support because they're technically
fluent, and never infer that someone lacks technical knowledge because
they asked for a step to be spelled out. Both inferences are wrong, and
conflating them is the most common way to fail someone with this
profile.

What this implies concretely for KRAKADYL's interface, taken directly
from `terminal-first`'s own rules:

- One actionable next step surfaced at a time — the full plan lives in
  the system, not in the person's head, and is available on request but
  never forced.
- No assumed memory of where a session, a shift, or a case left off —
  state is reconstructed from what's recorded, not from what anyone is
  expected to remember.
- When someone is lost or a case doesn't match what they expected: stop
  and ask what the current real state is, then resume from there — never
  repeat the same instruction reworded, because what changed was the
  state, not the clarity of the sentence.

This generalizes past any one diagnosis: investigators under shift
fatigue, incident responders mid-crisis, or anyone who has been
interrupted mid-task experience the same gap between what they know and
what they can execute right now. KRAKADYL's continuity invariants treat
that gap as the normal case, not the exception.

## No individual blame, by construction

From [Janus](https://github.com/annatchijova/janus), a sibling project
in the same portfolio: its organizational report generator enforces a
fixed, bilingual list of banned blame/incompetence words, and its
house style states explicitly that findings describe *processes and
context*, never people — including a dedicated behavioral profile,
`CORRECTO_SILENCIOSO`, for "did the right thing, but didn't report it,"
precisely because the point of the report is the systemic gap, not a
verdict on anyone's judgment.

KRAKADYL applies the same rule to discrepancy and handoff reporting. An
unverified claim is reported as a state of the case — "this requirement
has no independent verification and its source expires in N minutes" —
never as a statement about the person who made the claim. Investigations
fail for many reasons unrelated to any one person's competence or
diligence, and the system's language has to reflect that by rule, not by
whoever happens to be writing the report that day remembering to phrase
it kindly.
