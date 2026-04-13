# Row Cache Invalidation Policy v1

Status: Frozen entry artifact for Phase 09 pre-implementation hardening.

Date: 2026-04-13.

Phase linkage: `phase-09-row-isolation-cache` (D01, D02, D10).

## 1. Purpose

Define one contract-safe cache key model for row-level parse artifacts before Phase 09 optimization work starts.

This policy is pre-phase governance only:

- no backend API changes
- no wire contract changes
- no production memo/cache behavior change in this document alone

## 2. Canonical Key Contract

Canonical key fields:

1. `threadId`
2. `itemId`
3. `updatedAt`
4. `mode`
5. `rendererVersion`

Canonical key shape:

- `cache_schema=<CACHE_SCHEMA_VERSION>|renderer=<rendererVersion>|mode=<mode>|thread=<threadId>|item=<itemId>|updated_at=<updatedAt>`

Reference implementation:

- `frontend/src/features/conversation/components/v3/parseCacheContract.ts`

## 3. Frozen Modes

Allowed `ParseCacheMode` values:

1. `message_markdown`
2. `reasoning_summary`
3. `reasoning_detail`
4. `tool_output_markdown`
5. `diff_stats`
6. `diff_unified`

Any new mode requires contract update before implementation use.

## 4. Invalidation Rules

Invalidate when any canonical key field changes:

1. `updatedAt` changed
2. `itemId` changed
3. `threadId` changed
4. `mode` changed
5. `rendererVersion` changed
6. `CACHE_SCHEMA_VERSION` changed

Do not invalidate by full snapshot replacement alone when canonical key fields are unchanged.

## 5. Default Runtime Policy (Phase 09 Baseline)

Frozen defaults for Phase 09 implementation:

1. cache scope: in-memory only
2. persistence: none (`localStorage` persistence is prohibited for parse cache)
3. eviction: bounded LRU
4. default LRU max entries: `1500`
5. default TTL: `10 minutes` (`600000` ms)
6. default renderer version: `v1`

These defaults live in:

- `PARSE_CACHE_LRU_MAX_ENTRIES_DEFAULT`
- `PARSE_CACHE_TTL_MS_DEFAULT`
- `PARSE_CACHE_RENDERER_VERSION`

## 6. Profiling-Only Hooks (Pre-Phase)

Pre-phase instrumentation can emit:

1. row render events
2. parse cache trace events (`hit`/`miss` telemetry path only)

Reference:

- `frontend/src/features/conversation/components/v3/messagesV3ProfilingHooks.ts`

Guardrail:

- profiling hooks must not alter user-visible behavior.
- profiling is opt-in outside tests:
  1. enabled in `test` mode
  2. or enabled with `VITE_ENABLE_MESSAGES_V3_PROFILING=1`
  3. or enabled by an attached profiling subscriber
- when profiling is disabled, emit calls are state no-ops (no tracked parse-key growth).
- parse-key tracking is bounded by `MAX_TRACKED_PARSE_KEYS = 2000` with FIFO eviction.
- tracked parse keys reset when `MessagesV3` thread lifecycle (`threadId`) changes.

## 7. Entry Criterion Mapping

This file satisfies manifest criterion:

- `row_cache_invalidation_policy_frozen`

Manifest reference:

- `docs/render/system-freeze/phase-manifest-v1.json`
