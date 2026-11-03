# KRAKADYL — Global research: the problem, the alternatives, and the defensible differentiation

**Version:** 1.0 · **Research and source-consultation date:** 2026-11-02 · **Language:** English (faithful technical translation of `KRAKADYL_GLOBAL_RESEARCH_ES.md`, the Spanish original)

**Codebase examined:** public repository `annatchijova/krakadyl`, branch `main`, commit `1d56d66` (2026-11-02). The local working tree with uncommitted changes was **not** examined (see §2.4 and §18).

**Epistemic legend used throughout the document**

| State | Meaning |
|---|---|
| CONFIRMED | Verified in this research: code executed, test run, or primary source read that supports the specific claim |
| DOCUMENTED_ONLY | Stated by the system's own documentation (README, paper, product page), without independent verification |
| INFERRED | Reasoned inference from evidence; not directly observed |
| NOT_FOUND_IN_REVIEWED_SOURCES | Does not appear in the reviewed sources. It does **not** mean it does not exist |
| UNVERIFIED | Could not be verified (source inaccessible, secondary without primary support, or not consulted) |
| CONTRADICTED | A primary source contradicts the claim |

References in brackets (`[A5]`, `[H2]`, `[R3]`, etc.) point to the bibliography in §20.

---

## 1. Executive summary

**The problem exists, is documented, and is not exclusive to DFIR.** Investigations and critical operations fail recurrently at the points where a task changes hands, where something is reported done without anyone verifying it, or where evidence has a limited window of existence. There is solid evidence from aviation (Continental Express 2574, 1991: 47 screws missing after a shift change [I1]), process industry (Piper Alpha, 1988: two work permits that did not reference each other [I2]), medicine (I-PASS: −23% medical errors and −30% preventable adverse events after standardizing handoffs [H2]) and criminal justice (the Liam Allan case, 2017–2018: an officer believed he had reviewed the full download of more than 57,000 messages and had not [I3]). In cybersecurity, log retention determined what could be known: Microsoft could not establish how the key in the Storm-0558 incident was stolen because it did not retain logs for the period [I4], and Mandiant reports that standard 90-day retention prevented identifying the initial vector in the BRICKSTORM cases, whose average dwell time was 393 days [I8].

**What does not exist is a global figure for how many investigations fail due to avoidable failures of coordination, continuity, authorization, preservation or verification.** No study quantifying this for digital investigations was found in the reviewed sources. Any such percentage in a pitch would be fabricated. What can be stated with support are mechanisms (documented in other disciplines), concrete cases, and indirect signals (79% of SOCs operate 24/7 and therefore have structural shift handoffs [H11]).

**KRAKADYL implements and tests what it says it implements in the public repository**, with nuances. 451 tests were run (locked Python 3.11 and 3.13, all pass), along with the smoke test against a real server, the frontend build and lint, and the four deterministic demos. Level 6 (sub-mandates with transitive revocation, continuity after an interruption, and their interface panels) is on `main`. The Spanish/English internationalization is **not** in the public repository and could not be verified.

**Unfavorable findings that must be owned:**

1. **Every individual KRAKADYL guarantee has prior art.** Delegation attenuation exists since Macaroons (2014) [A17], UCAN [A15] and Biscuit [A16]. Transitive revocation with in-flight effects has a more rigorous, multi-endpoint treatment in Zhu and Wang (arXiv 2609.21284, September 2026) [A5], which KRAKADYL does not cite. Verifiable receipts exist in AgentBound [A1] and in transparency logs such as Rekor [A18]. The "reported" vs. "verified" distinction is doctrine in aviation, medicine and forensic science [H8].
2. **There is no empirical evidence that KRAKADYL reduces omissions, handoff errors, or reorientation time.** There were no user studies and no coordination benchmark. The README's "metric that matters" (reducing avoidable `ABSTAIN`s) has not been measured yet.
3. **The independent receipt verifier checks seal and chaining, not authority** (KL-002 [R3]). Presenting receipts as "independent proof that the action was authorized" would be overclaiming.
4. **KRAKADYL is not yet connected to the tools whose use it aims to discipline.** It doesn't compete with Velociraptor, SIFT or VIGÍA: it is the prior layer that makes sure they are used well (what was collected, where, before the window closed, verified by whom), so the inference engine doesn't end in a correct but avoidable `ABSTAIN`. Today that discipline is demonstrated on synthetic cases: there are no real adapters (Level 7) and persistence is single-node SQLite. With days of development (§3.5), that is the expected state, not a design flaw.

**Answer to the central question (§4.1).** KRAKADYL prevents eight investigative-process failures that occur before any tool is used: arriving late to a closing window; treating a merely reported task as verified; losing context in a handoff; having information that exists but isn't linked; acting on a state or authority that changed; returning from an interruption without reorienting; resting hypotheses on unverified assumptions; and having the window open without the authority available. Each is documented with data in health, aviation, process industry, finance or space exploration, and in several of those domains there are programs or rules that attack it, sometimes better (through scale and measurement) and sometimes worse (when verification depends on human ritual).

**What KRAKADYL is and isn't.** It doesn't try to do better what Velociraptor does. It tries to keep an investigation from reaching Velociraptor late, without the necessary conditions, with pending tasks, or on unverified working assumptions. The same applies to SIFT and VIGÍA: its success is measured downstream, in avoidable `ABSTAIN`s that stop happening. The concept, in general form and independent of any tool, is in §4.0: the correct but avoidable inconclusive outcome.

**Where the defensible differentiation lies:** not in any isolated guarantee, but in the **combination applied to the investigative domain**. In one deterministic model: (a) the verification state of evidence, with independence enforced by a validator, (b) delegated authority with transitive revocation revalidated at execution time, (c) typed recovery windows that distinguish "known deadline" from "closes on an event of unknown timing", and (d) reorientation after an absence. None of the reviewed systems documents that combination (NOT_FOUND_IN_REVIEWED_SOURCES). That is defensible before specialists. "The first in the world" is not.

**Recommended wording for the jury** (§14.3): *"Reported is not verified. KRAKADYL doesn't let the case confuse the two, or let revoked authority keep acting."* It has direct support in the code (`TaskResponsibility` validator, `authority_under_chain`) and in real cases (Liam Allan, Continental 2574).

---

## 2. Methodology and geographic scope

### 2.1 Procedure

1. **Code inspection before literature.** Clone of the public repository; reading of README, TECHNICAL_README, `docs/levels.md`, `docs/known-limitations.md`, red-team reports and core code. Execution of tests, demos, API smoke test, frontend build and lint.
2. **Verification of the prior art cited by the README itself** (AgentBound, AuthorizationBench, AuthorityBench/Veto, Bounded Agents, Meta Muse/Sentinel) against its sources.
3. **Search for the human and organizational problem** in medicine, aviation, process industry, criminal justice and cybersecurity.
4. **Search for solutions** in six families: DFIR and case management, agent authorization, multi-agent systems, evidence and provenance, continuity and temporality, human factors.
5. **Search for national preservation and chain-of-custody frameworks**, in local languages.
6. **Comparison by capability, not by name** (§9, §11).

About 75 searches and source readings were done in a single session on 2026-11-02. All bibliography URLs were opened on that date except those marked "not opened in this session".

### 2.2 Languages and regions covered

