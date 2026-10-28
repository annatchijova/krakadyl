# Muse Stale Mandate Remediation

## Finding and inference

- **Firstness:** the endpoint loaded mandate revision 1, awaited the Muse adapter,
  then used the saved object to prepare an action. A synchronized test revoked the
  stored mandate during that adapter call; the endpoint still returned an
  `ALLOWED` decision and a prepared action.
- **Secondness:** an action decision must use the live mandate at the time the
  decision is made. A revocation that completes before preparation must prevent
  an allowed result.
- **Thirdness:** retaining an authorization object across an external call creates
  a mixed-time snapshot. The candidate is based on earlier case summaries while
  the authority decision can accidentally use earlier mandate state.

The benign hypothesis was that the downstream executor would revalidate the
mandate, so the endpoint's stale result could not create an effect. That guard did
block later execution, but it did not make the persisted `ALLOWED` decision truthful.
The predicted correction is to reload and recheck the mandate and principal after
the external call, before preparing or persisting the result. A test that mutates
the stored mandate while the adapter is running confirms the response is now
`FORBIDDEN` with no prepared action.

## Change

`propose_with_muse` still checks the caller before the billed call. After the call,
it reloads the current mandate and checks the principal again before it loads the
remaining preparation inputs. The deterministic preparation pipeline then uses
the reloaded mandate. Muse remains a suggestion source and cannot grant authority.

The test replaces the adapter function with an in-process fake. It makes no
network request and incurs no Muse cost.

## Limitations

The endpoint does not make the mandate read and decision persistence one database
transaction. A mandate can change after the post-call read and before the decision
is persisted. Execution independently revalidates against the current mandate, so
that later change still blocks an effect; the stored proposal can still reflect a
mandate that was current at the read but stale by persistence time. Closing that
last interval requires a transactional decision/write boundary and is outside this
patch.

## Skills applied

- `audit-before-patch`
- `software-archaeology`
- `secure-by-construction`
- `falsifiable-testing`
- `surgical-patcher`
- `red-teaming-auditing`
- `git-discipline`
