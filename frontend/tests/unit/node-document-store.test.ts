import { act } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { apiMock } = vi.hoisted(() => ({
  apiMock: {
    getNodeDocument: vi.fn(),
    putNodeDocument: vi.fn(),
  },
}))

vi.mock('../../src/api/client', () => {
  class ApiError extends Error {
    status: number
    code: string | null

    constructor(status = 400, payload: { message?: string; code?: string } | null = null) {
      super(payload?.message ?? 'Request failed')
      this.status = status
      this.code = payload?.code ?? null
    }
  }

  return {
    api: apiMock,
    ApiError,
  }
})

import { getNodeDocumentEntry, useNodeDocumentStore } from '../../src/stores/node-document-store'

function makeDocument(kind: 'frame' | 'spec', content: string) {
  return {
    node_id: 'root',
    kind,
    content,
    updated_at: '2026-03-21T00:00:00Z',
  }
}

describe('node-document-store', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.useRealTimers()
    useNodeDocumentStore.getState().reset()
  })

  it('loads a document once and caches its content', async () => {
    apiMock.getNodeDocument.mockResolvedValue(makeDocument('frame', '# Frame'))

    await act(async () => {
      await useNodeDocumentStore.getState().loadDocument('project-1', 'root', 'frame')
    })

    const entry = getNodeDocumentEntry('project-1', 'root', 'frame')
    expect(apiMock.getNodeDocument).toHaveBeenCalledWith('project-1', 'root', 'frame')
    expect(entry.content).toBe('# Frame')
    expect(entry.savedContent).toBe('# Frame')
    expect(entry.hasLoaded).toBe(true)
  })

  it('autosaves a dirty document after the debounce window', async () => {
    vi.useFakeTimers()
    apiMock.getNodeDocument.mockResolvedValue(makeDocument('frame', '# Start'))
    apiMock.putNodeDocument.mockResolvedValue(makeDocument('frame', '# Updated'))

    await act(async () => {
      await useNodeDocumentStore.getState().loadDocument('project-1', 'root', 'frame')
    })

    act(() => {
      useNodeDocumentStore.getState().updateDraft('project-1', 'root', 'frame', '# Updated')
    })

    await act(async () => {
      vi.advanceTimersByTime(799)
      await Promise.resolve()
    })
    expect(apiMock.putNodeDocument).not.toHaveBeenCalled()

    await act(async () => {
      vi.advanceTimersByTime(1)
      await Promise.resolve()
      await Promise.resolve()
    })

    expect(apiMock.putNodeDocument).toHaveBeenCalledWith('project-1', 'root', 'frame', '# Updated')
    expect(getNodeDocumentEntry('project-1', 'root', 'frame').savedContent).toBe('# Updated')
  })

  it('preserves the draft when save fails', async () => {
    vi.useFakeTimers()
    apiMock.getNodeDocument.mockResolvedValue(makeDocument('frame', '# Start'))
    apiMock.putNodeDocument.mockRejectedValue(new Error('save failed'))

    await act(async () => {
      await useNodeDocumentStore.getState().loadDocument('project-1', 'root', 'frame')
    })

    act(() => {
      useNodeDocumentStore.getState().updateDraft('project-1', 'root', 'frame', '# Draft')
    })

    await act(async () => {
      vi.advanceTimersByTime(800)
      await Promise.resolve()
      await Promise.resolve()
    })

    const entry = getNodeDocumentEntry('project-1', 'root', 'frame')
    expect(entry.content).toBe('# Draft')
    expect(entry.savedContent).toBe('# Start')
    expect(entry.error).toBe('save failed')
  })
})
