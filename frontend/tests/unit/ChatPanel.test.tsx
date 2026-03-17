import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { NodeRecord } from '../../src/api/types'
import { ChatPanel } from '../../src/features/breadcrumb/ChatPanel'
import type { ConversationSnapshot } from '../../src/features/conversation/types'
import { useChatStore } from '../../src/stores/chat-store'
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
      projectId="project-1"
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
    useChatStore.setState(useChatStore.getInitialState())
    useConversationStore.setState(useConversationStore.getInitialState())
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('keeps the legacy visible branch when execution-v2 host data is absent', () => {
    useChatStore.setState({
      ...useChatStore.getInitialState(),
      session: {
        project_id: 'project-1',
        node_id: 'node-1',
        active_turn_id: null,
        event_seq: 1,
        status: 'active',
        mode: 'execute',
        config: {
          access_mode: 'project_write',
          cwd: 'C:/workspace/alpha',
          writable_roots: ['C:/workspace/alpha'],
          timeout_sec: 120,
        },
        pending_input_request: null,
        messages: [
          {
            message_id: 'legacy_msg_1',
            role: 'assistant',
            content: 'Legacy execution transcript',
            status: 'completed',
            created_at: '2026-03-15T00:00:00Z',
            updated_at: '2026-03-15T00:00:00Z',
            error: null,
          },
        ],
      },
      connectionStatus: 'connected',
      loadSession: vi.fn(async () => {}),
    })

    render(<ChatPanel node={makeNode()} projectId="project-1" />)

    expect(screen.getByText('Legacy execution transcript')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Reset' })).toBeInTheDocument()
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

  it('shows v2 loading and a disabled composer while hydration is still pending', () => {
    useChatStore.setState({
      ...useChatStore.getInitialState(),
      session: {
        project_id: 'project-1',
        node_id: 'node-1',
        active_turn_id: null,
        event_seq: 1,
        status: 'active',
        mode: 'execute',
        config: {
          access_mode: 'project_write',
          cwd: 'C:/workspace/alpha',
          writable_roots: ['C:/workspace/alpha'],
          timeout_sec: 120,
        },
        pending_input_request: null,
        messages: [
          {
            message_id: 'legacy_msg_1',
            role: 'assistant',
            content: 'Legacy execution transcript',
            status: 'completed',
            created_at: '2026-03-15T00:00:00Z',
            updated_at: '2026-03-15T00:00:00Z',
            error: null,
          },
        ],
      },
      connectionStatus: 'connected',
      loadSession: vi.fn(async () => {}),
    })

    render(
      <ExecutionConversationHarness
        conversationId={null}
        bootstrapStatus="loading_snapshot"
      />,
    )

    expect(screen.getByText('Loading conversation...')).toBeInTheDocument()
    expect(screen.getByRole('textbox')).toBeDisabled()
    expect(screen.queryByText('Legacy execution transcript')).not.toBeInTheDocument()
  })

  it('shows v2 bootstrap errors without falling back to the legacy transcript', () => {
    useChatStore.setState({
      ...useChatStore.getInitialState(),
      session: {
        project_id: 'project-1',
        node_id: 'node-1',
        active_turn_id: null,
        event_seq: 1,
        status: 'active',
        mode: 'execute',
        config: {
          access_mode: 'project_write',
          cwd: 'C:/workspace/alpha',
          writable_roots: ['C:/workspace/alpha'],
          timeout_sec: 120,
        },
        pending_input_request: null,
        messages: [
          {
            message_id: 'legacy_msg_1',
            role: 'assistant',
            content: 'Legacy execution transcript',
            status: 'completed',
            created_at: '2026-03-15T00:00:00Z',
            updated_at: '2026-03-15T00:00:00Z',
            error: null,
          },
        ],
      },
      connectionStatus: 'connected',
      loadSession: vi.fn(async () => {}),
    })

    render(
      <ExecutionConversationHarness
        conversationId={null}
        bootstrapStatus="error"
        bootstrapError="v2 bootstrap failed"
      />,
    )

    expect(screen.getByRole('alert')).toHaveTextContent('v2 bootstrap failed')
    expect(screen.queryByText('Loading conversation...')).not.toBeInTheDocument()
    expect(screen.queryByText('Legacy execution transcript')).not.toBeInTheDocument()
  })

  it('sends through v2 and clears the keyed composer draft after success', async () => {
    const snapshot = makeConversationSnapshot()
    const conversationId = useConversationStore.getState().ensureConversation(snapshot)
    useConversationStore.getState().hydrateConversation(snapshot)
    useConversationStore.getState().setConnectionStatus(conversationId, 'connected')
    useConversationStore.getState().setComposerDraft(conversationId, 'Ship phase 3.3')
    const send = vi.fn(async () => ({ status: 'accepted' }))

    render(<ExecutionConversationHarness conversationId={conversationId} send={send} />)

    fireEvent.click(screen.getByRole('button', { name: 'Send' }))

    await waitFor(() => {
      expect(send).toHaveBeenCalledWith('Ship phase 3.3')
    })
    await waitFor(() => {
      expect(useConversationStore.getState().conversationsById[conversationId].composerDraft).toBe('')
    })
  })

  it('shows Stop while keeping the composer disabled after send acceptance leaves execution busy', async () => {
    const snapshot = makeConversationSnapshot()
    const conversationId = useConversationStore.getState().ensureConversation(snapshot)
    useConversationStore.getState().hydrateConversation(snapshot)
    useConversationStore.getState().setConnectionStatus(conversationId, 'connected')
    useConversationStore.getState().setComposerDraft(conversationId, 'Stay disabled')
    const send = vi.fn(async () => {
      useConversationStore.getState().patchRecord(conversationId, {
        active_stream_id: 'stream_live',
        status: 'active',
      })
      useConversationStore.getState().setSending(conversationId, false)
      return { status: 'accepted' }
    })

    render(<ExecutionConversationHarness conversationId={conversationId} send={send} />)

    fireEvent.click(screen.getByRole('button', { name: 'Send' }))

    await waitFor(() => {
      expect(send).toHaveBeenCalledWith('Stay disabled')
    })
    await waitFor(() => {
      expect(screen.getByRole('textbox')).toBeDisabled()
    })
    expect(screen.getByRole('button', { name: 'Stop' })).toBeInTheDocument()
    expect(useConversationStore.getState().conversationsById[conversationId].composerDraft).toBe('')
  })

  it('preserves the keyed composer draft and surfaces the v2 error on send failure', async () => {
    const snapshot = makeConversationSnapshot()
    const conversationId = useConversationStore.getState().ensureConversation(snapshot)
    useConversationStore.getState().hydrateConversation(snapshot)
    useConversationStore.getState().setConnectionStatus(conversationId, 'connected')
    useConversationStore.getState().setComposerDraft(conversationId, 'Keep this draft')
    const send = vi.fn(async () => {
      useConversationStore.getState().setError(conversationId, 'send failed', 'send')
      throw new Error('send failed')
    })

    render(<ExecutionConversationHarness conversationId={conversationId} send={send} />)

    fireEvent.click(screen.getByRole('button', { name: 'Send' }))

    await waitFor(() => {
      expect(send).toHaveBeenCalledWith('Keep this draft')
    })
    await waitFor(() => {
      expect(useConversationStore.getState().conversationsById[conversationId].composerDraft).toBe(
        'Keep this draft',
      )
    })
    expect(screen.getByRole('alert')).toHaveTextContent('send failed')
  })

  it('preserves Enter send and Shift+Enter newline semantics in the execution-v2 branch', async () => {
    const snapshot = makeConversationSnapshot()
    const conversationId = useConversationStore.getState().ensureConversation(snapshot)
    useConversationStore.getState().hydrateConversation(snapshot)
    useConversationStore.getState().setConnectionStatus(conversationId, 'connected')
    useConversationStore.getState().setComposerDraft(conversationId, 'Keyboard send')
    const send = vi.fn(async () => ({ status: 'accepted' }))

    render(<ExecutionConversationHarness conversationId={conversationId} send={send} />)

    const textarea = screen.getByRole('textbox')
    fireEvent.keyDown(textarea, { key: 'Enter', shiftKey: true })
    expect(send).not.toHaveBeenCalled()

    fireEvent.keyDown(textarea, { key: 'Enter' })

    await waitFor(() => {
      expect(send).toHaveBeenCalledWith('Keyboard send')
    })
  })

  it('re-enables the composer after the execution conversation reaches a terminal state', async () => {
    const snapshot = makeConversationSnapshot()
    const conversationId = useConversationStore.getState().ensureConversation(snapshot)
    useConversationStore.getState().hydrateConversation(snapshot)
    useConversationStore.getState().setConnectionStatus(conversationId, 'connected')
    useConversationStore.getState().patchRecord(conversationId, {
      active_stream_id: 'stream_live',
      status: 'active',
    })

    render(<ExecutionConversationHarness conversationId={conversationId} />)

    expect(screen.getByRole('textbox')).toBeDisabled()

    act(() => {
      useConversationStore.getState().patchRecord(conversationId, {
        active_stream_id: null,
        status: 'interrupted',
      })
    })

    await waitFor(() => {
      expect(screen.getByRole('textbox')).not.toBeDisabled()
    })
  })

  it('omits the legacy reset control in the execution-v2 branch', () => {
    const snapshot = makeConversationSnapshot()
    const conversationId = useConversationStore.getState().ensureConversation(snapshot)
    useConversationStore.getState().hydrateConversation(snapshot)
    useConversationStore.getState().setConnectionStatus(conversationId, 'connected')

    render(<ExecutionConversationHarness conversationId={conversationId} />)

    expect(screen.queryByRole('button', { name: 'Reset' })).not.toBeInTheDocument()
  })

  it('quotes assistant text back into the keyed composer draft in the execution-v2 branch', async () => {
    const snapshot = makeConversationSnapshotWithAssistantText('Quote this answer')
    const conversationId = useConversationStore.getState().ensureConversation(snapshot)
    useConversationStore.getState().hydrateConversation(snapshot)
    useConversationStore.getState().setConnectionStatus(conversationId, 'connected')

    render(<ExecutionConversationHarness conversationId={conversationId} />)

    fireEvent.click(await screen.findByRole('button', { name: 'Quote message' }))

    await waitFor(() => {
      expect(useConversationStore.getState().conversationsById[conversationId].composerDraft).toBe(
        '> Quote this answer\n\n',
      )
    })
    expect(screen.getByRole('textbox')).toHaveValue('> Quote this answer\n\n')
  })

  it('shows Stop while streaming and routes cancellation through the execution host', async () => {
    const snapshot = makeConversationSnapshotWithAssistantText('Streaming output')
    const conversationId = useConversationStore.getState().ensureConversation(snapshot)
    useConversationStore.getState().hydrateConversation({
      ...snapshot,
      record: {
        ...snapshot.record,
        active_stream_id: 'stream_live',
        status: 'active',
      },
    })
    useConversationStore.getState().setConnectionStatus(conversationId, 'connected')
    const cancelStream = vi.fn(async () => ({ status: 'accepted' }))

    render(
      <ExecutionConversationHarness
        conversationId={conversationId}
        cancelStream={cancelStream}
      />,
    )

    fireEvent.click(await screen.findByRole('button', { name: 'Stop' }))

    await waitFor(() => {
      expect(cancelStream).toHaveBeenCalledWith('stream_live')
    })
  })
})
