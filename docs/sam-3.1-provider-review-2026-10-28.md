# SAM 3.1 provider review — 2026-10-28

## Scope

This is a point-in-time review of Meta's public documentation for SAM 3.1 on Meta Model API. It records vendor claims relevant to a possible KRAKADYL integration; it is not legal advice, account-specific confirmation, or approval to send case evidence. No API request or media upload was made for this review.

## Verified public claims

- Meta lists `sam-3.1` on Meta Model API for image and video segmentation. The documented endpoint is `POST /v1/responses` at `https://api.meta.ai/v1`, authenticated with a bearer API key. The API returns boxes and masks; video requests can be streamed or returned as a completed response. [SAM 3.1 model page](https://dev.meta.ai/models/sam-3-1), [SAM API overview](https://dev.meta.ai/docs/sam/overview).
- The model page currently lists USD 2.50 per 1,000 segmented images and USD 0.20 per 1,000 video frames. Meta's pricing documentation says each video request is billed for at least 50 frames, including shorter clips. At the published rate, that minimum is USD 0.01 per video request. Prices are a dated snapshot and must be checked again before enabling a paid adapter. [SAM 3.1 pricing](https://dev.meta.ai/docs/pricing-rate-limits).
- Meta's Standard Services terms say submitted Content is not used to train Meta Models. The same terms permit retention and processing as needed to provide the service, comply with law, exercise contractual rights, and address policy, security, safety, abuse, or review concerns. Standard mode therefore does not mean zero retention. [Meta Model API Terms of Service, Sections 4.4 and 5.1](https://dev.meta.ai/legal/terms-of-service).
- Meta documents Zero Data Retention (ZDR) for qualified organizations, enabled separately by Meta at organization/team level. The help page says ZDR requests are not stored after the response except where required for law or misuse; it also lists retained policy-violation data (up to two years), usage statistics, account/team data, operational metadata, and support feedback. ZDR support may vary by model. [Meta ZDR help page](https://dev.meta.ai/help/policies-and-privacy/zero-data-retention).
- The ZDR help page says file uploads and other storage-dependent features are unavailable under ZDR. SAM's API documentation separately describes image/video inputs and a Files API. Public pages reviewed here do not establish which SAM input path is supported with ZDR, or whether ZDR applies to SAM 3.1 specifically. Treat that compatibility as unknown until Meta confirms it for the relevant organization and request shape. [ZDR help page](https://dev.meta.ai/help/policies-and-privacy/zero-data-retention), [API reference](https://dev.meta.ai/docs/api-reference).
- Meta also publishes downloadable SAM 3.1 model checkpoints and inference code. That route avoids transmitting evidence to Meta Model API, but it has separate license, hardware, deployment, patching, and operational costs. The repository's SAM license is distinct from the API terms. [SAM 3.1 release](https://ai.meta.com/blog/segment-anything-model-3/), [official SAM repository](https://github.com/facebookresearch/sam3), [SAM license](https://github.com/facebookresearch/sam3/blob/main/LICENSE).

## Decision status for KRAKADYL

**ABSTAIN from sending case evidence to Meta Model API for now.** The public documentation is enough to establish that a paid hosted SAM 3.1 API exists and to estimate its listed per-image/per-frame charge. It is not enough to establish account-specific ZDR eligibility or SAM compatibility, to approve the data scope, or to choose the first acquisition source and discriminating question.

Before enabling hosted processing, record all of the following for the actual organization and account:

1. Written confirmation that ZDR is enabled for the API key's organization/team and applies to `sam-3.1` for the exact media input path KRAKADYL will use.
2. The applicable Meta terms, data-processing terms, subprocessors, and policy/misuse retention exceptions accepted by the account owner; confirm that the case material may legally and contractually be submitted.
3. A concrete open requirement, source capability, human authorization, and exact media scope. The input must be the minimum material needed to test a discriminating question.
4. Finite per-attempt and cumulative limits, including image count or video frame count and maximum spend. Reserve the maximum charge durably before dispatch; keep the reservation on an unknown outcome until reconciled.
5. A named evaluator and an explicit rule that SAM output is an untrusted annotation candidate and cannot resolve an `EvidenceRequirement` or change hypothesis status by itself.

If any item cannot be verified, use a local inference route only after separately reviewing its license and operational requirements, or abstain. No default vendor, identity, evaluator, or budget is selected by this note.

## Limitations and falsifier

This review covers public pages available on 2026-10-28; it does not inspect the signed-in account, billing settings, enabled privacy controls, negotiated terms, or current API behavior. Reopen the review if Meta changes the published pricing/terms, if the selected account's ZDR configuration is confirmed, or if the deployment chooses self-hosted checkpoints instead of the hosted API.

Skills applied: `claim-provenance-discipline`, `data-provenance-mapping`, `secure-by-construction`, and `software-archaeology`.
