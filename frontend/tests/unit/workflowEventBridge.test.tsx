import { act, render } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../../src/api/client', () => ({
  appendAuthToken: (url: string) => url,
  buildProjectEventsUrlV2: (projectId: string) => `/v2/projects/${projectId}/events`,
}))

import { useWorkflowEventBridge } from '../../src/features/conversation/state/workflowEventBridge'
import { useDetailStateStore } from '../../src/stores/detail-state-store'

type EventSourceMockInstance = {
  url: string
  readyState: number
  emitOpen: () => void
  emitMessage: (data: string) => void
  emitError: () => void
  close: () => void
}

type EventSourceMockClass = {
  instances: EventSourceMockInstance[]
}

function getEventSourceMock(): EventSourceMockClass {
  return globalThis.EventSource as unknown as EventSourceMockClass
}

function WorkflowBridgeHarness({
  projectId = 'project-1',
  nodeId = 'node-1',
  enabled = true,
}: {
  projectId?: string | null
  nodeId?: string | null
  enabled?: boolean
}) {
  useWorkflowEventBridge(projectId, nodeId, enabled)
  return null
}

describe('workflowEventBridge', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    useDetailStateStore.setState(useDetailStateStore.getInitialState())
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('refreshes execution state for matching workflow and invalidate events', async () => {
    const refreshExecutionState = vi.fn().mockResolvedValue(undefined)
    useDetailStateStore.setState({
      refreshExecutionState,
    } as Partial<ReturnType<typeof useDetailStateStore.getState>>)

    render(<WorkflowBridgeHarness />)

    const eventSource = getEventSourceMock().instances[0]

    await act(async () => {
      eventSource.emitMessage(
        JSON.stringify({
          eventId: 'evt-workflow',
          channel: 'workflow',
          projectId: 'project-1',
          nodeId: 'node-1',
          occurredAt: '2026-03-28T00:00:00Z',
          type: 'node.workflow.updated',
          payload: {
            projectId: 'project-1',
            nodeId: 'node-1',
            executionState: 'completed',
          },
        }),
      )
      eventSource.emitMessage(
        JSON.stringify({
          eventId: 'evt-invalidate',
          channel: 'workflow',
          projectId: 'project-1',
          nodeId: 'node-1',
          occurredAt: '2026-03-28T00:00:01Z',
          type: 'node.detail.invalidate',
          payload: {
            projectId: 'project-1',
            nodeId: 'node-1',
            reason: 'execution_completed',
          },
        }),
      )
      await Promise.resolve()
    })

    expect(refreshExecutionState).toHaveBeenCalledTimes(2)
    expect(refreshExecutionState).toHaveBeenNthCalledWith(1, 'project-1', 'node-1')
    expect(refreshExecutionState).toHaveBeenNthCalledWith(2, 'project-1', 'node-1')
  })

  it('ignores workflow events for other targets or malformed payloads', async () => {
    const refreshExecutionState = vi.fn().mockResolvedValue(undefined)
    useDetailStateStore.setState({
      refreshExecutionState,
    } as Partial<ReturnType<typeof useDetailStateStore.getState>>)

    render(<WorkflowBridgeHarness />)

    const eventSource = getEventSourceMock().instances[0]

    await act(async () => {
      eventSource.emitMessage(
        JSON.stringify({
          eventId: 'evt-other-node',
          channel: 'workflow',
          projectId: 'project-1',
          nodeId: 'node-2',
          occurredAt: '2026-03-28T00:00:00Z',
          type: 'node.workflow.updated',
          payload: {
            projectId: 'project-1',
            nodeId: 'node-2',
            executionState: 'completed',
          },
        }),
      )
      eventSource.emitMessage('not-json')
      await Promise.resolve()
    })

    expect(refreshExecutionState).not.toHaveBeenCalled()
  })

  it('reconnects after workflow stream errors and closes on unmount', async () => {
    vi.useFakeTimers()

    const refreshExecutionState = vi.fn().mockResolvedValue(undefined)
    useDetailStateStore.setState({
      refreshExecutionState,
    } as Partial<ReturnType<typeof useDetailStateStore.getState>>)

    const view = render(<WorkflowBridgeHarness />)

    const EventSourceMock = getEventSourceMock()
    const firstEventSource = EventSourceMock.instances[0]

    await act(async () => {
      firstEventSource.emitError()
      await vi.advanceTimersByTimeAsync(1000)
    })

    expect(EventSourceMock.instances).toHaveLength(2)
    expect(firstEventSource.readyState).toBe(2)

    const secondEventSource = EventSourceMock.instances[1]
    view.unmount()

    expect(secondEventSource.readyState).toBe(2)
  })
})
