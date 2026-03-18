import { act, render, screen, waitFor } from '@testing-library/react'
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

import { ConversationSurface } from '../../src/features/conversation/components/ConversationSurface'
import { useExecutionConversation } from '../../src/features/conversation/hooks/useExecutionConversation'
import { useConversationRequests } from '../../src/features/conversation/hooks/useConversationRequests'
import { buildConversationRenderModel } from '../../src/features/conversation/model/buildConversationRenderModel'
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

function makeDurableRecoveredSnapshot(): ConversationSnapshot {
  return makeSnapshot(
    {
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
              payload: { text: 'Need an answer' },
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
          updated_at: '2026-03-15T00:00:03Z',
          lineage: {},
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
              updated_at: '2026-03-15T00:00:03Z',
              payload: { text: 'Answer ready', content: 'Answer ready' },
            },
          ],
        },
        {
          message_id: 'msg_exec_request:req_1',
          conversation_id: 'conv_exec_1',
          turn_id: 'turn_1',
          role: 'assistant',
          runtime_mode: 'execute',
          status: 'pending',
          created_at: '2026-03-15T00:00:04Z',
          updated_at: '2026-03-15T00:00:04Z',
          lineage: {},
          usage: null,
          error: null,
          parts: [
            {
              part_id: 'msg_exec_request:req_1:user_input_request',
              part_type: 'user_input_request',
              status: 'pending',
              order: 0,
              item_key: 'req_1',
              created_at: '2026-03-15T00:00:04Z',
              updated_at: '2026-03-15T00:00:04Z',
              payload: {
                part_id: 'msg_exec_request:req_1:user_input_request',
                request_id: 'req_1',
                request_kind: 'user_input',
                resolution_state: 'pending',
                title: 'Need runtime input',
                prompt: 'Choose one answer.',
                thread_id: 'thread_exec_1',
                turn_id: 'turn_1',
                item_id: 'item_req_1',
                questions: [],
              },
            },
          ],
        },
      ],
    },
    {
      active_stream_id: 'stream_1',
      status: 'active',
      event_seq: 4,
      updated_at: '2026-03-15T00:00:04Z',
    },
  )
}

function mockEventSources(): MockEventSourceInstance[] {
  return (globalThis.EventSource as unknown as { instances: MockEventSourceInstance[] }).instances
}

function ExecutionConversationRecoveryHarness() {
  const conversationState = useExecutionConversation({
    projectId: 'project-1',
    nodeId: 'node-1',
    enabled: true,
  })
  const requestState = useConversationRequests({
    projectId: 'project-1',
    nodeId: 'node-1',
    conversation: conversationState.conversation,
    refresh: conversationState.refresh,
    resolveRequest: async () => 'resolved',
  })
  const model = buildConversationRenderModel(conversationState.conversation?.snapshot ?? null)

  return (
    <>
      <div data-testid="conversation-id">{conversationState.conversationId ?? 'none'}</div>
      <div data-testid="active-request">{requestState.activeRequest?.requestId ?? 'none'}</div>
      <ConversationSurface
        model={model}
        connectionState={conversationState.conversation?.connectionStatus ?? 'idle'}
        isLoading={conversationState.bootstrapStatus === 'loading_snapshot'}
        errorMessage={conversationState.bootstrapError}
        emptyTitle="No messages yet"
        emptyHint="Start when you are ready."
      />
    </>
  )
}

describe('conversation recovery orchestration', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    useConversationStore.setState(useConversationStore.getInitialState())
    apiMock.executionConversationEventsUrl.mockImplementation(
      (projectId: string, nodeId: string, options: { afterEventSeq: number; expectedStreamId?: string | null }) =>
        `/v2/projects/${projectId}/nodes/${nodeId}/conversations/execution/events?after_event_seq=${options.afterEventSeq}&expected_stream_id=${options.expectedStreamId ?? ''}`,
    )
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('rebuilds the same semantic execution state after remount and ignores stale emissions from the old stream', async () => {
    apiMock.getExecutionConversation
      .mockResolvedValueOnce({
        conversation: makeSnapshot(),
      })
      .mockResolvedValueOnce({
        conversation: makeDurableRecoveredSnapshot(),
      })

    const view = render(<ExecutionConversationRecoveryHarness />)

    await waitFor(() => {
      expect(screen.getByTestId('conversation-id').textContent).toBe('conv_exec_1')
    })

    const [firstStream] = mockEventSources()
    act(() => {
      firstStream.emitOpen()
      firstStream.emitMessage(
        JSON.stringify({
          event_type: 'message_created',
          conversation_id: 'conv_exec_1',
          stream_id: 'stream_1',
          event_seq: 1,
          created_at: '2026-03-15T00:00:01Z',
          turn_id: 'turn_1',
          message_id: 'msg_user',
          payload: {
            message: makeDurableRecoveredSnapshot().messages[0],
          },
        }),
      )
      firstStream.emitMessage(
        JSON.stringify({
          event_type: 'message_created',
          conversation_id: 'conv_exec_1',
          stream_id: 'stream_1',
          event_seq: 2,
          created_at: '2026-03-15T00:00:02Z',
          turn_id: 'turn_1',
          message_id: 'msg_assistant',
          payload: {
            message: {
              ...makeDurableRecoveredSnapshot().messages[1],
              status: 'pending',
              parts: [
                {
                  ...makeDurableRecoveredSnapshot().messages[1].parts[0],
                  status: 'pending',
                  payload: { text: '', content: '' },
                },
              ],
            },
          },
        }),
      )
      firstStream.emitMessage(
        JSON.stringify({
          event_type: 'assistant_text_final',
          conversation_id: 'conv_exec_1',
          stream_id: 'stream_1',
          event_seq: 3,
          created_at: '2026-03-15T00:00:03Z',
          turn_id: 'turn_1',
          message_id: 'msg_assistant',
          item_id: 'part_assistant',
          payload: {
            part_id: 'part_assistant',
            text: 'Answer ready',
            status: 'completed',
          },
        }),
      )
      firstStream.emitMessage(
        JSON.stringify({
          event_type: 'request_user_input',
          conversation_id: 'conv_exec_1',
          stream_id: 'stream_1',
          event_seq: 4,
          created_at: '2026-03-15T00:00:04Z',
          turn_id: 'turn_1',
          payload: {
            message: makeDurableRecoveredSnapshot().messages[2],
          },
        }),
      )
    })

    await waitFor(() => {
      expect(screen.getByText('Answer ready')).toBeInTheDocument()
    })
    expect(screen.getByText('Need runtime input')).toBeInTheDocument()
    expect(screen.getByTestId('active-request').textContent).toBe('req_1')

    view.unmount()

    act(() => {
      firstStream.emitMessage(
        JSON.stringify({
          event_type: 'assistant_text_delta',
          conversation_id: 'conv_exec_1',
          stream_id: 'stream_1',
          event_seq: 5,
          created_at: '2026-03-15T00:00:05Z',
          turn_id: 'turn_1',
          message_id: 'msg_assistant',
          item_id: 'part_assistant',
          payload: {
            part_id: 'part_assistant',
            delta: ' stale delta',
            status: 'streaming',
          },
        }),
      )
    })

    render(<ExecutionConversationRecoveryHarness />)

    await waitFor(() => {
      expect(screen.getByText('Answer ready')).toBeInTheDocument()
    })
    expect(screen.getByText('Need runtime input')).toBeInTheDocument()
    expect(screen.getByTestId('active-request').textContent).toBe('req_1')
    expect(screen.queryByText(/stale delta/)).not.toBeInTheDocument()
  })
})
