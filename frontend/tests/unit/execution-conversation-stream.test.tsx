import { StrictMode } from 'react'
import { act, render, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { apiMock } = vi.hoisted(() => ({
  apiMock: {
    getExecutionConversation: vi.fn(),
    sendExecutionConversationMessage: vi.fn(),
    continueExecutionConversationMessage: vi.fn(),
    retryExecutionConversationMessage: vi.fn(),
    regenerateExecutionConversationMessage: vi.fn(),
    cancelExecutionConversation: vi.fn(),
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

function makeSnapshot(
  overrides: Partial<ConversationSnapshot> = {},
  recordOverrides: Partial<ConversationSnapshot['record']> = {},
): ConversationSnapshot {
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
      ...recordOverrides,
    },
    messages: [],
    ...overrides,
  }
}

function makeAssistantStreamingSnapshot(streamId = 'stream_1'): ConversationSnapshot {
  return makeSnapshot(
    {
      messages: [
        {
          message_id: 'msg_assistant',
          conversation_id: 'conv_exec_1',
          turn_id: 'turn_1',
          role: 'assistant',
          runtime_mode: 'execute',
          status: 'streaming',
          created_at: '2026-03-15T00:00:01Z',
          updated_at: '2026-03-15T00:00:01Z',
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
              created_at: '2026-03-15T00:00:01Z',
              updated_at: '2026-03-15T00:00:01Z',
              payload: { text: 'Hi' },
            },
          ],
        },
      ],
    },
    {
      active_stream_id: streamId,
      status: 'active',
      event_seq: 1,
      updated_at: '2026-03-15T00:00:01Z',
    },
  )
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
    vi.useRealTimers()
    latestHookState = null
    useConversationStore.setState(useConversationStore.getInitialState())
    apiMock.executionConversationEventsUrl.mockImplementation(
      (projectId: string, nodeId: string, options: { afterEventSeq: number; expectedStreamId?: string | null }) =>
        `/v2/projects/${projectId}/nodes/${nodeId}/conversations/execution/events?after_event_seq=${options.afterEventSeq}&expected_stream_id=${options.expectedStreamId ?? ''}`,
    )
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.restoreAllMocks()
  })

  it('hydrates keyed state from the execution snapshot and disconnects cleanly on unmount', async () => {
    apiMock.getExecutionConversation.mockResolvedValue({
      conversation: makeSnapshot({}, { active_stream_id: 'stream_1', event_seq: 2 }),
    })

    const view = render(<HookHarness projectId="project-1" nodeId="node-1" enabled />)

    await waitFor(() => {
      expect(
        useConversationStore.getState().getConversationIdByScope({
          project_id: 'project-1',
          node_id: 'node-1',
          thread_type: 'execution',
        }),
      ).toBe('conv_exec_1')
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

  it('rejects wrong-stream events after ownership is established', async () => {
    apiMock.getExecutionConversation.mockResolvedValue({
      conversation: makeAssistantStreamingSnapshot('stream_1'),
    })

    render(<HookHarness projectId="project-1" nodeId="node-1" enabled />)

    await waitFor(() => {
      expect(useConversationStore.getState().conversationsById.conv_exec_1.snapshot.record.active_stream_id).toBe(
        'stream_1',
      )
    })

    const [eventSource] = mockEventSources()
    act(() => {
      eventSource.emitOpen()
      eventSource.emitMessage(
        JSON.stringify({
          event_type: 'assistant_text_delta',
          conversation_id: 'conv_exec_1',
          stream_id: 'stream_other',
          event_seq: 2,
          created_at: '2026-03-15T00:00:02Z',
          turn_id: 'turn_1',
          message_id: 'msg_assistant',
          item_id: 'part_assistant',
          payload: {
            part_id: 'part_assistant',
            delta: ' ignored',
            status: 'streaming',
          },
        }),
      )
    })

    const conversation = useConversationStore.getState().conversationsById.conv_exec_1
    expect(conversation.snapshot.record.event_seq).toBe(1)
    expect(conversation.snapshot.record.active_stream_id).toBe('stream_1')
    expect(conversation.snapshot.messages[0]?.parts[0]?.payload).toMatchObject({ text: 'Hi' })
  })

  it('reconnects snapshot-first with refreshed cursor metadata and ignores stale event sequences', async () => {
    let resolveReconnectSnapshot: (() => void) | null = null
    apiMock.getExecutionConversation
      .mockResolvedValueOnce({
        conversation: makeSnapshot({}, { active_stream_id: 'stream_1', event_seq: 2 }),
      })
      .mockImplementationOnce(
        () =>
          new Promise((resolve) => {
            resolveReconnectSnapshot = () =>
              resolve({
                conversation: makeSnapshot(
                  {
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
                  },
                  {
                    active_stream_id: 'stream_2',
                    event_seq: 4,
                    updated_at: '2026-03-15T00:00:04Z',
                  },
                ),
              })
          }),
      )

    render(<HookHarness projectId="project-1" nodeId="node-1" enabled />)

    await waitFor(() => {
      expect(useConversationStore.getState().conversationsById.conv_exec_1.snapshot.record.event_seq).toBe(
        2,
      )
    })

    vi.useFakeTimers()
    vi.spyOn(Math, 'random').mockReturnValue(0.5)

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
      vi.advanceTimersByTime(250)
      await Promise.resolve()
    })

    await act(async () => {
      resolveReconnectSnapshot?.()
      await Promise.resolve()
    })

    expect(mockEventSources()).toHaveLength(2)
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

  it('exposes send through execution-v2 and patches active_stream_id after accepted response', async () => {
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

    const conversation = useConversationStore.getState().conversationsById.conv_exec_1
    expect(apiMock.sendExecutionConversationMessage).toHaveBeenCalledWith(
      'project-1',
      'node-1',
      'Ship Phase 3.1',
    )
    expect(conversation.isSending).toBe(false)
    expect(conversation.error).toBeNull()
    expect(conversation.snapshot.record.active_stream_id).toBe('stream_1')
    expect(conversation.snapshot.record.status).toBe('active')
    expect(conversation.snapshot.record.event_seq).toBe(0)
  })

  it('patches supersession locally after an accepted regenerate action', async () => {
    apiMock.getExecutionConversation.mockResolvedValue({
      conversation: makeSnapshot({
        messages: [
          {
            message_id: 'msg_user',
            conversation_id: 'conv_exec_1',
            turn_id: 'turn_1',
            role: 'user',
            runtime_mode: 'execute',
            status: 'completed',
            created_at: '2026-03-15T00:00:01Z',
            updated_at: '2026-03-15T00:00:01Z',
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
                created_at: '2026-03-15T00:00:01Z',
                updated_at: '2026-03-15T00:00:01Z',
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
            status: 'completed',
            created_at: '2026-03-15T00:00:02Z',
            updated_at: '2026-03-15T00:00:02Z',
            lineage: { parent_message_id: 'msg_user' },
            usage: null,
            error: null,
            parts: [
              {
                part_id: 'part_assistant',
                part_type: 'assistant_text',
                status: 'completed',
                order: 0,
                item_key: null,
                created_at: '2026-03-15T00:00:02Z',
                updated_at: '2026-03-15T00:00:02Z',
                payload: { text: 'Initial answer' },
              },
            ],
          },
        ],
      }),
    })
    apiMock.regenerateExecutionConversationMessage.mockResolvedValue({
      conversation_id: 'conv_exec_1',
      action: 'regenerate',
      action_status: 'accepted',
      target_message_id: 'msg_assistant',
      new_message_id: 'msg_regenerated',
      stream_id: 'stream_regenerated',
      turn_id: 'turn_2',
      assistant_text_part_id: 'part_regenerated',
    })

    render(<HookHarness projectId="project-1" nodeId="node-1" enabled />)

    await waitFor(() => {
      expect(latestHookState?.conversationId).toBe('conv_exec_1')
    })

    await act(async () => {
      await latestHookState?.regenerateFromMessage('msg_assistant')
    })

    const conversation = useConversationStore.getState().conversationsById.conv_exec_1
    const targetMessage =
      conversation.snapshot.messages.find((message) => message.message_id === 'msg_assistant') ?? null

    expect(apiMock.regenerateExecutionConversationMessage).toHaveBeenCalledWith(
      'project-1',
      'node-1',
      'msg_assistant',
    )
    expect(conversation.snapshot.record.active_stream_id).toBe('stream_regenerated')
    expect(conversation.snapshot.record.status).toBe('active')
    expect(targetMessage?.status).toBe('superseded')
    expect(targetMessage?.lineage.superseded_by_message_id).toBe('msg_regenerated')
  })

  it('surfaces initial snapshot failures without opening SSE', async () => {
    apiMock.getExecutionConversation.mockRejectedValue(new Error('snapshot failed'))

    render(<HookHarness projectId="project-1" nodeId="node-1" enabled />)

    await waitFor(() => {
      expect(latestHookState?.bootstrapStatus).toBe('error')
    })

    expect(latestHookState?.bootstrapError).toBe('snapshot failed')
    expect(mockEventSources()).toHaveLength(0)
  })

  it('surfaces send failures as scoped send errors without corrupting conversation state', async () => {
    apiMock.getExecutionConversation.mockResolvedValue({
      conversation: makeSnapshot(),
    })
    apiMock.sendExecutionConversationMessage.mockRejectedValue(new Error('send failed'))

    render(<HookHarness projectId="project-1" nodeId="node-1" enabled />)

    await waitFor(() => {
      expect(latestHookState?.conversationId).toBe('conv_exec_1')
    })

    let thrown: unknown = null
    await act(async () => {
      try {
        await latestHookState?.send('Ship Phase 3.1')
      } catch (error) {
        thrown = error
      }
    })

    const conversation = useConversationStore.getState().conversationsById.conv_exec_1
    expect(thrown).toBeInstanceOf(Error)
    expect((thrown as Error).message).toBe('send failed')
    expect(conversation.isSending).toBe(false)
    expect(conversation.error).toBe('send failed')
    expect(conversation.errorKind).toBe('send')
    expect(conversation.snapshot.record.active_stream_id).toBeNull()
  })

  it('bounds reconnect retries and ends in reconnect_exhausted terminal state', async () => {
    apiMock.getExecutionConversation
      .mockResolvedValueOnce({
        conversation: makeAssistantStreamingSnapshot('stream_1'),
      })
      .mockRejectedValue(new Error('reconnect failed'))

    render(<HookHarness projectId="project-1" nodeId="node-1" enabled />)

    await waitFor(() => {
      expect(useConversationStore.getState().conversationsById.conv_exec_1.snapshot.record.active_stream_id).toBe(
        'stream_1',
      )
    })

    vi.useFakeTimers()
    vi.spyOn(Math, 'random').mockReturnValue(0.5)

    const [eventSource] = mockEventSources()
    act(() => {
      eventSource.emitOpen()
      eventSource.emitError()
    })

    for (const delay of [250, 500, 1_000, 2_000, 4_000]) {
      await act(async () => {
        vi.advanceTimersByTime(delay)
        await Promise.resolve()
      })
    }

    const conversation = useConversationStore.getState().conversationsById.conv_exec_1
    expect(conversation.connectionStatus).toBe('error')
    expect(conversation.errorKind).toBe('reconnect_exhausted')
    expect(conversation.error).toBe('reconnect failed')
  })

  it('cleans up stale scope callbacks when project or node changes', async () => {
    apiMock.getExecutionConversation
      .mockResolvedValueOnce({
        conversation: makeSnapshot(),
      })
      .mockResolvedValueOnce({
        conversation: makeSnapshot(
          {},
          {
            conversation_id: 'conv_exec_2',
            node_id: 'node-2',
          },
        ),
      })

    const view = render(<HookHarness projectId="project-1" nodeId="node-1" enabled />)

    await waitFor(() => {
      expect(latestHookState?.conversationId).toBe('conv_exec_1')
    })

    const [firstStream] = mockEventSources()

    view.rerender(<HookHarness projectId="project-1" nodeId="node-2" enabled />)

    await waitFor(() => {
      expect(useConversationStore.getState().getConversationIdByScope({
        project_id: 'project-1',
        node_id: 'node-2',
        thread_type: 'execution',
      })).toBe('conv_exec_2')
    })

    expect(firstStream.readyState).toBe(2)

    act(() => {
      firstStream.emitError()
      firstStream.emitMessage(
        JSON.stringify({
          event_type: 'message_created',
          conversation_id: 'conv_exec_1',
          stream_id: 'stream_old',
          event_seq: 1,
          created_at: '2026-03-15T00:00:01Z',
          payload: {},
        }),
      )
    })

    expect(apiMock.getExecutionConversation).toHaveBeenCalledTimes(2)
    expect(mockEventSources()).toHaveLength(2)
    expect(mockEventSources()[1].url).toContain('/nodes/node-2/')
  })

  it('keeps EventSource cleanup idempotent under StrictMode mounting', async () => {
    apiMock.getExecutionConversation.mockResolvedValue({
      conversation: makeSnapshot(),
    })

    const view = render(
      <StrictMode>
        <HookHarness projectId="project-1" nodeId="node-1" enabled />
      </StrictMode>,
    )

    await waitFor(() => {
      expect(apiMock.getExecutionConversation).toHaveBeenCalled()
    })

    expect(mockEventSources().filter((source) => source.readyState !== 2)).toHaveLength(1)

    view.unmount()

    expect(mockEventSources().every((source) => source.readyState === 2)).toBe(true)
  })

  it('keeps accepted-send metadata and snapshot-first reconnect recovery coherent', async () => {
    apiMock.getExecutionConversation
      .mockResolvedValueOnce({
        conversation: makeSnapshot(),
      })
      .mockResolvedValueOnce({
        conversation: makeAssistantStreamingSnapshot('stream_server'),
      })
    apiMock.sendExecutionConversationMessage.mockResolvedValue({
      status: 'accepted',
      conversation_id: 'conv_exec_1',
      turn_id: 'turn_1',
      stream_id: 'stream_local',
      user_message_id: 'msg_user',
      assistant_message_id: 'msg_assistant',
      assistant_text_part_id: 'part_assistant',
    })

    render(<HookHarness projectId="project-1" nodeId="node-1" enabled />)

    await waitFor(() => {
      expect(latestHookState?.conversationId).toBe('conv_exec_1')
    })

    vi.useFakeTimers()
    vi.spyOn(Math, 'random').mockReturnValue(0.5)

    await act(async () => {
      await latestHookState?.send('Ship Phase 3.1')
    })

    expect(useConversationStore.getState().conversationsById.conv_exec_1.snapshot.record.active_stream_id).toBe(
      'stream_local',
    )

    const [eventSource] = mockEventSources()
    act(() => {
      eventSource.emitOpen()
      eventSource.emitError()
    })

    await act(async () => {
      vi.advanceTimersByTime(250)
      await Promise.resolve()
    })

    expect(mockEventSources()).toHaveLength(2)

    expect(useConversationStore.getState().conversationsById.conv_exec_1.snapshot.record.active_stream_id).toBe(
      'stream_server',
    )
  })
})
