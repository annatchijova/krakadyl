# SAM parser boundary review

Date: 2026-10-29
Branch: `docs/sam-parser-boundary-review`
Base: `b8c2289` (`main`)

## Decision

Keep the adapter’s annotation-candidate bytes (the joined `output_text` parts) as untrusted derived data in the acquisition success path. They are not the complete provider response and do not preserve output-text part boundaries. Do not add parsing to `MetaSamProcessor` in this change.

A parser is a useful follow-on capability, but a parser failure after a paid provider response must not turn a successfully returned result into an unknown acquisition outcome or discard the persisted annotation-candidate bytes. A future parser should run after those bytes are persisted, produce a separately versioned sidecar with its own digest and diagnostics bound to the candidate digest, and have no authority to change workflow completion, evaluation, requirement state, or hypothesis state.

The official `meta-sam-parser` Python package is published under Meta's SAM License. This review does not establish compatibility between that license and KRAKADYL's distribution policy. Do not add it as a dependency until that review is complete. An independently implemented parser would still need a complete, bounded contract and adversarial tests against the live wire grammar.

## Peircean observation and inference

### Firstness — observed

- The live adapter sends a non-streaming Responses request and persists the returned `output_text` as bytes.
- The existing synthetic adapter fixture contains `<|box;...|>` and `<|mask;x=0;y=0;data=1,2|>`; it checks preservation and provenance, not full SAM wire-format validity.
- The official Meta grammar describes a frame header, object IDs, paired box and mask tokens, dimensions, and encoded mask payloads. It accepts an empty output lane.
- A read-only design audit identified that parsing before candidate persistence can convert parser failure into a failed/unknown acquisition after provider dispatch.

### Secondness — expected context

The processor's documented contract is to preserve its collected annotation-candidate bytes as untrusted derived data. It does not claim to parse or validate masks. The acquisition coordinator persists the annotation and records provenance; no automatic evaluation is returned. This behavior is consistent with the declared boundary.

### Thirdness — inferred rule

Parsing is a new interpretation layer, not a correction to a demonstrated defect in the current candidate-byte path. It belongs downstream of durable candidate-byte persistence and must remain structurally separate from inference and hypothesis state.

### Abduction, deduction, induction, and refutation

- **Abduction:** SAM's structured tokens are currently inconvenient to consume as geometry; a parser could make a future human review interface possible.
- **Deduction:** If parsing is embedded in the provider success path, malformed or newly changed output could fail after a paid response and impair preservation of the provider result.
- **Induction:** Live calls and the current coordinator tests show that the adapter completes and preserves both non-empty and empty candidates without creating an evaluation. This supports retaining the existing boundary.
- **Refutation attempt:** The simpler explanation is that preserving the annotation-candidate bytes is already the intended contract and no parser defect exists. Live and repository evidence support that explanation. It survives; no parser code change is justified by this task.

## Live API check

The run used the existing generated synthetic PNG and `MetaSamProcessor` through `AcquisitionCoordinator`. No case data or personal data was submitted.

| Prompt | Outcome | Candidate bytes | Box token observed | Provider request ID | Evaluation |
|---|---|---:|---|---|---|
| `red square` | completed, non-empty | 1,693 | yes | present | none |
| `blue bicycle` | completed, empty | 0 | no | present | none |

The adapter reported 2,500 USD micros per call, or USD 0.005 total at the documented public list-price estimate. This is not an account billing reconciliation. These two calls establish only that the current live endpoint returned one non-empty candidate and one valid empty candidate through this path. They do not verify visual correctness, full box/mask grammar, mask payload decoding, account retention, or ZDR.

The full repository suite on this branch's base passed: `180 passed in 3.81s`.

## Parser boundary requirements for a later task

- Preserve and hash the adapter’s annotation-candidate bytes unchanged before interpreting them; do not claim complete provider-response or output-text part-boundary preservation.
- Store parsed structure and diagnostics separately, with parser name/version and a digest tied to the annotation-candidate digest.
- Keep masks opaque in the first parser slice; do not decode or allocate rasters.
- Treat an empty output lane as a valid empty result, distinct from a missing `output_text` field.
- Define explicit handling for multiple output-text parts, malformed records, nonzero image frame IDs, oversized dimensions, duplicate fields, invalid coordinates, and trailing bytes.
- Parser failure must not overwrite, delete, or invalidate the already persisted raw candidate.
- Parsing must not create an evaluation or mutate requirement/hypothesis state.
- Use fixtures conforming to the complete official wire grammar; current shortened mask fixtures are not format-conformance evidence.
- Resolve the official package license and dependency policy before adopting `meta-sam-parser`.

## Test integrity and blind spots

- Red-first for code changes: not applicable; this branch changes documentation only.
- Negative mutation: not applicable; no executable logic changed.
- Live boundary checked: a completed non-empty candidate and a completed empty candidate.
- Blind spots: no independent inspection of mask correctness or payload decoding; no full grammar parser was run; no billing dashboard or account-specific retention setting was inspected.

## Skills applied

`parser-differential-hunting`, `validate-at-the-boundary`, `deterministic-core`, `falsifiable-testing`, `software-archaeology`, `secure-by-construction`, `surgical-patcher`, `abductive-engineering`, and `git-discipline`.

## Sources

- Meta, [Read SAM segmentation output](https://dev.meta.ai/docs/sam/reading-segmentation) — current wire grammar and empty-output behavior.
- Meta, [SAM client libraries](https://dev.meta.ai/docs/sam/client-libraries) — official Python parser availability.
- Meta, [SAM License](https://github.com/meta-models/meta-sam/blob/main/LICENSE) — terms covering SAM materials.
- PyPI, [meta-sam-parser](https://pypi.org/project/meta-sam-parser/) — published package metadata and declared license.
