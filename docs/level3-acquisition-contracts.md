# Level 3 — Evidence acquisition contracts

Status: proposed contract; no runtime implementation or API use is authorized by this document.

## Purpose and boundary

Level 3 is complete only when KRAKADYL can carry a justified acquisition need through an authorized observation and report what changed in the evidence state. A model response, an uploaded file, or a successful API call is not by itself evidence that uncertainty was reduced.

KRAKADYL coordinates acquisition and preserves its provenance. It does not decide what an observation proves or change a hypothesis status. A named inference mechanism or investigator may consume independently checked evidence and return a typed evaluation; KRAKADYL records that evaluation with its producer and basis. SAM is one replaceable instrument for deriving candidate annotations from an observation.

## Contract invariants

1. **Discriminating need:** every acquisition proposal names an existing open evidence requirement and its linked hypothesis or hypotheses. It states a concrete question, the possible answer classes, and which answers could change the requirement's evaluation. If no possible answer can change that evaluation, acquisition is unjustified.
2. **Source capability and authority:** the proposal identifies a concrete source and the evidence that it can supply the requested observation within the relevant recovery window. The action, source, requested data, destination, and bounded cost are covered by the mandate. Human authorization is explicit and bound to that exact proposal; changing any bound field invalidates the authorization. Model output cannot establish source capability or authority.
3. **Immutable observation:** acquired bytes are a new observation with a digest, acquisition record, and custody history. Derivatives reference the exact observation ID and digest and never replace or rewrite the original.
4. **Three separate verification questions:**
   - Integrity and custody: do the bytes match the recorded artifact and is their acquisition/provenance documented?
   - Annotation validation: does a derived annotation meet its stated, independently checkable criterion?
   - Inferential evaluation: does validated evidence satisfy, contradict, or fail to discriminate the open requirement?

   Passing one question does not imply passing either of the others. The acquisition component may report integrity/custody checks and candidate annotation results; it cannot promote those results into an inferential conclusion.
5. **Typed, untrusted derivation:** a SAM result, including a technically valid mask, track, or empty result, is a derived candidate with tool/version, request, parent digest, response digest, and usage provenance. It cannot independently resolve a requirement, verify a claim, change a hypothesis status, grant authority, or trigger execution.
6. **Explicit evaluation outcome:** the inference mechanism or investigator returns one of `SUPPORTS_REQUIREMENT`, `CONTRADICTS_REQUIREMENT`, `NO_DISCRIMINATING_CHANGE`, or `INSUFFICIENT_OR_INVALID`, tied to the requirement, the evidence and annotation versions considered, the criterion applied, and the evaluator. These are evaluation records, not direct hypothesis-status mutations by acquisition code.
7. **Bounded recovery:** an insufficient capture leaves the requirement open and records why. A next proposal may be offered only if a different or improved authorized source remains available and the configured per-requirement attempt and cumulative cost/resource limits allow it. Otherwise the workflow abstains with the reason recorded. Limits must be durable across restart and enforced before any paid call; no unbounded automatic retry is permitted.
8. **Honest degradation:** absent, malformed, empty, timed-out, over-limit, unauthorized, or unverifiable results remain visibly distinct. None can be represented as a successful resolution. An empty SAM result is a valid model outcome, but is not automatically a negative finding about the case.

## Contract records

| Record | Minimum binding fields | Must not do |
|---|---|---|
| `DiscriminatingNeed` | requirement ID; linked hypothesis IDs; question; possible outcomes and their effect on requirement evaluation; current uncertainty; eligible-source criteria; recovery window | infer a source, authority, or answer from free text/model output |
| `AcquisitionProposal` | need ID; source ID and capability basis; requested capture specification; expected discriminating outcomes; mandate/action scope; cost and resource ceiling; expiry; status | acquire before exact-scope human authorization |
| `AcquisitionAttempt` | proposal ID; authorizer and time; attempt number; start/end; outcome; cost/resource usage; failure or insufficiency reason | retry without checking durable bounds |
| `Observation` | immutable artifact digest; acquisition time/source/actor; custody and transformations; link to attempt | overwrite source bytes or become verified solely because upload succeeded |
| `DerivedAnnotation` | parent observation ID and digest; tool/model and version; exact request; output digest; parse/validation status; usage; empty-result flag | become an accepted claim or requirement evaluation by itself |
| `EvidenceEvaluation` | requirement ID; evidence and annotation IDs/digests; evaluator identity/type; criterion/version; one explicit outcome; rationale and timestamp | be silently authored by the acquisition adapter or mutate hypothesis status |

The names above are conceptual contract labels, not a commitment to specific Python class names or storage layout.

## Required falsifiers and acceptance scenarios

The contract is falsified if any scenario below produces a forbidden state transition or loses its audit link.

