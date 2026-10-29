# SAM image annotation sidecar

Status: implementation complete; independent adversarial findings corrected and reviewed on `feat/sam-annotation-sidecar`.

## Contract

The parser is a pure consumer of the already persisted annotation-candidate bytes. It is not called from `MetaSamProcessor` or `AcquisitionCoordinator`. It returns a deterministic, immutable, versioned structural view bound to the SHA-256 digest of those exact candidate bytes. The digest is an integrity link to the candidate, not proof of provider authenticity, mask validity, or visual truth.

The parser never changes the candidate bytes, acquisition outcome, evaluation, requirement state, or hypothesis state. It does not decode masks or allocate memory based on mask dimensions. Mask payloads remain opaque and are referenced by half-open byte offsets into the bound candidate; consumers must verify the candidate digest before slicing. Source width and height are checked for consistency across records and used to bound boxes, but are not compared with decoded observation pixels; the source adapter currently checks image signatures rather than fully decoding image dimensions.

## Pinned profile and compatibility

Profile `sam3-image-v1` is pinned to Meta's public SAM protocol at commit `cdf2e8b5625a3471e6dab3be7127b80fa83beb0d`, scoped to one image. It supports optional commas before records, field-order independence, and decimal confidence including exponents. Object IDs retain their exact decimal lexemes; duplicate numeric IDs are rejected. All records in the image must report identical source dimensions. Confidence is preserved as text and range-checked with exact rational arithmetic; its text is capped at 64 ASCII characters and exponent magnitude at 18 before `Fraction` construction. It never enters a decision path. Integer values are capped at JavaScript's maximum safe integer, and the parser accepts at most 4,096 object records.

This profile intentionally returns `unsupported` (without partial records) for otherwise valid constructs outside its scope, including additional frames, frame-header fields, unknown tokens or fields, invalid/repeated optional confidence fields, mask dimensions outside the hosted-doc rule that both raster dimensions are smaller than the source frame, and record counts above the configured cap. The pinned protocol does not state the hosted page's mask-to-frame size relation; this conservative subset reports such records as unsupported rather than malformed. Unsupported handling also differs from the upstream protocol's warning-and-ignore behavior for unknown tokens or fields. The profile accepts only ASCII and at most one final LF or CRLF. These are explicit compatibility limits, not claims that other upstream output is malformed.

## Outcomes

- `empty`: candidate bytes are exactly empty.
- `parsed`: the profile's image wire structure was parsed. This does not validate or decode mask contents.
- `unsupported`: the bytes are outside this profile or exceed a parser-specific record/numeric bound, including unsafe mask-dimension products and invalid optional confidence. No records are returned.
- `malformed`: syntax, required fields, duplicate required fields/tokens or numeric object IDs, integer syntax, nonpositive dimensions, inconsistent per-image dimensions, coordinate bounds, or mask marker/alphabet is invalid. No records are returned.
- Input of the wrong type or larger than the existing 8 MiB response ceiling raises `SamAnnotationInputError` before hashing.

Whitespace-only bytes are `unsupported`, not `empty`. One final LF or CRLF is accepted; additional frame lines are `unsupported`. Diagnostics contain a fixed code and bounded byte offset only; they never embed provider text. Decimal lexemes and integer runs are length-checked before exact conversion. All numeric geometry remains integer-valued; confidence range checks use `Fraction` with explicit mantissa/exponent caps.

The sidecar digest uses KRAKADYL's existing `canonical_bytes()` encoder over schema version, profile version, candidate digest, outcome, records, offsets, and diagnostics. The sidecar digest field itself is excluded from the hashed payload.

## Falsifiers

- Empty bytes and whitespace-only bytes must produce distinct outcomes.
- Malformed later records must not leave a valid prefix in the returned record tuple.
- Unicode digit lookalikes, duplicate fields/tokens, missing paired box or mask, out-of-bounds coordinates, invalid markers, and inconsistent per-image dimensions must not produce `parsed`.
- Leading field whitespace must not shift half-open byte offsets; `007` must remain the object ID lexeme while colliding numerically with `7` for duplicate detection.
- Invalid optional confidence and mask dimensions outside the hosted-doc subset must return `unsupported`, with no partial records.
- Both confidence exponent forms within the documented numeric cap and optional record commas must parse; oversized confidence exponents must return `unsupported` before constructing a `Fraction`.
- Box and mask tokens may appear in either order without changing the parsed payload range.
- Large declared dimensions must not allocate a raster; dimensions outside safe integer or box bounds must not parse.
- Every mask payload range must slice the exact opaque payload bytes from the same candidate after candidate-digest verification; a changed candidate must be rejected.
- Repeated parses of identical bytes must produce identical sidecar digests.
- Live API output can establish compatibility with observed responses only. It cannot establish mask accuracy or change the candidate's status in the acquisition ledger.

## Verification snapshot — 2026-10-29

- Full repository suite after all parser and test changes: `209 passed in 3.63s` on Python 3.12.3.
- Red-first sidecar-integrity test: before the guard, `test_sidecar_tampering_is_detected_before_payload_slice` failed because the altered offset did not raise. After digest verification, it passed.
- Regression tests reproduced three independent audit findings: whitespace before `data=` shifted the payload offset, object ID `007` normalized to `7`, and differing frame dimensions across records were accepted. The corrected cases now pass. The profile also distinguishes unsupported hosted-doc mask-size constraints from malformed protocol structure.
- Negative controls: changed the frame check from `frame_index != 0` to `frame_index < 0`; the nonzero-frame test failed (`parsed` instead of `unsupported`). Then inverted the per-image dimension comparison; the mismatched-dimensions test failed (`parsed` instead of `malformed`). Restored both mutations; both focused tests passed.
- Live Meta calls: four calls in two batches using only the existing generated synthetic PNG. Each `red square` result completed and parsed as one record; the first candidate/payload lengths were 1,681/1,603 bytes, and the post-correction candidate/payload lengths were 1,685/1,607 bytes. Both `blue bicycle` calls completed with empty candidates and `empty` sidecars. All four had provider request IDs, candidate-digest binding, and no evaluation; each reported 2,500 USD micros. Estimated list-price usage was USD 0.010 total; no account billing reconciliation was performed.
- No real case evidence was submitted. The live run does not validate mask decoding, visual correctness, model accuracy, account retention, or ZDR. Mask payloads were not decoded.

## Skills applied

`parser-differential-hunting`, `validate-at-the-boundary`, `deterministic-core`, `versioned-schema-evolution`, `honest-degradation`, `invariant-hunting`, `data-provenance-mapping`, `falsifiable-testing`, `software-archaeology`, `secure-by-construction`, `surgical-patcher`, `abductive-engineering`, and `git-discipline`.

## Sources

- Meta, [SAM 3 protocol at the pinned revision](https://github.com/meta-models/meta-sam/blob/cdf2e8b5625a3471e6dab3be7127b80fa83beb0d/protocol/sam3.md).
- Meta, [hosted SAM segmentation output grammar](https://dev.meta.ai/docs/sam/reading-segmentation).
