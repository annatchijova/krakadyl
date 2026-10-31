# Red Team — Receipt-Chain Integrity Under Live Concurrency — 2026-10-31

**Method:** Abductive Engineering (A–D–I) + `red-team-auditing` +
`concurrency-reasoning` + `distributed-write-atomicity`.
**Base:** `main` @ `22192ac`.
**Reproducible evidence:** `tools/redteam_chain_probes.py` (live uvicorn server,
raw-byte SQLite oracle) and two deterministic regressions in `tests/test_store.py`:
`test_receipt_head_follows_append_order_not_handler_timestamp` (RT-CHAIN-01) and
`test_replacing_a_denied_receipt_links_to_the_real_head_not_itself` (RT-CHAIN-02).

## Scope

KL-005 recorded the concurrent receipt-append problem as closed on 2026-10-30,
verified by a forced two-thread interleaving at the store layer and an
in-process handler test. This round asks whether the invariant survives the one
path those tests do not exercise: many concurrent executions racing through a
real uvicorn server and the real SQLite file. OS compromise and direct database
editing remain out of scope.

## Invariant under test

```text
The persisted execution receipts for a case form exactly one hash-linked chain:
one root (prev_hash = null), every other receipt's prev_hash equal to the hash
of the single receipt appended before it, no two receipts sharing a predecessor
(no fork), no prev_hash pointing at a hash that is not present (no dangling).
```

## Epistemic legend

CODE FACT · PLAUSIBLE HYPOTHESIS · CONFIRMED BY INDUCTION · FALSIFIED

## RT-CHAIN-01 — the chain forks under concurrent execution

**Severity:** High (it breaks the project's central claim — a single,
independently verifiable chain of custody — under ordinary concurrent API load).
**Status:** CLOSED 2026-10-31. **Epistemic level:** CONFIRMED BY INDUCTION.
**Bucket:** software vulnerability (availability/integrity of the custody record;
not an authority bypass — no unauthorized execution occurs).

**Surprise.** The in-process N=2 test passed, but a raw-byte scan of the
persisted receipts after live concurrent bursts found two distinct receipts
sharing one predecessor hash. One clean run (N=8) was followed by a forked run;
the fork was intermittent, which is exactly why a single clean run is not
evidence.

**Abduction (ranked).** (1) The append is not actually serialized. (2) The
append is serialized, but the *head* it links against is chosen by a
non-authoritative key. (3) Oracle bug. Economy of research favored dumping the
raw topology to separate (2) from (3).

**Deduction.** `store.append_execution_receipt` serializes under a write lock
and `BEGIN IMMEDIATE` (so (1) is out), but selects the head with
`ORDER BY updated_at DESC, rowid DESC`. `updated_at` is `now().isoformat()`
computed in the API handler *before* it contends for the lock. Predict: if two
appends acquire the lock in an order that disagrees with their handler
timestamps, a later-appended receipt carrying an earlier timestamp will not be
seen as the head, and the next append will link to a stale predecessor — two
receipts then share it.

**Induction.** A topology dump of a forking run (rowid = true insertion order):

```
rowid  updated_at                        prev_hash   hash
 107   2026-10-31T17:41:44.144517+00:00  ...          6689b10bdc
 108   2026-10-31T17:41:44.143389+00:00  6689b10bdc   b1797a8950   <- updated_at < rowid 107 (inversion)
 133   2026-10-31T17:41:44.209675+00:00  6689b10bdc   b6baabc3e3   <- also links to 6689b10bdc  => FORK
```

rowid 108 was appended after 107 but carries an earlier timestamp; the next
append (133) selected the head by `updated_at DESC`, saw 107 as newest, and
linked to it — so 108 and 133 both descend from `6689b10bdc`, and 108's hash
`b1797a8950` is orphaned. The single timestamp inversion is exactly where the
fork attaches. Hypothesis confirmed; oracle bug (3) falsified by the raw dump.

**Fix.** Select the head by `rowid DESC` alone — insertion order, which is
authoritative because the append is serialized and `rowid` is monotonic with
INSERT. `updated_at` is removed from the head ordering. Re-ran
`tools/redteam_chain_probes.py`: 3 rounds × N=8 produced a single intact chain
(24 receipts, one root, no fork, no dangling); a 6-round raw-byte scan over 48
receipts found no fork where the unfixed code forked by round 3–4.

## RT-CHAIN-02 — replay replacement links to the row it overwrites

**Severity:** Medium (chain-tail integrity under a replay race; one receipt, no
unauthorized execution). **Status:** CLOSED 2026-10-31. **Epistemic level:**
CONFIRMED BY INDUCTION. **Bucket:** software vulnerability (integrity).

**Surprise.** With RT-CHAIN-01 fixed, the distinct-action rounds were clean, but
a replay race (M=6 concurrent executions of one prepared action) left a dangling
prev_hash and a chain tail that did not reach the last receipt.

**Deduction → induction.** A denied execution can win the append lock before the
successful one; both carry the same `obj_id` (`receipt-<proposed_action_id>`).
The denied receipt INSERTs first and becomes the highest-rowid receipt. The
successful receipt then computes the head by `rowid DESC`, sees the denied row
(its own obj_id) as newest, links to the denied receipt's transient hash, and
UPDATEs that same row — overwriting the hash it just linked to. Result: the
surviving receipt's prev_hash points at a hash that no longer exists. Confirmed
by the deterministic store regression (denied for action R persisted first, then
the successful R; the successful one linked to the denied row's hash, not the
real head) and by the live replay probe's dangling report.

**Fix.** Exclude the candidate's own `obj_id` from the head query
(`AND obj_id != ?`), so a receipt never reads a prior version of itself as its
predecessor. The successful replacement now links to the real head. Re-ran the
live probe: replay yields exactly one executed receipt, five denied, and a
single intact chain of 25 with no dangling link.

## Discarded / confirmed-safe observations

| Observation | Result | Why |
|-------------|--------|-----|
| Append not serialized | FALSIFIED | lock + `BEGIN IMMEDIATE` confirmed; the defect was head *selection*, not serialization |
| One clean N=8 run proves no fork | REJECTED | the fork is intermittent; a 6-round raw-byte scan was needed to surface it |
| Nonce replay admits a second execution | not reproduced | the one-shot nonce still yields exactly one execution under M=6 (induction) |
| Oracle miscount | FALSIFIED | raw `Counter` over persisted `prev_hash` bytes agrees with the topology dump |

## Result

Two chain-integrity defects, both intermittent and both invisible to the
store-layer and in-process tests, found by driving the real server and reading
the persisted bytes; both CONFIRMED BY INDUCTION, fixed with authoritative
append-order head selection, and regression-locked. Full suite 425 passed. KL-005
is updated to point here: its closure held for the race it tested, not for the
head-ordering and replay-replacement races this round adds.
