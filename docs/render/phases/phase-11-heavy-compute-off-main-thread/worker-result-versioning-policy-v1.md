# Worker Result Versioning Policy v1

Status: Frozen (`worker_result_versioning_policy_frozen`).

Phase: `phase-11-heavy-compute-off-main-thread`.

Primary contract linkage: `C5` Frontend State Contract v1.

## 1. Purpose

Prevent stale async worker results from mutating active render state while preserving deterministic render semantics.

## 2. Version Token Rules

Version token base:

- `version_token_base = buildParseArtifactVariantKey(parseKey, artifactId)`

Job token:

- `job_token = version_token_base + "|request_seq=" + requestSeq`

Request sequence policy:

- `requestSeq` must be monotonic per `(threadId, itemId, mode, artifactId)`.
- Sequence increments for any content freshness boundary change (for example `updatedAt`, append patch, or row identity switch).

## 3. Apply and Drop Policy

Apply worker result only when all are true:

1. `response.ok === true`
2. `response.requestSeq === latest requestSeq recorded for version_token_base`
3. item identity and freshness context still match active row context

Drop worker result when any are true:

1. `response.requestSeq` is older than latest recorded sequence
2. target row was replaced or moved to a different freshness key
3. phase mode no longer allows worker apply (`off` or `shadow`)

Stale apply invariants:

- stale result apply count must remain `0`
- stale results may complete, but must not mutate active UI artifacts

## 4. Timeout and Fallback Policy

Timeout baseline:

- interactive path default: `300ms`
- deferred/background path default: `800ms`

On worker timeout/error/postMessage failure:

1. mark worker request as failed
2. keep or recompute synchronous fallback artifact
3. do not clear canonical row semantics

## 5. Rollout Mode Semantics

- `off`: no worker dispatch, sync path only
- `shadow`: worker dispatch allowed for parity checks; UI apply remains sync path
- `on`: worker dispatch and apply allowed under version-token guard; sync remains fallback

## 6. Required Test Evidence

The following must be covered before Phase 11 closeout:

1. stale response receives drop (no UI artifact mutation)
2. newer sequence applies successfully
3. timeout/error falls back to sync path with equivalent output semantics
4. shadow mode never applies worker artifact
