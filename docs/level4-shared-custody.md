# Level 4 — shared custody, team investigations

Status (2026-10-30): implemented on `feat/level4-shared-custody`, which is stacked on `feat/level3-case-acquisition` because it needs that branch's proven operator identity. Offline-tested, red-teamed, and walked end to end in a browser. Not merged: Level 3 is not closed yet (its live SAM run is pending), and this branch carries Level 3's commits.

## What the roadmap asked for, and where it lives

| `docs/levels.md` Level 4 | Implementation |
|---|---|
| More than one investigator on the same case | Every statement and handoff is bound to the operator token the request proves (`KRAKADYL_OPERATOR_TOKENS`), never to a name in the request body. |
| A teammate's claim is recorded as *claimed*, not *verified*, until independently confirmed | `core/team.py`: `REPORTED_DONE` records move the requirement to `REPORTED_DONE` only; `VERIFIED` must come from someone other than the claimant (and other than the first claimant on record). |
| ...or until B explicitly marks it with evidence attached | Interpreted conservatively (D2): attached evidence is integrity-checked and shown, but never verifies its own claim. |
| Conflicting claims surface loudly, not silently | `find_conflicts` derives four conflict kinds from the records. An open conflict makes the governed evidence `CONFLICTING` at prepare **and** at execute, blocks verification, and appears first in the handoff view and as a badge on the evidence row. |
| Shift handoff: "what do I need to know to pick this up", from recorded state | `core/handoff.py`: a view built only from stored records, a handoff bound to the digest of exactly that view, and an acceptance that transfers ownership without transferring authority. |

## Decisions

**D1. Statements are append-only records; conflicts are derived, never stored.** `team_records` and `shift_events` reject `UPDATE` with a database trigger. A correction is a new record that refers to the old one. Conflicts are recomputed from the records on every read, so there is no second copy that can drift from them. *Exception:* the token-gated dev reset can still delete them, as it deletes everything else in a demo case.

**D2. Attached evidence never verifies its own claim.** The roadmap's "or until B explicitly marks it with evidence attached" could be read as "evidence makes it verified". That would contradict invariant 4 (a self-report is not a verification). Here, cited artifacts are re-hashed when the claim is recorded, and again every time conflicts are computed. Evidence that stops matching becomes an `evidence_mismatch` conflict; it never upgrades the claim.

**D3. Four conflict kinds, all computed from records:**
- `competing_completion` — two people claim done, citing different evidence.
- `disputed` — a statement disputes earlier records, or the requirement's current recorded state (so verifications from the seed or from a Level 3 evaluation can be contested too).
- `evidence_mismatch` — cited evidence no longer matches what was recorded.
- `status_contradiction` — one person's latest statement says blocked, another's says done.

**D4. A conflict is resolved by someone who is not part of it.** The parties are everyone named in the conflict's records. For disputes, they also include whoever the disputed state names (`reported_done_by`, `verified_by`). There are two decisions:
- `keep_current_state` — not allowed for evidence mismatch.
- `reopen_requirement` — sets the requirement to `UNKNOWN` and unresolved, and starts a new epoch (D5).

**D5. A reopen starts a new epoch.** Records before the latest reopen stay visible, but they no longer form conflicts and can no longer be verified or disputed. Otherwise the claim that was just overturned could be verified straight back into place (red team F1).

**D6. A handoff binds to what the outgoing person saw.** It carries the view's `state_digest` and is refused if the case moved since. On acceptance:
- A transferred requirement becomes the incoming person's only if it did not change after the handoff; otherwise it is listed as not transferred, with the reason.
- `REPORTED_DONE`, `BLOCKED` and `UNKNOWN` keep their status (red team F2).
- No mandate changes. Owning the work does not grant capture or export authority: in the demo, investigator-E owns the clock requirement after the handoff, but only investigator-A can capture for it.

**D7. Generated language describes the case, never a person.** Conflict and handoff text is checked in tests against `BLAME_TERMS` (English and Spanish), following the "No individual blame, by construction" rule in `levels.md`. Party names are kept as data fields, not woven into the narration of a conflict.

## Falsifiers (each has a test)

- A self-verification, or a person labelling their check `tool:` → refused.
- Verifying while a conflict is open → refused. Negative control: removing that check makes `test_competing_completions_…` fail.
- A party resolving its own conflict → refused. Negative control: removing that check makes the same test fail.
- A conflict raised after prepare → execute refuses and writes no package.
- A stale requirement revision, or broken cited evidence → refused, nothing written.
- A requirement that moved after the handoff → not transferred.
- `UPDATE` on `team_records` → the database aborts it.

## Verification snapshot — 2026-10-30

- `pytest`: 313 passed (adds `test_team.py`, `test_handoff.py`, `test_api_team.py`, `test_red_team_level4.py`).
- Frontend: `tsc -b`, `oxlint` (the one pre-existing `App.tsx` warning), `vite build` clean.
- Browser (Chromium), seeded case with five operator tokens:
  - B disputes req-a1, and obs-a1 shows "team conflict".
  - Prepare returns `forbidden`, with "open team conflict on the requirement governing: obs-a1".
  - D resolves it with "keep the current state".
  - A hands the shift to E, transferring the clock requirement; E accepts and becomes owner, `acknowledged`.
  - No page errors.
- Found during testing, not in review: the API's evidence checker read the store from inside the core's transaction and deadlocked on its non-reentrant lock. Fixed by snapshotting the records first; the constraint is documented on `RefChecker`.

## Open

- Anyone with a token can raise a dispute, and so block a package until a non-party resolves it. This is intended ("surface loudly"); it is also a way to stall a case. Revisit if disputes become noisy.
- `hyp-002`'s review reason reads "is no longer resolved" for a requirement that was never resolved. That wording is pre-existing (`invalidation.py`), and harmless but imprecise.
- The handoff view ranks conflicts first and leaves everything after them unranked. Ordering conflicts against expiring claims is a judgment the system does not make for you.
