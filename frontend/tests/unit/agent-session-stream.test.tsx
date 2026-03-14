import { act, render, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { apiMock } = vi.hoisted(() => ({
  apiMock: {
    agentEventsUrl: vi.fn(),
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

import { useAgentEventStream } from '../../src/api/hooks'
import type { AgentEvent } from '../../src/api/types'
import { useProjectStore } from '../../src/stores/project-store'

type MockEventSourceInstance = {
  readyState: number
  close: () => void
  emitOpen: () => void
  emitError: () => void
  emitMessage: (data: string) => void
}

function HookHarness({ projectId, nodeId }: { projectId: string | null; nodeId: string | null }) {
  useAgentEventStream(projectId, nodeId)
  return null
}

function mockEventSources(): MockEventSourceInstance[] {
  return (globalThis.EventSource as unknown as { instances: MockEventSourceInstance[] }).instances
}

describe('useAgentEventStream', () => {
  beforeEach(() => {
    useProjectStore.setState(useProjectStore.getInitialState())
    apiMock.agentEventsUrl.mockReturnValue('/v1/projects/project-1/nodes/node-1/agent/events')
  })

  it('buffers agent events until the initial node resync completes and clears on unmount', async () => {
    let resolveResync: (() => void) | null = null
    const resyncNodeArtifacts = vi.fn(
      () =>
        new Promise<void>((resolve) => {
          resolveResync = resolve
        }),
    )
    const applyAgentEvent = vi.fn()
    const clearAgentState = vi.fn()
    const setAgentConnectionStatus = vi.fn()

    useProjectStore.setState({
      ...useProjectStore.getInitialState(),
      resyncNodeArtifacts,
      applyAgentEvent,
      clearAgentState,
      setAgentConnectionStatus,
    })

    const view = render(<HookHarness projectId="project-1" nodeId="node-1" />)
    const [eventSource] = mockEventSources()

    act(() => {
      eventSource.emitOpen()
      eventSource.emitMessage(
        JSON.stringify({
          type: 'operation_progress',
          event_seq: 1,
          node_id: 'node-1',
          operation: 'plan',
          stage: 'thinking',
          message: 'Planner is thinking.',
          timestamp: '2026-03-13T00:00:00Z',
        } satisfies AgentEvent),
      )
    })

    expect(applyAgentEvent).not.toHaveBeenCalled()

    await act(async () => {
      resolveResync?.()
    })

    await waitFor(() => {
      expect(applyAgentEvent).toHaveBeenCalledWith(
        'project-1',
        'node-1',
        expect.objectContaining({
          type: 'operation_progress',
          stage: 'thinking',
        }),
      )
    })

    view.unmount()

    expect(eventSource.readyState).toBe(2)
    expect(clearAgentState).toHaveBeenCalled()
  })

  it('re-syncs the node on reconnect', async () => {
    const resyncNodeArtifacts = vi
      .fn<() => Promise<void>>()
      .mockResolvedValueOnce(undefined)
      .mockResolvedValueOnce(undefined)
    const applyAgentEvent = vi.fn()
    const clearAgentState = vi.fn()
    const setAgentConnectionStatus = vi.fn()

    useProjectStore.setState({
      ...useProjectStore.getInitialState(),
      resyncNodeArtifacts,
      applyAgentEvent,
      clearAgentState,
      setAgentConnectionStatus,
    })

    render(<HookHarness projectId="project-1" nodeId="node-1" />)
    const [eventSource] = mockEventSources()

    await waitFor(() => {
      expect(resyncNodeArtifacts).toHaveBeenCalledTimes(1)
    })

    act(() => {
      eventSource.emitOpen()
      eventSource.emitError()
      eventSource.emitOpen()
    })

    await waitFor(() => {
      expect(resyncNodeArtifacts).toHaveBeenCalledTimes(2)
    })
    expect(setAgentConnectionStatus).toHaveBeenCalledWith('reconnecting')
  })
})
