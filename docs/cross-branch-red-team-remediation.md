# Cross-Branch Red-Team Remediation

Date: 2026-10-28

## Scope and branch boundaries

The findings below were reproduced against the live branch content, then fixed in
separate branches. No branches were merged.

| Scope | Branch | Commit | Verification |
| --- | --- | --- | --- |
| SQLite shared connection and replay admission | `feat/sqlite-concurrency` | `22937dc175aba8660e06e8fe1bfe9a6656939235` | `python3 -m pytest -q`: 100 passed |
| Muse stale mandate snapshot | `fix/muse-stale-mandate` | `979dc5e446703fc2be84bb544c72288e353e7244` | `python3 -m pytest -q`: 92 passed |
| Cross-branch audit handoff | `docs/cross-branch-red-team` | this documentation change | No code tests apply |

All work branches start from the repository's `main` commit
`447e1099ed86a743841ea976b0a0d626ff709760`; the SQLite remediation continues
the existing SQLite task branch, while the Muse fix is isolated on its own branch.

## Threat model and evidence boundary

- A caller can submit two overlapping requests for the same prepared action.
- Case state can be revoked or reassigned while the external Muse adapter is
  still running.
- The caller cannot write the SQLite database directly or alter server code.
- Reproductions used temporary local databases and a fake Muse adapter. No
  production endpoint or billed Muse call was used.

The demonstrated impact is duplicate or unavailable action handling and a
persisted decision that does not reflect a revocation completed before
preparation. The tests do not demonstrate an unauthorized package effect after
revocation: the executor independently revalidates authority and blocked it in
the Muse reproduction.

## Findings

### SQLite request race and shared connection

- **Firstness:** concurrent API handlers using the shared connection reproduced
  `sqlite3.InterfaceError: bad parameter or other API misuse`. A synchronized
  execution reproduction also showed both requests observing the same nonce as
  unused and both entering the effect path.
- **Secondness:** a one-time prepared action must produce at most one package
  publication, and requests sharing the store must not fail from interleaved
  connection operations.
- **Thirdness:** a request-local check followed by effect and later persistence is
  check-then-act; a database uniqueness constraint applied after the effect cannot
  arbitrate that effect. Unlocked operations on one Python connection create a
  separate concurrency failure before the executor.

The SQLite branch now serializes all access to its shared connection. It claims a
nonce and records `execution_claimed` in one SQLite transaction before invoking
the executor. The database unique key arbitrates across store instances and
processes. A duplicate claim reaches the executor only with its nonce marked as
already claimed, so it returns a denied receipt before the effect path. A storage
error never reaches the executor. Successful receipt persistence is protected by
`BEGIN IMMEDIATE`; a denied replay cannot replace a successful receipt, including
when separate store instances race.

Claiming consumes the prepared action even if later validation fails or the
process stops. A crash can leave an `execution_claimed` event without a receipt;
that state is unresolved and must not be interpreted as proof that an effect did
or did not occur. The receipt and outcome event are separate commits, so a crash
between them can leave the receipt without its matching outcome event.

The shared-connection lock does not make the multi-method development reset and
reseed atomic. Readers wait for an in-flight transaction on one store instance,
but can still observe the committed interval between reset and reseed. Multiple
workers also do not share the Python lock; only nonce uniqueness and the receipt
promotion transaction are coordinated across stores/processes.

Reproduction tests:
`tests/test_api.py::test_concurrent_execution_claims_nonce_once_and_preserves_success_receipt`,
`tests/test_store.py::test_concurrent_nonce_claims_across_store_instances_have_one_winner`,
and
`tests/test_store.py::test_successful_receipt_wins_concurrent_persistence_across_store_instances`.
Run them with:
`python3 -m pytest tests/test_api.py::test_concurrent_execution_claims_nonce_once_and_preserves_success_receipt tests/test_store.py::test_concurrent_nonce_claims_across_store_instances_have_one_winner tests/test_store.py::test_successful_receipt_wins_concurrent_persistence_across_store_instances -q`.

### Muse mandate snapshot

- **Firstness:** the endpoint loaded mandate revision 1, awaited the Muse adapter,
  and used that saved object to prepare the result. A deterministic fake revoked
  the stored mandate during the call; the endpoint returned `ALLOWED` with a
  prepared action.
- **Secondness:** preparation must use the live authority state when the decision
  is made. A revocation completed before preparation must prevent `ALLOWED`.
- **Thirdness:** keeping an authorization object across external I/O creates a
  mixed-time snapshot.

The Muse branch retains the pre-call principal check, then reloads the current
mandate and rechecks the principal after the adapter returns. The deterministic
pipeline uses that refreshed mandate. The regression test failed before the patch
with `ALLOWED`, and passes after it with `FORBIDDEN` and no prepared action. The
test replaces the adapter with a local fake and makes no billed network call.
The reproducer is
`tests/test_api.py::test_propose_with_muse_revalidates_mandate_after_external_call`;
run it with `python3 -m pytest tests/test_api.py::test_propose_with_muse_revalidates_mandate_after_external_call -q`.

One interval remains: the mandate can change after the post-call read but before
the decision and prepared action are persisted. Execution independently checks
the current mandate, so a later change blocks an effect; the stored proposal can
still be stale relative to the exact persistence instant. A transactional
read/decision/write boundary is outside this remediation.

## Cross-branch integration finding

The existing `feat/muse-rate-limit` and `feat/sqlite-concurrency` branches both
edit `docs/red-team-api-and-frontend.md`. An in-memory three-way merge showed
conflicts in the adjacent F5/F6 summary row and Recommendations section. Taking
one branch's whole file would drop the other branch's finding or current limits.
This report does not resolve that shared-file conflict or merge branches. Any
later integration must preserve both F5 and F6, including their distinct scope
limits, in a deliberate conflict resolution.

The red-team also refuted two candidate findings:

- The four original feature branches produced identical OpenAPI output; no schema
  drift was found in this set of changes.
- The Level 2 hypothesis-recovery branch has no API, persistence, or frontend
  integration with these paths, so no cross-branch transition was established.

## Skills applied

- `red-team-auditing`
- `audit-before-patch`
- `software-archaeology`
- `concurrency-reasoning`
- `atomic-state-mutation`
- `secure-by-construction`
- `falsifiable-testing`
- `surgical-patcher`
- `git-discipline`
- `remediation-driven-reporting`
