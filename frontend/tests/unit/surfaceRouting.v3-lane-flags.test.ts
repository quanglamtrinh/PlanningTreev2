import { describe, expect, it } from 'vitest'

import {
  isExecutionAuditV2SurfaceEnabled,
  isAuditUiuxV3FrontendEnabled,
  isExecutionUiuxV3FrontendEnabled,
  resolveLegacyRouteTarget,
  resolveV2RouteTarget,
} from '../../src/features/conversation/surfaceRouting'

describe('surfaceRouting hard cutover defaults', () => {
  it('always keeps execution/audit on chat-v2 surface', () => {
    expect(isExecutionAuditV2SurfaceEnabled(null)).toBe(true)
    expect(isExecutionAuditV2SurfaceEnabled(undefined)).toBe(true)
  })

  it('always enables v3 conversation render for execution/audit lanes', () => {
    expect(isExecutionUiuxV3FrontendEnabled(null)).toBe(true)
    expect(isAuditUiuxV3FrontendEnabled(undefined)).toBe(true)
  })

  it('routes legacy execution/audit tabs to chat-v2', () => {
    expect(
      resolveLegacyRouteTarget({
        requestedThreadTab: 'execution',
        isReviewNode: false,
      }),
    ).toEqual({ surface: 'v2', threadTab: 'execution' })
    expect(
      resolveLegacyRouteTarget({
        requestedThreadTab: 'audit',
        isReviewNode: false,
      }),
    ).toEqual({ surface: 'v2', threadTab: 'audit' })
  })

  it('routes review nodes to audit tab on chat-v2', () => {
    expect(
      resolveLegacyRouteTarget({
        requestedThreadTab: null,
        isReviewNode: true,
      }),
    ).toEqual({ surface: 'v2', threadTab: 'audit' })
    expect(
      resolveV2RouteTarget({
        requestedThreadTab: null,
        isReviewNode: true,
      }),
    ).toEqual({ surface: 'v2', threadTab: 'audit' })
  })

  it('keeps ask lane on legacy surface', () => {
    expect(
      resolveLegacyRouteTarget({
        requestedThreadTab: 'ask',
        isReviewNode: false,
      }),
    ).toEqual({ surface: 'legacy', threadTab: 'ask' })
    expect(
      resolveV2RouteTarget({
        requestedThreadTab: 'ask',
        isReviewNode: false,
      }),
    ).toEqual({ surface: 'legacy', threadTab: 'ask' })
  })
})
