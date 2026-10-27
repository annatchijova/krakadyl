# Supply-chain due diligence — the `laya` dependency

**Date:** 2026-10-27
**Method:** `dependency-provenance`-style check, before `pip install`, not after.
**Trigger:** wiring Laya (https://github.com/NandhaKishorM/laya) in as the typed semantic sensor named in `docs/levels.md` invariant 2. Before installing a third-party package into a forensic-investigation project, its provenance gets checked — same discipline `docs/levels.md`'s "Untrusted content and supply chain" section already applies to this project's own dependency pinning.

## The anomaly that triggered the check

Initial research (confirming Laya's interface against its actual source — `Router.predict`/`predict_batch`/`decide`, a FastAPI server at `/v1/systemone`, Apache 2.0 license) also surfaced something worth distrust on its own: the repo showed **~34,460 stars and ~3,090 forks** despite being created **2026-09-18** — about five to six weeks old. That ratio is a classic signal for inflated/bot stars or a supply-chain-risk package riding a fake popularity signal.

## What was checked, and what it found

| Check | Result |
|---|---|
| Commit/contributor history | 100+ distinct contributors returned by the GitHub API; top author 951 commits, next two 499/274, long tail of small contributions, `dependabot[bot]` doing routine dependency bumps. Organic incremental development — no single "dump everything" commit, no sign of history rewriting. |
| Who is the author | `NandhaKishorM` = Nandakishor M, GitHub account since **March 2019** (not a throwaway), bio: "CEO Convai Innovations. Former Principal investigator IIT Palakkad Technology IHUB foundation." Independently corroborated by a Crunchbase entry (Founder/CEO, Convai Innovations, Kasaragod India, founded 2021) and a Google Scholar profile. A company site (`convaiinnovations.com`) and a dedicated `laya.convaiinnovations.com` page exist. |
| Issues/PRs | Substantive technical content sampled: a real GPU-fallback bug report with a follow-up fix PR, a feature request thread with 10 real comments, a 17-comment PR adding the HTTP server. Reads as genuine engagement, not bot filler. |
| PyPI | Package exists at `pypi.org/project/laya`; metadata (author "Convai Innovations", description) matches the GitHub repo. No conflicting, more-established `laya` package found — low typosquat risk. |
| `setup.py` / `pyproject.toml` | `setup.py` is a two-line setuptools shim. No custom install commands, no post-install hooks of any kind. |
| `hooks.py` / network behavior | `hooks.py` is a pure prediction-lifecycle callback framework (observe/short-circuit a `predict()` call), unrelated to package-install hooks. Grepped the whole package for `requests.*`, `httpx.`, `urllib.request`, `urlopen`, telemetry/analytics strings, `exec(`, `eval(`, `pickle.loads`, `subprocess.`, `os.system` — the only network calls are standard `huggingface_hub` model-checkpoint downloads (expected ML behavior), no phone-home. |
| Independent footprint | A genuine Hacker News front-page launch ("I built non-autoregressive decision models with RL a year ago"), 1,156+ points / 281 comments, reported ~6,000 GitHub stars in three days. Multiple independent write-ups exist, some skeptical (benchmark numbers questioned on HN). The star/fork ratio is explained by real organic virality, not bot activity. |

## Conclusion

Every anomaly traced to a real, verifiable cause: a funded startup founder with an established, multi-year GitHub history and a corroborated public profile; organic HN virality explaining the unusual growth rate; real contributor and issue activity; a clean, hook-free install path. **No supply-chain red flags found.** Proceeded with installation, pinned to the exact version reviewed (`laya==0.4.15`, not a range) in `pyproject.toml`'s `laya` extra — the version string itself is the commitment; bumping it later means re-reviewing, not a silent `pip install -U`.

## Post-install: confirmed live, on real hardware

Installed into a dedicated virtualenv (`krakadyl/.venv`) rather than the
machine's shared system Python, to isolate `torch`/`transformers` from
other projects (e.g. `vigia-repo`) that already had a conflicting
`huggingface-hub` version pinned globally — found by hitting that
conflict directly (`ImportError: huggingface-hub>=1.5.0,<2.0 is
required... but found huggingface-hub==2.1.1`) before installing
anything.

First real call against the installed package found a real bug in
this project's own question schema (not in `laya` itself): a `score`
question needs `criteria` as a list of level descriptions; the
adapter's `urgency` question used a `legend` dict instead (the shape of
a score *answer*, not a valid question field), and Laya's real
validator rejected it outright. Fixed at the source — see
`docs/levels.md`'s Laya section for the full account — and locked in
with a regression test (`test_score_question_uses_criteria_not_legend`).

Re-run after the fix succeeded end-to-end on real hardware: GPU memory
sampled via `nvidia-smi` rose from a ~282–298MiB baseline to **2042MiB**
on the RTX 3090 while the model was loaded for inference, confirming
Laya's own CUDA autodetection worked with zero extra configuration
from this codebase.

## What this review did not cover

- No `pip download --no-deps` hash comparison against the GitHub release tag was performed (recommended by the research pass, not completed in this round).
- The model checkpoint itself (`ModernBERT`-family weights pulled from HuggingFace at first real use) was not independently audited — this project trusts HuggingFace's own distribution the same way it trusts PyPI's, not with additional scrutiny beyond that.
- Laya's own classification accuracy/calibration was not benchmarked. Per `docs/levels.md` invariant 2, this doesn't matter for authority — Laya's output never grants anything — but it does matter for how much a human should trust the signal when deciding whether to act on it, which is why the UI frames every Laya output as a bounded, typed number with an explicit "informational only" label rather than a verdict.
