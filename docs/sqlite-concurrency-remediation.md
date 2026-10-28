# SQLite Concurrency Remediation

## Finding and inference

- **Firstness:** concurrent requests against the shared connection reproduced
  `sqlite3.InterfaceError: bad parameter or other API misuse`. A separate
  synchronized handler reproduction observed both requests enter execution with
  the same nonce absent from their request-local snapshots and both publish an
  effect.
- **Secondness:** the execution invariant allows at most one package publication
  for a one-time `PreparedAction`, and shared-connection requests must not fail
  due to overlapping SQLite operations. The observed duplicate effect and
  connection error violate those expectations.
- **Thirdness:** checking a per-request nonce snapshot and persisting the nonce
  after the effect leaves a time-of-check/time-of-use race. Unlocked concurrent
  access also lets calls interleave on one connection object.

The benign hypothesis was that SQLite's unique nonce key and its own locking
already made the complete request safe. It does not: the uniqueness check happened
after both effects, and it cannot serialize operations on one Python connection.
The predicted result of an atomic pre-effect claim is one winner and one replay
denial. Synchronized API and two-store tests confirm that result after the change.

The initial SQLite review also reproduced a transaction leak: after duplicate
`consume_nonce()` raised `sqlite3.IntegrityError`, the method caught the error but
left the connection in a transaction. A write through a second store instance
then failed with `database is locked`. The write lock and connection context
manager in the original branch fix rolled back before returning the duplicate
result; the remediation keeps that behavior and adds atomic pre-effect claims.

## Execution replay admission

The API now atomically claims a prepared action's nonce and writes an
`execution_claimed` event in one SQLite transaction before calling the executor.
The unique nonce key arbitrates requests across store instances and processes. A
duplicate claim is passed to the executor as an already claimed nonce, which
returns a denied receipt without publishing a package. A storage error aborts the
request before the executor is called.

Claiming is deliberately one-shot. A prepared action remains consumed if later
validation fails or the process stops after the claim. A crash after the claim and
before a receipt can leave an `execution_claimed` event without a result; the
absence of a receipt does not prove whether an external effect occurred. The
investigator must treat that state as unresolved and prepare a new action only
after reviewing the case activity. The nonce therefore means “execution attempt
claimed,” not “effect completed.”

Execution receipts use a stable identifier per proposed action. Persistence keeps
the first receipt unless a successful receipt replaces an earlier denied receipt,
so a replay cannot overwrite successful custody evidence. This read/modify/write
uses `BEGIN IMMEDIATE`, making the promotion safe across store instances and
processes. Each completed request also writes an execution outcome event, but the
receipt and outcome event are separate transactions. A crash between them can
leave a receipt without its matching outcome event.

## Shared connection access

The store instance lock now covers reads as well as writes on its shared SQLite
connection. This prevents concurrent FastAPI worker threads from interleaving
connection operations and makes a reader wait for an in-progress transaction on
that instance. The lock is not held while package assembly runs.

SQLite's unique nonce constraint remains the cross-instance arbitration point.
The Python lock does not coordinate other processes or provide a transaction
across multiple store methods. In particular, development reset and reseeding
remain separate operations, so a reader can observe the interval between their
commits. Multi-worker deployment and atomic reset/reseed require a separate
design.

## Verification

Tests cover concurrent API execution, concurrent nonce claims through two store
instances, receipt preservation after replay, successful receipt promotion across
two store instances, fail-closed storage errors, and a failed execution attempt
that burns its nonce. The repository's full test output is recorded with the
remediation branch review.

## Skills applied

- `audit-before-patch`
- `software-archaeology`
- `concurrency-reasoning`
- `atomic-state-mutation`
- `secure-by-construction`
- `falsifiable-testing`
- `surgical-patcher`
- `red-team-auditing`
- `git-discipline`
