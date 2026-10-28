# Muse Rate Limit Remediation

## Finding

The `/api/cases/{case_id}/actions/propose-with-muse` endpoint made a billed Meta
Model API call without a frequency bound. A caller who can reach the endpoint can
assert the configured principal, so principal matching alone does not control
cost exposure. This was a cost-exposure vulnerability, not a demonstrated data
access or authority bypass.

## Evidence and fix

The predicted result before the fix was that request N+1 would still reach the
Muse adapter. The regression test failed on the unfixed code with HTTP 200 for
that request; after the fix it receives HTTP 429 before summary construction or
adapter invocation. Direct thread tests cover concurrent admissions, and a local
Uvicorn check verified the configured zero limit rejects before calling Muse.

The endpoint now reserves capacity in a lock-protected rolling 60-second window
after case and principal validation but before building summaries or calling the
adapter. `KRAKADYL_MUSE_RATE_LIMIT_PER_MINUTE` defaults to 10; zero is a kill
switch, and invalid or negative values fail startup. An admitted request consumes
capacity even if the adapter fails, because the external call may already have
incurred cost.

## Threat model and limits

The caller can send HTTP requests and control request fields, but cannot write
server memory or source code. No billed external call was used for the regression
tests. The bound is per process: restart clears the window, and multiple workers
or instances do not coordinate. W workers can admit approximately W times the
configured limit per minute. This is not authentication and is not a distributed
rate limit.

## Reproduction

Run the endpoint and concurrency checks with:

```text
python3 -m pytest tests/test_api.py::test_propose_with_muse_rate_limit_rejects_n_plus_one_before_summary_or_adapter tests/test_api.py::test_muse_rate_limiter_admission_is_atomic_across_threads tests/test_api.py::test_muse_rate_limiter_uses_its_lock_for_admission -q
```

The original branch commit is `7e82177344c7f0cff796fcb72f564b243dad453a`.

## Skills applied

- `red-team-auditing`
- `audit-before-patch`
- `secure-by-construction`
- `falsifiable-testing`
- `surgical-patcher`
- `remediation-driven-reporting`
- `git-discipline`
