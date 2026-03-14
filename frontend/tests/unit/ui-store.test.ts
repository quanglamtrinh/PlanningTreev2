import { beforeEach, describe, expect, it, vi } from 'vitest'

describe('ui-store', () => {
  beforeEach(() => {
    window.localStorage.clear()
    vi.resetModules()
  })

  it('defaults to the default theme when storage is empty', async () => {
    const { useUIStore } = await import('../../src/stores/ui-store')

    expect(useUIStore.getState().theme).toBe('default')
  })
})
