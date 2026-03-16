import { act, render, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { apiMock } = vi.hoisted(() => ({
  apiMock: {
    getPlanningConversation: vi.fn(),
    planningConversationEventsUrl: vi.fn(),
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

import { usePlanningConversation } from '../../src/features/conversation/hooks/usePlanningConversation'
import type { ConversationEventEnvelope, ConversationSnapshot } from '../../src/features/conversation/types'
import { useConversationStore } from '../../src/stores/conversation-store'

type MockEventSourceInstance = {
  url: string
  readyState: number
  close: () => void
  emitOpen: () => void
  emitError: () => void
  emitMessage: (data: string) => void
}

let latestHookState: ReturnType<typeof usePlanningConversation> | null = null

function makeSnapshot(
  overrides: Partial<ConversationSnapshot> = {},
  recordOverrides: Partial<ConversationSnapshot['record']> = {},
): ConversationSnapshot {
  return {
    record: {
      conversation_id: 'conv_plan_1',
      project_id: 'project-1',
      node_id: 'node-1',
      thread_type: 'planning',
      app_server_thread_id: null,
      current_runtime_mode: 'planning',
      status: 'idle',
      active_stream_id: null,
      event_seq: 0,
      created_at: '2026-03-15T00:00:00Z',
      updated_at: '2026-03-15T00:00:00Z',
      ...recordOverrides,
    },
    messages: [],
    ...overrides,
  }
}

function makeActiveSnapshot(): ConversationSnapshot {
  return makeSnapshot(
    {
      messages: [
        {
          message_id: 'planning_msg:turn_1:user',
          conversation_id: 'conv_plan_1',
          turn_id: 'turn_1',
          role: 'user',
          runtime_mode: 'planning',
          status: 'completed',
          created_at: '2026-03-15T00:00:01Z',
          updated_at: '2026-03-15T00:00:01Z',
          lineage: {},
          usage: null,
          error: null,
          parts: [
            {
              part_id: 'planning_part:turn_1:user_text',
              part_type: 'user_text',
              status: 'completed',
              order: 0,
              item_key: null,
              created_at: '2026-03-15T00:00:01Z',
              updated_at: '2026-03-15T00:00:01Z',
              payload: { text: 'Split the node into slices.' },
            },
          ],
        },
        {
          message_id: 'planning_msg:turn_1:assistant',
          conversation_id: 'conv_plan_1',
          turn_id: 'turn_1',
          role: 'assistant',
          runtime_mode: 'planning',
          status: 'pending',
          created_at: '2026-03-15T00:00:01Z',
          updated_at: '2026-03-15T00:00:01Z',
          lineage: {},
          usage: null,
          error: null,
          parts: [
            {
              part_id: 'planning_part:turn_1:assistant_text',
              part_type: 'assistant_text',
              status: 'pending',
              order: 0,
              item_key: null,
              created_at: '2026-03-15T00:00:01Z',
              updated_at: '2026-03-15T00:00:01Z',
              payload: { text: '' },
            },
          ],
        },
      ],
    },
    {
      active_stream_id: 'planning_stream:turn_1',
      status: 'active',
      event_seq: 2,
      updated_at: '2026-03-15T00:00:01Z',
    },
  )
}

function makeCompletedSnapshot(): ConversationSnapshot {
  return makeSnapshot(
    {
      messages: [
        {
          message_id: 'planning_msg:turn_1:user',
          conversation_id: 'conv_plan_1',
          turn_id: 'turn_1',
          role: 'user',
          runtime_mode: 'planning',
          status: 'completed',
          created_at: '2026-03-15T00:00:01Z',
          updated_at: '2026-03-15T00:00:01Z',
          lineage: {},
          usage: null,
          error: null,
          parts: [
            {
              part_id: 'planning_part:turn_1:user_text',
              part_type: 'user_text',
              status: 'completed',
              order: 0,
              item_key: null,
              created_at: '2026-03-15T00:00:01Z',
              updated_at: '2026-03-15T00:00:01Z',
              payload: { text: 'Split the node into slices.' },
            },
          ],
        },
        {
          message_id: 'planning_msg:turn_1:assistant',
          conversation_id: 'conv_plan_1',
          turn_id: 'turn_1',
          role: 'assistant',
          runtime_mode: 'planning',
          status: 'completed',
          created_at: '2026-03-15T00:00:01Z',
          updated_at: '2026-03-15T00:00:03Z',
          lineage: {},
          usage: null,
          error: null,
          parts: [
            {
              part_id: 'planning_part:turn_1:assistant_text',
              part_type: 'assistant_text',
              status: 'completed',
              order: 0,
              item_key: null,
              created_at: '2026-03-15T00:00:01Z',
              updated_at: '2026-03-15T00:00:03Z',
              payload: { text: 'Split completed. Created 2 child tasks.' },
            },
            {
              part_id: 'planning_part:turn_1:tool_call:0',
              part_type: 'tool_call',
              status: 'completed',
              order: 1,
              item_key: null,
              created_at: '2026-03-15T00:00:03Z',
              updated_at: '2026-03-15T00:00:03Z',
              payload: {
                tool_name: 'emit_render_data',
                arguments: { kind: 'split_result', payload: { subtasks: [{ order: 1 }, { order: 2 }] } },
              },
            },
          ],
        },
      ],
    },
    {
      active_stream_id: null,
      status: 'completed',
      event_seq: 5,
      updated_at: '2026-03-15T00:00:03Z',
    },
  )
}

function makeMessageCreatedEvent(message: ConversationSnapshot['messages'][number], eventSeq: number): ConversationEventEnvelope {
  return {
    event_type: 'message_created',
    conversation_id: 'conv_plan_1',
    stream_id: 'planning_stream:turn_1',
    event_seq: eventSeq,
    created_at: '2026-03-15T00:00:01Z',
    turn_id: 'turn_1',
    message_id: message.message_id,
    payload: { message },
  }
}

function HookHarness({
  projectId,
  nodeId,
  enabled,
}: {
  projectId: string | null
  nodeId: string | null
  enabled: boolean
}) {
  latestHookState = usePlanningConversation({ projectId, nodeId, enabled })
  return null
}

function mockEventSources(): MockEventSourceInstance[] {
  return (globalThis.EventSource as unknown as { instances: MockEventSourceInstance[] }).instances
}

describe('usePlanningConversation', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.useRealTimers()
    latestHookState = null
    useConversationStore.setState(useConversationStore.getInitialState())
    apiMock.planningConversationEventsUrl.mockImplementation(
      (
        projectId: string,
        nodeId: string,
        options: { afterEventSeq: number; expectedStreamId?: string | null },
      ) =>
        `/v2/projects/${projectId}/nodes/${nodeId}/conversations/planning/events?after_event_seq=${options.afterEventSeq}&expected_stream_id=${options.expectedStreamId ?? ''}`,
    )
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.restoreAllMocks()
  })

  it('hydrates keyed state from the planning snapshot and disconnects cleanly on unmount', async () => {
    apiMock.getPlanningConversation.mockResolvedValue({
      conversation: makeSnapshot({}, { active_stream_id: 'planning_stream:turn_1', event_seq: 2 }),
    })

    const view = render(<HookHarness projectId="project-1" nodeId="node-1" enabled />)

    await waitFor(() => {
      expect(
        useConversationStore.getState().getConversationIdByScope({
          project_id: 'project-1',
          node_id: 'node-1',
          thread_type: 'planning',
        }),
      ).toBe('conv_plan_1')
    })

    const [eventSource] = mockEventSources()
    expect(apiMock.getPlanningConversation).toHaveBeenCalledWith('project-1', 'node-1')
    expect(eventSource.url).toContain('after_event_seq=2')
    expect(eventSource.url).toContain('expected_stream_id=planning_stream:turn_1')

    act(() => {
      eventSource.emitOpen()
    })

    await waitFor(() => {
      expect(useConversationStore.getState().conversationsById.conv_plan_1.connectionStatus).toBe(
        'connected',
      )
    })

    view.unmount()

    expect(eventSource.readyState).toBe(2)
    expect(useConversationStore.getState().conversationsById.conv_plan_1.connectionStatus).toBe(
      'disconnected',
    )
  })

  it('applies normalized planning message_created events to visible keyed transcript state', async () => {
    apiMock.getPlanningConversation.mockResolvedValue({
      conversation: makeSnapshot(),
    })

    render(<HookHarness projectId="project-1" nodeId="node-1" enabled />)

    await waitFor(() => {
      expect(latestHookState?.conversationId).toBe('conv_plan_1')
    })

    const [eventSource] = mockEventSources()
    const activeSnapshot = makeActiveSnapshot()

    act(() => {
      eventSource.emitOpen()
      eventSource.emitMessage(JSON.stringify(makeMessageCreatedEvent(activeSnapshot.messages[0], 1)))
      eventSource.emitMessage(JSON.stringify(makeMessageCreatedEvent(activeSnapshot.messages[1], 2)))
    })

    await waitFor(() => {
      const conversation = useConversationStore.getState().conversationsById.conv_plan_1
      expect(conversation.snapshot.messages).toHaveLength(2)
      expect(conversation.snapshot.record.active_stream_id).toBe('planning_stream:turn_1')
      expect(conversation.snapshot.record.status).toBe('active')
      expect(conversation.snapshot.messages[1].status).toBe('pending')
    })
  })

  it('triggers a guarded refresh after terminal completion and converges to the refreshed planning snapshot', async () => {
    apiMock.getPlanningConversation
      .mockResolvedValueOnce({
        conversation: makeActiveSnapshot(),
      })
      .mockResolvedValueOnce({
        conversation: makeCompletedSnapshot(),
      })

    render(<HookHarness projectId="project-1" nodeId="node-1" enabled />)

    await waitFor(() => {
      expect(latestHookState?.conversationId).toBe('conv_plan_1')
    })

    const [firstEventSource] = mockEventSources()
    act(() => {
      firstEventSource.emitOpen()
      firstEventSource.emitMessage(
        JSON.stringify({
          event_type: 'assistant_text_final',
          conversation_id: 'conv_plan_1',
          stream_id: 'planning_stream:turn_1',
          event_seq: 3,
          created_at: '2026-03-15T00:00:03Z',
          turn_id: 'turn_1',
          message_id: 'planning_msg:turn_1:assistant',
          item_id: 'planning_part:turn_1:assistant_text',
          payload: {
            part_id: 'planning_part:turn_1:assistant_text',
            text: 'Split completed. Created 2 child tasks.',
            status: 'completed',
          },
        }),
      )
      firstEventSource.emitMessage(
        JSON.stringify({
          event_type: 'completion_status',
          conversation_id: 'conv_plan_1',
          stream_id: 'planning_stream:turn_1',
          event_seq: 4,
          created_at: '2026-03-15T00:00:03Z',
          turn_id: 'turn_1',
          message_id: 'planning_msg:turn_1:assistant',
          payload: {
            status: 'completed',
            finished_at: '2026-03-15T00:00:03Z',
            error: null,
          },
        }),
      )
    })

    await waitFor(() => {
      expect(apiMock.getPlanningConversation).toHaveBeenCalledTimes(2)
    })

    await waitFor(() => {
      const conversation = useConversationStore.getState().conversationsById.conv_plan_1
      expect(conversation.snapshot.record.event_seq).toBe(5)
      expect(conversation.snapshot.record.active_stream_id).toBeNull()
      expect(
        conversation.snapshot.messages[1].parts[0].payload.text,
      ).toBe('Split completed. Created 2 child tasks.')
    })

    const eventSources = mockEventSources()
    expect(eventSources).toHaveLength(2)
    expect(eventSources[1].url).toContain('after_event_seq=5')
  })
})
