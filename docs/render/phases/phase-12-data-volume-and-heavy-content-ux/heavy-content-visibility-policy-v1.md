# Heavy Content Visibility Policy v1 (Phase 12)

Superseded by: `heavy-content-visibility-policy-v2.md` (adaptive cap model).

Status: Frozen (heavy_content_visibility_policy_frozen).

Phase: `phase-12-data-volume-and-heavy-content-ux`.

Date frozen: 2026-04-14.

## 1. Purpose

Freeze the Phase 12 visibility defaults so implementation and review focus on correctness, not re-deciding heuristics in code review.

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

## 5. Scrollback Cap Defaults

1. `soft_cap=1000`
2. `hard_cap=1200`
3. `trim_target=900`

Rule:

1. When active live items exceed `hard_cap`, trim oldest live rows to `trim_target`.
2. Preserve item ordering and anchor invariants.
3. Initial snapshot load uses `live_limit=1000`.

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

## 8. Change Control

Any change to thresholds/precedence requires:

1. explicit policy revision proposal (`v2` doc),
2. gate impact note (`P12-G1/P12-G2/P12-G3`),
3. approval before implementation divergence.
