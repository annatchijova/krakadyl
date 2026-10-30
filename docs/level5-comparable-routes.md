# Level 5 — comparable routes

Status (2026-10-30): implemented on `feat/level5-comparable-routes`, which is stacked on `feat/level4-shared-custody` (itself on the Level 3 branch). Offline-tested, red-teamed, and walked in a browser. Not merged, and neither is either branch below it.

The roadmap asks: *"What would this case allow under a different evidence or authority limit?" as a measured counterfactual, kept visibly separate from the real case state — never silently merged back into it.*

## Design

**Closed, typed assumptions** (`core/counterfactual.py`, `DeltaKind`). Up to 8 per counterfactual. Each kind requires exactly its own field (`value`, `requirement_id` or `until`), and free-form assumptions are rejected by the schema.

| Kind | Limit it changes |
|---|---|
| `grant_resource`, `grant_operation`, `grant_destination` | mandate scope |
| `extend_mandate_until` | mandate validity |
| `mandate_not_revoked` | revocation |
| `requirement_verified` | an independent verification that has not happened |
| `requirement_unresolvable` | an abstention that has not happened |
| `conflict_resolved` | a Level 4 conflict resolution that has not happened |
| `source_available` | a Level 3 acquisition route that does not exist |

**Same pipeline, on copies.** The assumptions are applied to copies rebuilt through the models' constructors, so every validator still runs. The unmodified `prepare_evidence_package` (`check_mandate` → `check_evidence` → `decide`) and `next_move` then run on those copies. No decision logic is duplicated.

**Measured.** Every counterfactual holds three things:
- The real outcome and the hypothetical outcome, computed at the same instant.
- For each assumption, two measurements:
  - **necessary**: dropping only that assumption changes the hypothetical verdict;
  - **sufficient alone**: that assumption by itself changes the real verdict.

  That is 2 + 2n pipeline runs for n assumptions; n ≤ 8.

**Kept apart:**
- Results are stored in their own append-only `counterfactuals` table, never in `objects`, which is what every real decision reads.
- The `PreparedAction` the pipeline creates on a copy is discarded inside `_outcome`. Only the resource ids are kept, so a counterfactual id is never accepted by `execute` (tested: 404).
- Each result carries a digest of the real inputs it was computed from. `is_stale` flags a counterfactual once those inputs change, or once the real outcome recomputed now differs from the stored one, which catches a mandate expiring with nothing else changed.
- The UI shows the hypothetical with a dashed border, labelled "HYPOTHETICAL — not the case", next to the real outcome. Activity entries start with `[HYPOTHETICAL]`.

## Decisions

- **D1. "Assume these bytes are intact" is not modelable.** Integrity is read from disk and no assumption overrides it (tested: every assumption combined still yields FORBIDDEN on a tampered file). A hypothetical that waves away tampering invites exactly the reasoning KRAKADYL exists to stop.
- **D2. Only the package-export question for now,** against the case's export mandate. Counterfactuals about the capture mandate or about acquisitions are not modelled yet.
- **D3. An assumed verification names no one.** It reads `verified_by = counterfactual-assumption` and `verification_method = counterfactual:assumed`, never the `tool:` prefix reserved for automated checks. It exists only in memory.
- **D4. Attribution needs a proven operator token**, like every other write. Reading counterfactuals is as open as the other read endpoints.

## Verification snapshot — 2026-10-30

- `pytest`: 337 passed (adds `test_counterfactual.py`, `test_api_counterfactual.py`, `test_red_team_level5.py`).
- Negative control: forcing `necessary = True` makes `test_unverified_gap_measures_which_assumption_matters` fail.
- Browser (Chromium), seeded case:
  - B disputes req-a1, so the real verdict is `forbidden`.
  - Assumptions "conflict on req-a1 resolved" + "destination court-registry": the hypothetical verdict is `allowed`.
  - The resolution is necessary and sufficient on its own; the destination is not needed.
  - A real prepare afterwards was still `forbidden`. No page errors.

## Open

- Measurements are per assumption (leave-one-out and single). Minimal sufficient *sets* are not searched.
- Counterfactuals are unbounded in number per case (each needs a token). Cap them if it becomes noisy.
- The hypothetical `next_move` is computed but not shown in the UI.
