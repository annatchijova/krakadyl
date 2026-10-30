# API Authentication and Authorization

Status: implemented 2026-10-30.

## Trust model

The API derives operator identity from `Authorization: Bearer <token>`. Tokens
are configured as `identity=sha256(token)` pairs through
`KRAKADYL_OPERATOR_TOKENS`; the plaintext is generated once by
`tools/operator_token.py` and is not stored by the runtime. A request-body
`principal` is legacy wire compatibility only. If present, it must match the
authenticated identity, but it cannot establish identity.

When `KRAKADYL_OPERATOR_TOKENS` is absent, operator-dependent routes return
`503` rather than silently accepting anonymous requests. With a configured
verifier, a missing or invalid bearer credential returns `401` with a Bearer
challenge.

## Authorization matrix

| Actor and credential | Case reads | Level 1/2 actions | Level 3–5 actions | Dev routes when enabled |
|---|---:|---:|---:|---:|
| Anonymous | 401 | 401 | 401 | 401 |
| Configured operator, wrong mandate principal | allowed for reads | 403 | route-specific scope checks | allowed only where route permits |
| Configured operator, mandate principal | allowed | allowed if the live mandate and state permit | allowed if the live mandate and state permit | allowed |

All case metadata reads are protected, including activity, acquisition, team,
handoff, and counterfactual views. Level 1/2 actions authenticate before
loading the prepared action or performing a billed Muse call. This prevents an
unauthenticated caller from using a resource identifier as an existence oracle
or spending the Meta API budget.

The dev router is opt-in with `KRAKADYL_ENABLE_DEV_ROUTES=1` and still requires
an operator bearer token. It is disabled by default.

## Frontend behavior

The frontend has an explicit operator unlock screen. The token is held only in
React memory and sent as a bearer header for normal API requests; it is not
written to local storage, cookies, or the repository. A page reload requires
authentication again.

## Security limits

This is a local deployment credential boundary, not a production identity
provider. Credentials currently have no expiry, rotation protocol, MFA,
revocation endpoint, or independent directory. The Muse rate limiter remains
process-local, and SQLite concurrency remains a Level 4 deployment concern.
Before network exposure or multi-team use, adopt an expiring session or signed
token lifecycle, explicit read scopes, credential rotation, and a distributed
cost limiter.

## Verification

The regression suite covers anonymous read rejection, bearer identity binding,
wrong-principal rejection, mandate scoping, dev-route authentication, and
backward-compatible requests without a body principal. An authenticated run on
2026-10-30 passed 344 tests, excluding the optional Laya adapter test module.
The later rerun in the shell used for this commit was blocked by a reproducible
`TestClient` hang even with a minimal FastAPI application; it did not produce a
test failure and is recorded as an environment limitation rather than a green
result.

Skills used for this round: `authorization-surface-mapping`,
`secure-by-construction`, `agent-trust-boundaries`,
`live-contract-compatibility`, `secret-lifecycle-discipline`,
`falsifiable-testing`, `audit-before-patch`, `surgical-patcher`, and
`git-discipline`.
