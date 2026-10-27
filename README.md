# KRAKADYL

**An active-investigation agent for forensic work under time pressure.**

KRAKADYL keeps a case organized, identifies what evidence is missing
*while it can still be recovered*, and coordinates the next verifiable
step — within a mandate it never silently expands. It does not decide
what the evidence proves; that stays with the inference engine and the
human investigator. It helps the investigation arrive at those tools
better prepared.

> Lee esto en español: [README.es.md](README.es.md)

![The crocodile keeps the evidence](visual/evidence.png)

Built during the [Meta Global AI Developer Hackathon](https://cerebralvalley.ai/e/meta-ai-developer-hackathon)
(building period: Oct 27 – Nov 4, 2026) by [Anna Tchijova](https://github.com/annatchijova).

## The scenario this exists for

An investigation doesn't always fail because someone made a mistake.
Sometimes it fails because everyone assumed someone else had already
done something.

Picture three investigators working the same case. An evidence
acquisition task was assigned. Someone reported it done. Another
investigator assumed the evidence had already been preserved.

Nobody verified it independently.

By the time the discrepancy surfaces, that evidence may no longer exist.

This isn't only a technical problem. It's also a problem of
coordination, cognitive load, working memory, and executive function.
Investigators face interruptions, shifting priorities, long shifts,
incomplete information, and handoffs between teams — technical
expertise doesn't turn human attention and memory into unlimited
resources.

## Why this exists

Working with her own forensic/DFIR tooling, Anna kept running into the
same gap: an inference engine like [VIGÍA](https://github.com/annatchijova/vigia-intent-analysis)
can correctly return `ABSTAIN` — the evidence does not support a
conclusion — but by the time that happens, the missing piece is often no
longer recoverable: a volatile artifact wasn't preserved, a chain-of-custody
field wasn't logged, a source went offline. The cost of finding this out
late is not symmetric with the cost of finding it out early.

KRAKADYL is the layer that runs *before* that — designed to:

- Preserve investigation continuity across people, shifts, and interruptions.
- Distinguish between work that's assigned, accepted, reported done, and independently verified.
- Identify missing evidence while it can still be recovered.
- Record uncertainty, conflicting information, and responsibility — without assigning personal blame.
- Help investigators find the next concrete, verifiable step without having to mentally reconstruct the whole case file.
- Keep AI-generated proposals separate from verified authority, through deterministic authorization decisions and auditable records.

**KRAKADYL will not decide what the evidence proves.** That stays with
the investigator and the appropriate analysis systems. Its job is to
help people and teams reach those decisions with better-preserved
evidence, fewer avoidable omissions, and a clearer picture of what's
still unknown — so the investigator (junior or senior, any investigator
working under time pressure) reaches VIGÍA, SIFT, or any other analysis
tool with a case that is actually ready to be evaluated.

**Reducing avoidable `ABSTAIN`s caused by incomplete preparation — while
preserving every `ABSTAIN` that is actually necessary — is the metric
that matters.** A case KRAKADYL cannot complete should close honestly as
"this evidence is not available," never as a narrative pushed into
looking complete.

This reflects something Anna considers foundational, not incidental:
**technical competence and executive-function capacity are independent
variables.** Good tools should account for both — see
[docs/terminal-first-and-blame.md](docs/terminal-first-and-blame.md) for
where that principle comes from.

## How it fits with the rest of the ecosystem

| System | Responsibility |
|---|---|
| Acquisition/analysis tools (Velociraptor, SIFT, i2, etc.) | Acquire and examine artifacts within their own capabilities |
| [VIGÍA](https://github.com/annatchijova/vigia-intent-analysis) or another inference engine | Decide what the evidence supports — including a legitimate `ABSTAIN` |
| **KRAKADYL** | Keep the case organized, identify what's missing, coordinate the next investigative step |
| The investigator | Defines scope, authorizes actions, exercises professional judgment |

KRAKADYL does not replace or re-decide what these systems already do
well. It is the missing piece upstream of them — related in spirit to
[ZAYNOR](https://github.com/annatchijova/zaynor) (case-bound investigation
memory and audit verification) and [ANNACONDA](https://github.com/annatchijova/annaconda)
(autonomous DFIR agent fleet with a sealed, court-defensible verdict) in
the same portfolio, and to [VELO](https://github.com/annatchijova/velo)
(zero-knowledge attestation for forensic verdicts) for anything that
eventually needs to be proven without exposing the underlying evidence.

Target integrations as the project grows: **Velociraptor** (acquisition),
**SIFT Workstation**, **i2 Analyst's Notebook**, and VIGÍA itself — each
as an adapter with its own explicit contract, not a hardcoded assumption.

## Architecture, in one paragraph

An agent proposes an action (powered by Meta's Muse Spark for reasoning
and tool use, and SAM 3.1 for visual grounding where the case has images
or video). A typed semantic sensor ([Laya](https://github.com/NandhaKishorM/laya))
interprets unstructured context into typed signals — it never grants
authority by itself, a probabilistic signal is not a verified fact. The
environment supplies the verifiable facts (who granted what permission,
over what resource, with what scope and validity). A deterministic
policy engine decides `ALLOWED` / `CONFIRM` / `GATHER_EVIDENCE` /
`FORBIDDEN` over the typed action plus those verified facts — never over
the model's or the sensor's interpretation alone. Every decision produces
a chained, independently verifiable receipt.

This separation — the model proposes, a sensor interprets, the
environment verifies, a deterministic engine decides — is not new on its
own; see the acknowledgements below for the closest prior art, read and
verified before this project claimed any novelty.

## Not just forensics

KRAKADYL is released under an open license specifically so it is not
locked to one investigative domain. The core mechanism — track what's
unknown, resolve what's still resolvable, act only within a verified
mandate, close honestly when something can't be recovered — generalizes
to any investigation under time pressure and incomplete information:
incident response and cybersecurity investigations (the people Anna works
with in forensics and infosec are the first people who'd actually use
this), journalism, and — a domain Anna considers directly relevant — **AI
safety investigations**, where "what do we actually know, what's still
missing, and what can we no longer verify" is the same question wearing
a different case file. Forensic DFIR is the first complete, demonstrable
experience because it's the domain Anna has real, verifiable criteria
in — not because the architecture is forensics-specific.

## Scope and honesty about where this stands

This was built under the real constraint of a 9-day hackathon building
period (Oct 27 – Nov 4, 2026), not stretched to look bigger than it is.
Levels not reached by the submission deadline are documented as roadmap,
not simulated as if they were already built. See `docs/` for the
architecture levels, the benchmark design, and what's genuinely new here
versus what's prior art (acknowledged explicitly, not glossed over).

**This project continues after the hackathon regardless of outcome.** It
was built to be used — by Anna, and by the forensic and cybersecurity
people in her own network — not to be abandoned once judging ends.

## The methodology behind how this gets built

Levels are not "cut down to fit the deadline" — they're built toward a
known, ambitious destination (a product meant to be kept and used over
months), and what varies with available time is how many coherent levels
get reached, never how complete the levels actually attempted are. This
follows Anna's own engineering skill:
[destination-driven-construction](https://github.com/annatchijova/SKILLS/tree/main/destination-driven-construction)
(part of her [SKILLS](https://github.com/annatchijova/SKILLS) collection).

## Acknowledgements and prior art

No part of this project is presented as inventing authority-bounded
agents, agent authorization benchmarks, or deterministic governance
layers — all of those already exist, verified against source before this
README was written:

- Meta's own [Muse](https://about.fb.com/news/2026/09/introducing-muse-personal-ai-agent/)
  is already a personal agent handling broad goals across apps, and
  [Sentinel](https://research.meta.ai/blog/security-and-safety-for-ai-agents-our-approach-with-muse)
  is already a host-side deterministic authority separate from the
  model, governing connectors and network egress.
- [AgentBound](https://arxiv.org/abs/2606.30970) — deterministic
  governance between authorization and execution, with cryptographic
  per-action receipts.
- [AuthorizationBench](https://arxiv.org/abs/2610.27548) — benchmarks
  exactly the claim that task completion does not imply staying within
  authorization.
- [AuthorityBench / Veto](https://github.com/yazcaleb/can-is-not-may) —
  deterministic authority interception, and the finding that individually
  permitted actions can combine into a violation (tool-chaining).
- [Bounded Agents / APC](https://arxiv.org/abs/2608.15888) — delegation
  limits enforced via composition closure across action history.
- [Rehearsal](https://github.com/dhansxd/rehearsal) — rehearsing outcomes
  before approving an action.
- [Laya](https://github.com/NandhaKishorM/laya) — the typed semantic
  sensor used here.

What this project claims as its own contribution is the specific
combination: a personal agent built on Meta's models, given a broad goal
rather than a sequence of orders, that investigates what it doesn't know
before interrupting a human, distinguishes "a document claims I have
permission" from "I have a verified permission," and is evaluated on
investigation-domain cases — not the existence of authority layers or
authorization benchmarks in general, which already belong to the
projects listed above.

## License

Apache License 2.0 — see [LICENSE](LICENSE). Public and open from the
first commit, so anyone can read, adapt, or extend it for their own
investigative domain.
