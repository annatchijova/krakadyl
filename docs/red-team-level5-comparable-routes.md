# Red team — Level 5 comparable routes (2026-10-30)

Scope: `core/counterfactual.py`, the Level 5 API section and `WhatIfPanel.tsx` on `feat/level5-comparable-routes`, up to commit `5a57d17`. The question throughout: can a hypothetical leak into the real case, be executed, or be mistaken for the real case? Each finding was reproduced by a failing test before it was fixed (`tests/test_red_team_level5.py`).

## Findings fixed

| # | Severity | Finding (reproduced) | Fix |
|---|---|---|---|
| F1 | Medium | Staleness only compared a digest of the inputs. Time alone can change the real verdict (a mandate expires), and the digest is blind to it, so an old counterfactual kept showing its "real" side as the current state. The API-level test passed only by coincidence: the seeded capture mandate expires at the same moment and shifts the acquisition routes. The isolated core test shows the gap: digest equal, verdict changed. | `is_stale` also recomputes the real outcome at the current time and compares it with the stored one. |
| F2 | Low | The shared activity log said "forbidden would become allowed", which reads like a real verdict change when skimmed. | Entries start with `[HYPOTHETICAL]`, name the assumptions, and state that the case is unchanged. |

## Checked and holding

- **No writes to case state.** Inputs are copied and rebuilt through the constructors; a test compares the inputs before and after, and the stored counterfactual adds no row to `objects`.
- **No execution path.** The `PreparedAction` built on a copy never leaves `_outcome`, and `execute` with a counterfactual id returns 404.
- **No reach into the other levels.** Muse, Laya, team evidence references, acquisition and handoff read only `objects` or their own tables, never `counterfactuals`.
- **Tampering cannot be assumed away:** every assumption kind combined still returns FORBIDDEN on a tampered file.
- **Free-form assumptions** are rejected by the schema (422). Unknown requirement ids, contradictory assumptions and more than 8 are rejected (409).
- **Updates** to the `counterfactuals` table are aborted by its trigger.

## Residual risks — accepted

- **Unbounded count.** Each counterfactual costs up to 18 pipeline runs and a row. Writing one requires a token; there is no per-case cap yet.
- **Open reads.** Counterfactuals are readable without a token, like the other metadata reads. Keep the API on localhost.
- **Scope.** Only the package-export question is modelled; nothing hypothetical exists yet for capture or acquisition.
