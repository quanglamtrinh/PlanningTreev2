import { act, render } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../../src/features/workflow_v2/api/client', () => ({
  openWorkflowEventsStreamV2: (projectId: string) => new EventSource(`/v4/projects/${projectId}/events`),
  parseWorkflowEventV2: (raw: string) => JSON.parse(raw),
}))

import { useWorkflowEventBridgeV2 } from '../../src/features/workflow_v2/hooks/useWorkflowEventBridgeV2'
import { useWorkflowStateStoreV2 } from '../../src/features/workflow_v2/store/workflowStateStoreV2'

type EventSourceMockInstance = {
  url: string
  readyState: number
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
  useWorkflowEventBridgeV2(projectId, nodeId, enabled)
  return null
}

describe('workflowEventBridgeV2', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    useWorkflowStateStoreV2.getState().reset()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('refreshes workflow state on state, action, and artifact events', async () => {
    const loadWorkflowState = vi.fn().mockResolvedValue(undefined)
    useWorkflowStateStoreV2.setState({
      loadWorkflowState,
    } as Partial<ReturnType<typeof useWorkflowStateStoreV2.getState>>)

    render(<WorkflowBridgeHarness />)

    const eventSource = getEventSourceMock().instances[0]
    expect(eventSource.url).toBe('/v4/projects/project-1/events')

    await act(async () => {
      eventSource.emitMessage(
        JSON.stringify({
          eventId: 'evt-state',
          projectId: 'project-1',
          nodeId: 'node-1',
          occurredAt: '2026-04-24T00:00:00Z',
          type: 'workflow/state_changed',
        }),
      )
      eventSource.emitMessage(
        JSON.stringify({
          eventId: 'evt-action-completed',
          projectId: 'project-1',
          nodeId: 'node-1',
          occurredAt: '2026-04-24T00:00:02Z',
          type: 'workflow/action_completed',
        }),
      )
      eventSource.emitMessage(
        JSON.stringify({
          eventId: 'evt-action-failed',
          projectId: 'project-1',
          nodeId: 'node-1',
          occurredAt: '2026-04-24T00:00:03Z',
          type: 'workflow/action_failed',
        }),
      )
      eventSource.emitMessage(
        JSON.stringify({
          eventId: 'evt-artifact',
          projectId: 'project-1',
          nodeId: 'node-1',
          occurredAt: '2026-04-24T00:00:04Z',
          type: 'workflow/artifact_confirmed',
        }),
      )
      await Promise.resolve()
      await Promise.resolve()
    })

    expect(loadWorkflowState).toHaveBeenCalledTimes(4)
    expect(loadWorkflowState).toHaveBeenNthCalledWith(1, 'project-1', 'node-1')
    expect(loadWorkflowState).toHaveBeenNthCalledWith(2, 'project-1', 'node-1')
    expect(loadWorkflowState).toHaveBeenNthCalledWith(3, 'project-1', 'node-1')
    expect(loadWorkflowState).toHaveBeenNthCalledWith(4, 'project-1', 'node-1')
  })

  it('filters other targets and ignores malformed events', async () => {
    const loadWorkflowState = vi.fn().mockResolvedValue(undefined)
    useWorkflowStateStoreV2.setState({
      loadWorkflowState,
    } as Partial<ReturnType<typeof useWorkflowStateStoreV2.getState>>)

    render(<WorkflowBridgeHarness />)

    const eventSource = getEventSourceMock().instances[0]

    await act(async () => {
      eventSource.emitMessage(
        JSON.stringify({
          eventId: 'evt-other-node',
          projectId: 'project-1',
          nodeId: 'node-2',
          occurredAt: '2026-04-24T00:00:00Z',
          type: 'workflow/state_changed',
        }),
      )
      eventSource.emitMessage('not-json')
      await Promise.resolve()
    })

    expect(loadWorkflowState).not.toHaveBeenCalled()
  })

  it('reconnects after stream errors and closes on unmount', async () => {
    vi.useFakeTimers()
    const loadWorkflowState = vi.fn().mockResolvedValue(undefined)
    useWorkflowStateStoreV2.setState({
      loadWorkflowState,
    } as Partial<ReturnType<typeof useWorkflowStateStoreV2.getState>>)

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
