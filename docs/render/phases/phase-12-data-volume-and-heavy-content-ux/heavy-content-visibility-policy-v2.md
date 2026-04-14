# Heavy Content Visibility Policy v2 (Phase 12)

Status: Frozen (heavy_content_visibility_policy_frozen_v2).

Phase: `phase-12-data-volume-and-heavy-content-ux`.

Date frozen: 2026-04-14.

Supersedes: `heavy-content-visibility-policy-v1.md` for E01 cap behavior only.

## 1. Purpose

Freeze the adaptive cap model for Phase 12 completion so we remove fixed hard-cap assumptions while keeping bounded memory and contract safety.

## 2. Scope

Applies to:

1. D08 default-collapse behavior.
2. E01 active live-feed cap behavior.
3. E02 preview/truncation presentation behavior.

Does not change:

1. canonical backend payload text content.
2. replay/resync contract.
3. backend semantic coalescing ownership.

## 3. Policy Precedence (highest to lowest)

1. Manual user toggle state (persisted per thread).
2. Active lifecycle state:
   - `in_progress` rows auto-expand.
3. Heavy defaults:
   - completed heavy rows default collapsed.
4. Non-heavy defaults:
   - non-heavy tool rows may default expanded.

## 4. Heavy Classification Defaults

1. `toolType=commandExecution` heavy when:
   - output chars `>= 600`, or
   - output lines `>= 12`.
2. `toolType=fileChange`/diff-heavy when:
   - file count `>= 5`, or
   - summary + patch payload chars `>= 3000`.
3. `toolType=generic` heavy when:
   - output chars `>= 2000`.
4. Never auto-collapse:
   - `userInput`, `status`, `error`.

## 5. Adaptive Scrollback Cap Defaults

1. Baseline:
   - `soft_cap=1000`
   - `snapshot live_limit=1000`
2. Runtime profile selection:
   - env override: `VITE_PTM_PHASE12_CAP_PROFILE=low|standard|high`
   - fallback runtime hint: `navigator.deviceMemory`
   - fallback default: `standard`
3. Headroom mapping:
   - `low`: `+100`
   - `standard`: `+200`
   - `high`: `+400`
4. Computed policy:
   - `effective_hard_cap = soft_cap + headroom`
   - `effective_trim_target = soft_cap` (always 1000)

Rules:

1. Enforce cap on all mutation paths:
   - snapshot hydrate/reload
   - batched stream event flush
   - history prepend (`loadMoreHistory`)
   - reconnect/resync snapshot path
2. When live items exceed `effective_hard_cap`, trim oldest rows to keep newest `effective_trim_target`.
3. Preserve item ordering and Phase 10 anchor invariants.
4. Preserve known canonical `totalItemCount` across trim.

## 6. Preview Policy (View Only)

1. Preview limits:
   - `max_chars=1200`
   - `max_lines=60`
2. UI behavior:
   - primary row renders preview when truncated.
   - "View full" opens full-content panel/modal from canonical item payload.
3. Constraint:
   - no backend payload mutation for truncation.

## 7. API and Contract Impact

1. Snapshot endpoint supports optional `live_limit`.
2. Snapshot payload may include `historyMeta`:
   - `hasOlder`
   - `oldestVisibleSequence`
   - `totalItemCount`
3. History pagination endpoint:
   - `/history?node_id=...&before_sequence=...&limit=...`
4. No replay/resync contract changes.

## 8. Change Control

Any change to profile mapping/precedence requires:

1. explicit policy revision proposal (`v3` doc),
2. gate impact note (`P12-G1/P12-G2/P12-G3`),
3. approval before implementation divergence.
