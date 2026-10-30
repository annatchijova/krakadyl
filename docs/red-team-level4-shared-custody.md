# Red team — Level 4 shared custody (2026-10-30)

Scope: `core/team.py`, `core/handoff.py`, the Level 4 API section and `TeamPanel.tsx` on `feat/level4-shared-custody` (up to commit `7c64649`). Method: as for Level 3. Every path that can change a requirement, an owner, or a policy verdict was re-read adversarially. Each candidate was reproduced as a failing test before it was fixed (`tests/test_red_team_level4.py`: 5 failing → 0).

## Findings fixed

| # | Severity | Finding (reproduced) | Fix |
|---|---|---|---|
| F1 | High | After a dispute reopened a requirement, a non-party could verify the *same old claim* the reopen had just overturned, and the requirement became resolved again with nothing new. Records from before the reopen also kept forming fresh conflicts with new statements. | `current_epoch`: records before the latest reopen are history. They no longer form conflicts and cannot be verified or disputed; a new claim is required. |
| F2 | Medium | Accepting a handoff turned `BLOCKED` and `UNKNOWN` requirements into `ACKNOWLEDGED`, erasing the uncertainty being handed over. | Acceptance keeps `REPORTED_DONE`, `BLOCKED` and `UNKNOWN` as they are; only ownership moves. |
| F3 | Low | Resolving a conflict with `reopen_requirement` cleared `unresolvable`, silently undoing an owner's explicit "this evidence is not obtainable". | Reopen leaves `unresolvable` and its reason untouched. |

## Found while building (before review), also fixed

- **Deadlock.** The API's evidence checker read the store from inside the core's transaction, which holds a non-reentrant lock. Fixed by snapshotting the records first; the constraint is documented on `RefChecker`.
- **Undisputable verifications.** A dispute could only target team records, so verifications from the seed or from a Level 3 evaluation could not be contested. Fixed: a dispute without references targets the current recorded state, and whoever that state names counts as a party.
- **Muse path missing a policy input.** The Muse proposal path did not pass Level 3 acquisition routes to the policy engine. It now passes those and the Level 4 conflicts, like every other path.

## Checked and holding

- Identity comes from the token. An `actor` field in the request body is ignored (FastAPI drops unknown fields), and the token's owner is recorded.
- `tool:` verification methods cannot be claimed by a person, and stored methods always start with `peer-verification:`.
- Verification, dispute and resolution references resolve only within the same requirement's records.
- Two concurrent statements on one requirement: the second fails its revision check (one write lock, revision compared inside the transaction).
- Handoff races: two handoffs of the same requirement to different people. The first acceptance changes the revision, so the second reports it as not transferred.
- Handoff never touches a mandate (asserted in `test_api_team.py`).

## Residual risks — accepted

- **Dispute as a stall.** Any authenticated operator can block a package with a dispute until a non-party resolves it. This is intended; it is also abusable inside a team.
- **Unauthenticated metadata reads.** `GET /team` and `GET /handoff` list operator names, statements and conflicts without a token, like the other read endpoints. Localhost only.
- **Snapshot window.** The evidence checker resolves *records* from a snapshot taken just before the transaction; *bytes* are re-hashed inside it. A record replaced in that window would be judged against the snapshot. Records are not replaced by any non-dev path today.
- **Superseded records in the UI.** The statement form still lists them; the server refuses them with an explicit reason.
