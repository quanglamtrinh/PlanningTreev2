import { act, render } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../../src/api/client', () => ({
  appendAuthToken: (url: string) => url,
  buildProjectEventsUrlV3: (projectId: string) => `/v3/projects/${projectId}/events`,
}))

import { useWorkflowEventBridgeV3 } from '../../src/features/conversation/state/workflowEventBridgeV3'
import { useWorkflowStateStoreV3 } from '../../src/features/conversation/state/workflowStateStoreV3'
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
  useWorkflowEventBridgeV3(projectId, nodeId, enabled)
  return null
}

describe('workflowEventBridge', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    useDetailStateStore.setState(useDetailStateStore.getInitialState())
    useWorkflowStateStoreV3.getState().reset()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('refreshes workflow-state on workflow events and detail-state only on invalidate events', async () => {
    const callOrder: string[] = []
    const loadWorkflowState = vi.fn().mockImplementation(async () => {
      callOrder.push('workflow')
      return undefined
    })
    const refreshExecutionState = vi.fn().mockImplementation(async () => {
      callOrder.push('detail')
      return undefined
    })

    useWorkflowStateStoreV3.setState({
      loadWorkflowState,
    } as Partial<ReturnType<typeof useWorkflowStateStoreV3.getState>>)
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
      await Promise.resolve()
      await Promise.resolve()
    })

    expect(callOrder).toEqual(['workflow'])

    await act(async () => {
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
      await Promise.resolve()
    })

    expect(loadWorkflowState).toHaveBeenCalledTimes(2)
    expect(loadWorkflowState).toHaveBeenNthCalledWith(1, 'project-1', 'node-1')
    expect(loadWorkflowState).toHaveBeenNthCalledWith(2, 'project-1', 'node-1')
    expect(refreshExecutionState).toHaveBeenCalledTimes(1)
    expect(refreshExecutionState).toHaveBeenNthCalledWith(1, 'project-1', 'node-1')
    expect(callOrder).toEqual(['workflow', 'workflow', 'detail'])
  })

  it('ignores workflow events for other targets or malformed payloads', async () => {
    const loadWorkflowState = vi.fn().mockResolvedValue(undefined)
    const refreshExecutionState = vi.fn().mockResolvedValue(undefined)
    useWorkflowStateStoreV3.setState({
      loadWorkflowState,
    } as Partial<ReturnType<typeof useWorkflowStateStoreV3.getState>>)
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

    expect(loadWorkflowState).not.toHaveBeenCalled()
    expect(refreshExecutionState).not.toHaveBeenCalled()
  })

  it('reconnects after workflow stream errors and closes on unmount', async () => {
    vi.useFakeTimers()

    const loadWorkflowState = vi.fn().mockResolvedValue(undefined)
    const refreshExecutionState = vi.fn().mockResolvedValue(undefined)
    useWorkflowStateStoreV3.setState({
      loadWorkflowState,
    } as Partial<ReturnType<typeof useWorkflowStateStoreV3.getState>>)
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
