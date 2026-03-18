import { StrictMode } from 'react'
import { act, render, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { apiMock } = vi.hoisted(() => ({
  apiMock: {
    getAskConversation: vi.fn(),
    sendAskConversationMessage: vi.fn(),
    askConversationEventsUrl: vi.fn(),
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

import { useAskConversation } from '../../src/features/conversation/hooks/useAskConversation'
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

let latestHookState: ReturnType<typeof useAskConversation> | null = null

function makeSnapshot(
  overrides: Partial<ConversationSnapshot> = {},
  recordOverrides: Partial<ConversationSnapshot['record']> = {},
): ConversationSnapshot {
  return {
    record: {
      conversation_id: 'conv_ask_1',
      project_id: 'project-1',
      node_id: 'node-1',
      thread_type: 'ask',
      app_server_thread_id: null,
      current_runtime_mode: 'ask',
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

function makeAssistantStreamingSnapshot(streamId = 'ask_stream:turn_1'): ConversationSnapshot {
  const derivedTurnId = streamId.includes(':') ? streamId.split(':').at(-1) ?? 'turn_1' : 'turn_1'
  return makeSnapshot(
    {
      messages: [
        {
          message_id: 'msg_assistant',
          conversation_id: 'conv_ask_1',
          turn_id: derivedTurnId,
          role: 'assistant',
          runtime_mode: 'ask',
          status: 'streaming',
          created_at: '2026-03-15T00:00:01Z',
          updated_at: '2026-03-15T00:00:01Z',
          lineage: {},
          usage: null,
          error: null,
          parts: [
            {
              part_id: 'ask_part:msg_assistant:assistant_text',
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
      event_seq: 6,
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
  latestHookState = useAskConversation({ projectId, nodeId, enabled })
  return null
}

function mockEventSources(): MockEventSourceInstance[] {
  return (globalThis.EventSource as unknown as { instances: MockEventSourceInstance[] }).instances
}

describe('useAskConversation', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.useRealTimers()
    latestHookState = null
    useConversationStore.setState(useConversationStore.getInitialState())
    apiMock.askConversationEventsUrl.mockImplementation(
      (
        projectId: string,
        nodeId: string,
        options: { afterEventSeq: number; expectedStreamId?: string | null },
      ) =>
        `/v2/projects/${projectId}/nodes/${nodeId}/conversations/ask/events?after_event_seq=${options.afterEventSeq}&expected_stream_id=${options.expectedStreamId ?? ''}`,
    )
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.restoreAllMocks()
  })

  it('hydrates keyed state from the ask snapshot and disconnects cleanly on unmount', async () => {
    apiMock.getAskConversation.mockResolvedValue({
      conversation: makeSnapshot({}, { active_stream_id: 'ask_stream:turn_1', event_seq: 3 }),
    })

    const view = render(<HookHarness projectId="project-1" nodeId="node-1" enabled />)

    await waitFor(() => {
      expect(
        useConversationStore.getState().getConversationIdByScope({
          project_id: 'project-1',
          node_id: 'node-1',
          thread_type: 'ask',
        }),
      ).toBe('conv_ask_1')
    })

    const [eventSource] = mockEventSources()
    expect(apiMock.getAskConversation).toHaveBeenCalledWith('project-1', 'node-1')
    expect(eventSource.url).toContain('after_event_seq=3')
    expect(eventSource.url).toContain('expected_stream_id=ask_stream:turn_1')

    act(() => {
      eventSource.emitOpen()
    })

    await waitFor(() => {
      expect(useConversationStore.getState().conversationsById.conv_ask_1.connectionStatus).toBe(
        'connected',
      )
    })

    view.unmount()

    expect(eventSource.readyState).toBe(2)
    expect(useConversationStore.getState().conversationsById.conv_ask_1.connectionStatus).toBe(
      'disconnected',
    )
  })

  it('exposes send through ask-v2 and patches active_stream_id after accepted response', async () => {
    apiMock.getAskConversation.mockResolvedValue({
      conversation: makeSnapshot(),
    })
    apiMock.sendAskConversationMessage.mockResolvedValue({
      status: 'accepted',
      conversation_id: 'conv_ask_1',
      turn_id: 'turn_1',
      stream_id: 'ask_stream:turn_1',
      user_message_id: 'msg_user',
      assistant_message_id: 'msg_assistant',
      assistant_text_part_id: 'ask_part:msg_assistant:assistant_text',
    })

    render(<HookHarness projectId="project-1" nodeId="node-1" enabled />)

    await waitFor(() => {
      expect(latestHookState?.conversationId).toBe('conv_ask_1')
    })

    await act(async () => {
      await latestHookState?.send('Clarify the scope')
    })

    const conversation = useConversationStore.getState().conversationsById.conv_ask_1
    expect(apiMock.sendAskConversationMessage).toHaveBeenCalledWith(
      'project-1',
      'node-1',
      'Clarify the scope',
    )
    expect(conversation.isSending).toBe(false)
    expect(conversation.error).toBeNull()
    expect(conversation.snapshot.record.active_stream_id).toBe('ask_stream:turn_1')
    expect(conversation.snapshot.record.status).toBe('active')
  })

  it('supports explicit refresh after reset and rehydrates the same ask scope deterministically', async () => {
    apiMock.getAskConversation
      .mockResolvedValueOnce({
        conversation: makeSnapshot(
          {
            messages: [
              {
                message_id: 'msg_old',
                conversation_id: 'conv_ask_1',
                turn_id: 'turn_old',
                role: 'assistant',
                runtime_mode: 'ask',
                status: 'completed',
                created_at: '2026-03-15T00:00:01Z',
                updated_at: '2026-03-15T00:00:01Z',
                lineage: {},
                usage: null,
                error: null,
                parts: [
                  {
                    part_id: 'ask_part:msg_old:assistant_text',
                    part_type: 'assistant_text',
                    status: 'completed',
                    order: 0,
                    item_key: null,
                    created_at: '2026-03-15T00:00:01Z',
                    updated_at: '2026-03-15T00:00:01Z',
                    payload: { text: 'Old ask transcript' },
                  },
                ],
              },
            ],
          },
          { event_seq: 9, status: 'completed' },
        ),
      })
      .mockResolvedValueOnce({
        conversation: makeSnapshot({}, { event_seq: 12, status: 'idle' }),
      })

    render(<HookHarness projectId="project-1" nodeId="node-1" enabled />)

    await waitFor(() => {
      expect(latestHookState?.conversationId).toBe('conv_ask_1')
    })
    expect(
      useConversationStore.getState().conversationsById.conv_ask_1.snapshot.messages[0]?.message_id,
    ).toBe('msg_old')

    await act(async () => {
      latestHookState?.refresh()
    })

    await waitFor(() => {
      expect(apiMock.getAskConversation).toHaveBeenCalledTimes(2)
    })
    expect(useConversationStore.getState().conversationsById.conv_ask_1.snapshot.record.event_seq).toBe(12)
    expect(useConversationStore.getState().conversationsById.conv_ask_1.snapshot.messages).toEqual([])
  })

  it('ignores an older refresh result after the mounted ask scope switches', async () => {
    let resolveRefresh: ((value: { conversation: ConversationSnapshot }) => void) | null = null
    apiMock.getAskConversation
      .mockResolvedValueOnce({
        conversation: makeSnapshot({}, { event_seq: 2, status: 'active', active_stream_id: 'ask_stream:turn_1' }),
      })
      .mockImplementationOnce(
        () =>
          new Promise((resolve) => {
            resolveRefresh = resolve
          }),
      )
      .mockResolvedValueOnce({
        conversation: makeSnapshot(
          {},
          {
            conversation_id: 'conv_ask_2',
            node_id: 'node-2',
            event_seq: 4,
            status: 'idle',
          },
        ),
      })

    const view = render(<HookHarness projectId="project-1" nodeId="node-1" enabled />)

    await waitFor(() => {
      expect(latestHookState?.conversationId).toBe('conv_ask_1')
    })

    await act(async () => {
      latestHookState?.refresh()
    })

    view.rerender(<HookHarness projectId="project-1" nodeId="node-2" enabled />)

    await waitFor(() => {
      expect(
        useConversationStore.getState().getConversationIdByScope({
          project_id: 'project-1',
          node_id: 'node-2',
          thread_type: 'ask',
        }),
      ).toBe('conv_ask_2')
    })

    await act(async () => {
      resolveRefresh?.({
        conversation: makeSnapshot(
          {
            messages: [
              {
                message_id: 'msg_stale',
                conversation_id: 'conv_ask_1',
                turn_id: 'turn_old',
                role: 'assistant',
                runtime_mode: 'ask',
                status: 'completed',
                created_at: '2026-03-15T00:00:01Z',
                updated_at: '2026-03-15T00:00:09Z',
                lineage: {},
                usage: null,
                error: null,
                parts: [
                  {
                    part_id: 'ask_part:msg_stale:assistant_text',
                    part_type: 'assistant_text',
                    status: 'completed',
                    order: 0,
                    item_key: null,
                    created_at: '2026-03-15T00:00:01Z',
                    updated_at: '2026-03-15T00:00:09Z',
                    payload: { text: 'stale refresh result' },
                  },
                ],
              },
            ],
          },
          { event_seq: 9, status: 'completed' },
        ),
      })
      await Promise.resolve()
    })

    expect(latestHookState?.conversationId).toBe('conv_ask_2')
    expect(useConversationStore.getState().conversationsById.conv_ask_2.snapshot.record.event_seq).toBe(4)
    expect(useConversationStore.getState().conversationsById.conv_ask_1.snapshot.record.event_seq).toBe(2)
    expect(useConversationStore.getState().conversationsById.conv_ask_1.snapshot.messages).toEqual([])
  })

  it('reconnects snapshot-first and ignores stale event sequences after rehydrate', async () => {
    let resolveReconnectSnapshot: (() => void) | null = null
    apiMock.getAskConversation
      .mockResolvedValueOnce({
        conversation: makeSnapshot({}, { active_stream_id: 'ask_stream:turn_1', event_seq: 3 }),
      })
      .mockImplementationOnce(
        () =>
          new Promise((resolve) => {
            resolveReconnectSnapshot = () =>
              resolve({
                conversation: makeAssistantStreamingSnapshot('ask_stream:turn_2'),
              })
          }),
      )

    render(<HookHarness projectId="project-1" nodeId="node-1" enabled />)

    await waitFor(() => {
      expect(useConversationStore.getState().conversationsById.conv_ask_1.snapshot.record.event_seq).toBe(3)
    })

    vi.useFakeTimers()
    vi.spyOn(Math, 'random').mockReturnValue(0.5)

    const [initialStream] = mockEventSources()
    act(() => {
      initialStream.emitOpen()
      initialStream.emitError()
    })

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
    expect(reconnectStream.url).toContain('after_event_seq=6')
    expect(reconnectStream.url).toContain('expected_stream_id=ask_stream:turn_2')

    act(() => {
      reconnectStream.emitOpen()
      reconnectStream.emitMessage(
        JSON.stringify({
          event_type: 'assistant_text_delta',
          conversation_id: 'conv_ask_1',
          stream_id: 'ask_stream:turn_2',
          event_seq: 6,
          created_at: '2026-03-15T00:00:04Z',
          turn_id: 'turn_2',
          message_id: 'msg_assistant',
          item_id: 'ask_part:msg_assistant:assistant_text',
          payload: {
            part_id: 'ask_part:msg_assistant:assistant_text',
            delta: ' stale',
            status: 'streaming',
          },
        }),
      )
      reconnectStream.emitMessage(
        JSON.stringify({
          event_type: 'assistant_text_delta',
          conversation_id: 'conv_ask_1',
          stream_id: 'ask_stream:turn_2',
          event_seq: 7,
          created_at: '2026-03-15T00:00:05Z',
          turn_id: 'turn_2',
          message_id: 'msg_assistant',
          item_id: 'ask_part:msg_assistant:assistant_text',
          payload: {
            part_id: 'ask_part:msg_assistant:assistant_text',
            delta: ' there',
            status: 'streaming',
          },
        }),
      )
    })

    const conversation = useConversationStore.getState().conversationsById.conv_ask_1
    expect(conversation.snapshot.record.event_seq).toBe(7)
    expect(conversation.snapshot.messages[0]?.parts[0]?.payload).toMatchObject({
      text: 'Hi there',
      content: 'Hi there',
    })
  })

  it('keeps EventSource cleanup idempotent under StrictMode mounting', async () => {
    apiMock.getAskConversation.mockResolvedValue({
      conversation: makeSnapshot(),
    })

    const view = render(
      <StrictMode>
        <HookHarness projectId="project-1" nodeId="node-1" enabled />
      </StrictMode>,
    )

    await waitFor(() => {
      expect(apiMock.getAskConversation).toHaveBeenCalled()
    })

    expect(mockEventSources().filter((source) => source.readyState !== 2)).toHaveLength(1)

    view.unmount()

    expect(mockEventSources().every((source) => source.readyState === 2)).toBe(true)
  })
})
