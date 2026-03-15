import { act, render, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { apiMock } = vi.hoisted(() => ({
  apiMock: {
    getExecutionConversation: vi.fn(),
    sendExecutionConversationMessage: vi.fn(),
    executionConversationEventsUrl: vi.fn(),
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

import { useExecutionConversation } from '../../src/features/conversation/hooks/useExecutionConversation'
import type { ConversationSnapshot } from '../../src/features/conversation/types'
import { useConversationStore } from '../../src/stores/conversation-store'

type MockEventSourceInstance = {
  url: string
  readyState: number
  close: () => void
  emitOpen: () => void
  emitError: () => void
  emitMessage: (data: string) => void
}

let latestHookState: ReturnType<typeof useExecutionConversation> | null = null

function makeSnapshot(overrides: Partial<ConversationSnapshot> = {}): ConversationSnapshot {
  return {
    record: {
      conversation_id: 'conv_exec_1',
      project_id: 'project-1',
      node_id: 'node-1',
      thread_type: 'execution',
      app_server_thread_id: null,
      current_runtime_mode: 'execute',
      status: 'idle',
      active_stream_id: null,
      event_seq: 0,
      created_at: '2026-03-15T00:00:00Z',
      updated_at: '2026-03-15T00:00:00Z',
    },
    messages: [],
    ...overrides,
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
  latestHookState = useExecutionConversation({ projectId, nodeId, enabled })
  return null
}

function mockEventSources(): MockEventSourceInstance[] {
  return (globalThis.EventSource as unknown as { instances: MockEventSourceInstance[] }).instances
}

describe('useExecutionConversation', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    latestHookState = null
    useConversationStore.setState(useConversationStore.getInitialState())
    apiMock.executionConversationEventsUrl.mockImplementation(
      (_projectId: string, _nodeId: string, options: { afterEventSeq: number; expectedStreamId?: string | null }) =>
        `/v2/execution/events?after_event_seq=${options.afterEventSeq}&expected_stream_id=${options.expectedStreamId ?? ''}`,
    )
  })

  it('hydrates keyed state from the execution snapshot and disconnects cleanly on unmount', async () => {
    apiMock.getExecutionConversation.mockResolvedValue({
      conversation: makeSnapshot({
        record: {
          ...makeSnapshot().record,
          active_stream_id: 'stream_1',
          event_seq: 2,
        },
      }),
    })

    const view = render(<HookHarness projectId="project-1" nodeId="node-1" enabled />)

    await waitFor(() => {
      expect(useConversationStore.getState().getConversationIdByScope({
        project_id: 'project-1',
        node_id: 'node-1',
        thread_type: 'execution',
      })).toBe('conv_exec_1')
    })

    const [eventSource] = mockEventSources()
    expect(apiMock.getExecutionConversation).toHaveBeenCalledWith('project-1', 'node-1')
    expect(eventSource.url).toContain('after_event_seq=2')
    expect(eventSource.url).toContain('expected_stream_id=stream_1')

    act(() => {
      eventSource.emitOpen()
    })

    await waitFor(() => {
      expect(useConversationStore.getState().conversationsById.conv_exec_1.connectionStatus).toBe(
        'connected',
      )
    })

    view.unmount()

    expect(eventSource.readyState).toBe(2)
    expect(useConversationStore.getState().conversationsById.conv_exec_1.connectionStatus).toBe(
      'disconnected',
    )
  })

  it('reconnects snapshot-first with refreshed cursor metadata and ignores stale event sequences', async () => {
    let resolveReconnectSnapshot: (() => void) | null = null
    apiMock.getExecutionConversation
      .mockResolvedValueOnce({
        conversation: makeSnapshot({
          record: {
            ...makeSnapshot().record,
            active_stream_id: 'stream_1',
            event_seq: 2,
          },
        }),
      })
      .mockImplementationOnce(
        () =>
          new Promise((resolve) => {
            resolveReconnectSnapshot = () =>
              resolve({
                conversation: makeSnapshot({
                  record: {
                    ...makeSnapshot().record,
                    active_stream_id: 'stream_2',
                    event_seq: 4,
                    updated_at: '2026-03-15T00:00:04Z',
                  },
                  messages: [
                    {
                      message_id: 'msg_user',
                      conversation_id: 'conv_exec_1',
                      turn_id: 'turn_1',
                      role: 'user',
                      runtime_mode: 'execute',
                      status: 'completed',
                      created_at: '2026-03-15T00:00:03Z',
                      updated_at: '2026-03-15T00:00:03Z',
                      lineage: {},
                      usage: null,
                      error: null,
                      parts: [
                        {
                          part_id: 'part_user',
                          part_type: 'user_text',
                          status: 'completed',
                          order: 0,
                          item_key: null,
                          created_at: '2026-03-15T00:00:03Z',
                          updated_at: '2026-03-15T00:00:03Z',
                          payload: { text: 'Hello' },
                        },
                      ],
                    },
                    {
                      message_id: 'msg_assistant',
                      conversation_id: 'conv_exec_1',
                      turn_id: 'turn_1',
                      role: 'assistant',
                      runtime_mode: 'execute',
                      status: 'streaming',
                      created_at: '2026-03-15T00:00:03Z',
                      updated_at: '2026-03-15T00:00:04Z',
                      lineage: {},
                      usage: null,
                      error: null,
                      parts: [
                        {
                          part_id: 'part_assistant',
                          part_type: 'assistant_text',
                          status: 'streaming',
                          order: 0,
                          item_key: null,
                          created_at: '2026-03-15T00:00:03Z',
                          updated_at: '2026-03-15T00:00:04Z',
                          payload: { text: 'Hi' },
                        },
                      ],
                    },
                  ],
                }),
              })
          }),
      )

    render(<HookHarness projectId="project-1" nodeId="node-1" enabled />)

    await waitFor(() => {
      expect(useConversationStore.getState().conversationsById.conv_exec_1.snapshot.record.event_seq).toBe(
        2,
      )
    })

    const [initialStream] = mockEventSources()
    act(() => {
      initialStream.emitOpen()
      initialStream.emitMessage(
        JSON.stringify({
          event_type: 'message_created',
          conversation_id: 'conv_exec_1',
          stream_id: 'stream_1',
          event_seq: 3,
          created_at: '2026-03-15T00:00:03Z',
          turn_id: 'turn_1',
          message_id: 'msg_user',
          payload: {
            message: {
              message_id: 'msg_user',
              conversation_id: 'conv_exec_1',
              turn_id: 'turn_1',
              role: 'user',
              runtime_mode: 'execute',
              status: 'completed',
              created_at: '2026-03-15T00:00:03Z',
              updated_at: '2026-03-15T00:00:03Z',
              lineage: {},
              usage: null,
              error: null,
              parts: [
                {
                  part_id: 'part_user',
                  part_type: 'user_text',
                  status: 'completed',
                  order: 0,
                  item_key: null,
                  created_at: '2026-03-15T00:00:03Z',
                  updated_at: '2026-03-15T00:00:03Z',
                  payload: { text: 'Hello' },
                },
              ],
            },
          },
        }),
      )
      initialStream.emitError()
    })

    expect(useConversationStore.getState().conversationsById.conv_exec_1.connectionStatus).toBe(
      'reconnecting',
    )

    await act(async () => {
      resolveReconnectSnapshot?.()
    })

    await waitFor(() => {
      expect(mockEventSources()).toHaveLength(2)
    })

    const reconnectStream = mockEventSources()[1]
    expect(reconnectStream.url).toContain('after_event_seq=4')
    expect(reconnectStream.url).toContain('expected_stream_id=stream_2')

    act(() => {
      reconnectStream.emitOpen()
      reconnectStream.emitMessage(
        JSON.stringify({
          event_type: 'assistant_text_delta',
          conversation_id: 'conv_exec_1',
          stream_id: 'stream_2',
          event_seq: 4,
          created_at: '2026-03-15T00:00:04Z',
          turn_id: 'turn_1',
          message_id: 'msg_assistant',
          item_id: 'part_assistant',
          payload: {
            part_id: 'part_assistant',
            delta: ' stale',
            status: 'streaming',
          },
        }),
      )
      reconnectStream.emitMessage(
        JSON.stringify({
          event_type: 'assistant_text_delta',
          conversation_id: 'conv_exec_1',
          stream_id: 'stream_2',
          event_seq: 5,
          created_at: '2026-03-15T00:00:05Z',
          turn_id: 'turn_1',
          message_id: 'msg_assistant',
          item_id: 'part_assistant',
          payload: {
            part_id: 'part_assistant',
            delta: ' there',
            status: 'streaming',
          },
        }),
      )
    })

    const conversation = useConversationStore.getState().conversationsById.conv_exec_1
    const assistant = conversation.snapshot.messages.find(
      (message) => message.message_id === 'msg_assistant',
    )
    expect(conversation.snapshot.record.event_seq).toBe(5)
    expect(assistant?.parts[0].payload).toMatchObject({
      text: 'Hi there',
      content: 'Hi there',
    })
  })

  it('sends through the execution-v2 route and updates sending state', async () => {
    apiMock.getExecutionConversation.mockResolvedValue({
      conversation: makeSnapshot(),
    })
    apiMock.sendExecutionConversationMessage.mockResolvedValue({
      status: 'accepted',
      conversation_id: 'conv_exec_1',
      turn_id: 'turn_1',
      stream_id: 'stream_1',
      user_message_id: 'msg_user',
      assistant_message_id: 'msg_assistant',
      assistant_text_part_id: 'part_assistant',
    })

    render(<HookHarness projectId="project-1" nodeId="node-1" enabled />)

    await waitFor(() => {
      expect(latestHookState?.conversationId).toBe('conv_exec_1')
    })

    await act(async () => {
      await latestHookState?.send('Ship Phase 3.1')
    })

    expect(apiMock.sendExecutionConversationMessage).toHaveBeenCalledWith(
      'project-1',
      'node-1',
      'Ship Phase 3.1',
    )
    expect(useConversationStore.getState().conversationsById.conv_exec_1.isSending).toBe(false)
    expect(useConversationStore.getState().conversationsById.conv_exec_1.error).toBeNull()
  })
})
