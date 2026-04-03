import { describe, expect, it } from 'vitest'

import {
  loadMessagesV3ViewState,
  saveMessagesV3ViewState,
} from '../../src/features/conversation/components/v3/messagesV3.viewState'

describe('messagesV3.viewState', () => {
  it('returns safe defaults for invalid schema payloads', () => {
    window.localStorage.setItem(
      'ptm.uiux.v3.thread.thread-1.viewState',
      JSON.stringify({
        schemaVersion: 999,
        expandedItemIds: ['x'],
        collapsedToolGroupIds: ['y'],
        dismissedPlanReadyKeys: ['z'],
      }),
    )

    const loaded = loadMessagesV3ViewState('thread-1')
    expect(loaded.schemaVersion).toBe(1)
    expect(loaded.expandedItemIds).toEqual([])
    expect(loaded.collapsedToolGroupIds).toEqual([])
    expect(loaded.dismissedPlanReadyKeys).toEqual([])
  })

  it('persists per-thread state without leaking across thread keys', () => {
    saveMessagesV3ViewState('thread-1', {
      schemaVersion: 1,
      expandedItemIds: ['a'],
      collapsedToolGroupIds: ['g1'],
      dismissedPlanReadyKeys: ['thread-1:plan-1:1'],
      updatedAt: '2026-04-01T00:00:00Z',
    })
    saveMessagesV3ViewState('thread-2', {
      schemaVersion: 1,
      expandedItemIds: ['b'],
      collapsedToolGroupIds: ['g2'],
      dismissedPlanReadyKeys: ['thread-2:plan-2:1'],
      updatedAt: '2026-04-01T00:00:00Z',
    })

    expect(loadMessagesV3ViewState('thread-1').expandedItemIds).toEqual(['a'])
    expect(loadMessagesV3ViewState('thread-2').expandedItemIds).toEqual(['b'])
  })

  it('enforces payload cap by trimming least-priority lists first', () => {
    const veryLarge = Array.from({ length: 2500 }, (_, index) => `dismiss-${index}`)
    saveMessagesV3ViewState('thread-1', {
      schemaVersion: 1,
      expandedItemIds: ['keep-expanded'],
      collapsedToolGroupIds: ['keep-group'],
      dismissedPlanReadyKeys: veryLarge,
      updatedAt: '2026-04-01T00:00:00Z',
    })

    const loaded = loadMessagesV3ViewState('thread-1')
    expect(loaded.expandedItemIds).toContain('keep-expanded')
    expect(loaded.collapsedToolGroupIds).toContain('keep-group')
    expect(loaded.dismissedPlanReadyKeys.length).toBeLessThan(veryLarge.length)
  })
})

