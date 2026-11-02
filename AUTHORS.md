# KRAKADYL — Authors & Attribution

## Principal Investigator

### Anna Tchijova

**Role:** Creator, Principal Investigator, Architect

**Contribution:** Conceived KRAKADYL as the pre-inference continuity layer for
investigative work: the system that runs *before* the inference engine, so a
correct `ABSTAIN` never arrives after the missing evidence has become
unrecoverable. Designed the core distinctions the system enforces — reported
vs. verified, assigned vs. accepted vs. independently confirmed, known deadline
vs. event-closed window — and the mandate discipline (delegated authority with
transitive revocation, revalidated at execution time). Directed the KRAKADYL AI
Collective across 7 models. Built during the Meta Global AI Developer
Hackathon (building period: Oct 27 – Nov 4, 2026). Made all architecture
decisions, rejected proposals that violated determinism or authority
principles, and maintained the integrity of the pipeline throughout.

*"The One Who Refused to Confuse Reported with Verified."*

---

## KRAKADYL AI Collective

| Member | Organization | Role | Contributions |
|--------|-------------|------|---------------|
| **Muse Spark** | Meta | Runtime proposer model, research collaborator, problem-framing partner | The model behind `propose-with-muse`: drafts proposals that the deterministic mandate/evidence pipeline then allows or denies — it has no path to sealed values or execution authority. Adversarial probe 2026-10-30 (`docs/muse-adversarial-probe-2026-10-30.md`): 4 scenarios (baseline, prompt injection in evidence text, out-of-scope resource, insufficient evidence) — behaved within the mandate in all four. Problem thinking, idea generation, exploration of alternatives, expanding the analysis beyond forensics into aviation, medicine, and process industry evidence |
| **Muse Image** | Meta | Visual asset generation | Visual identity assets for the project (`visual/`, landing): the crocodile imagery carrying the "keep the evidence" motif |
| **Muse Wonder** | Meta | Ideation & alternative exploration | Generating ideas, examining alternatives, widening the problem frame beyond the strictly forensic |
| **Claude** | Anthropic | Systems integration engineer | Branch integration, red-team audit response and remediation, hardening of the deterministic boundary between proposal and authority |
| **ChatGPT** | OpenAI | Research & adversarial red team | Global research collaboration (problem existence, prior art, differentiation), stress testing, uncomfortable questions about scope and overclaiming |
| **Codex** | OpenAI | Implementation engineer | Four independent implementation branches from `main` (handoff in `docs/codex-handoff-2026-10-27.md`): `feat/muse-rate-limit` (per-process cost bound for billed Muse calls), `feat/sqlite-concurrency` (serialized SQLite write transactions), `feat/typescript-codegen` (OpenAPI-generated frontend types), `feat/level2-hypothesis-recovery` (reviewable recovery questions for invalidated hypotheses) — test counts verified per branch, none merged by Codex |
| **Kimi** | Moonshot AI | Research & systems specialist | Research collaboration and red-team review across the verification, custody, and delegation model |

*"The One Who Stayed Inside the Mandate."* — Muse Spark
*"The One Who Drew the Crocodile."* — Muse Image
*"The One Who Asked What Else It Could Be."* — Muse Wonder
*"The One Who Connected the Wires."* — Claude
*"The One Who Asked the Uncomfortable Questions."* — ChatGPT
*"The One Who Shipped Four Branches."* — Codex
*"The One Who Read Every Invariant."* — Kimi

---

## Methodology — SKILLS

The engineering discipline of this project — abductive diagnosis, audit before
patch, red-team auditing, deterministic core, honest degradation — is encoded
as reusable agent skills in the author's skills repository:

- [annatchijova/SKILLS](https://github.com/annatchijova/SKILLS)

The red-team rounds documented in `docs/red-team-*.md` and the remediation
records next to them were run under that discipline: every finding verified
against the live file before patching, every patch surgical and backed up,
every limitation that could not be closed documented in
[`docs/known-limitations.md`](./docs/known-limitations.md) instead of hidden.

---

## Prior art & intellectual lineage

KRAKADYL's defensible differentiation is the *combination* applied to the
investigative domain, not any isolated guarantee. Each individual mechanism has
prior art, documented in `KRAKADYL GLOBAL RESEARCH EN.md`:

| Source | Contribution KRAKADYL builds on |
|--------|---------------------------------|
| Macaroons (2014), UCAN, Biscuit | Delegation attenuation |
| Zhu and Wang (arXiv 2609.21284, Sep 2026) | Transitive revocation with in-flight effects (more rigorous, multi-endpoint treatment — cited, not matched) |
| AgentBound, Rekor / Sigstore | Verifiable receipts and transparency logs |
| Aviation, medicine (I-PASS), forensic science doctrine | Reported vs. verified; standardized handoffs |
| Continental Express 2574, Piper Alpha, Liam Allan case | What happens when handoffs and verification fail |
| [VIGÍA](https://github.com/annatchijova/vigia-intent-analysis) (same author) | The inference engine whose correct-but-avoidable `ABSTAIN` motivated KRAKADYL as its prior layer |

---

## Open Source Dependencies

- [Pydantic](https://github.com/pydantic/pydantic) (validation core)
- [FastAPI](https://github.com/fastapi/fastapi) (API layer)
- [Uvicorn](https://github.com/encode/uvicorn) (ASGI server)
- [pytest](https://github.com/pytest-dev/pytest) (test suite)
- [httpx](https://github.com/encode/httpx) (API testing)
- Laya `==0.4.15` (pinned exact per supply-chain discipline; due-diligence trail in `docs/red-team-laya-integration.md`)

---

## Academic Citation

```bibtex
@software{krakadyl2026,
  author    = {Tchijova, Anna and {KRAKADYL AI Collective}},
  title     = {KRAKADYL: An Active-Investigation Agent for Forensic Work Under Time Pressure},
  year      = {2026},
  url       = {https://github.com/annatchijova/krakadyl},
  note      = {AI Collective: Muse Spark, Muse Image, Muse Wonder (Meta),
               Claude (Anthropic), ChatGPT and Codex (OpenAI),
               Kimi (Moonshot AI).
               Built during the Meta Global AI Developer Hackathon,
               Oct 27 - Nov 4, 2026}
}
```

---

## Ethics Statement

All contributors agree to:

1. **Non-maleficence:** KRAKADYL will not be used to fabricate, plant, or
   misrepresent evidence, or to silently expand an investigative mandate.
2. **Reported is not verified:** the system never presents a merely reported
   task, an unverified assumption, or a revoked authority as a settled fact.
3. **No blame:** uncertainty, conflicting information, and responsibility are
   recorded without assigning personal blame.
4. **LLM out of the decision path:** the model proposes; the deterministic
   engine disposes. No model output can authorize, execute, or seal anything.
5. **Open source commitment:** all code is Apache 2.0. Limitations are
   documented in [`docs/known-limitations.md`](./docs/known-limitations.md)
   without sanitization.

*"We build tools to keep the case honest, not to close it early."*

---

## Note on Authorship and AI Tools

KRAKADYL was created by Anna Tchijova using AI models as technical
collaborators. The problem framing, architecture decisions, mandate doctrine,
case design, and all substantive choices belong to the human author. AI models
contributed research, implementation, integration, red-team auditing, and
visual assets under human direction.

This methodology is disclosed transparently because it is consistent with the
project's own principles: a system that refuses to confuse reported with
verified cannot be vague about its own creation process.