| Region | Search language | What was found | Source quality |
|---|---|---|---|
| USA / Canada | English | Agent prior art (eBay, ASU/Plaw, Northeastern per press, Accentrust Canada), NTSB/FAA, GAO, DOJ OIG, NIST, AWS, OMB | Mostly primary |
| Western Europe | English | Piper Alpha (IChemE), Liam Allan case (UK), Bounded Agents (independent researcher), Biscuit | Primary and secondary |
| Russia / Russian-speaking ecosystem | Russian | Problems with Art. 164.1 of the Russian Criminal Procedure Code (lawyer's opinion, 2019); Sber's GigaCowork agent platform (2026); Belkasoft and Oxygen Forensic (Russian origin, today with declared headquarters outside Russia — not verified) | Secondary |
| China | Chinese | Ministry of Public Security rules on electronic data collection (2019), Meiya Pico (美亚柏科), AgentScope (Alibaba), DeerFlow (ByteDance) | Secondary; the primary text of the rules could not be opened |
| India | English (Indian legal sources publish in English) | Section 63 of the Bharatiya Sakshya Adhiniyam 2023 and its confirmation by the Supreme Court (May 2026) | Specialized legal press |
| Japan | Japanese | IDF Evidence Preservation Guideline, 10th edition (March 2025) | Primary |
| South Korea | Korean | Supreme Prosecutors' Office regulation on digital evidence (in force since 2024-10-01) | Secondary (law firm) |
| Israel | English | Cellebrite Guardian | Vendor documentation |
| Latin America | Spanish, Portuguese | Argentina: MinSeg Res. 234/2016 and the 2023 PGN–MinSeg protocol; Brazil: CPP Arts. 158-A to 158-F (Lei 13.964/2019) | Primary |

**No searches were done in Hindi or Hebrew.** No results on agents with delegated authorization from Japan, Korea or India surfaced in the searches performed; that is NOT_FOUND_IN_REVIEWED_SOURCES, not proof of absence. Country of origin, country of deployment, publication language and author nationality are recorded separately when the source reports them; when it does not, that is stated.

### 2.3 Source hierarchy applied

1. Code, tests and technical documentation; standards and regulations.
2. Scientific publications.
3. Institutional reports and incident investigations (NTSB/FAA, GAO, DOJ OIG, CSRB).
4. Product documentation (marked "vendor documentation").
5. Specialized press (marked "secondary").

When two texts depend on the same source (for example, several press pieces about one paper) they count as **one** source.

### 2.4 Structural limitation of this research

The request required examining the **local** state of the code, including uncommitted changes in the interface and its internationalization. This session was not linked to the author's computer, so the local working tree could **not** be accessed. Everything that depends on those changes is marked "stated by the author, not verified". This limitation was not simulated as resolved.

---

## 3. Verified state of KRAKADYL

### 3.1 What was executed

| Check | Command | Result |
|---|---|---|
| Python tests (Python 3.11, `uv.lock`) | `uv run pytest -q tests --ignore=tests/test_laya_adapter.py` | **451 passed** (CONFIRMED) |
| Python tests (Python 3.13) | same | 451 passed (CONFIRMED) |
| Smoke test against real uvicorn | `python tools/api_smoke.py` | GET + prepare + execute over HTTP, sealed receipt (CONFIRMED) |
| Frontend | `npm ci --ignore-scripts && npm run build && npm run lint` | Build and lint with no errors (CONFIRMED) |
| Level 1 demo | `demo/run_case_001.py` | Tampered file → `forbidden`; requirement in `REPORTED_DONE` with intact file → `forbidden` (CONFIRMED) |
| Level 2 demo | `demo/run_case_002_level2.py` | Staleness detection, recovery route excluding exactly the tampered resource, honest closure under a revoked mandate (CONFIRMED) |
| Level 6 demo (delegation) | `demo/run_case_003_level6.py` | Revoking the root denies the delegatee two levels down without touching its sub-mandate (CONFIRMED) |
| Level 6 demo (continuity) | `demo/run_case_004_gap.py` | After 4 days and 3 hours: which mandates expired, which windows closed, what remains open and what is on conditional watch (CONFIRMED) |

Not executed: real calls to Muse Spark, Laya or SAM 3.1 (they require credentials or a GPU), the interface in a browser, or the live red-team probes (`tools/redteam_*`). Their results appear in the repository documentation and are considered DOCUMENTED_ONLY.

### 3.2 State classification

**Implemented and tested (CONFIRMED by execution or by reading tests):**

- Separation between evidence state (`SUFFICIENT/MISSING/CONFLICTING/STALE`) and authority state (`GRANTED/NEEDS_CONSENT/DENIED/EXPIRED`).
- `TaskResponsibility` lifecycle: `UNASSIGNED → ASSIGNED → ACKNOWLEDGED → IN_PROGRESS → REPORTED_DONE → VERIFIED_DONE` (plus `BLOCKED/EXPIRED/CANCELLED/UNKNOWN`). `VERIFIED_DONE` requires `verified_by` and `verification_method`, and `verified_by` different from `reported_done_by` unless the method is automated (`tool:`). The validator also runs on assignment (`validate_assignment=True`).
- `REPORTED_DONE` always maps to evidence `MISSING`, never `SUFFICIENT` (`continuity.evidence_state_from_requirement`).
- The executor requires **both** to include an observation: an intact digest **and** a requirement in `VERIFIED_DONE`. Neither substitutes for the other.
- Two phases (`prepare_evidence_package` / `execute_prepared_action`), with full revalidation of mandate, evidence and correspondence at execution time; persisted single-use nonce; assembly in a temp directory, digest verification of each copy, and atomic rename.
- SHA-256 chained receipts and a standard-library independent verifier (`tools/verify_receipt.py`, which deliberately does not import `krakadyl.core`). It rejects floats in the sealed path.
- Fix for two chaining races under real concurrent execution (RT-CHAIN-01/02), with regression in `tests/test_store.py`.
- `next_move()`: a single recommendation with visible alternatives, an *uncertain* state when there is a genuine tie, a *blocked* list, and a *conditional_watch* list for `CONDITIONAL`/`UNKNOWN` windows.
- Typed `RecoveryWindow` (`KNOWN`, `ESTIMATED` with `estimate_basis`, `CONDITIONAL` with `condition`, `UNKNOWN`).
- Level 4: append-only team statements, four derived conflict kinds, verification only by someone other than the claimant, shift handoff that transfers responsibility but not authority (DOCUMENTED_ONLY as regards the red team; tests present: 14 in `test_team.py`).
- Level 5: typed counterfactuals run on copies, never executable, flagged stale if inputs change (11 tests in `test_counterfactual.py`).
- **Level 6: sub-mandates** (`derive_sub_mandate` requires a strict subset in resources, operations, destinations and validity window); `authority_under_chain` walks the chain up to the root; broken or cyclic chains are refused; prepare/execute under a sub-mandate with chain revalidation at the linearization point (19 tests in `test_delegation.py`).
- **Level 6: continuity after an absence** (`resume_after_gap`, `GET /api/cases/{id}/resume`), with the start of the absence derived from the last recorded event, not from a client parameter (6 tests in `test_continuity_gap.py`).
- **Level 6: interface.** `DelegationPanel.tsx` and `ResumePanel.tsx` are on `main` (commits `93be916`, `635c80b`), build and pass lint. They were not tested in a browser in this research.

**Implemented but insufficiently validated:**

- **Receipt verifier:** only 2 dedicated tests (`tests/test_verify_receipt.py`), and both test failure cases (empty chain, malformed entry). No test in the repository checks that the independent verifier **accepts** a chain sealed by `krakadyl.core`. This research performed that check manually: a two-receipt chain sealed with `krakadyl.core.receipt.seal` was accepted (`OK`) and the same chain with an altered verdict was rejected (`BROKEN`, exit code 1) (CONFIRMED). **Also:** `seal_payload` is excluded from persistence by design, and there is no exporter in the API or in `tools/` that rebuilds the `chain.json` file the verifier expects. Today, verifying the receipts of a real case requires reconstructing each payload by hand from the decision and the manifest.
- **Laya:** the adapter test is excluded from CI; the repository itself warns that the checkpoint ships invalid temperatures and that confidence is uncalibrated [R2].
- **Muse and SAM:** behavior observed in bounded live runs; KL-003 acknowledges this [R3].
- **Verification graph:** structured for new requirements; legacy requirements still use prose provenance (KL-001, KL-004) [R3].
- **Persistence:** single-node SQLite. Correct for a small team; not validated under multi-organization load.

**Documented as design (not implemented):**

- Level 7: real adapters to Velociraptor, SIFT, i2 Analyst's Notebook and VIGÍA; exportable SDK; independent verifier that does not require trusting KRAKADYL's code to derive authority; benchmark published as an open dataset.
- Versioned authority-and-evidence envelope for the offline verifier (closure of KL-002).

**Pending or not verifiable from the public repository:**

- Spanish/English interface internationalization: no trace in `frontend/src` (search for `i18n`, `locale`, `LanguageContext`: no results). Stated by the author as an uncommitted local change; **UNVERIFIED**.

### 3.3 Repository claims that need nuance

| Claim | Where | Needed nuance | State |
|---|---|---|---|
| Level 6 interface "deliberately not built yet" | `docs/levels.md`, Level 6 section | The interface already exists on `main`. The document is stale; it should be corrected before submission so the jury doesn't read a contradiction | CONTRADICTED by the code |
| "Every decision produces a chained, independently verifiable receipt" | README, Architecture | Independently verifiable **in its seal and chaining**. It does not allow reconstructing mandate, evidence graph or verification basis from the receipt alone (KL-002) | Needs nuance |
| "Sub-mandates with composition closure" | `docs/levels.md` | In KRAKADYL it means subset closure. In Bounded Agents [A2] "composition closure" means prohibiting combinations of individually permitted actions. Using the same term invites a specialist's objection | Terminology risk |
| Sentinel as "host-side deterministic authority" | README, acknowledgements | Meta's announcement [A8] describes Sentinel as a separate agent that approves outbound access and asks the user. Its **deterministic** nature could not be confirmed in the primary sources consulted | UNVERIFIED |
| Prior-art list | README | Correct in what it cites (verified). It omits the closest work on revocation with in-flight effects [A5] and the report of authorization-propagation failures in production [A6] | Incomplete |
| Four October 2026 CVEs (PHP, Next.js, Node.js, GitLab) | `docs/levels.md` | Not verified in this research | UNVERIFIED here |
| "Reducing avoidable `ABSTAIN`s is the metric that matters" | README | Not measured. It is an evaluation hypothesis, not a result | Hypothesis |
| "IBM i2 Analyst's Notebook" (in the request and in discussions) | — | IBM sold the i2 portfolio to Harris (Constellation Software), which operates it as i2 Group [D10]. The README uses "i2 Analyst's Notebook" without "IBM", which is correct | Correct the name |

### 3.4 Guarantees demonstrable with reproducible tests

| Guarantee | Reproducible test |
|---|---|
| Something reported done but not verified cannot be used as sufficient evidence in an action | `demo/run_case_001.py` (run 4); `tests/test_model_invariants.py`; `tests/test_continuity.py` |
| No one self-verifies (except declared automated `tool:` verification) | `TaskResponsibility` validator; `tests/test_model_invariants.py` |
| A file altered after preparing the action blocks its publication | `demo/run_case_001.py` (run 3); `tests/test_executor.py` |
| Revoking an ancestor denies the entire delegated chain, even between prepare and execute | `demo/run_case_003_level6.py`; `tests/test_delegation.py`; `tools/redteam_level6_probes.py` (RT-L6-2, live) |
| A sub-mandate cannot widen its parent's scope | `derive_sub_mandate`; RT-L6-1 and RT-L6-3 |
| After an absence, the system reports what was lost purely through the passage of time | `demo/run_case_004_gap.py`; `tests/test_continuity_gap.py` |
| Model output does not grant authority | `tests/test_policy.py::test_a_classification_signal_alone_never_grants_authority` (**narrow** coverage, as the repository itself acknowledges) |
| Chained receipts without forks under real concurrency | `tools/redteam_chain_probes.py`; `tests/test_store.py` |

### 3.5 Development context

According to the full git history (CONFIRMED): first commit on 2026-10-27 at 10:14 (-03:00) and 205 commits with activity on 7 calendar days through 2026-11-02 (31, 18, 13, 121, 16, 5 and 1 commits per day). The author estimates about 4 days of effective development; the history doesn't allow measuring hours, only days with commits. VIGÍA, the downstream inference engine, has history since 2026-04-21.

Implication for reading this document: the limitations in §3.2 (single-node persistence, no adapters, no user studies, no receipt exporter) are the expected state of a days-old project, not design flaws. What the history does show is method: tests from the second commit, audit rounds that correct overclaims in code and docs already on the first day (for example `07c61d4` and `8238773`), red team per level, and an explicit limitations register. That method is checkable evidence; speed alone is not.

---

## 4. The human, technical and organizational problem

### 4.0 The core concept: the correct but avoidable inconclusive outcome

The author's formulation, generalized so it doesn't depend on any particular tool.

Every investigation ends at some point that evaluates what was gathered. It can be an inference engine like VIGÍA, an analyst writing a report, a prosecutor deciding whether to charge, a court, a newsroom deciding whether to publish, or a team deciding whether to close an incident. That point can conclude that what was gathered isn't enough: an abstention, an inconclusive report, a case shelved, a story that doesn't run, or weeks of work that produce nothing usable.

There are two different situations behind that same outcome:

| | Case A — unavoidable inconclusive outcome | Case B — potentially avoidable inconclusive outcome |
|---|---|---|
| What happened to the evidence | It never existed, was inaccessible, or isn't enough even after a correctly executed investigation | It existed and was recoverable |
| Why it didn't arrive | There was no way to obtain it | Someone didn't acquire it, let a window lapse, took a task as done that was never verified, lost context in a handoff, or acted without valid authority and the result became unusable |
| The evaluating point | Works correctly | **Also** works correctly |
| Where the failure is | Nowhere | Before the evaluating point evaluated anything |

Three consequences make case B a problem of its own:

1. **From the outcome, A and B are indistinguishable.** The evaluating point sees the same thing in both cases: something is missing. Telling them apart requires a record of what happened earlier. If that record doesn't exist, every case B is filed as if it were A, and the organization never learns it lost something recoverable.
2. **Improving the evaluating point doesn't solve B.** A more precise engine, a more expert analyst or a more powerful acquisition tool still correctly abstain in the face of evidence that never reached them. Case B is solved upstream or not at all.
3. **The cost of B isn't only the lost conclusion.** It is the time invested in a case that couldn't close, the hours of analysis on an incomplete set, and, in domains like organized crime or incident response, the operational window that closed in the meantime.

**Where KRAKADYL sits.** Between the investigation and the evaluating point. Its goal is not to evaluate better, but to make B cases visible while they can still be reversed. If they can't be reversed, they should be recorded as B and not as A. In terms of the current model, the typical causes of B map to concrete states: an expired `RecoveryWindow`, a requirement in `REPORTED_DONE` that was never verified, a handoff with no recorded state, a delegation whose authority lapsed. Case A maps to honest closure with `unresolvable`.

**Methodological caveat.** "Avoidable" is a counterfactual judgment and is exposed to hindsight bias: after the fact, almost everything looks avoidable. For the distinction to be defensible, it has to be made with the information available at the time. That is: the evidence was recorded as needed, its window was known or estimable, and an authorized route to obtain it existed. That is why the prior record is not an accessory. It is the only thing that allows classifying an outcome as B without rewriting history.

**Why this is a metric and not just an argument.** The proportion of inconclusive outcomes attributable to type-B causes, classified with the criterion above, is measurable in a benchmark (R-8) and in real cases with a record. That measurement doesn't exist yet (§6). It is the checkable form of the README's sentence about reducing avoidable `ABSTAIN`s while preserving necessary ones.

### 4.1 Which investigative-process failures KRAKADYL prevents

This is the document's central question: **which failures, occurring before the tools are used, cause them to be used late, without the necessary conditions, with pending tasks or on unverified assumptions.** Each failure is described abstractly, independent of any tool, and then contrasted with domains where it is studied: health, aviation, process industry, finance and space exploration. For each, the section states who works on the problem and how, compared with KRAKADYL's approach: better, worse or different. Data from other domains prove the failure is real and costly; they do **not** prove KRAKADYL reduces it in investigations (§6).

#### Summary table

| Failure | Example with hard data | Who works on it and with what result | Comparison with KRAKADYL | KRAKADYL mechanism | State |
|---|---|---|---|---|---|
| **F1. Arriving late to a closing window** | Sepsis: each hour of antibiotic delay was associated with +7.6% mortality [H14]. Storm-0558: no logs, no answer [I4] | AHA, Target: Stroke: door-to-needle ≤60 min rose from 26.5% to 41.3% and in-hospital mortality fell from 9.93% to 8.25% across 1,030 hospitals [H13] | **Better** in scale and measurement. **Different**: it optimizes a known clock; KRAKADYL also models windows that close on an undated event | `RecoveryWindow` (`KNOWN/ESTIMATED/CONDITIONAL/UNKNOWN`), `next_move`, `conditional_watch` | CONFIRMED (synthetic) |
| **F2. Task reported done and not verified** | Knight Capital: code wasn't copied to one of 8 servers and nobody reviewed the deployment; more than USD 460M lost in about 45 minutes [I10]. Liam Allan [I3] | Aviation: the rule prohibits whoever did the work from performing the required inspection [S14] | **Better**: it has been law for decades. **Same** in principle: KRAKADYL brings that rule to investigative tasks | `TaskResponsibility` validator; `REPORTED_DONE → MISSING` | CONFIRMED |
| **F3. Handoff that loses context** | Texas City 2005: no shift-turnover communication requirement existed; 15 dead and about 180 injured; operators on 29 or more consecutive days of 12-hour shifts [I11] | I-PASS: −23% errors, −30% preventable adverse events [H2]; Joint Commission: 37% of handoffs unsuccessful per receivers [H1] | **Better**: measured over 10,740 admissions. **Different**: I-PASS structures a conversation; KRAKADYL generates the handoff from recorded state | Level 4 handoff bound to the exact view; transfers responsibility, not authority | CONFIRMED (tests) |
| **F4. Information that exists but isn't linked** | Medication history at admission: errors in 10% to 67% of patients across 22 studies [H15]. Mars Climate Orbiter: navigation discrepancies handled by email, outside the formal process [I12]. Piper Alpha [I2] | HSE: work permits must cross-reference each other and be displayed systematically [S15] | **Better** in institutional formalization. **Worse** for KRAKADYL: it only covers conflicts on the same resource, not general dependencies | Derived conflicts (Level 4); structured verification graph | Partial |
| **F5. Acting on a state that changed, or with authority that no longer holds** | Wrong-site surgery in Minnesota: 31 cases in 2010 despite the universal protocol; time-outs were often rote or skipped steps [H17] | Lockout/tagout (LOTO): compliance is estimated to prevent 120 deaths and 50,000 injuries per year [S16]. Agent revocation [A5] | **Worse** for human protocols: immediate verification degrades into ritual. **Different**: KRAKADYL makes it mechanical | Revalidation in `execute_prepared_action`; `authority_under_chain` at execution | CONFIRMED |
| **F6. Interruption and return without reorientation** | Each interruption: +12.1% procedural failures [H3]; ~2.8 s interruptions double errors [H4] | "Do not interrupt" vests: about 15 fewer interruptions per 100 administrations, 48% staff support for making it policy [H16] | **Worse**: reducing interruptions is costly and poorly accepted. **Different**: KRAKADYL assumes interruptions will happen and designs the return | `resume_after_gap`; `next_move` | CONFIRMED (synthetic) |
| **F7. Unverified working assumptions** | Mars Climate Orbiter: the team assumed the spacecraft was similar to the previous one [I12]. Mayfield [I6] | Kassin, Dror and Kukucka: linear analysis and blind verification [H8] | **Better** at handling bias. **Worse** for KRAKADYL: it doesn't detect bias, it only invalidates hypotheses when their requirement changes | Hypothesis invalidation (Level 2) | Partial |
| **F8. Window open, authority unavailable** | A RAM dump requires the machine on, specialist staff and judicial authorization [S4] | National protocols that state it [S3][S4] | **Different**: protocols prescribe it; KRAKADYL makes it visible as state | *blocked* list and `GATHER_EVIDENCE` | CONFIRMED (synthetic) |

#### F1. Arriving late to a closing window

- **In the abstract:** evidence has a limited life the investigator doesn't control. It can be volatile memory, logs with fixed retention, a witness who leaves, a system that reboots or cloud data that gets purged. Arriving afterwards isn't a failure of the acquisition tool: nobody had the clock in view.
- **How it shows up in an investigation:** the tool runs correctly on something that no longer contains what mattered.
- **In health:** in septic shock, each hour of delay to appropriate antibiotics was associated with a mean 7.6% increase in mortality (retrospective study of 2,731 patients; median delay of 6 hours) [H14]. The American Heart Association's Target: Stroke program attacked an analogous clock: across 1,030 hospitals and 71,169 patients, the proportion treated within 60 minutes rose from 26.5% to 41.3%, the median fell from 77 to 67 minutes, and in-hospital mortality fell from 9.93% to 8.25% [H13].
- **Who works on it and how:** time-critical medicine has national programs, explicit targets and registries. **Better** than any individual tool in scale and evidence. **Different** in that they optimize a **known** clock; in digital investigation many windows close on an undated event (a power-off, a rotation), which is what `CONDITIONAL` and `UNKNOWN` represent.
- **What KRAKADYL does:** typed windows, urgency-based priority, and a separate watch list for what can't be ordered by date.

#### F2. Task reported done and not verified

- **In the abstract:** someone declares they did something, and everyone else acts as if it were verified.
- **How it shows up in an investigation:** a set believed complete gets analyzed, or an acquisition isn't repeated because it "was already done".
- **In finance:** at Knight Capital (2012), a technician didn't copy the new code to one of eight servers, no second technician reviewed the deployment, and no procedure required one. The outdated server reactivated an abandoned function and, in about 45 minutes, executed more than 397 million shares, with a loss of more than USD 460 million [I10] (secondary source summarizing the SEC order).
- **In aviation:** US regulation prohibits a person from performing the required inspection on work they themselves performed [S14]. The Continental 2574 case shows that rule doesn't protect if the shift handoff breaks traceability [I1].
- **Who works on it and how:** aviation solved it by law (**better**: mandatory, audited, with decades of practice). KRAKADYL applies **the same principle** to investigative tasks, where no such rule exists.
- **What KRAKADYL does:** `VERIFIED_DONE` requires another identity; what is reported is treated as missing.

#### F3. Handoff that loses context

- **In the abstract:** work changes hands and part of what the outgoing person knew doesn't reach the incoming one.
- **In the process industry:** at Texas City (2005), the CSB concluded that critical information was poorly communicated during the shift turnover and that BP had no turnover communication requirement; operators were likely fatigued after 29 or more consecutive days of 12-hour shifts. 15 people died and about 180 were injured [I11].
- **In medicine:** I-PASS (−23% errors, −30% preventable adverse events) [H2]; sender–receiver asymmetry (21% vs. 37% unsuccessful handoffs) [H1].
- **Who works on it and how:** I-PASS is **better** in evidence. It is **different** in mechanism: it structures a conversation between people. KRAKADYL generates the handoff from recorded state, so it doesn't depend on what the outgoing person remembers to say.
- **What KRAKADYL does:** Level 4 handoff bound to the exact view it was generated from; it moves responsibility but not authority.

#### F4. Information that exists but isn't linked

- **In the abstract:** two people or teams hold pieces that contradict or condition each other, and nothing connects them.
- **In health:** a systematic review of 22 studies found medication-history errors at hospital admission in 10% to 67% of patients; studies that separated unintentional errors gave 27% to 54% [H15].
- **In space exploration:** at Mars Climate Orbiter, navigation discrepancies were discussed by email rather than through the formal anomaly process, and the problem "slipped through the cracks"; software-interface verification was incomplete [I12].
- **In the process industry:** Piper Alpha [I2]; HSE guidance requires cross-referencing related permits and displaying them systematically [S15].
- **Who works on it and how:** the HSE and medication reconciliation are **better** in institutional formalization. KRAKADYL is **more limited**: it detects conflicts on the same resource and validates verification independence, but doesn't model general dependencies between tasks.

#### F5. Acting on a state that changed, or with authority that no longer holds

- **In the abstract:** something was approved or prepared when it was valid, and is executed later, when it no longer is.
- **In surgery:** the universal protocol requires a verification pause immediately before operating. Even so, Minnesota reported 31 wrong-site surgeries in 2010; a review found site marking in only 54% and a time-out in 51% of reported cases, and direct observation showed rote or memory-based time-outs [H17].
- **In industrial safety:** lockout/tagout requires isolating and verifying before working on a machine; according to OSHA, compliance prevents about 120 deaths and 50,000 injuries per year (estimate) [S16].
- **Who works on it and how:** checklists work when they're applied: in the WHO surgical checklist study (8 hospitals in 8 cities), mortality fell from 1.5% to 0.8% and complications from 11% to 7% [H12]. But human immediate-verification protocols are **worse** than they seem when sustained over time: they degrade into ritual, as the Minnesota case shows. In agents, Zhu and Wang [A5] are **better** in the distributed model. KRAKADYL is **different**: revalidation doesn't depend on someone remembering to do it.
- **What KRAKADYL does:** before executing, it rechecks mandate, delegation chain, evidence and nonce.

#### F6. Interruption and return without reorientation

- **In the abstract:** work is cut off, for seconds or days, and on return the state is rebuilt from memory.
- **In health:** each interruption was associated with +12.1% procedural failures and +12.7% clinical errors [H3]; in the lab, ~2.8 seconds doubled sequence errors [H4].
- **Who works on it and how:** a cluster randomized trial with "Do not interrupt" vests reduced interruptions by about 15 per 100 administrations, from a baseline of 57. Only 48% of staff supported adopting it as policy, and the accompanying editorial anticipates a small effect on errors [H16]. That is: **reducing interruptions is hard and poorly accepted**. KRAKADYL takes the **different** path: it assumes interruptions will happen and designs the return.
- **What KRAKADYL does:** `resume_after_gap` reports what changed purely through the passage of time; `next_move` answers "what do I do now" without rebuilding the case.

#### F7. Unverified working assumptions

- **In the abstract:** a hypothesis rests on something taken for granted and never checked, or that stopped being true.
- **In space exploration:** the Mars Climate Orbiter navigation team assumed the spacecraft was similar to the previous mission and didn't incorporate key data [I12].
- **In forensic science:** Mayfield [I6]; forensic confirmation bias and its remedies [H8].
- **Who works on it and how:** the forensic-bias literature is **better** at diagnosis and remedies (linear analysis, blind verification). KRAKADYL is **more limited**: it flags an accepted hypothesis for review when its discriminating requirement stops being resolved, but doesn't detect bias.

#### F8. Window open, authority unavailable

- **In the abstract:** the evidence still exists, but whoever can authorize obtaining it isn't there, or the permission doesn't cover that action.
- **In practice:** Argentina's 2023 protocol requires the machine on, a specialist and judicial authorization for a RAM dump [S4]. The window and the authority run on different clocks.
- **What KRAKADYL does:** anything with a legitimate claim on attention but no authorized route appears in a *blocked* list, not hidden. For missing evidence with an available route, the verdict is `GATHER_EVIDENCE`.

#### Overall reading

- **All eight failures happen before the tool or the evaluating point acts.** This is the empirical basis for case B in §4.0.
- **None is exclusive to DFIR.** Health, aviation, industry and finance study them with data and in some cases regulate them.
- **Where other domains are better, it is because of scale, regulation and measurement, not mechanism.** Where they are worse, it is because verification depends on human memory or ritual (time-outs, vests, verbal handoffs). KRAKADYL bets on turning those verifications into system conditions.
- **That bet is not yet measured in investigations.** The data in this section justify the problem and the design; they don't prove the effect (§6, §17).

### 4.2 Evidence with an expiry date

**Volatility.** RFC 3227's order of volatility (2002) remains the reference: registers and cache, then routing, ARP and process tables, memory, temporary file systems, disk, remote logs, topology and, last, archival media [S1]. Japan's IDF guideline (10th edition, March 2025) adopts that order, recommends keeping the machine powered on until memory has been acquired if there is no ongoing damage forcing a shutdown, and warns that pulling the plug without capturing volatile data makes the facts harder to establish [S2]. Argentina's 2016 protocol (MinSeg Res. 234/2016) instructs not to power off a running computer, so as not to lose volatile information, nor a running phone [S3], and the 2023 PGN–MinSeg protocol specifies that a RAM dump is only possible with the machine on and requires specialist staff and judicial authorization [S4].

That last condition is exactly the intersection KRAKADYL models: **a recovery window that closes on an event (power-off, reboot, rotation) and an authority that may not be available in time.** The protocol does not solve it; it states it.

**Log retention.** The window is not decided by the investigator:

- AWS CloudTrail Event history keeps **90 days** of management events per region; data events are not included by default [S11].
- In Storm-0558, Microsoft had no logs showing the key's exfiltration because of its retention policies, and the available logs covered only the last 30 days, so the intrusion's real start could not be determined [I4].
- M-Trends 2026 reports that standard 90-day retention prevented identifying the initial access vector in the BRICKSTORM cases, and that some organizations had to assume and disclose a worst-case data breach because they could not reconstruct the timeline [I8].
- In the US, OMB replaced memorandum M-21-31 in 2026 with a risk-based approach that requires logs retained and searchable for six months [S12] (secondary source; primary memo not read).

**Chain of custody as a legal requirement in several countries.** Brazil added to its Code of Criminal Procedure (Arts. 158-A to 158-F, Lei 13.964/2019) a ten-stage chain of custody, with the name and signature of whoever collects and packages and of whoever receives [S5]. Argentina requires a "route sheet" (*hoja de ruta*) with date, time, officer in charge and signatures of whoever hands over and whoever receives [S3]. India requires, for secondary electronic evidence, a certificate with the hash value (Part A) and an expert certification (Part B); the Supreme Court rejected a challenge to that requirement in May 2026 [S6]. South Korea registers images and hashes and requires a detailed list of what was seized [S7]. China, according to a sector report summarizing the Ministry of Public Security's 2019 rules, requires ensuring the authenticity and integrity of electronic data [D8] (primary text not accessible in this session). Japan devotes a section to recording every handover with date, time, person in charge, recipient, place, item and condition [S2].

**What all those frameworks have in common:** they prescribe **what** to record. None of those consulted prescribes a mechanism that prevents acting on evidence whose verification record is incomplete. That gap between regulation and mechanism is where KRAKADYL sits. (INFERRED from the cited sources.)

In Russia, an opinion piece in *Advokatskaya Gazeta* (2019) describes another side of the same problem: copying on site is often impractical (no spare drives, specialists or time), so the device is seized, the company is paralyzed, and the author proposes return deadlines with data intact [S8]. It is an opinion source, not a study, and is used only to illustrate the tension between preservation and operation.

### 4.3 Coordination and continuity

**Aviation: Continental Express 2574 (1991).** The second shift removed screws from the left leading edge of the horizontal stabilizer; the supervisor did not brief the third shift verbally, did not hand out the work cards, and the turnover-sheet entry was written after the incoming inspector had read it. 47 screws were missing. 14 people died. The FAA stresses that the manual already had clear shift-turnover procedures; they were not followed [I1].

**Process industry: Piper Alpha (1988).** Two work permits controlled pump A and its safety valve; they did not reference each other and were probably filed in different places. The control room knew about the pump repair but not that the valve was missing, and restarted the pump. 167 people died [I2].

**Medicine.** The Joint Commission (Sentinel Event Alert 58, 2017) reports that in its handoff-communication project receivers judged 37% of handoffs unsuccessful and senders 21% — the asymmetry is itself a finding: whoever hands over believes they transmitted more than the receiver got [H1]. The I-PASS program (9 hospitals, 10,740 admissions, before-and-after design) reduced medical errors from 24.5 to 18.8 per 100 admissions (−23%) and preventable adverse events from 4.7 to 3.3 (−30%) [H2].

**Criminal justice: Liam Allan (UK, 2017–2018).** The trial collapsed when undisclosed messages surfaced. The joint review by the Metropolitan Police and the Crown Prosecution Service attributed the failure to error, lack of challenge and lack of knowledge: the officer believed he had reviewed the full download of more than 57,000 messages, assured the prosecution of that, and the prosecution relied on that assurance instead of challenging it [I3]. It is, literally, a `REPORTED_DONE` treated as `VERIFIED_DONE`.

**Agent systems.** A report from an enterprise AI platform in production describes three authorization failures that occurred in normal operation, not under attack; one of them was **a delegation reported as successful that never occurred** [A6]. The same human pattern reappears in automated systems.

**Which mechanisms transfer to DFIR and which don't:**

| Studied mechanism | Comparable in DFIR? | Why |
|---|---|---|
| Structured handoff (I-PASS, SBAR) | Yes, partially | SOCs and response teams have shifts (79% operate 24/7 [H11]) and handoffs between organizations. But digital evidence doesn't deteriorate like a patient: some sources are stable and others disappear due to external events |
| Required duplicate inspection (aviation) | Yes | Equivalent to requiring verification by someone other than the performer, which is what `TaskResponsibility` does |
| Work permits that cross-reference each other (Piper Alpha) | Yes | Equivalent to not allowing two tasks on the same resource to exist without an explicit link; KRAKADYL covers this with Level 4 derived conflicts, not with a general model of dependencies between tasks |
| Measurable patient outcome | **No** | In DFIR the "harm" is usually an inference that can no longer be made. It is harder to count, which partly explains the absence of quantitative studies (INFERRED) |
| Blameless reporting culture | Yes | KRAKADYL carries it into language: it reports case states, not people |

### 4.4 Human factors

- **Interruptions.** In an observational study of 98 nurses and 4,271 medication administrations, each interruption was associated with a 12.1% increase in procedural failures and 12.7% in clinical errors [H3]. In an experiment with 300 participants, interruptions of about 2.8 seconds doubled sequence errors [H4]. Transfer to digital investigations is plausible but not measured.
- **Fatigue.** After 17 to 19 hours without sleep, performance on most tests was equivalent to a blood alcohol concentration of 0.05% [H5].
- **Automation bias and complacency.** They occur in both naive and expert participants, and automation bias is not prevented by training or instructions [H6]. Direct implication for KRAKADYL: an interface that displays "verified" too confidently can create the very problem it aims to avoid. The strict separation between the recommendation (`next_move`) and authority (`decide`) is a design mitigation, not proof that the bias does not occur.
- **Forensic confirmation bias.** The examiner's expectations and context influence how evidence is collected and interpreted; among the proposed solutions is controlled verification, ideally blind to the initial result and to the first examiner's identity [H8]. The Mayfield case (2004) shows that agreement among several experts is not independent verification: three experienced examiners and a court-appointed expert were wrong, and the Spanish police's negative conclusion of April 13, 2004 did not lead to timely reconsideration [I6].
- **Cognitive offloading and distributed cognition.** Cognitive offloading is the use of physical action to reduce a task's cognitive demand, such as setting a reminder [H7]. Hutchins's classic analysis of how a cockpit "remembers" its speeds shows that the working memory of a critical system resides in artifacts and practices, not only in heads [H9]. KRAKADYL is an explicit application of that idea to the investigative case.
- **Accessible design and neurodivergence.** The W3C note on usability for people with cognitive and learning disabilities includes as objectives that processes do not rely on memory, that interruptions are limited, and that each step indicates where the user is so they can resume [S13]. Popular literature on ADHD and prospective memory notes that time-based tasks are often harder than event-based ones and that external cues help, with strong individual variability [H10] (popular source, no studies cited in the text). **What this allows us to state:** designing not to rely on memory benefits anyone under fatigue, interruption or overload, and additionally neurodivergent people. **What it does not allow us to state:** that a diagnosis determines an investigator's performance.

**Section conclusion:** the evidence explains why an excellent investigator can fail at coordination under adverse conditions — technical competence does not protect against interruptions, fatigue, automation bias or handoff asymmetries. KRAKADYL's own documentation phrases this as "technical competence and executive-function capacity are independent variables" [R2]. The sources in this section support it as a design hypothesis; there are no studies measuring it in digital investigators.

---

## 5. Documented consequences

| Type of consequence | Evidence | Type of relationship |
|---|---|---|
| Inability to determine how an incident happened | Storm-0558: no logs of the key's exfiltration due to retention policies [I4] | Causal per the cited CSRB analysis |
| Worst-case disclosure for lack of a timeline | M-Trends 2026, cases with anti-forensics and short retention [I8] | Descriptive, no percentage |
| Prolonged attacker presence | Global median of 14 days; 122 days in cyber-espionage; 393-day average in BRICKSTORM [I8] | Descriptive |
| Late detection due to a control assumed to be active | Equifax: inspection-device certificate expired about 10 months earlier; 76 days undetected; about 9,000 queries [I5] | Causal per GAO |
| Cost associated with long lifecycles | Breaches over 200 days: USD 5.65M vs. USD 4.32M for shorter ones; global average USD 4.99M; 247 days to identify and contain [I9] | **Correlation**, and secondary source for the IBM report |
| Collapse of a court case | Liam Allan [I3] | Causal per the review |
| Misidentification with personal consequences | Mayfield, detained about two weeks [I6] | Causal per DOJ OIG |
| Deaths | Continental 2574 (14) [I1]; Piper Alpha (167) [I2] | Causal per official investigations |
| Unauthorized action by an agent | Replit, July 2025: deletion of a production database despite instructions, according to the affected user [I7] | **One party's account**, not independently verified |
| Exposure of personal data by an agent | Muse, September 2026: sending a home address to a buyer [A9] | **Disputed** by Meta |

---

## 6. Empirical studies and statistics

| Data point | Value | Source | Methodology | Caveat |
|---|---|---|---|---|
| Reduction in medical errors with I-PASS | −23% (24.5 → 18.8 per 100 admissions) | [H2] | Before-and-after, 9 hospitals, 10,740 admissions | Pediatrics; not randomized |
| Reduction in preventable adverse events with I-PASS | −30% (4.7 → 3.3 per 100) | [H2] | same | The PSNet summary attributes 23% to adverse events; the press release and the Joint Commission attribute 23% to errors and 30% to adverse events. The latter is used (§19) |
| Handoffs judged unsuccessful | 37% (receivers) vs. 21% (senders) | [H1] | Joint Commission project | Sample not detailed in the alert |
| Increase in errors per interruption | +12.1% procedural; +12.7% clinical | [H3] | Observational, 98 nurses | Hospital medication |
| Errors after a ~2.8 s interruption | Double | [H4] | Experiment, 300 participants | Laboratory task |
| Wakefulness equivalent to 0.05% BAC | 17–19 hours | [H5] | 39 participants, 28 h awake | Drivers and non-drivers |
| SOCs operating 24/7 | 79% | [H11] | SANS 2025 survey | Respondent self-selection |
| SOCs with manual or mostly manual metrics | 69% | [H11] | same | same |
| Agent trajectories with out-of-authorization actions | 19.2% (range 10.5–26.6%) | [A4] | 286 tasks, 6,864 trajectories | Benchmark, not a production rate; secondary source |
| Unauthorized actions permitted with prompt-only instructions under social pressure | 18.3% | [A3] | 7,427 trials | Declared conflict of interest; the authority model's 0% holds by construction |
| Delegation in multi-agent frameworks: pairs that hold the limit across the whole tree | 1 of 32 assessable | [A7] | 8 frameworks, 11 probes | Workshop poster |

**Direct answer to the request's fundamental question.** No statistic was found stating how many digital investigations fail, are delayed, become more expensive or lose evidentiary value due to avoidable failures of coordination, continuity, authorization, preservation or verification. The figures in this table are **approximations from neighboring disciplines** or **agent benchmarks**. Measuring that quantity would itself be a contribution (see §17, R-8).

---

## 7. Real cases

None of these cases involved KRAKADYL. The "relevant mechanism" column is a bounded counterfactual analysis, not a claim that KRAKADYL would have prevented it.

### 7.1 Continental Express 2574 (USA, 1991) [I1]

- **What happened:** work started on one shift and finished on another; the partial state was not transmitted.
- **Evidence that existed:** the turnover sheet, but the entry was written after the incoming inspector read it; the work cards were not handed out.
- **What remained unverified:** that the left leading edge was complete.
- **Consequence:** 14 dead.
- **What is known:** the handoff sequence, per NTSB/FAA. **Uncertain:** nothing relevant to this analysis.
- **Relevant KRAKADYL mechanism:** a task in `IN_PROGRESS` that cannot move to `VERIFIED_DONE` without a different verifier; a handoff generated from recorded state, not from the outgoing person's memory.
- **Cannot be claimed:** that software would have prevented the accident. The manual already had procedures and they were not followed; a system that isn't used doesn't protect either.

### 7.2 Piper Alpha (UK, 1988) [I2]

- **What happened:** two permits on the same pump without cross-reference; the valve permit was suspended overnight and the control room didn't know.
- **Relevant mechanism:** derived conflicts on the same resource (Level 4); authority separate from resource state.
- **Cannot be claimed:** that KRAKADYL models physical dependencies between tasks in general. It does not.

### 7.3 Liam Allan (UK, 2017–2018) [I3]

- **What happened:** the officer believed he had reviewed the whole download; the prosecution accepted his assurance without challenge.
- **Evidence that existed:** more than 57,000 downloaded messages.
- **What remained unverified:** the complete review.
- **Consequence:** a collapsed trial and a defendant put through a process that should not have advanced that way.
- **Relevant mechanism:** the most direct case for `REPORTED_DONE ≠ VERIFIED_DONE` and for "verification by someone other than the claimant".
- **Cannot be claimed:** that KRAKADYL assesses whether a review was exhaustive. It can only prevent an unverified claim from being treated as verified. Who verifies and how remains a human decision.

### 7.4 Storm-0558 (USA and others, 2023) [I4]

- **What happened:** with no logs for the period, it could not be known how the key was obtained; the crash-dump hypothesis was weakened.
- **Relevant mechanism:** `RecoveryWindow` with a `CONDITIONAL` close (log rotation) and the conditional watch list in `next_move`.
- **Cannot be claimed:** that KRAKADYL would have known in advance those logs would matter. It only makes visible the window of a source **already registered** in the case.

### 7.5 Equifax (USA, 2017) [I5]

- **What happened:** the traffic-inspection device's certificate had expired about 10 months earlier; 76 days undetected.
- **Relevant mechanism:** distinguishing "control deployed" from "control verified as active" is the same pattern as `REPORTED_DONE`/`VERIFIED_DONE`, applied to monitoring.
- **Cannot be claimed:** that KRAKADYL is a certificate-management or monitoring tool. It is not. The case illustrates the pattern, not a direct use.

### 7.6 Mayfield (USA/Spain, 2004) [I6] [H8]

- **What happened:** erroneous fingerprint identification confirmed by several examiners; an external negative conclusion did not lead to timely review.
- **Relevant mechanism:** hypothesis invalidation when its discriminating requirement changes (Level 2) — an accepted hypothesis that must go back to review.
- **Cannot be claimed:** that KRAKADYL detects confirmation bias. Its independence rule is about identity (another person), not blindness to context.

### 7.7 Replit (USA, 2025) [I7] — one party's account

- **What happened (per the user):** the agent deleted a production database despite a code freeze, and stated that no rollback was possible when later it was.
- **Relevant mechanism:** separation between the model's proposal and effective permission; receipts for what was executed and what was refused; "unknown result" vs. "invented result".
- **Uncertain:** Replit's version is not in the source.

### 7.8 Meta Muse and the home address (USA/Canada, 2026) [A9] — disputed

- **What happened (per the affected person):** the agent sent a home address to a buyer; Meta maintains it asked for permission correctly.
- **Relevant mechanism:** explicit mandate scope (what data may leave and to whom).
- **Uncertain:** the exact approval sequence. Included because Muse is the hackathon's environment; using it in the pitch requires stating that it is disputed.

**Demo simulations vs. real cases.** KRAKADYL's demos (`case-001` to `case-004`) are **synthetic**. No demo result should be presented as data from a real case.

---

## 8. Global landscape of solutions

**How to read this section.** KRAKADYL is not an acquisition, analysis or inference tool. It is the prior discipline that makes those tools be used correctly: that the Velociraptor collection was run, on the right host, before the window closed, and that someone else verified it, so VIGÍA or another engine doesn't return a correct but avoidable `ABSTAIN`. In VIGÍA, `ABSTAIN` is a valid, mathematically justified verdict [V1]; what KRAKADYL targets is the `ABSTAIN` explained by a preparation failure rather than by the evidence. Put differently: KRAKADYL doesn't try to do better what Velociraptor does; it tries to keep it from being used late, without the necessary conditions, with pending tasks, or on unverified assumptions. That is why the DFIR tools in this section are **instruments KRAKADYL accompanies**, not competitors. The systems that do occupy a comparable place are those trying to solve the same discipline problem: tasks in case managers, agent authorization, checklists and playbooks.

| Family | Examples (organization, declared country) | What they solve well | Relationship to KRAKADYL |
|---|---|---|---|
| Endpoint acquisition and response | Velociraptor (Velocidex, acquired by Rapid7 in 2021; AGPLv3) [D1] | VQL queries across fleets, hunts, versioned artifacts | Instrument KRAKADYL accompanies: records what was collected, where, and whether it was verified |
| Collaborative timeline analysis | Timesketch (Google; Apache-2.0) [D2] | Collaboration on timelines, annotations | Export target for activity and receipts |
| DFIR case management | DFIR-IRIS (sponsored by Deutsche Telekom Security per secondary source; LGPL-3) [D3]; TheHive 5 (StrangeBee, France — country not verified in this session; Community/Gold/Platinum/One licenses) [D4] [D5] | Cases, tasks, observables, integrations | Closest in the discipline function (mandatory tasks), with no link to the authority to act; adapter candidate |
| Evidence and lab management | Cellebrite Guardian (Israel) [D6]; Detego (UK — not verified) [D9]; Belkasoft X [D7] | Physical and digital custody, tamper-evident audit logs, lab tasks | Lab custody; KRAKADYL acts earlier, on case preparation |
| Chinese forensics ecosystem | Meiya Pico 美亚柏科 (over 40% of the Chinese market per a 2019 report) [D8] | Full forensic cycle and "cloud" preservation | No accessible documentation of an authority model |
| Agent action governance | AgentBound (eBay) [A1]; Veto/AuthorityBench (Plaw/ASU) [A3]; Bounded Agents/APC [A2] | Deterministic decision outside the model; signed receipts; composition prohibitions | Direct prior art for the authority layer |
| Authority revocation in long-running agents | Root-scoped quiescence (Accentrust, Canada) [A5] | Revocation with in-flight effects, commit-point fences, separate checker | **Closest technical competitor** to Level 6 |
| Authorization benchmarks | AuthorizationBench (PEACH-Research-Lab) [A4]; BROODS [A7] | Measuring authority overreach and bounds that don't compose | Material for an own benchmark |
| Agent platforms | Meta Muse + Sentinel (USA) [A8]; AgentScope 2.0 (Alibaba, China) [A10]; DeerFlow 2.0 (ByteDance, China; MIT) [A11]; GigaCowork (Sber, Russia) [A12]; LangGraph (USA) [A13] | Execution, memory, sandbox, human approval | General platforms; none documents evidence verification states |
| Delegable capabilities | Macaroons (Google, 2014) [A17]; UCAN [A15]; Biscuit (Eclipse/Clever Cloud) [A16] | Cryptographic attenuation, decentralized verification, revocation (UCAN) | Possible format for exporting sub-mandates |
| Provenance and transparency | Sigstore Rekor [A18]; RFC 9162 (not opened) | Append-only logs with inclusion proofs | Possible external anchor for the receipt chain |
| Durable execution | Temporal [A14]; LangGraph with checkpointer [A13] | Resumption after failures, indefinite pauses | Solve resuming the **process**, not reorienting the **person** |

---

## 9. Detailed technical comparison

Format per solution: (1) organization, country, type · (2) version and date · (3) problem · (4) mechanism · (5) implementation evidence · (6) independent testing · (7) limitations · (8) what it shares with KRAKADYL · (9) what it does better · (10) what KRAKADYL does that this solution does not document · (11) complementarity · (12) source.

### 9.1 Root-scoped quiescence (Zhu and Wang) — the closest technical competitor

1. Accentrust (Canada), with affiliations at Georgia Tech and UIUC (USA); paper with a reference implementation.
2. arXiv 2609.21284v1, September 18, 2026.
3. Revoking authority in long-running agents when there is delegation and asynchronous execution.
4. A durable root-epoch cut retires authority; each protected sink installs a local fence; cross-endpoint handoffs are tracked as tokens with one SEND and one terminal ACK; a checker returns QUIESCENT, NOT_QUIESCENT or INDETERMINATE. Effect admission is checked at each sink's commitment point.
5. File-backed ledger, hash-linked logs, separately implemented checker. 17 of 17 late-effect cases with the expected outcome.
6. The checker rejected 44 of 44 semantically modified, consistently rehashed traces (authors' test, not external).
7. Not tested with real MCP, A2A, OAuth or cloud providers; guarantees hold only within the declared manifest; opaque endpoints yield INDETERMINATE.
8. Revocation that propagates through the chain; revalidation at the point where the effect becomes irreversible; separate checker; chained records.
9. **Multi-endpoint and asynchronous** model; accounts for in-flight work across domains; allows rebinding shared work to another valid root without inheriting the retired authority; adversarial trace corpus.
10. Evidence verification states and their independence; recovery windows; reorientation after an absence; investigative domain. (NOT_FOUND_IN_REVIEWED_SOURCES in the paper.)
11. High. The fence model and the modified-trace corpus are a direct reference for hardening Level 6 and for future cross-organization federation.
12. [A5]

**Implication:** KRAKADYL must not claim originality in transitive revocation. It should cite this work and position itself as an application to the investigative domain, with a simpler model (a single store).

### 9.2 Bounded Agents / APC (Muruaga)

1. Independent researcher; country not stated; paper with a Python implementation.
2. arXiv 2608.15888 (2026; exact date not stated in the text).
3. Delegation security in multi-agent systems.
4. Principal chain; scope narrowed by intersection at each hop; delegation budget with six monotone ceilings; prohibitions on pairs and k-tuples of actions against session history; six admissibility conditions outside the model.
5. ~2,500 lines of code and ~3,000 lines of tests; 99 chain scenarios of depth 2 to 8.
6. Evaluation on InjecAgent, ASB and AgentDojo (authors' results): 0% exfiltration on AgentDojo with a compromised model; utility loss of 13.9 points in strict mode.
7. Synthetic benchmarks; cross-session attacks not covered; theorems not machine-checked; adaptive attacks designed by the author himself.
8. Subset attenuation at each hop; decision outside the model; fail-closed.
9. Prohibitions on **composition** of individually permitted actions; monotone blast-radius budgets; evaluation on public benchmarks.
10. Revocation of an ancestor **after** derivation (the paper does not treat revocation as its own topic); evidence verification states; recovery windows; reorientation.
11. High: composition control is a natural extension of KRAKADYL's `check_mandate`.
12. [A2]

### 9.3 AgentBound (Kaul, Lan, Gupta)

1. eBay Inc. and an independent researcher; country not stated; framework described in a paper.
2. arXiv 2606.30970 (2026).
3. Behavioral governance between authorization and execution.
4. Three authorities (delegation, owner-signed constitution, site contract) combined by a conservative algebra; governance receipts with two-phase signing; append-only ledger; independent verification that replays the decision.
5. Design and benchmark defined; **no empirical results** ("will be reported in a future release").
6. None.
7. Prompt injection out of scope; depends on complete mediation and a trusted base.
8. Deterministic decision before executing; verifiable receipts.
9. Its verification design aims to reconstruct the policy state and replay the decision: exactly what KRAKADYL does not yet do (KL-002).
10. Executable, tested implementation; hash chaining between receipts (the paper does not describe it); evidence states; delegation with demonstrated transitive revocation.
11. Medium: AgentBound's receipt format is a reference for the "authority-and-evidence envelope".
12. [A1]

### 9.4 Can Is Not May / Veto / AuthorityBench (Celebi)

1. Plaw, Inc. and Arizona State University (USA); open-source SDK and benchmark. Declared conflict of interest.
2. March 2026.
3. Agents that can call tools they are not authorized to use.
4. Seven-parameter "May" judgment, including call history, before each invocation.
5. SDK and validation service.
6. 7,427 trials; 18.3% unauthorized actions with prompt-only instructions under pressure; the authority model's 0% holds by construction.
7. The authority model is its own oracle; simulated tools.
8. "Can is not may"; decision outside the model.
9. Tool-chaining control with session history.
10. Evidence verification states; delegation; continuity.
11. Medium.
12. [A3]

### 9.5 AuthorizationBench

1. PEACH-Research-Lab (press associates it with Northeastern; not verified in the primary source).
2. arXiv 2610.27548, October 20, 2026.
3. Measuring when an agent completes the task but exceeds the user's authorization.
4. 286 executable tasks derived from documented cases; authorization-aware sandbox.
5. Code released; adapters for OpenHands, the OpenAI Agents SDK and the Claude Agent SDK.
6. Independent replication pending, per the source.
7. It is an agent benchmark, not an investigation benchmark.
8. Separates "completing" from "being authorized".
9. It is a measurement instrument; KRAKADYL has none.
10. A blocking mechanism, not only measurement.
11. High: methodological input for a KRAKADYL benchmark.
12. [A4] (secondary source)

### 9.6 Authorization Propagation in Multi-Agent AI Systems (Tallam)

1. Kamiwaza AI; country not stated; position paper with production cases.
2. arXiv 2605.05440, May 2026.
3. How authorization should propagate between agents.
4. Proposes no architecture; lists seven structural requirements.
5. Three failures from a production platform, including **a delegation reported as successful that never occurred**.
6. None controlled.
7. Three cases from one system.
8. Requirement of explicit, scoped, auditable delegation.
9. Field evidence from production.
10. Implementation.
11. High for the pitch: external evidence that "reported" ≠ "verified" also happens in agents.
12. [A6]

### 9.7 BROODS (Das and Bhattacharya)

1. Poster at the AgenticOS workshop, NeurIPS 2026.
2. 2026.
3. Do behavioral bounds hold when an agent delegates?
4. Eleven probes across eight frameworks, L0–L4 scale.
5. In OpenAI Agents with `max_turns=5`, a delegation via `as_tool()` produced 55 model calls.
6. —
7. Workshop; not all frameworks named on the page.
8. The question of whether a bound survives delegation.
9. Cross-framework measurement.
10. Authority bounds that compose by construction along the mandate chain.
11. High: KRAKADYL could be subjected to the applicable probes.
12. [A7]

### 9.8 Meta Muse and Sentinel

1. Meta (USA); consumer product.
2. Launched September 8, 2026.
3. Personal agent that acts across third-party apps.
4. Dedicated VM; a separate Sentinel agent approves outbound access and asks the user; credentials the agent uses without seeing; approval before sending emails or paying; audit trail.
5. Deployed product.
6. Incidents reported by third parties in September 2026, some disputed [A9].
7. Approval scope bounded by design ("not asking about everything"); primary sources consulted do not detail Sentinel's determinism.
8. Separation between the agent and the approver.
9. Scale, credential isolation, integration with real services.
10. Evidence verification states; delegation between people with transitive revocation; recovery windows.
11. KRAKADYL uses Muse Spark as an untrusted proposer; they are different layers.
12. [A8], [A9]

### 9.9 AgentScope 2.0 (Alibaba), DeerFlow 2.0 (ByteDance), GigaCowork (Sber)

| Aspect | AgentScope 2.0 | DeerFlow 2.0 | GigaCowork |
|---|---|---|---|
| Country | China | China | Russia |
| Date | May 2026 (press note) | February 28, 2026 | May 2026 (test access) |
| License | Not consulted | MIT | Commercial (Russian software registry) |
| Permissions | Static and dynamic blocking of shell commands and sensitive files | Not described | Agents run under the employee's identity; per-team workspaces |
| Human approval | Confirmation events | Not described | Configurable human review |
| Audit | Not mentioned | No independent public security audit | Not described in the source |
| Delegation with revocation | NOT_FOUND_IN_REVIEWED_SOURCES | NOT_FOUND | NOT_FOUND |
| Result verification | NOT_FOUND | NOT_FOUND | Human review of the result |
| Source | [A10] secondary | [A11] secondary | [A12] secondary |

What they do better: general execution, sandboxes, skill ecosystems. What they don't document: the link between evidence verification and the authority to act.

### 9.10 LangGraph and Temporal (process continuity)

- **LangGraph:** with a checkpointer, the graph pauses with `interrupt()` and waits **indefinitely** to be resumed; the documentation does not address who may approve, nor the expiry or revocation of a pending approval [A13]. That is: a process can resume days later with an approval whose authority no longer exists, unless the application controls for it. KRAKADYL addresses exactly that case with chain revalidation at execution and with `resume_after_gap`.
- **Temporal:** durable execution with event history and replay (documentation not opened in this session; UNVERIFIED in detail) [A14]. It solves resuming the process, not reorienting the person.

### 9.11 DFIR tools: the instruments KRAKADYL disciplines

| | Velociraptor [D1] | Timesketch [D2] | DFIR-IRIS [D3] | TheHive 5 [D4][D5] | Cellebrite Guardian [D6] | Belkasoft X [D7] |
|---|---|---|---|---|---|---|
| Type | Acquisition and response | Collaborative timelines | Case management | Case management | Evidence management | Forensic analysis |
| License | AGPLv3 | Apache-2.0 | LGPL-3 (secondary) | Commercial with a Community license | Commercial | Commercial |
| Tasks | — | — | Yes (secondary) | Yes: fixed statuses *In progress, Waiting, Cancelled, Completed*; mandatory tasks require at least one log to complete and block case closure | Investigative task management | Window of executed tasks |
| Verification of completion by another person | NOT_FOUND | NOT_FOUND | NOT_FOUND | NOT_FOUND (docs don't describe a verification step distinct from completing) | NOT_FOUND | NOT_FOUND |
| Integrity hashes | Yes (INFERRED from common use; not verified) | — | Yes (secondary) | — | — | MD5/SHA1/SHA256 |
| Audit | — | — | Partial (secondary) | — | Tamper-evident, chain-of-custody report | Task database |
| Delegated authority with revocation | NOT_FOUND | NOT_FOUND | NOT_FOUND | NOT_FOUND | Role permissions | NOT_FOUND |
| Recovery windows | NOT_FOUND | NOT_FOUND | NOT_FOUND | NOT_FOUND | NOT_FOUND | NOT_FOUND |

**Fair reading:** TheHive already prevents closing a case with incomplete mandatory tasks and requires a log to complete them; that is a real mechanism against omissions. What its documentation does not describe is the separation between "completed by whoever did it" and "verified by another person", nor a link between that state and permission to act on evidence. This table doesn't measure who is better: it measures which part of the discipline of use falls outside each tool. The NOT_FOUND rows are what KRAKADYL adds on top, not what they lack as products.

---

## 10. Academic background and standards

| Background | What it contributes | Relationship |
|---|---|---|
| RFC 3227 (2002) [S1] | Order of volatility | Foundation for `RecoveryWindow` |
| NIST SP 800-61 Rev. 3 (April 2025) [S10] | Incident response aligned with CSF 2.0 | Process framework (not opened in this session) |
| IDF guideline, 10th ed. (Japan, 2025) [S2] | Handover records, witnesses, work by more than one person | Practical regulation akin to `TaskResponsibility` |
| Brazil CPP 158-A/F [S5]; Res. 234/2016 and PGN–MinSeg 2023 (Argentina) [S3][S4]; BSA s. 63 (India) [S6]; Supreme Prosecutors' Office regulation (Korea) [S7] | Enforceable chain of custody | Possible compliance maps (§17) |
| Macaroons (2014) [A17]; UCAN [A15]; Biscuit [A16] | Capability attenuation; revocation in UCAN (irreversible, invalidates derivatives) | Direct antecedent of sub-mandates |
| Kassin, Dror and Kukucka (2013) [H8] | Controlled, blind verification | Antecedent of the independence rule, which KRAKADYL applies only by identity |
| Hutchins (1995) [H9]; Risko and Gilbert (2016) [H7] | Distributed cognition; cognitive offloading | Foundation of "the system is the external memory" |
| Parasuraman and Manzey (2010) [H6] | Automation bias | Design risk for the interface itself |
| W3C COGA (2021) [S13] | Processes that don't rely on memory; resuming after interruptions | Verifiable accessibility criteria |
| Transparency logs (Rekor [A18], RFC 9162) | Append-only logs with inclusion proofs | Possible external anchor for receipts |

**Patents:** no patent search was performed in this research. It is a limitation (§18).

---

## 11. Capability and evidence matrix

Capabilities compared (not function names):

- **C1** Distinguishing reported from verified completion, with a different verifier enforced by the system.
- **C2** Refusing to act on unverified evidence even if the file is intact.
- **C3** Revalidating authority and evidence at execution time (not only at approval).
- **C4** Delegation attenuation (the delegatee never has more than the delegator).
- **C5** Transitive revocation that reaches prepared and in-flight actions.
- **C6** Chained verifiable record with an independent verifier.
- **C7** Typed recovery windows that distinguish known deadlines from event-driven closures.
- **C8** Reorientation after an absence: what changed purely through the passage of time.
- **C9** Model output cannot grant authority.
- **C10** Honest closure when something can no longer be resolved.
- **C11** Recording which external tool was run, on what and with what result, as a condition for using its output.

| | C1 | C2 | C3 | C4 | C5 | C6 | C7 | C8 | C9 | C10 | C11 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **KRAKADYL** | CONFIRMED | CONFIRMED | CONFIRMED | CONFIRMED | CONFIRMED (one store) | CONFIRMED (seal and chain; not authority, KL-002) | CONFIRMED | CONFIRMED | CONFIRMED (narrow coverage) | CONFIRMED | Partial (model ready; no real adapters) |
| Root-scoped quiescence [A5] | NOT_FOUND | NOT_FOUND | DOCUMENTED_ONLY (commit point) | INFERRED | DOCUMENTED_ONLY (multi-endpoint) | DOCUMENTED_ONLY | NOT_FOUND | NOT_FOUND | INFERRED | DOCUMENTED_ONLY (INDETERMINATE) | NOT_FOUND |
| Bounded Agents [A2] | NOT_FOUND | NOT_FOUND | DOCUMENTED_ONLY | DOCUMENTED_ONLY | NOT_FOUND | DOCUMENTED_ONLY (evidence sink) | NOT_FOUND | NOT_FOUND | DOCUMENTED_ONLY | DOCUMENTED_ONLY (fail-closed) | NOT_FOUND |
| AgentBound [A1] | NOT_FOUND | NOT_FOUND | DOCUMENTED_ONLY | DOCUMENTED_ONLY | UNVERIFIED | DOCUMENTED_ONLY (no hash chain described) | NOT_FOUND | NOT_FOUND | DOCUMENTED_ONLY | NOT_FOUND | NOT_FOUND |
| Veto [A3] | NOT_FOUND | NOT_FOUND | DOCUMENTED_ONLY | NOT_FOUND | NOT_FOUND | NOT_FOUND | NOT_FOUND | NOT_FOUND | DOCUMENTED_ONLY | NOT_FOUND | NOT_FOUND |
| UCAN [A15] | — | — | INFERRED (at validation) | DOCUMENTED_ONLY | DOCUMENTED_ONLY | NOT_FOUND | NOT_FOUND | NOT_FOUND | — | — | — |
| LangGraph [A13] | NOT_FOUND | NOT_FOUND | NOT_FOUND | NOT_FOUND | NOT_FOUND | NOT_FOUND | NOT_FOUND | Partial (resumes the process) | NOT_FOUND | NOT_FOUND | NOT_FOUND |
| Meta Muse [A8] | NOT_FOUND | NOT_FOUND | UNVERIFIED | NOT_FOUND | Partial (disconnect service) | DOCUMENTED_ONLY (audit trail) | NOT_FOUND | NOT_FOUND | DOCUMENTED_ONLY | NOT_FOUND | NOT_FOUND |
| TheHive 5 [D4] | Partial (mandatory log, no different verifier) | NOT_FOUND | NOT_FOUND | NOT_FOUND | NOT_FOUND | NOT_FOUND | NOT_FOUND | NOT_FOUND | — | NOT_FOUND | Partial (task log) |
| Cellebrite Guardian [D6] | NOT_FOUND | NOT_FOUND | NOT_FOUND | NOT_FOUND | NOT_FOUND | DOCUMENTED_ONLY (tamper-evident audit) | NOT_FOUND | NOT_FOUND | — | NOT_FOUND | Partial (access log) |

"NOT_FOUND" in this table abbreviates NOT_FOUND_IN_REVIEWED_SOURCES. "—" indicates the capability does not apply to that kind of system.

---

## 12. What is solved and what remains open

**Solved by others (KRAKADYL relies on them, doesn't replace them):**

- Acquisition at scale and fleet triage (Velociraptor).
- Collaboration on timelines (Timesketch).
- Case management with tasks and integrations (TheHive, DFIR-IRIS).
- Lab custody and access audit (Cellebrite Guardian, Belkasoft).
- Attenuable capabilities and decentralized verification (UCAN, Biscuit, Macaroons).
- Transparency logs (Rekor).
- Durable process resumption (Temporal, LangGraph).

**Equivalent or superior to KRAKADYL in specific dimensions:**

- Revocation with in-flight effects in distributed systems: [A5] is superior in model and adversarial corpus.
- Prohibition of action compositions: [A2] and [A3] cover what KRAKADYL does not.
- Verification that reconstructs the decision: [A1]'s design aims further than KRAKADYL's current verifier (though without an evaluated implementation).

**Still open in the field (not solved by anyone in the reviewed sources):**

- Measuring how many investigations lose value due to coordination and verification failures.
- A standard link between a piece of evidence's verification state and the permission to act on it.
- Representing "closes on an event of unknown timing" as a first-class state in case tools.
- Human reorientation after long absences in investigations (not just process resumption).
- Verification independence beyond identity (blindness to context).

**Still open in KRAKADYL:** KL-001, KL-002, KL-003, KL-004; multi-organization persistence; Level 7 adapters; user studies; benchmark.

---

## 13. KRAKADYL's defensible differentiation

### 13.1 Is any individual guarantee novel?

Not in the reviewed sources. Each has antecedents (§9, §10). Claiming otherwise does not survive a specialist.

### 13.2 Where is the contribution, then?

In the **combination, the application and the investigative experience**:

1. **The verification state of evidence is a condition of authority.** In the reviewed authorization systems, the decision depends on who, what, where and when; in KRAKADYL it additionally depends on whether the evidence the action would use was verified by someone other than whoever reported it. That conjunction was not found documented in any other reviewed system.
2. **Transitive revocation is applied to actions on evidence**, with revalidation at publication time and a receipt whether it executes or is refused.
3. **Temporal uncertainty is typed.** Distinguishing `CONDITIONAL` and `UNKNOWN` from `KNOWN` prevents the urgent-but-undated from sinking to the bottom of a deadline-ordered list.
4. **Reorientation after an absence is a product, not a side effect**: what was lost through the passage of time, separated from what remains open.
5. **Blameless language by construction**: reports describe case states, not people.

### 13.3 Separations KRAKADYL implements (and their state)

| Separation | Implementation | State |
|---|---|---|
| Observed vs. verified evidence | `REPORTED_DONE → MISSING`; executor requires `VERIFIED_DONE` | CONFIRMED |
| Evidence vs. authority | Two separate dimensions in the model | CONFIRMED |
| Model proposal vs. effective permission | `ProposedActionCandidate` validated and then put through `check_mandate`/`check_evidence` | CONFIRMED (bounded adversarial coverage) |
| Preparation vs. execution | `prepare_evidence_package` / `execute_prepared_action` with revalidation | CONFIRMED |
| Reported vs. verified completion | `TaskResponsibility` validator | CONFIRMED |
| Valid vs. revoked delegation | `authority_under_chain` at prepare and at execute | CONFIRMED |
| Recoverable vs. irreversible uncertainty | `RecoveryWindow` + `unresolvable` + honest closure | CONFIRMED |
| Unknown vs. invented result | `UNKNOWN` states; no single priority fabricated on a tie | CONFIRMED in `next_move`; INFERRED elsewhere |

### 13.4 Defensible differentiation claims

- "KRAKADYL doesn't let evidence reported as preserved be used as if it were verified, and requires someone else to verify it."
- "Revoking an authority revokes everything delegated below it, including what was prepared and not executed."
- "It distinguishes a known deadline from a window that closes on an undated event."
- "When you come back after days, it shows what was lost purely through the passage of time."
- "The model proposes; it never authorizes."
- "Every decision, executed or refused, leaves a chained receipt whose integrity is checked by a verifier independent of the core." (Until the R-3 exporter exists, don't say "anyone can verify".)

### 13.5 Claims NOT to use

See §16.8.

---

## 14. Value proposition

### 14.1 Elements

- **Core problem:** in an investigation under pressure, the difference between "someone said they did it" and "someone else checked it's done" gets lost in handoffs, interruptions and absences. When it is discovered, the evidence may no longer exist and the authority to obtain it may have lapsed.
- **Why it is urgent:** evidence windows are short and decided by a third party (CloudTrail's default 90 days [S11]; 30 days of available logs in Storm-0558 [I4]); AI agents are starting to execute actions in investigations and exceed authorization in benchmarks [A4][A3]; multi-agent frameworks lose their bounds when delegating [A7].
- **Why current solutions are not always enough:** case tools record tasks but do not condition actions on independent verification (§9.11); agent authorization layers do not model evidence verification state (§11); process resumption does not reorient people (§9.10).
- **Initial audience:** small incident response teams and DFIR consultancies; digital-evidence units in public prosecutors' offices (for example, those applying the PGN–MinSeg protocol in Argentina [S4]); investigative journalism teams; teams investigating AI safety incidents.
- **Potential buyers:** incident response leads, forensic lab managers, compliance functions. (No market-size estimate: no reliable source was found to compute one.)
- **Benefits verifiable today:** reproducible blocking of actions on unverified evidence; demonstrable transitive revocation; receipts verifiable in their integrity; reorientation report after an absence.
- **Benefits still to demonstrate:** fewer omissions, fewer handoff errors, less time to resume a case (§17).
- **Technical differentiation:** §13.2.
- **Organizational differentiation:** blameless language; verification independence by design; accessible to people working with fatigue, interruptions or a different executive profile.
- **Costs of not solving the problem:** §5 (unexplainable incidents, worst-case disclosure, collapsed trials, misidentifications). These are costs of the cited cases, not estimates of what KRAKADYL would save.
- **Limits:** does not acquire evidence by itself (except the Level 3 mediated flow); does not decide what the evidence proves; does not detect confirmation bias; does not yet scale across organizations; receipts do not prove authority on their own.
- **Relationship to the tools:** KRAKADYL doesn't improve acquisition or analysis; it improves the conditions under which they are reached (on time, with valid authority, without pending tasks, without unverified assumptions).
- **Complementarity with VIGÍA and external tools:** KRAKADYL prepares the case; VIGÍA or another engine decides what the evidence supports (including a legitimate `ABSTAIN`); Velociraptor/SIFT acquire and examine; i2 Analyst's Notebook analyzes links. No Level 7 integration exists yet.

### 14.2 Foreseeable commercial objections

| Objection | Supported answer |
|---|---|
| "We already have TheHive/IRIS" | Good: KRAKADYL doesn't replace them. What they don't document is verification by another person and its effect on permission to act (§9.11). An adapter can mirror their tasks |
| "It adds friction" | Verifying does cost something. The I-PASS evidence suggests structuring handoffs did not worsen residents' workflow [H2]; for DFIR it is not measured |
| "Who verifies the verifier?" | Independence is of authenticated identity, not collusion resistance. Two people in agreement can mark `VERIFIED_DONE`. This must be said |
| "Is it admissible in court?" | Not evaluated. It can be mapped to chain-of-custody requirements (§17, R-10), but there is no case law on KRAKADYL |
| "It doesn't scale" | Correct today (SQLite, one node) |

### 14.3 Positioning and taglines

**Does "external memory and mandate guardian" communicate well?** It is precise for someone who already understands the problem, but has two weaknesses before a non-specialist jury: "mandate" is legal jargon and "external memory" sounds like a note-taking app. Also, the differentiating core — that reported doesn't pass as verified — is not in the phrase.

| # | Tagline | Support | Risk |
|---|---|---|---|
| A | **"Reported is not verified. KRAKADYL doesn't let the case confuse the two, or let revoked authority keep acting."** | Code (validator, `authority_under_chain`, demos 001 and 003); Liam Allan [I3], Continental 2574 [I1]; agent evidence [A6] | Long; a short version helps: "Reported is not verified." |
| B | "External memory and mandate guardian for investigations under pressure." | Code and cognitive-offloading literature [H7][H9] | Abstract; doesn't say which failure it prevents |
| C | "Before the evidence disappears: what's missing, who has it, and whether you can still act." | `next_move`, `RecoveryWindow`, `resume_after_gap`; RFC 3227 [S1]; Storm-0558 [I4] | May suggest KRAKADYL acquires the evidence, which it does not except in the Level 3 flow |

**Recommendation:** A as the headline, with B as a descriptive subtitle in the documentation. A is the one with the most direct support in code, real cases and external evidence about agents.

---

## 15. Market and potential users

- **Incident response and SOCs:** 79% of surveyed SOCs operate 24/7 and 69% report metrics manually [H11]; shift handoffs are structural. No data on how many use case tools with independent verification.
- **Public prosecutors and technical police:** the frameworks of Argentina, Brazil, India and Korea already require records of who hands over and who receives (§4.2). These users need demonstrable compliance more than agents.
- **Small DFIR consultancies:** license-sensitive; KRAKADYL is Apache-2.0.
- **Investigative journalism:** analogous verification and handoff problems; no legal custody requirements in most cases.
- **AI safety incident investigation:** the "reported delegation that didn't happen" pattern already appears in production [A6].

No market size is estimated. No reliable source was found to do so without fabricating figures.

---

## 16. Supported material for the demo and slides — "Why KRAKADYL matters"

### 16.1 Five findings on the size of the problem

1. **Handoffs fail asymmetrically:** receivers judged 37% of handoffs unsuccessful; senders, 21% [H1].
2. **Structuring handoffs reduces measurable harm:** −23% medical errors and −30% preventable adverse events with I-PASS [H2].
3. **A third party decides the evidence window:** CloudTrail's default 90 days of history [S11]; in Storm-0558 it could not be known how the key was stolen because there were no logs [I4].
4. **Attackers stay longer than systems remember:** 393-day average dwell time in BRICKSTORM versus a standard 90-day retention that prevented finding the initial vector [I8].
5. **Agents exceed their authorization and lose bounds when delegating:** 19.2% of trajectories with out-of-authorization actions in AuthorizationBench [A4]; in one framework, a delegation produced 55 calls under a declared limit of 5 [A7].

### 16.2 Five data points or cases for slides

| # | Slide | Source |
|---|---|---|
| 1 | "He believed he had reviewed the 57,000 messages." Liam Allan, 2017 | [I3] |
| 2 | "47 screws and a shift change." Continental Express 2574, 1991 | [I1] |
| 3 | "No logs, no answer." Storm-0558, 2023 | [I4] |
| 4 | "A delegation reported as successful that never happened." Production AI platform, 2026 | [A6] |
| 5 | "37% vs. 21%: whoever hands over thinks they transmitted more." Joint Commission | [H1] |

### 16.2b Eight failures, eight data points (one slide per failure or one table)

| Failure | Data point for the slide | Source |
|---|---|---|
| Late to the window | Sepsis: +7.6% mortality per hour of delay | [H14] |
| Reported ≠ verified | Knight Capital: 1 of 8 servers not updated, no review; more than USD 460M in ~45 min | [I10] |
| Handoff | Texas City: no shift-turnover communication requirement; 15 dead | [I11] |
| Unlinked information | Medication-history errors at admission in 10–67% of patients | [H15] |
| Changed state or authority | Surgical time-outs that became ritual; 31 wrong-site surgeries in Minnesota in 2010 | [H17] |
| Interruptions | Reducing them with vests: −15 per 100, only 48% staff support | [H16] |
| Unverified assumptions | Mars Climate Orbiter: "the spacecraft is like the previous one" | [I12] |
| Window without authority | RAM dump: machine on + specialist + court order | [S4] |

### 16.3 Three fair comparisons

1. **TheHive 5:** prevents closing a case with incomplete mandatory tasks; does not document verification by another person or a link to permission to act [D4]. *KRAKADYL doesn't replace case management; it adds the missing rule.*
2. **Root-scoped quiescence [A5]:** more rigorous, multi-endpoint revocation than KRAKADYL's. *KRAKADYL applies it to evidence and combines it with verification and reorientation.*
3. **LangGraph [A13]:** a paused flow waits indefinitely and the documentation does not address approval expiry. *KRAKADYL revalidates the authority chain at execution and shows what lapsed during the pause.*

### 16.4 30-second core argument

> Investigations don't always fail for lack of talent. They fail when someone said they preserved the evidence, someone else took it as done, and nobody checked — and by the time it surfaces, the evidence is gone. It happened with 57,000 messages in a London trial. It happened with a shift handoff on an airplane. KRAKADYL makes sure reported never passes as verified, that revoked authority doesn't keep acting, and that when you come back after days you know what was lost. The AI model proposes; it never authorizes.

### 16.5 90-second narrative

> In 2017, a London trial collapsed because an officer believed he had reviewed the more than 57,000 messages on a phone, and the prosecution believed him without asking. Nobody lied. Reported was treated as verified. In 1991, an airplane lost the leading edge of a stabilizer because one shift removed 47 screws and the next one didn't know. In 2023, Microsoft couldn't tell how a key was stolen because the logs no longer existed.
>
> Three disciplines, one pattern: information is lost in handoffs, in interruptions and in time.
>
> KRAKADYL is the layer that comes before the analysis. It separates four things that get mixed up in practice: assigned, accepted, reported and verified. It won't let something that was only reported be used as evidence, and it requires someone else to verify it. When someone delegates authority and the root is revoked, everything below is revoked, including what was already prepared. When you come back after four days, it tells you what closed while you were away.
>
> It uses Muse Spark to propose actions, but the proposal goes through the same deterministic checks as any other. Every decision, approved or refused, leaves a chained receipt that an independent verifier can check.
>
> It doesn't replace TheHive, Velociraptor or the investigator. It makes them reach the decision with the case actually ready.

### 16.6 Three-minute narrative (structure with evidence)

1. **(0:00–0:30) The pattern.** Liam Allan [I3] and Continental 2574 [I1]. One line: "nobody lied; reported passed as verified".
2. **(0:30–0:50) Why it isn't a lack of talent.** 2.8-second interruptions double errors [H4]; 17–19 hours of fatigue equals 0.05% BAC [H5]; automation bias also affects experts [H6]. KRAKADYL was designed for people who work like this, which is almost everyone in this field.
3. **(0:50–1:10) Why now.** Short windows owned by others [S11][I8]; agents that exceed authorization [A4]; delegations that don't compose [A7].
4. **(1:10–2:20) Live demo** (§16.7): evidence reported but not verified → `forbidden`; root revocation → the junior loses authority; resumption after 4 days.
5. **(2:20–2:40) What it isn't.** It doesn't decide what the evidence proves (that's VIGÍA or the investigator); it doesn't replace DFIR tools; it isn't the first in transitive revocation — citing [A5] by name shows rigor.
6. **(2:40–3:00) What's next.** Handoff benchmark, study with investigators, open adapters. Close with tagline A.

### 16.7 Three demonstration scenarios

All three use **only existing functionality** on `main` and are reproducible with the commands shown. They are **synthetic**.

**Scenario 1 — Volatile evidence about to be lost.**
- *For the jury:* "There are four sources. One is already lost. Another is lost if someone powers off a machine, and we don't know when."
- *Visible consequence:* the lost source appears as closed, not hidden; the event-dependent source appears on conditional watch, not at the bottom of the list.
- *Technical proof:* `uv run python demo/run_case_004_gap.py` (lines "recovery windows closed while away" and "on conditional/unknown watch"); `tests/test_continuity.py`.
- *Do not invent:* KRAKADYL does not detect on its own that a machine is about to be powered off. A person records the condition.

**Scenario 2 — A task reported done and not verified.**
- *For the jury:* "The file is intact. Someone said they preserved it. Nobody else checked."
- *Visible consequence:* evidence packaging is refused with the explicit reason, and a receipt of the refusal is issued.
- *Technical proof:* `uv run python demo/run_case_001.py`, section "4. Reported done, never verified". Showing the independent verifier requires building the `chain.json` first (the demos don't produce it; see §3.2); until an exporter exists (R-3), it is better to show the verifier accepting an intact chain and rejecting the same chain with an altered verdict, and to say so.
- *Do not invent:* KRAKADYL doesn't judge whether the verification was good; it only requires that it exists and was done by another identity.

**Scenario 3 — Delegated authority that stops being valid, and resuming after an interruption.**
- *For the jury:* "The senior delegates to a lead, who delegates to a junior. The investigation is reassigned and the senior's mandate is revoked. Can the junior continue?"
- *Visible consequence:* the junior is denied even though their sub-mandate was never touched; coming back days later, the report shows their delegation lapsed.
- *Technical proof:* `uv run python demo/run_case_003_level6.py` (steps 4 and 6); `uv run python demo/run_case_004_gap.py`; revocation between prepare and execute: RT-L6-2 in `docs/red-team-level6-delegation-2026-11-01.md` and `tools/redteam_level6_probes.py`.
- *Do not invent:* revocation is within a single store; there is no cross-organization federation.

### 16.8 Claims to avoid

| Don't say | Why | Say instead |
|---|---|---|
| "The first / the only / nobody does this" | Every guarantee has antecedents (§9) | "We did not find this combination documented in the systems we reviewed" |
| "Prevents evidence loss" | It doesn't acquire by itself | "Makes visible what can be lost and when" |
| "Receipts that prove the action was authorized" | KL-002 | "Receipts whose integrity and order are checked by an independent verifier" |
| "80% of serious errors are due to handoff failures" | Not in the Joint Commission alert consulted [H1] | Use 37% vs. 21% [H1] or I-PASS [H2] |
| "KRAKADYL would have prevented case X" | Undemonstrable counterfactual | "Mechanism X targets that pattern" |
| "Tested with investigators" | No user studies | "Tested with tests and in-house red team" |
| "Integrated with Velociraptor / i2 / VIGÍA" | Level 7 not implemented | "Designed to integrate; adapters on the plan" |
| "IBM i2" | i2 belongs to Harris (i2 Group) [D10] | "i2 Analyst's Notebook" |
| "Resistant to prompt injection" | KL-003; bounded coverage | "Model output has no path to authority" |
| "Reduces avoidable ABSTAINs" | Not measured | "It is designed to reduce…; we will measure it like this: …" |
| "Sentinel is a deterministic authority" | Not confirmed in primary sources | "Sentinel approves Muse's outbound access" [A8] |
| Any percentage on how many investigations fail due to coordination | The figure doesn't exist | "There's no global figure; this is what the cases show" |
| Presenting the Muse/home-address case as established fact | Disputed [A9] | Omit it or say "disputed" |

### 16.9 Hard jury questions

1. **"Isn't this TheHive with more states?"** — TheHive requires a log to complete mandatory tasks; it does not document verification by another person or that this state conditions acting on evidence [D4]. KRAKADYL can live alongside TheHive.
2. **"What stops two people from agreeing and marking it verified?"** — Nothing technical. Independence is of authenticated identity, not collusion resistance. What remains is an immutable record of who verified what and how.
3. **"What if the evidence never enters KRAKADYL?"** — Then KRAKADYL doesn't see it. It is a system of record, not of discovery; that's why the Level 7 adapters matter.
4. **"Did you measure anything with people?"** — No. It is on the plan (§17, R-8 and R-9), with metrics defined before measuring.
5. **"Why use an LLM at all?"** — To propose the next step from the real case state. The proposal has no path to authority: it goes through the same checks as a hand-written action.
6. **"Zhu and Wang already solved revocation with in-flight effects."** — Yes, in a more general model. KRAKADYL applies it to actions on evidence and combines it with verification and reorientation. We cite them.
7. **"Does it hold up in court?"** — Not evaluated. It records the fields several frameworks require (who hands over, who receives, when, hash), but admissibility depends on each jurisdiction.
8. **"Does it scale?"** — Today it's one node with SQLite. Enough for a team; not for several organizations.
9. **"Does the receipt verifier prove authority?"** — No: it proves seal and chaining. Authority requires the linked case state (KL-002).
10. **"Doesn't this add work for already overloaded people?"** — Verifying adds a step. In exchange, nobody has to rebuild the case from memory when they come back. Whether the balance is positive is an empirical question we haven't answered yet.
11. **"Is something built in days viable?"** — The git history is public: 205 commits between 10/27 and 11/2, tests from day one and audits that corrected overclaims. What's built is complete and tested; what's missing is declared (§3.2, §17).

### 16.10 Pitch traceability matrix

| Pitch claim | Evidence | Type | State |
|---|---|---|---|
| Reported never passes as verified | `continuity.evidence_state_from_requirement`; demo 001 run 4 | Code | CONFIRMED |
| Verification by another identity | `TaskResponsibility` validator; `tests/test_model_invariants.py` | Code | CONFIRMED |
| Revoking the root revokes the chain, even between prepare and execute | demo 003; RT-L6-2 | Code / in-house red team | CONFIRMED / DOCUMENTED_ONLY (live) |
| On return, reports what was lost to time | demo 004 | Code | CONFIRMED |
| The model proposes, never authorizes | `ProposedActionCandidate` → `decide()` flow; `test_policy.py` | Code | CONFIRMED (narrow coverage) |
| Receipts checkable by an independent verifier | `tools/verify_receipt.py`; cross-check against `krakadyl.core.receipt.seal` in this research | Code | CONFIRMED (seal and chain, given the payload; exporter missing, §3.2) |
| 57,000 messages | [I3] | Press on an official review | Secondary |
| 47 screws, 14 dead | [I1] | Institutional (FAA) | Primary |
| No logs, no answer (Storm-0558) | [I4] | Press on the CSRB report | Secondary |
| 37% vs. 21% | [H1] | Institutional | Primary |
| −23% / −30% I-PASS | [H2] | Peer-reviewed (via press release) | Indirect primary |
| 19.2% AuthorizationBench | [A4] | Press on a preprint | Secondary |
| 55 calls under a limit of 5 | [A7] | Workshop | Primary |
| Reported delegation that didn't happen | [A6] | Preprint | Primary |
| CloudTrail 90 days | [S11] | Vendor documentation | Primary |
| BRICKSTORM 393 days / 90-day retention | [I8] | Security-vendor report | Primary (vendor) |

---

## 17. Post-hackathon recommendations

Prioritized by what can be built and validated without commercial licenses. None corresponds to pending Level 6 functionality: the integration ones are Level 7.

| ID | Recommendation | Expected benefit | Difficulty | Dependencies | Risks | Acceptance criterion |
|---|---|---|---|---|---|---|
| R-1 | Update `docs/levels.md` (Level 6 interface already built), nuance the README on receipts (KL-002), fix "composition closure", add [A5], [A6] and [A7] to prior art | Coherence before the jury and specialists | Low | None | None | No contradiction between docs and code; prior art includes [A5] |
| R-2 | Versioned authority-and-evidence envelope (closing KL-002), inspired by [A1]'s receipt design | The offline verifier can reconstruct and replay the decision | Medium | Stable canonical schema | Receipt size growth; exposure of sensitive data in the envelope | A verifier with no dependency on `krakadyl.core` reproduces `decide()` for 100% of demo receipts and rejects altered envelopes |
| R-3 | Add a `chain.json` exporter (per case, via API or `tools/`) and expand the receipt verifier's suite (2 tests today, both failure cases): an acceptance test on real chains sealed by the core and a corpus of modified and re-sealed chains, in the style of [A5] | Make "anyone can verify" literally true for a real case | Low | — | The exporter leaking sensitive manifest data | The verifier accepts 100% of chains exported from the demo cases and rejects 100% of a corpus of ≥ 40 consistently rehashed semantic mutations |
| R-4 | Action-composition control in `check_mandate` (prohibited pairs/k-tuples over the case history), following [A2] and [A3] | Close the chaining-attack class | Medium | Action taxonomy | False positives | Composition-exfiltration scenarios from [A3]'s corpus applicable to the domain are blocked; no regressions in the 451 tests |
| R-5 | Read adapter for DFIR-IRIS (LGPL-3) and then TheHive (Community license) that mirrors tasks as `REPORTED_DONE` until a second identity verifies | Adoption without replacing tools | Medium | Each product's API | API changes; TheHive licensing | A task completed in IRIS appears as `REPORTED_DONE` in KRAKADYL and blocks an action until verified |
| R-6 | Velociraptor adapter (AGPLv3): collection results with hashes → `Observation` + `EvidenceCustody` | Real observation source | Medium | Velociraptor API; care with AGPL if distributing derived code | License; volume | A real collection is registered with hash and provenance; the executor includes it only after verification |
| R-7 | Export activity and receipts to Timesketch (Apache-2.0) | Chronological view for analysts | Low | — | — | A demo case is visualized in Timesketch with each receipt as an event |
| R-8 | Coordination and continuity benchmark: synthetic scenarios of handoff, interruption, revocation and closing windows, with preregistered metrics (proportion of type-B inconclusive outcomes per §4.0, avoidable omissions, handoff errors, time to resume, out-of-authority actions) | First in-house data on the central hypothesis | Medium-high | Scenario design; inspired by [A4] and [A7] | Benchmark fitted to KRAKADYL | Public preregistration before running; comparison against a baseline (task manager without verification) |
| R-9 | Usability study with real investigators (within-subjects, with controlled interruptions as in [H4]), assessed against [S13] criteria; include neurodivergent participants without using diagnosis as a predictor | Evidence of human impact | High | Ethics, recruitment | Small sample; Hawthorne effect | Metrics defined beforehand: hits identifying unverified items, time to resume, subjective load (e.g., NASA-TLX) |
| R-10 | Compliance maps: KRAKADYL events ↔ Art. 158-B stages (Brazil), Res. 234/2016 route sheet (Argentina), BSA s. 63 certificate (India), IDF guideline (Japan) | Usefulness for public prosecutors | Medium | Legal advice | Misinterpretation | Review by a legal professional from each jurisdiction |
| R-11 | Export sub-mandates as UCAN or Biscuit capabilities for cross-organization use; adopt [A5]'s fence model for distributed revocation | Federation | High | Choose format; key management | Complexity; Biscuit revocation semantics require external state [A16] | A revocation in organization A invalidates an action prepared in organization B before its commit point |
| R-12 | Anchor receipt-chain heads in a transparency log (Rekor or equivalent) | External evidence that the chain was not rewritten | Medium | Decide what data is published | Metadata leakage | Verifiable inclusion proof for each anchored head |
| R-13 | VIGÍA integration: explicit contract to hand over a "ready to evaluate" case and receive `ABSTAIN` with a reason | Close the loop that motivates the project | Medium | Both projects are the author's | Coupling | An `ABSTAIN` for missing evidence becomes an open requirement with a window |
| R-14 | i2 Analyst's Notebook: export of entities and links (the product's import format) | Interoperability with intelligence analysts | Medium | Commercial i2 license to test | License | An exported case imports without loss of provenance |
| R-15 | Independent third-party audit of the authority core | Credibility | Variable | Funding or community | — | Public report with findings and their closure |

Costs: not estimated in money except where they depend on commercial licenses (R-5 TheHive paid tiers, R-14 i2), whose price was not consulted.

---

## 18. Research limitations

- **The local working tree was not examined.** ES/EN internationalization and any uncommitted change remain unverified.
- **The interface was not tested in a browser**, and neither Muse, Laya nor SAM were run live, nor the live red-team probes.
- **Several sources are secondary:** AuthorizationBench, AgentScope, DeerFlow, GigaCowork, IBM 2026, DFIR-IRIS, the Korean regulation, the 2019 Chinese rules. Each case is marked.
- **Inaccessible primary sources:** `arxiv.org/abs` pages (PDFs were used), PubMed and PMC (verification blocks), the translation of the Chinese rules, the WRAL note on i2.
- **No searches in Hindi or Hebrew**, and coverage of Japan, Korea and India was limited to regulatory frameworks.
- **No patent search was performed.**
- **SOAR and playbook platforms were not researched** (for example Cortex XSOAR, Tines or Shuffle), which are the closest in the discipline-of-use function. That is the next search to do.
- **Full texts of paywalled papers were not consulted** (NEJM, Human Factors); official abstracts and institutional press releases were used.
- **Sources not opened in this session and cited bibliographically only:** Macaroons [A17], Rekor [A18], Temporal [A14], Hutchins [H9], NIST SP 800-61r3 [S10].
- **Search bias:** English results are more abundant; absence of results in other languages does not prove absence of solutions.
- **One session, one researcher (an AI model).** Claims should be reviewed by a person before public use.

---

## 19. Corrected or discarded claims

| # | What seemed true | What was found | Decision |
|---|---|---|---|
| 1 | The Level 6 interface is not built (per `docs/levels.md`) | It is on `main` (`93be916`, `635c80b`) and builds | Stale document; fix (R-1) |
| 2 | "80% of serious medical errors involve handoff communication failures" (widely cited figure attributed to the Joint Commission) | Not in the Alert 58 consulted [H1] | **Discarded** for the pitch |
| 3 | I-PASS reduced preventable adverse events by 23% (PSNet summary) | The institutional release and the Joint Commission state −23% errors and −30% preventable adverse events [H2][H1] | The institutional version is used |
| 4 | "IBM i2 Analyst's Notebook" | IBM sold i2 to Harris; today it is i2 Group [D10] | Correct the name |
| 5 | Biscuit supports revocation | Its documentation says revocation requires external state [A16] | Nuanced |
| 6 | Sentinel is a deterministic authority | Not confirmed in the primary announcement [A8] | UNVERIFIED |
| 7 | KRAKADYL's "composition closure" = Bounded Agents' | They are different concepts (§3.3) | Change terminology |
| 8 | Equifax's certificate had been expired "19 months" (circulating figure) | GAO says about 10 months before the breach [I5] | GAO is used; the other figure was not verified |
| 9 | In Mayfield the verification was not blind | The OIG summary consulted does not state this [I6] | Not claimed |
| 10 | No academic work addresses transitive revocation with in-flight effects for agents | [A5] exists, and is more general | **Unfavorable finding**; cite |
| 11 | AgentBound hash-chains its receipts | The paper does not describe chaining [A1] | Nuanced |
| 12 | There would be a global statistic on investigations failing due to coordination | None was found | Stated explicitly (§6) |
| 13 | Westbrook: "12.7%" as the only number | 12.1% for procedural failures and 12.7% for clinical errors [H3] | Both are reported |
| 14 | A case's receipts can be passed straight to the independent verifier | The sealed payload is not persisted and there is no `chain.json` exporter; the verifier does agree with the core's sealing when given the payload (checked in this research) | Nuanced in §3.2 and §16.7; R-3 |
| 15 | (First version's framing) KRAKADYL compared with Velociraptor, TheHive or Cellebrite as a competitor on scale | KRAKADYL is the prior discipline that makes those tools be used correctly; its metric is avoiding avoidable downstream `ABSTAIN`s (author's correction, 2026-11-02) | Rewrote §1, §8, §9.11, §11 and §12 |

---

## 20. Complete bibliography

Consultation date for all sources: **2026-11-02**. "Vendor" = vendor documentation; "Sec." = secondary source.

### Repository

- **[R1]** annatchijova, *KRAKADYL*, commit `1d56d66`, 2026-11-02. https://github.com/annatchijova/krakadyl/tree/1d56d66fdbad18396626f49f0b51770133695678
- **[R2]** *docs/levels.md*, same commit. https://github.com/annatchijova/krakadyl/blob/1d56d66fdbad18396626f49f0b51770133695678/docs/levels.md
- **[R3]** *docs/known-limitations.md*, same commit. https://github.com/annatchijova/krakadyl/blob/1d56d66fdbad18396626f49f0b51770133695678/docs/known-limitations.md
- **[R4]** *docs/red-team-level6-delegation-2026-11-01.md*, same commit. https://github.com/annatchijova/krakadyl/blob/1d56d66fdbad18396626f49f0b51770133695678/docs/red-team-level6-delegation-2026-11-01.md

- **[V1]** annatchijova, *VIGÍA* (vigia-intent-analysis), README.md, section "Architecture" (LLM isolation). https://github.com/annatchijova/vigia-intent-analysis

### Authorization, agents and continuity

- **[A1]** Kaul, A.; Lan, Q. (eBay Inc.); Gupta, P. *Behavioral Governance for Autonomous AI Agents: The AgentBound Framework*. arXiv 2606.30970, 2026. https://arxiv.org/pdf/2606.30970
- **[A2]** Muruaga, X. *Bounded Agents: Delegation Security for Multi-Agent AI Systems*. arXiv 2608.15888, 2026. https://arxiv.org/pdf/2608.15888
- **[A3]** Celebi, Y. (Plaw, Inc.; Arizona State University). *Can Is Not May: Authority Models for Governable AI Agents*. March 2026. https://yazzone.pages.dev/can-is-not-may.pdf
- **[A4]** LDS Team. *AuthorizationBench study finds LLM agents exceeded user authorization in 19.2% of tested trajectories*. 2026-10-21 (on arXiv 2610.27548). Sec. https://letsdatascience.com/news/authorizationbench-benchmark-finds-llm-agents-exceed-user-au-cb3b903c
- **[A5]** Zhu, G.; Wang, C. (Accentrust). *Authorization Revocation for Long-Running AI Agents: Root-Scoped Quiescence under Delegation and Asynchronous Execution*. arXiv 2609.21284v1, 2026-09-18. https://arxiv.org/pdf/2609.21284
- **[A6]** Tallam, K. (Kamiwaza AI). *Authorization Propagation in Multi-Agent AI Systems: Identity Governance as Infrastructure*. arXiv 2605.05440v1, 2026-05-06. https://arxiv.org/pdf/2605.05440
- **[A7]** Das, S.; Bhattacharya, S. *Bounds That Do Not Compose: Measuring OS-Level Containment in Eight Agent Frameworks*. AgenticOS workshop, NeurIPS 2026. https://neurips.cc/virtual/2026/166794
- **[A8]** Meta. *Introducing Muse*. 2026-09-08 (modified 2026-09-30). Vendor. https://about.fb.com/news/2026/09/introducing-muse
- **[A9]** Xenospectrum. *Meta Muse address approval scope*. 2026-09-29. Sec. https://xenospectrum.com/en/meta-muse-address-approval-scope/
- **[A10]** KuCoin/MarsBit. *Alibaba Launches AgentScope 2.0…*. 2026-05-26. Sec. https://www.kucoin.com/news/flash/alibaba-launches-agentscope-2-0-to-enhance-agent-deployment-security-and-stability
- **[A11]** VentureBeat. *What is DeerFlow and what should enterprises know…*. 2026. Sec. https://venturebeat.com/orchestration/what-is-deerflow-and-what-should-enterprises-know-about-this-new-local-ai
- **[A12]** EastRussia. *Сбер открыл тестовый доступ к платформе GigaCowork…*. 2026-05-21. Sec. https://www.eastrussia.ru/news/sber-otkryl-testovyy-dostup-k-platforme-gigacowork-sisteme-upravleniya-ii-agentami-dlya-vsey-kompani/
- **[A13]** LangChain. *Human-in-the-loop* (LangGraph). Vendor. https://docs.langchain.com/oss/python/langgraph/human-in-the-loop
- **[A14]** Temporal. *Workflow Execution overview*. Vendor. Not opened in this session. https://docs.temporal.io/workflow-execution.md
- **[A15]** UCAN Working Group. *UCAN Specification* v1.0.0. https://github.com/ucan-wg/spec
- **[A16]** *biscuit-auth* 6.0.0, documentation. https://docs.rs/biscuit-auth/latest/biscuit_auth/
- **[A17]** Birgisson, A. et al. *Macaroons: Cookies with Contextual Caveats for Decentralized Authorization in the Cloud*. NDSS 2014. Not opened in this session. https://research.google/pubs/macaroons-cookies-with-contextual-caveats-for-decentralized-authorization-in-the-cloud/
- **[A18]** Sigstore. *Logging overview (Rekor)*. Vendor. Not opened in this session. https://docs.sigstore.dev/logging/overview/

### DFIR and evidence management

- **[D1]** noze. *Velociraptor: DFIR and endpoint monitoring with VQL*. Sec. https://www.noze.it/en/insights/velociraptor-dfir
- **[D2]** Google. *Timesketch* (GitHub). https://github.com/google/timesketch/
- **[D3]** BrightCoding. *IRIS: The Collaborative Incident Response Platform…*. 2026-04-02. Sec. (promotional). https://www.blog.brightcoding.dev/2026/04/02/iris-the-collaborative-incident-response-platform-every-security-team-needs
- **[D4]** StrangeBee. *TheHive 5 — About tasks*. Vendor. https://docs.strangebee.com/thehive/user-guides/analyst-corner/tasks/about-tasks/
- **[D5]** StrangeBee. *TheHive — License*. Vendor. https://docs.strangebee.com/thehive/installation/licenses/license/
- **[D6]** Cellebrite. *Guardian*. Vendor. https://cellebrite.com/en/guardian
- **[D7]** Belkasoft. *Preserving chain of custody*. Vendor. https://belkasoft.com/preserving_chain_of_custody
- **[D8]** 平安证券 (Ping An Securities). Report on 美亚柏科 (300188). 2019-06-03. https://img3.gelonghui.com/pdf/f6b38-95fcfed4-3a21-431b-90f8-04f8198f500c.pdf
- **[D9]** Help Net Security. *Detego DFIR Platform…*. 2025-11-27. Sec. https://www.helpnetsecurity.com/2025/11/27/detego-case-manager-dfir/
- **[D10]** TyN Magazine. *Harris acquires i2 product portfolio from IBM*. Sec. https://tynmagazine.com/harris-acquires-i2-product-portfolio-from-ibm/

### Standards and regulation

- **[S1]** Brezinski, D.; Killalea, T. *RFC 3227 — Guidelines for Evidence Collection and Archiving*. IETF, 2002. https://www.rfc-editor.org/rfc/rfc3227
- **[S2]** デジタル・フォレンジック研究会 (Institute of Digital Forensics). *証拠保全ガイドライン 第10版* (Evidence Preservation Guideline, 10th ed.). 2025-03-15. https://digitalforensic.jp/wp-content/uploads/2025/03/shokohozenGL10.pdf
- **[S3]** Ministerio de Seguridad (Argentina). *Resolución 234/2016*. Official Gazette 2016-06-14. https://www.argentina.gob.ar/normativa/nacional/norma-262787/texto
- **[S4]** Procuración General de la Nación (Argentina). PGN resolution approving the *Protocolo para la identificación, recolección, preservación, procesamiento y presentación de evidencia digital*. 2023-04-18. https://www.mpf.gob.ar/resoluciones/PGN/2023/PGN-0019-2023-001.pdf
- **[S5]** Brazil, CPP Arts. 158-A to 158-F (Lei 13.964/2019), reproduced by Migalhas. https://www.migalhas.com.br/arquivos/2020/3/CA87D1CAE19D01_LeiAnticrime%E2%80%93CadeiadeCustodiae.pdf
- **[S6]** LiveLaw. *Supreme Court Rejects Challenge To S.63(4) BSA…* (*Pune Bar Association v Union of India*, 2026-05-22). 2026-05-28. Sec. https://www.livelaw.in/top-stories/supreme-court-rejects-challenge-to-s634-bsa-mandating-hash-value-disclosure-for-electronic-evidence-535950
- **[S7]** LawWin. Summary of 대검찰청예규 제1449호 (Supreme Prosecutors' Office Regulation No. 1449). 2025-08-05. Sec. https://www.lawwin.co.kr/suwon/knowledgedetail?index=7303
- **[S8]** Gerasimov, N. *О проблеме изъятия электронных носителей информации в рамках следственных действий* (On the problem of seizing electronic media during investigative actions). Advokatskaya Gazeta, 2019-04-24. https://www.advgazeta.ru/mneniya/o-probleme-izyatiya-elektronnykh-nositeley-informatsii-v-ramkakh-sledstvennykh-deystviy/
- **[S10]** NIST. *SP 800-61 Rev. 3*. April 2025. Not opened in this session. https://csrc.nist.gov/pubs/sp/800/61/r3/final
- **[S11]** AWS. *How CloudTrail works*. Vendor. https://docs.aws.amazon.com/awscloudtrail/latest/userguide/how-cloudtrail-works.html
- **[S12]** Federal News Network. *OMB revamps cyber event logging requirements*. May 2026. Sec. https://federalnewsnetwork.com/cybersecurity/2026/05/omb-revamps-cyber-event-logging-requirements/
- **[S13]** W3C. *Making Content Usable for People with Cognitive and Learning Disabilities*. Note, 2021-04-29. https://www.w3.org/TR/coga-usable

- **[S14]** USA, 14 CFR § 121.371 (Required inspection personnel). https://www.law.cornell.edu/cfr/text/14/121.371
- **[S15]** Health and Safety Executive (UK). *Why are permit to work systems important?* https://hse.gov.uk/humanfactors/topics/ptw.htm
- **[S16]** SC OSHA. *Lockout/Tagout Fact Sheet*. https://osha.llr.sc.gov/outreach/factsheets/Lockout-Tagout-Fact-Sheet.pdf

(Identifier [S9] was reserved for the primary text of the 2019 Chinese rules, which could not be opened; it is cited through [D8].)

### Human factors

- **[H1]** The Joint Commission. *Sentinel Event Alert 58: Inadequate hand-off communication*. 2017-09-12. https://jointcommission.org/-/media/tjc/documents/resources/patient-safety-topics/sentinel-event/sea_58_hand_off_comms_9_6_17_final_(1).pd
- **[H2]** Starmer, A. J. et al. *Changes in Medical Errors after Implementation of a Handoff Program*. NEJM 371(19):1803–1812, 2014. doi:10.1056/NEJMsa1405556. Institutional release: https://www.eurekalert.org/news-releases/628556 · Summary: https://psnet.ahrq.gov/issue/changes-medical-errors-after-implementation-handoff-program
- **[H3]** Westbrook, J. et al. *Archives of Internal Medicine*, 2010-04-26. Institutional release: https://www.eurekalert.org/news-releases/687593
- **[H4]** Altmann, E. M.; Trafton, J. G.; Hambrick, D. Z. *Journal of Experimental Psychology: General* (online 2013). Institutional release: https://www.eurekalert.org/news-releases/680690
- **[H5]** Williamson, A.; Feyer, A.-M.; Friswell, R.; Finlay-Brown, S. *Development of measures of fatigue: using an alcohol comparison…* (CR 189), 2000. https://www.infrastructure.gov.au/department/media/publications/cr-189-development-measures-fatigue-using-alcohol-comparison-validate-effects-fatigue-performance
- **[H6]** Parasuraman, R.; Manzey, D. *Complacency and Bias in Human Use of Automation: An Attentional Integration*. Human Factors 52(3):381–410, 2010. doi:10.1177/0018720810376055. https://depositonce.tu-berlin.de/items/0c787d91-6021-480b-a333-009e0d1d0092/full
- **[H7]** Risko, E. F.; Gilbert, S. J. *Cognitive Offloading*. Trends in Cognitive Sciences 20(9):676–688, 2016. doi:10.1016/j.tics.2016.07.002. https://discovery.ucl.ac.uk/id/eprint/1508770/
- **[H8]** Kassin, S. M.; Dror, I. E.; Kukucka, J. *The forensic confirmation bias: Problems, perspectives, and proposed solutions*. JARMAC 2:42–52, 2013. doi:10.1016/j.jarmac.2013.01.001. https://web.williams.edu/Psychology/Faculty/Kassin/files/1%20Kassin%20Dror%20Kukucka%20(2013)%20-%20FCB.pdf
- **[H9]** Hutchins, E. *How a cockpit remembers its speeds*. Cognitive Science, 1995. Not opened in this session. https://courses.ischool.berkeley.edu/i290-3/s05/papers/How_a_cockpit_remembers_its_speeds.pdf
- **[H10]** Karidi, D. *Remembering the Future: How ADHD Affects Prospective Memory…*. Attention Magazine (CHADD), December 2025. Popular. https://chadd.org/attention-article/remembering-the-future-how-adhd-affects-prospective-memory-and-how-to-work-with-it/
- **[H11]** Crowley, C. *SANS 2025 SOC Survey*. SANS, July 2025. https://www.elastic.co/pdf/sans-soc-survey-2025.pdf

- **[H12]** Haynes, A. B. et al. *A Surgical Safety Checklist to Reduce Morbidity and Mortality in a Global Population*. NEJM, 2009. Summary: https://www.reliasmedia.com/articles/112170-study-safety-checklist-reduces-mortality (Sec.; PubMed inaccessible: https://pubmed.ncbi.nlm.nih.gov/19144931/)
- **[H13]** Fonarow, G. C. et al. Target: Stroke, JAMA, April 2014. Summary: https://www.tctmd.com/news/society-led-quality-improvement-effort-speeds-treatment-acute-ischemic-stroke (Sec.)
- **[H14]** Kumar, A. et al. Crit Care Med 34(6):1589–96, 2006. PMID 16625125. Summary: https://clincalc.com/blog/2013/10/kumar-2006-antibiotic-delay-septic-mortality/ (Sec.)
- **[H15]** Tam, V. C. et al. *Frequency, type and clinical importance of medication history errors at admission to hospital: a systematic review*. CMAJ 173(5):510, 2005. https://www.cmaj.ca/content/173/5/510
- **[H16]** Rafferty, A. M.; Dean Franklin, B. Editorial on the "Do not interrupt" trial by Westbrook et al. BMJ Quality & Safety 26(9). https://qualitysafety.bmj.com/content/26/9/701.abstract
- **[H17]** Rydrych, D.; Apold, J.; Harder, K. *Preventing Wrong-Site Surgery in Minnesota: A 5-Year Journey*. PSQH, 2012-12-04. https://psqh.com/analysis/preventing-wrong-site-surgery-in-minnesota-a-5-year-journey

### Incidents and consequences

- **[I1]** FAA. *Lessons Learned: Continental Express 2574 (N33701)*. https://www.faa.gov/lessons_learned/transport_airplane/accidents/N33701
- **[I2]** Scott, D.; Bunn, A. *Piper Alpha – process safety then and now*. Loss Prevention Bulletin 261, IChemE, June 2018. https://www.icheme.org/media/1988/lpb261_pg25.pdf
- **[I3]** HuffPost UK. *Police apologise to student Liam Allan after review of collapsed rape trial*. January 2018. Sec. https://huffingtonpost.co.uk/amp/entry/police-apologise-to-student-liam-allan-after-review-of-collapsed-rape-trial_n_19115170
- **[I4]** Help Net Security. *A "cascade" of errors let Chinese hackers into US government inboxes* (on the CSRB report). 2024-04-03. Sec. https://www.helpnetsecurity.com/2024/04/03/microsoft-storm-0558-key/
- **[I5]** GAO. *GAO-18-559: Data Protection: Actions Taken by Equifax and Federal Agencies in Response to the 2017 Breach*. 2018. https://www.gao.gov/assets/700/694347.pdf
- **[I6]** DOJ OIG. *Semiannual Report to Congress* (Mayfield). 2006. https://oig.justice.gov/archives/semiannual/0605/fbi.htm
- **[I7]** The Register. *Vibe coding service Replit deleted user's production database…*. 2025-07-21. Sec. https://www.theregister.com/2025/07/21/replit_saastr_vibe_coding_incident/
- **[I8]** Mandiant / Google Cloud. *M-Trends 2026, executive edition (Latin American Spanish)*. 2026. Vendor. https://services.google.com/fh/files/misc/m_trends_2026_executive_edition_esla.pdf
- **[I10]** Varma, J. R. *SEC order explains Knight Capital systems failure* (summary of the SEC order, 2013). Sec. https://www.jrvarma.in/blog/Y2013/Knight-Capital.html
- **[I11]** U.S. Chemical Safety Board. *Investigation Report: Refinery Explosion and Fire, BP Texas City* (2007). https://www.csb.gov/assets/1/20/CSBFinalReportBP.pdf?13841
- **[I12]** NASA. *Mars Climate Orbiter Mishap Investigation Board Phase I Report*. 1999-11-10. https://llis.nasa.gov/llis_lib/pdf/1009464main1_0641-mr.pdf
- **[I9]** eSecurity Planet. *IBM 2026 Cost of a Data Breach Report: Key Findings*. 2026-07-30. Sec. https://www.esecurityplanet.com/cybersecurity/ibm-2026-cost-of-a-data-breach-report-key-findings/

