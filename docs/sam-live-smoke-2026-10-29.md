# SAM Live Smoke Campaign — 2026-10-29

Status: bounded integration evidence using generated synthetic material. This campaign does not close Level 3 or establish model accuracy.

## Scope and method

The campaign ran against `main` at `b8c22899184694d877f18491410cd224490d580f`. Each request used the Meta `sam-3.1` endpoint through `MetaSamProcessor` and `AcquisitionCoordinator`. Synthetic authorization, scope, retention, and budget policies were injected into `SQLiteAcquisitionGate`; they are test fixtures, not production trust controls.

The image was a generated 128×128 PNG containing a red square on a white background (429 bytes). No case evidence, personal data, or user-provided image was sent. The processor stores model output as an untrusted annotation candidate. No `EvidenceEvaluation` was produced and no requirement or hypothesis was changed.

## Results

| Cohort | Calls | Concurrency | Annotation output | Persisted workflow | Estimated list-price usage |
|---|---:|---:|---|---|---:|
| Prompt `red square` on the red-square PNG | 40 | Up to 4 calls at once; isolated temporary SQLite database per call | 40 non-empty | 40 completed attempts with provider request IDs | USD 0.10 |
| Prompt `blue bicycle` on the same PNG | 20 | Up to 4 calls at once; isolated temporary SQLite database per call | 20 empty | 20 completed attempts with provider request IDs | USD 0.05 |
| Prompt `red square`, shared-database check | 4 | Four threads and four `KrakadylStore` connections sharing one SQLite file | 4 non-empty | 4 completed workflows; 8 completed phase attempts; 4 distinct authorizations | USD 0.01 |
| **Total** | **64** | **Maximum 4 concurrent requests** | **40 non-empty, 20 empty, 4 non-empty** | **64 completed processor attempts; no automatic evaluations** | **USD 0.16** |

For the shared-database run, the gate committed 10,000 USD micros of conservative usage and left zero reserved micros. All four annotations referenced the digest of their acquired observation. The database and JSON report remain under `/tmp/krakadyl-sam-shared-20261029T201058Z-jcrnl6y3/` on the machine where the run occurred; these are synthetic records only.

The reported amount is calculated from Meta's published image rate of USD 2.50 per 1,000 images. It is not an account billing receipt; the account usage dashboard was not inspected. The published documentation lists 3,000 RPM for `sam-3.1` per team, while account-specific limits can still govern the key. All 64 requests completed without an HTTP error or rate-limit response. [Meta pricing and rate limits](https://dev.meta.ai/docs/pricing-rate-limits)

## Adversarial setup result

The first 20-worker live harness was rejected before workflow creation: its deployment-duration grant exceeded the injected policy cap. The resulting SQLite file contained zero workflows, attempts, reservations, or events, so no API request was dispatched. A second 20-worker offline-transport harness admitted and completed four workflows, then denied the remaining 16 before workflow creation because its cumulative deployment-duration grant was too small; the four completions used a fake transport and made no external requests. After setting a four-call aggregate ceiling, an offline four-connection run completed 4/4 before the four-call live run. These were harness configuration errors, not product-code findings.

## What this demonstrates

Within these runs, the adapter accepted the generated PNG, returned a parseable completed response, preserved empty and non-empty output as distinct candidates, and carried provider request IDs into completed attempts. The shared-file cohort exercised concurrent admission and completion through four independent SQLite connections while using separate cases and authorization IDs.

The 40/40 and 20/20 output patterns describe this one image and these two prompts only. They do not estimate SAM's accuracy or establish that the masks match the object. The raw provider output was not retained for independent mask review; `MemoryArtifacts` held it only during each process. The four-connection cohort had no contention on the same case or authorization, and it does not test cross-host SQLite behavior, crash recovery after provider dispatch, or production policy implementations.

Meta's current documentation says Standard mode content is not used to train its models. Zero Data Retention is available only for qualifying organizations after separate enablement, and this run did not verify whether the API key's organization has it. The campaign used synthetic material for that reason; it does not approve uploading case evidence. [Meta Zero Data Retention eligibility](https://dev.meta.ai/help/policies-and-privacy/zero-data-retention), [Meta Model API terms](https://dev.meta.ai/legal/terms-of-service)

The conclusion would be reopened by a shared-file run that shows lost or duplicated workflows, a processor response that is not durably correlated with its provider request ID or observation digest, or a human-reviewed mask that contradicts the recorded empty/non-empty classification.

## Skills applied

`git-discipline`, `destination-driven-construction`, `software-archaeology`, `surgical-patcher`, `secret-lifecycle-discipline`, `irreversible-action-gate`, `data-provenance-mapping`, `red-team-auditing`, `falsifiable-testing`, `concurrency-reasoning`, `distributed-write-atomicity`, `abductive-engineering`, `claim-provenance-discipline`, and `daubert-defensible-writing`.
