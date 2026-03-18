import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { NodeRecord } from '../../src/api/types'
import { ChatPanel } from '../../src/features/breadcrumb/ChatPanel'
import type { ConversationSnapshot } from '../../src/features/conversation/types'
import { useConversationStore } from '../../src/stores/conversation-store'

function makeNode(overrides: Partial<NodeRecord> = {}): NodeRecord {
  return {
    node_id: 'node-1',
    parent_id: null,
    child_ids: [],
    title: 'Execution Node',
    description: 'Ship the execution flow',
    status: 'ready',
    phase: 'executing',
    node_kind: 'original',
    planning_mode: null,
    depth: 0,
    display_order: 0,
    hierarchical_number: '1',
    split_metadata: null,
    chat_session_id: null,
    has_planning_thread: true,
    has_execution_thread: true,
    planning_thread_status: 'idle',
    execution_thread_status: 'active',
    has_ask_thread: false,
    ask_thread_status: null,
    is_superseded: false,
    created_at: '2026-03-15T00:00:00Z',
    ...overrides,
  }
}

function makeConversationSnapshot(
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
      status: 'completed',
      active_stream_id: null,
      event_seq: 1,
      created_at: '2026-03-15T00:00:00Z',
      updated_at: '2026-03-15T00:00:01Z',
      ...recordOverrides,
    },
    messages: [],
    ...overrides,
  }
}

function makeConversationSnapshotWithAssistantText(text: string): ConversationSnapshot {
  return makeConversationSnapshot({
    messages: [
      {
        message_id: 'msg_assistant_1',
        conversation_id: 'conv_exec_1',
        turn_id: 'turn_1',
        role: 'assistant',
        runtime_mode: 'execute',
        status: 'completed',
        created_at: '2026-03-15T00:00:01Z',
        updated_at: '2026-03-15T00:00:01Z',
        lineage: {},
        usage: null,
        error: null,
        parts: [
          {
            part_id: 'part_assistant_1',
            part_type: 'assistant_text',
            status: 'completed',
            order: 0,
            item_key: null,
            created_at: '2026-03-15T00:00:01Z',
            updated_at: '2026-03-15T00:00:01Z',
            payload: { text },
          },
        ],
      },
    ],
  })
}

function ExecutionConversationHarness({
  conversationId,
  bootstrapStatus = 'idle',
  bootstrapError = null,
  composerEnabled = true,
  composerPlaceholder = 'Message Execution Node...',
  emptyTitle = 'Execution Conversation',
  emptyHint = 'Execution messages will appear here.',
  send = vi.fn(async () => undefined),
  cancelStream = vi.fn(async () => undefined),
}: {
  conversationId: string | null
  bootstrapStatus?: 'idle' | 'loading_snapshot' | 'error'
  bootstrapError?: string | null
  composerEnabled?: boolean
  composerPlaceholder?: string
  emptyTitle?: string
  emptyHint?: string
  send?: (content: string) => Promise<unknown>
  cancelStream?: (streamId: string | null) => Promise<unknown>
}) {
  const conversation = useConversationStore((state) =>
    conversationId ? state.conversationsById[conversationId] ?? null : null,
  )

  return (
    <ChatPanel
      node={makeNode()}
      composerEnabled={composerEnabled}
      composerPlaceholder={composerPlaceholder}
      emptyTitle={emptyTitle}
      emptyHint={emptyHint}
      executionConversation={{
        conversationId,
        conversation,
        bootstrapStatus,
        bootstrapError,
        send,
        cancelStream,
      }}
    />
  )
}

describe('ChatPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    useConversationStore.setState(useConversationStore.getInitialState())
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('renders the execution-v2 branch through the shared surface', () => {
    const snapshot = makeConversationSnapshotWithAssistantText('Execution v2 transcript')
    const conversationId = useConversationStore.getState().ensureConversation(snapshot)
    useConversationStore.getState().hydrateConversation(snapshot)
    useConversationStore.getState().setConnectionStatus(conversationId, 'connected')

    render(<ExecutionConversationHarness conversationId={conversationId} />)

    expect(screen.getByText('Execution v2 transcript')).toBeInTheDocument()
    expect(screen.getByText('connected')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Reset' })).not.toBeInTheDocument()
  })

  it('shows loading while hydration is still pending', () => {
    render(
      <ExecutionConversationHarness
        conversationId={null}
        bootstrapStatus="loading_snapshot"
      />,
    )

    expect(screen.getByText('Loading conversation...')).toBeInTheDocument()
    expect(screen.getByRole('textbox')).toBeDisabled()
  })

  it('shows bootstrap errors without any legacy fallback', () => {
    render(
      <ExecutionConversationHarness
        conversationId={null}
        bootstrapStatus="error"
        bootstrapError="execution v2 bootstrap failed"
      />,
    )

    expect(screen.getByRole('alert')).toHaveTextContent('execution v2 bootstrap failed')
    expect(screen.queryByText('Legacy execution transcript')).not.toBeInTheDocument()
  })

  it('sends through execution v2 and clears the keyed composer draft after success', async () => {
    const snapshot = makeConversationSnapshot()
    const conversationId = useConversationStore.getState().ensureConversation(snapshot)
    useConversationStore.getState().hydrateConversation(snapshot)
    useConversationStore.getState().setConnectionStatus(conversationId, 'connected')
    useConversationStore.getState().setComposerDraft(conversationId, 'Ship the patch')
    const send = vi.fn(async () => ({ status: 'accepted' }))

    render(<ExecutionConversationHarness conversationId={conversationId} send={send} />)

    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'Ship the patch' } })
    fireEvent.click(screen.getByRole('button', { name: 'Send' }))

    await waitFor(() => {
      expect(send).toHaveBeenCalledWith('Ship the patch')
    })
    expect(
      useConversationStore.getState().conversationsById[conversationId]?.composerDraft,
    ).toBe('')
  })
})
