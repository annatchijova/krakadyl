# Meta SAM 3.1 processor

Status: opt-in provider adapter behind the Level 3 `EvidenceProcessor` port. It is not exposed as a production API route and does not evaluate evidence or change requirement or hypothesis state.

## Boundary

`MetaSamProcessor` accepts one already-authorized PNG or JPEG observation and a short prompt bound into the approved `ProcessorRequest`. It sends the image as a base64 data URL to the fixed Meta Responses endpoint and stores the returned `output_text` bytes as an untrusted annotation candidate. An empty output is preserved as an empty candidate. The adapter does not parse masks, validate an annotation, or infer what the observation means.

The coordinator calls `validate_request()` after re-reading and hashing the observation, but before committing processor dispatch intent. The processor repeats input checks immediately before dispatch and binds the request to the committed attempt digest. The adapter's resource usage is passed to the artifact repository and must match the persisted annotation usage exactly. Provider errors preserve a bounded request ID when Meta returns one. Failures after dispatch remain unknown outcomes; this adapter never retries automatically.

## Bounds and cost representation

- Model and destination are fixed to `sam-3.1` at `https://api.meta.ai/v1/responses`.
- Only PNG/JPEG signatures are accepted; the adapter does not fully decode or prove image-format validity.
- Input is limited to 10 MiB, prompt text to 256 characters, response JSON and annotation output to 8 MiB, and the absolute HTTP send/read deadline to 120 seconds (also bounded by the authorized duration ceiling).
- The standard-library DNS resolver is not interruptible by the socket deadline. If name resolution returns after the deadline, the adapter stops before sending the request body; the attempt may still require reconciliation because request headers could already have been sent.
- Arbitrary SAM parameters, video, remote image URLs, and redirects are not supported by this adapter contract.
- The request ceiling must reserve at least 2,500 USD micros per image. `usage.usd_micros` records the current public Standard list-price estimate ($2.50 per 1,000 images, checked 2026-10-29), not a provider-reconciled account charge. Taxes, credits, account pricing, and final billing are outside this record.

Meta's current documentation says Standard-mode content is not used to train Meta models. This is not a Zero Data Retention or deletion guarantee. Account-specific retention terms have not been verified here. Do not submit real case evidence until the data scope and retention terms have been reviewed and explicitly approved.

## Verification boundary

Offline adapter tests use synthetic bytes and an injected transport. The live smoke run used only a generated synthetic PNG; it does not establish retention terms, model accuracy, production authorization, budget-ledger integration, or Level 3 completion. On 2026-10-29, one additional live run passed through `AcquisitionCoordinator` and `SQLiteAcquisitionGate` using a temporary SQLite database, injected synthetic policy implementations, and a generated 128×128 PNG (429 bytes). Meta returned a completed, non-empty annotation and a provider request ID; the gate persisted a completed workflow and attempt, linked the annotation to the observation digest, and committed 2,500 USD micros as its conservative usage bound. No evaluation was produced. This is a one-run integration observation, not a provider billing receipt or evidence of visual correctness. No empty response is a negative finding about the case. No SAM output is automatically verified or promoted to evidence.

The prompt's linguistic form is not automatically proven to be a noun phrase. The exact prompt remains part of the approved request digest; reviewers must authorize its content. Provider response text and segmentation tokens remain untrusted data.

## Skills applied

`software-archaeology`, `secure-by-construction`, `validate-at-the-boundary`, `data-provenance-mapping`, `resource-exhaustion-review`, `falsifiable-testing`, `secret-lifecycle-discipline`, `git-discipline`, `audit-before-patch`, `beyond-the-fix`, and `invariant-hunting`.

The SQLite-backed live smoke follow-up used `destination-driven-construction`, `git-discipline`, `software-archaeology`, `secret-lifecycle-discipline`, `data-provenance-mapping`, `irreversible-action-gate`, `red-team-auditing`, `falsifiable-testing`, `surgical-patcher`, and `daubert-defensible-writing`.
