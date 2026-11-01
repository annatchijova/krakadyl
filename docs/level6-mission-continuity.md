# Level 6 — Mission continuity across a real-time gap

The second Level 6 strand, alongside sub-mandates
([level6-sub-mandates.md](level6-sub-mandates.md)): work that spans days or weeks
of actual investigation time, picked up after a gap without having lost the
thread.

## What this adds over what already existed

`next_move` already answers "what now" from the current requirement set, and the
shift-handoff already answers "what do I need to know to take this over." Neither
knows how much real time has passed. `next_move` ranks recovery windows by their
absolute `until`, so a window that *closed while the investigator was away* would
still be ranked as if it were open — the one thing a long gap makes dangerous.

`krakadyl/core/continuity.py::resume_after_gap` is the long-gap companion. Given
the moment of the last recorded activity (`since`) and now, it reports what
crossed a threshold in the half-open interval `(since, now]` purely because time
passed:

- **mandates that expired while away**, and which of them were **delegations**
  (sub-mandates) — so a returning senior learns the slice they gave a junior has
  lapsed;
- **recovery windows that closed while away** (KNOWN/ESTIMATED with an `until` in
  the gap, on still-open requirements), separated from windows that had already
  closed before the gap (old news);
- **recovery windows still open**, ranked soonest-deadline first, so what is
  still savable and most urgent is immediate;
- **conditional/unknown/windowless** open requirements on a separate watch list,
  because they cannot be honestly time-ranked (the same discipline `next_move`
  already uses).

It is a pure read: no authority changes, nothing is mutated, and no float enters
(the gap is integer seconds; the human string is cosmetic).

## Wired to the API

`GET /api/cases/{case_id}/resume` returns the briefing, membership-gated like the
other reads. `since` is the timestamp of the last recorded event on the case (or
the mission's creation if there are none) — never a value the caller supplies, so
the gap cannot be spoofed to hide or invent a change. `now` is the server clock.
Because resume is a read and logs no event, calling it repeatedly reports the same
gap until a real action moves the case forward.

## Evidence

`tests/test_continuity_gap.py` (6 cases): the gap is humanized in whole units; a
mandate that expired during the gap is reported while one that expired before it
is not; an expired sub-mandate is also flagged as a lapsed delegation; windows
closed during the gap are separated from still-open ones (ranked soonest first)
and from windows closed before the gap; conditional/unknown/windowless open
requirements go to watch; resolved and unresolvable requirements are excluded.
`tests/test_api.py::test_resume_briefing_is_membership_gated_and_well_formed`
confirms the endpoint is wired, gated, and shaped.
`demo/run_case_004_gap.py` walks a case resumed after a simulated multi-day gap.

## Deliberately not built yet (documented, not approximated)

- **No forward-looking urgency horizon invented here.** resume reports what
  closed and lists what is still open by deadline; it does not fabricate a
  "newly urgent" threshold for still-open windows, because any such horizon would
  be an arbitrary constant. If a measured model for that ever earns its way in,
  it layers on top; it is not faked now.
- **Re-orientation is read-only.** resume does not itself invalidate or re-open
  anything that expired — it surfaces the change for a human to act on through
  the normal authority and verification paths, the same separation the rest of
  the system keeps.
- **No workspace UI yet** for the briefing (shared with the sub-mandate strand).