| Scenario | Prediction / oracle | Falsifier |
|---|---|---|
| No discriminating question | Proposal creation is refused with the missing requirement/question identified; no source call occurs | A capture can be proposed without a linked open requirement and outcome map |
| Unauthorized or changed proposal | No acquisition occurs; changing source, scope, data, destination, or cost requires fresh authorization | Any stale approval authorizes the changed proposal, or a model output supplies the authority |
| Authorized complete path | A real acquisition creates an immutable observation; separate checks and an identified evaluator produce a linked evaluation; the receipt says exactly what changed | The file, annotation, or API success directly resolves a requirement or changes hypothesis status |
| Valid but non-discriminating capture | The observation and valid SAM result are preserved; evaluation is `NO_DISCRIMINATING_CHANGE` or `INSUFFICIENT_OR_INVALID`; requirement remains open; system records an authorized alternative or abstains | A technically valid but irrelevant output is counted as knowledge or resolution |
| Convincing incorrect annotation | Adversarial annotation remains untrusted; no requirement/claim/hypothesis is automatically verified or accepted | Plausible wording, mask, or track crosses into accepted evidence without its independent criterion and evaluator |
| Authentic but insufficient evidence | Integrity/custody can pass while annotation validation or inferential evaluation fails/abstains; all three statuses remain separately visible | Authenticity is treated as proof of the annotation or of the hypothesis |
| Retry and budget exhaustion | Attempt/cost counters survive restart; the next request is blocked before the external call; workflow abstains with a reason | Restart resets the bound, a retry loop occurs, or an over-budget paid call is sent |
| Empty/malformed/service failure | Empty is recorded as a valid empty model response; malformed, timeout, and service failure are distinct warnings/failures; no resolution occurs | Empty is interpreted as absence in the case, or any failure is collapsed into success |

### Level-closing sequence

The closing experiment must execute the full acquisition lifecycle against a concrete discriminating need: pending requirement → source proposal → exact-scope human authorization → actual authorized capture → immutable observation → derived analysis → independent integrity/custody, annotation, and inferential evaluation records → auditable account of what changed and what remains unknown.

The insufficiency case must use that actual sensor execution: when SAM is selected, the real SAM call must return a technically valid result that does not discriminate the stated question. KRAKADYL must preserve the uncertainty, record the attempt, and either offer another bounded, authorized route or abstain. A separate adversarial run supplies a convincing incorrect annotation and verifies that it cannot be promoted automatically. Fake sensors and recorded fixtures remain useful for offline contract tests, but cannot satisfy this level-closing criterion.

Offline contract tests may use a fake sensor and synthetic fixtures. They do not establish live SAM behavior. A live external call with sanitized material is a separate gate requiring current vendor/data-retention review, explicit data-scope approval, and a user-approved spend ceiling. No call is authorized by passing these offline tests.

## Decision record

### Forces

The README assigns KRAKADYL evidence preparation and preservation, while an appropriate inference system or investigator determines what evidence supports. The existing Level 3 roadmap combines active acquisition with SAM-based visual processing. The code has a discriminating requirement link and a `GATHER_EVIDENCE` verdict, but the executor currently passes `resolvable_by_authorized_source=False`; no end-to-end acquisition lifecycle is implemented. Real vendor processing and cost are not approved by this contract.

### Decision

Treat acquisition need, source/authority, observation custody, derived annotation validation, and inferential evaluation as separate linked records. Keep acquisition code outside the inferential decision path. Require the full positive and insufficient-evidence sequences above before calling Level 3 complete.

### Alternatives considered

- **Make SAM the Level 3 center:** rejected because visual segmentation cannot establish why an observation is needed, whether its source is authorized, or whether its result discriminates the open requirement. Its strongest argument is that the current roadmap explicitly names SAM; retain it as a sensor within the level.
- **Let acquisition resolve the requirement when custody and integrity pass:** rejected because authentic bytes can carry an incorrect annotation and can be irrelevant to the hypothesis. Its strongest argument is lower implementation complexity; the separate evaluation record keeps the transition explicit.
- **Use a numeric information-gain score:** deferred because no calibrated outcome probabilities or validated scale exist in the current design. Record observable categorical change first; revisit only with a defensible evaluation method.

### Assumptions, reversibility, and revisit triggers

This contract assumes KRAKADYL remains the acquisition and evidence-readiness layer, with hypothesis evaluation owned by an identified inference mechanism or investigator. The record schema is one-way-ish once persisted and consumed by integrations; class names and storage layout remain open until implementation review. Revisit if the README's responsibility boundary changes, a concrete evaluator contract is selected, a source integration can authorize/capture without human mediation, or retention terms and data scope for an external processor are verified and approved.

## Not decided here

- Concrete attempt, file-size, frame-count, duration, concurrency, and monetary limits. All must have finite configured ceilings before any paid adapter can be enabled.
- Whether the first sensor is hosted SAM, local SAM, or another tool; vendor capabilities, prices, retention, and terms must be rechecked at the time of implementation.
- The identity and contract of the inference mechanism that consumes `EvidenceEvaluation`.
- Whether a human or an external inference system may mark an `EvidenceRequirement` resolved, and the exact verification authority for that transition.

These are implementation gates, not defaults for the adapter to guess.
